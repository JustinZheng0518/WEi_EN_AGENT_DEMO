"""Transactional review with explicit provenance, edits and dependency invalidation."""
import json
import re
from decimal import Decimal
from typing import Literal

from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ConfigDict

TABLES={'assessment':'assembly_assessments','product':'products','specification':'product_specifications','relation':'product_relations',
        'evidence':'evidence','candidate':'product_candidates'}
FIELDS={
 'assessment':{'scope','findings'},
 'product':{'model','order_number','category','gender','termination','contact_count','pe_contacts','housing_size'},
 'specification':{'parameter','value_number','value_text','unit','conditions'},
 'relation':{'relation','conditions'},
 'evidence':{'quotation','region'},
 'candidate':{'model_candidate','order_number_candidate'},
}

class ReviewError(ValueError):
    def __init__(self,message,status=400): super().__init__(message); self.status=status

class ReviewAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision:Literal['save','approve','conflict','reject']
    actor:str=Field(min_length=1,max_length=100)
    note:str=Field(min_length=1,max_length=2000)
    expected_version:int=Field(ge=0)
    edits:dict=Field(default_factory=dict)

def table_for(kind):
    if kind not in TABLES: raise ReviewError('Unknown review entity',404)
    return TABLES[kind]

def version(conn,kind,entity_id):
    return conn.execute('SELECT coalesce(max(id),0) AS n FROM review_events WHERE entity_type=%s AND entity_id=%s',
        (kind,entity_id)).fetchone()['n']

def get_record(conn,kind,entity_id):
    table=table_for(kind)
    row=conn.execute(sql.SQL('SELECT * FROM {} WHERE id=%s').format(sql.Identifier(table)),(entity_id,)).fetchone()
    if not row: raise ReviewError('Record not found',404)
    if kind=='candidate': page_id=row['page_id']
    else:
        ev=row if kind=='evidence' else conn.execute('SELECT * FROM evidence WHERE id=%s',(row['evidence_id'],)).fetchone()
        page_id=ev['page_id']
    page=conn.execute('SELECT global_page,printed_page FROM pages WHERE id=%s',(page_id,)).fetchone()
    history=conn.execute('''SELECT id,action,actor,note,created_at,changes FROM review_events
        WHERE entity_type=%s AND entity_id=%s ORDER BY id DESC LIMIT 30''',(kind,entity_id)).fetchall()
    return {'entity':kind,'record':row,'page':page,'editable_fields':sorted(FIELDS[kind]),
            'version':version(conn,kind,entity_id),'history':history}

def event(conn,kind,row,actor,note,action,after):
    conn.execute('''INSERT INTO review_events(entity_type,entity_id,action,actor,note,changes)
        VALUES(%s,%s,%s,%s,%s,%s)''',(kind,row['id'],action,actor,note,
        Jsonb({'before':row,'after':after},dumps=lambda v:json.dumps(v,default=str))))

def invalidate(conn,kind,row,actor,note):
    targets=[]
    if kind=='evidence':
        for child,table in [('product','products'),('specification','product_specifications'),('relation','product_relations')]:
            targets.extend((child,r) for r in conn.execute(sql.SQL("SELECT * FROM {} WHERE evidence_id=%s AND review_status<>'pending' FOR UPDATE").format(sql.Identifier(table)),(row['id'],)).fetchall())
    if kind=='product':
        targets.extend(('specification',r) for r in conn.execute("SELECT * FROM product_specifications WHERE product_id=%s AND review_status<>'pending' FOR UPDATE",(row['id'],)).fetchall())
        targets.extend(('relation',r) for r in conn.execute("SELECT * FROM product_relations WHERE (source_product_id=%s OR target_product_id=%s) AND review_status<>'pending' FOR UPDATE",(row['id'],row['id'])).fetchall())
    for child,old in targets:
        new=conn.execute(sql.SQL("UPDATE {} SET review_status='pending' WHERE id=%s RETURNING *").format(sql.Identifier(TABLES[child])),(old['id'],)).fetchone()
        event(conn,child,old,actor,'Dependency changed: '+note,'invalidate',new)
        if child=='product': invalidate(conn,child,old,actor,note)
    if kind in {'evidence','product','specification','relation'}:
        # A reviewed engineering conclusion must never outlive an edited supporting catalog fact.
        for old in conn.execute("SELECT * FROM assembly_assessments WHERE review_status='reviewed' FOR UPDATE").fetchall():
            new=conn.execute("UPDATE assembly_assessments SET review_status='pending' WHERE id=%s RETURNING *",(old['id'],)).fetchone()
            event(conn,'assessment',old,actor,'Catalog fact changed: '+note,'invalidate',new)

