"""Source-linked HA-010 enclosure pilot. No automatic approvals."""
import json
from psycopg.types.json import Jsonb
from .db import connect

def seed_ha010(conn):
    needed=[57,73,76,445,469,470,1401]
    present=conn.execute('SELECT global_page FROM pages WHERE global_page=ANY(%s)',(needed,)).fetchall()
    if {r['global_page'] for r in present}!=set(needed):
        raise ValueError('Import catalog pages before HA-010 companion data')
    families={}
    for code,name,category in [('H10A','10A metal hoods and housings','enclosure'),('WNA','Metal cable glands','cable_entry')]:
        families[code]=conn.execute('''INSERT INTO product_families(code,name,category) VALUES(%s,%s,%s)
            ON CONFLICT(code) DO UPDATE SET code=excluded.code RETURNING id''',(code,name,category)).fetchone()['id']
    def evidence(key,page,region,quote):
        return conn.execute('''INSERT INTO evidence(evidence_key,page_id,region,quotation,method)
            VALUES(%s,(SELECT id FROM pages WHERE global_page=%s),%s,%s,'visual_transcription')
            ON CONFLICT(evidence_key) DO UPDATE SET evidence_key=excluded.evidence_key RETURNING id''',
            (key,page,Jsonb(region),quote)).fetchone()['id']
    hood_ev=evidence('ha010-metal-hoods',469,[.06,.10,.94,.51],
        '10A Metal hoods/housings; Degree of protection: IP65; M20 H10A-SE-2B-M20 110 010 510 1002; '
        'M20 H10A-TE-2B-M20 110 010 410 1002')
    base_ev=evidence('ha010-bulkhead-housing',470,[.06,.10,.94,.29],
        '10A Metal hoods/housings; Bulkhead mounted housings; H10A-BK-1L/SC 110 010 321 1001; '
        'Please refer to page 15-02 for choosing proper model of lock.')
    gland_ev=evidence('wna-m20-glands',1401,[.06,.10,.94,.89],
        'Metal cable gland; Nickel-plate brass; Sealing Nylon and NBR; IP68(with O-sealing); '
        'M20x1.5 WNA-M20(D4-8) 102 107 018 1503; WNA-M20(D6-12) 102 107 015 1001; '
        'WNA-M20(D8-14) 102 107 015 1002; thread length 8mm')
    lock_ev=evidence('h-series-lock-options',445,[.06,.47,.94,.77],
        'Levers for option; L/SC Stainless steel+TPR; high-strength locking, device with rubber cover; '
        'L/PSE PC+Stainless steel; removable locking device')
    assembly_ev=evidence('rectangular-component-roles',57,[.05,.05,.95,.95],
        'Parts of the heavy duty connector: Cable gland; Hoods; Male insert or Female insert; '
        'Crimp contacts (only for crimp connection insert); Housings')
    technical=conn.execute("SELECT id FROM evidence WHERE evidence_key='ha-technical-01-02'").fetchone()
    if not technical: raise ValueError('Run the base pilot seed before importing HA-010 companion data')
    conn.execute("UPDATE pages SET printed_page='15-02' WHERE global_page=445")
    for page,printed in [(57,'00-02'),(469,'15-17'),(470,'15-18'),(1401,'32-07')]:
        conn.execute('UPDATE pages SET printed_page=%s WHERE global_page=%s',(printed,page))
    def spec(pid,parameter,eid,number=None,text=None,unit=None,conditions=None):
        conn.execute('''INSERT INTO product_specifications(product_id,parameter,value_number,value_text,unit,conditions,evidence_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (pid,parameter,number,text,unit,Jsonb(conditions or {}),eid))
    ids={}
    for insert in conn.execute("SELECT id,termination FROM products WHERE model LIKE 'HA-010-%%'").fetchall():
        lo,hi={'screw':(.75,2.5),'spring':(.14,2.5),'crimp':(.14,4)}[insert['termination']]
        spec(insert['id'],'wire_cross_section_min',technical['id'],number=lo,unit='mm2')
        spec(insert['id'],'wire_cross_section_max',technical['id'],number=hi,unit='mm2')
    rows=[('H10A-SE-2B-M20','1100105101002','hood','H10A',hood_ev),
          ('H10A-TE-2B-M20','1100104101002','hood','H10A',hood_ev),
          ('H10A-BK-1L/SC','1100103211001','housing','H10A',base_ev),
          ('WNA-M20(D4-8)','1021070181503','cable_entry','WNA',gland_ev),
          ('WNA-M20(D6-12)','1021070151001','cable_entry','WNA',gland_ev),
          ('WNA-M20(D8-14)','1021070151002','cable_entry','WNA',gland_ev)]
    for model,order,category,family,ev in rows:
        pid=conn.execute('''INSERT INTO products(family_id,model,order_number,category,gender,housing_size,evidence_id)
            VALUES(%s,%s,%s,%s,'none',%s,%s) ON CONFLICT(order_number)
            DO UPDATE SET order_number=excluded.order_number RETURNING id''',
            (families[family],model,order,category,'10A' if family=='H10A' else None,ev)).fetchone()['id']
        ids[model]=pid
        spec(pid,'standard_pack_quantity',ev,number=1,unit='pcs')
        if category=='hood':
            spec(pid,'entry_thread_designation',ev,text='M20')
            spec(pid,'locking_geometry',ev,text='2B')
            spec(pid,'entry_direction',ev,text='side' if '-SE-' in model else 'top')
        elif category=='housing':
            spec(pid,'locking_variant',lock_ev,text='1L/SC',conditions={'order_confirmation_required':True})
            spec(pid,'mounting',ev,text='bulkhead')
        else:
            a,b={'WNA-M20(D4-8)':(4,8),'WNA-M20(D6-12)':(6,12),'WNA-M20(D8-14)':(8,14)}[model]
            spec(pid,'entry_thread_designation',ev,text='M20x1.5')
            spec(pid,'cable_diameter_min',ev,number=a,unit='mm')
            spec(pid,'cable_diameter_max',ev,number=b,unit='mm')
            spec(pid,'thread_length',ev,number=8,unit='mm')
            spec(pid,'sealing',ev,text='Nylon and NBR; O-sealing required for stated IP rating')
        spec(pid,'ip_rating',ev,text='IP68' if category=='cable_entry' else 'IP65',
            conditions={'requires_assembled_sealing_verification':True})
    template=conn.execute('''INSERT INTO assembly_templates(code,description)
        VALUES('ha010-cable-panel','HA-010, one cable entry, bulkhead panel, 10 ordinary contacts plus PE; pending engineering review')
        ON CONFLICT(code) DO UPDATE SET code=excluded.code RETURNING id''').fetchone()['id']
    for role,condition,quantity in [('male_insert',{},'quantity'),('female_insert',{},'quantity'),('hood',{},'quantity'),
            ('panel_housing',{},'quantity'),('cable_entry',{},'quantity'),
            ('male_contacts',{'termination':'crimp'},'contacts * quantity; PE terminal must be verified separately'),
            ('female_contacts',{'termination':'crimp'},'contacts * quantity; PE terminal must be verified separately')]:
        conn.execute('''INSERT INTO assembly_requirements(template_id,role,required,condition,quantity_rule)
            VALUES(%s,%s,true,%s,%s) ON CONFLICT DO NOTHING''',(template,role,Jsonb(condition),quantity))
    for code,description,rule,eid in [
        ('ha010-component-roles','Cable-panel assembly requires both inserts, hood, housing and cable entry',{'template':'ha010-cable-panel','no_automatic_approval':True},assembly_ev),
        ('ha010-lock-selection','Choose actual L/SC or L/PSE variant; do not synthesize an unlisted order number',{'requires_order_variant_confirmation':True},lock_ev),
        ('ha010-thread-sealing','Check thread pitch, engagement length and seal assembly; nominal M20 alone is insufficient',{'requires_thread_pitch_confirmation':True,'requires_sealing_confirmation':True},gland_ev)]:
        conn.execute('''INSERT INTO compatibility_rules(code,description,rule,evidence_id) VALUES(%s,%s,%s,%s)
            ON CONFLICT DO NOTHING''',(code,description,Jsonb(rule),eid))
    # No mates_with relation is inferred from size, gender or co-occurrence on a catalog page.
    return {'new_pilot_companions':len(rows),'models':list(ids),'review_status':'pending',
            'source_pages':[57,76,445,469,470,1401]}

if __name__=='__main__':
    with connect() as conn: print(json.dumps(seed_ha010(conn),ensure_ascii=False))