def validate_values(kind,row):
    for key in FIELDS[kind]-{'contact_count','pe_contacts','value_number','conditions','region','scope','findings'}:
        if row[key] is not None and not isinstance(row[key],str): raise ReviewError(f'{key} must be text')
    if kind=='product':
        if not str(row['model'] or '').strip() or not re.fullmatch(r'\d{13}',str(row['order_number'])):
            raise ReviewError('Model and a 13-digit order number are required')
        if row['category'] not in {'insert','contact','tool','hood','housing','cable_entry','accessory','frame','seal','cable'}:
            raise ReviewError('Unsupported product category')
        if row['gender'] not in {'male','female','none',None}: raise ReviewError('Invalid gender')
        for key in ['contact_count','pe_contacts']:
            value=row[key]
            if value is not None and (type(value) is not int or value<(1 if key=='contact_count' else 0)):
                raise ReviewError('Invalid contact count')
    if kind=='specification':
        if not str(row['parameter'] or '').strip(): raise ReviewError('Parameter is required')
        if row['value_number'] is None and not str(row['value_text'] or '').strip(): raise ReviewError('Value is required')
        if row['value_number'] is not None:
            try:
                if not Decimal(str(row['value_number'])).is_finite(): raise ValueError()
            except Exception: raise ReviewError('Numeric value must be finite')
        if not isinstance(row['conditions'],dict): raise ReviewError('Conditions must be a JSON object')
    if kind=='relation' and not isinstance(row['conditions'],dict): raise ReviewError('Conditions must be a JSON object')
    if kind=='evidence':
        if not str(row['quotation'] or '').strip(): raise ReviewError('Evidence quotation is required')
        r=row['region']
        if not isinstance(r,list) or len(r)!=4 or any(type(v) not in (float,int) for v in r) or not (0<=r[0]<r[2]<=1 and 0<=r[1]<r[3]<=1):
            raise ReviewError('Region must be [x0,y0,x1,y1] within 0–1')
    if kind=='candidate' and not re.fullmatch(r'\d{13}',str(row['order_number_candidate'])):
        raise ReviewError('Candidate order number must have 13 digits')
    if kind=='assessment':
        if not isinstance(row['scope'],dict) or not isinstance(row['findings'],dict):
            raise ReviewError('Assessment scope and findings must be JSON objects')

def apply_review(conn,kind,entity_id,action):
    table=table_for(kind)
    if not action.actor.strip() or not action.note.strip(): raise ReviewError('Reviewer and reason are required')
    if set(action.edits)-FIELDS[kind]: raise ReviewError('Unsupported editable field')
    with conn.transaction():
        # Serialize review mutations to keep cascade invalidation and optimistic versions consistent.
        conn.execute('SELECT pg_advisory_xact_lock(9237101)')
        old=conn.execute(sql.SQL('SELECT * FROM {} WHERE id=%s FOR UPDATE').format(sql.Identifier(table)),(entity_id,)).fetchone()
        if not old: raise ReviewError('Record not found',404)
        if version(conn,kind,entity_id)!=action.expected_version: raise ReviewError('Record changed; reload before saving',409)
        proposed={**old,**action.edits}
        validate_values(kind,proposed)
        if kind=='candidate' and action.decision=='conflict': raise ReviewError('Use reject for an incorrect candidate')
        if kind!='candidate' and action.decision=='reject': raise ReviewError('Use conflict for an incorrect fact')
        if action.decision=='approve' and kind not in {'evidence','candidate'}:
            ev=conn.execute('SELECT review_status FROM evidence WHERE id=%s',(old['evidence_id'],)).fetchone()
            if ev['review_status']!='reviewed': raise ReviewError('Review the source evidence first')
            if kind=='relation':
                ready=conn.execute("""SELECT count(*) AS n FROM products p JOIN evidence e ON e.id=p.evidence_id
                    WHERE p.id=ANY(%s) AND p.review_status='reviewed' AND e.review_status='reviewed'""",
                    ([old['source_product_id'],old['target_product_id']],)).fetchone()['n']
                if ready!=2: raise ReviewError('Review both product identities before approving a relation')
        status={'save':'pending','approve':'accepted' if kind=='candidate' else 'reviewed',
                'conflict':'conflict','reject':'rejected'}[action.decision]
        updates={**action.edits,'review_status':status}
        if kind=='evidence':
            updates['reviewed_by']=action.actor.strip() if status=='reviewed' else None
            updates['reviewed_at']=conn.execute('SELECT now() AS t').fetchone()['t'] if status=='reviewed' else None
        changed=any(proposed[k]!=old[k] for k in action.edits)
        if (changed or status!='reviewed') and kind in {'evidence','product','specification','relation'}:
            invalidate(conn,kind,old,action.actor.strip(),action.note)
        columns=list(updates)
        values=[Jsonb(updates[k]) if isinstance(updates[k],(dict,list)) else updates[k] for k in columns]
        new=conn.execute(sql.SQL('UPDATE {} SET {} WHERE id=%s RETURNING *').format(sql.Identifier(table),
            sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in columns)),values+[entity_id]).fetchone()
        event(conn,kind,old,action.actor.strip(),action.note,action.decision,new)
    return get_record(conn,kind,entity_id)
