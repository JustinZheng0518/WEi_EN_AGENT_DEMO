from enum import Enum
import pymupdf as fitz
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from psycopg import IntegrityError, sql
from .db import ROOT
from .review import ReviewAction, ReviewError, TABLES, get_record, apply_review
from .selection import SelectionRequest,select
from .catalog import sections as catalog_sections,summary as catalog_summary
from .ha_series import coverage as ha_coverage
from pydantic import BaseModel,ConfigDict,Field,PositiveInt
from typing import Literal
from psycopg.types.json import Jsonb
from .db import connect
from .service import stats, search_products, product_details

app=FastAPI(title='WAIN Catalog Database',version='0.1.0',
    description='Evidence database with local review tools. Pending facts are not validated selections.')
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]','testserver'])
app.mount('/static',StaticFiles(directory=ROOT/'wain/static'),name='static')

@app.get('/catalog/summary')
def catalog_overview():
    with connect() as conn: return catalog_summary(conn)

@app.get('/series/ha/coverage')
def ha_transcription_coverage():
    with connect() as conn: return ha_coverage(conn)

@app.get('/catalog/sections')
def catalog_entries(group:str|None=None,q:str=Query('',max_length=100)):
    with connect() as conn:
        return {'items':catalog_sections(conn,group,q),'scope':'opening_contents_navigation',
                'notice':'Entries include series, component groups and references; sample counts do not imply complete SKU coverage or business priority.'}

def require_local_review(request):
    origin=request.headers.get('origin')
    if request.headers.get('x-wain-review')!='1' or (origin and origin.rstrip('/')!=str(request.base_url).rstrip('/')):
        raise HTTPException(403,'Same-origin review header is required')

class NewRelation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_product_id:PositiveInt
    target_product_id:PositiveInt
    relation:Literal['mates_with','uses_contact','uses_housing','requires_accessory','optional_accessory','alternative']
    evidence_id:PositiveInt
    conditions:dict=Field(default_factory=dict)
    actor:str=Field(min_length=1,max_length=100)
    note:str=Field(min_length=1,max_length=2000)

class NewAssessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    check_code:Literal['derating','mechanical_sealing','pe_termination','pinout_mounting']
    scope:dict
    findings:dict
    evidence_id:PositiveInt
    actor:str=Field(min_length=1,max_length=100)
    note:str=Field(min_length=1,max_length=2000)

@app.post('/selection/ha010')
def select_ha010(request:SelectionRequest):
    with connect() as conn: return select(conn,request)

@app.post('/review/relations')
def new_relation(body:NewRelation,request:Request):
    require_local_review(request)
    if not body.actor.strip() or not body.note.strip(): raise HTTPException(422,'Reviewer and reason are required')
    try:
        with connect() as conn:
            row=conn.execute('''INSERT INTO product_relations(source_product_id,target_product_id,relation,conditions,evidence_id)
                VALUES(%s,%s,%s,%s,%s) RETURNING *''',(body.source_product_id,body.target_product_id,body.relation,Jsonb(body.conditions),body.evidence_id)).fetchone()
            conn.execute("INSERT INTO review_events(entity_type,entity_id,action,actor,note,changes) VALUES('relation',%s,'create',%s,%s,%s)",
                (row['id'],body.actor,body.note,Jsonb({'after':dict(row)},dumps=lambda v:__import__('json').dumps(v,default=str))))
            return get_record(conn,'relation',row['id'])
    except IntegrityError: raise HTTPException(422,'Invalid or duplicate relation; no changes saved')

@app.post('/review/assessments')
def new_assessment(body:NewAssessment,request:Request):
    require_local_review(request)
    if not body.actor.strip() or not body.note.strip(): raise HTTPException(422,'Reviewer and reason are required')
    if set(body.scope)!={'request','products'}: raise HTTPException(422,'Use exact scope from a selection report')
    try:
        with connect() as conn:
            row=conn.execute('''INSERT INTO assembly_assessments(check_code,scope,findings,evidence_id)
                VALUES(%s,%s,%s,%s) RETURNING *''',(body.check_code,Jsonb(body.scope),Jsonb(body.findings),body.evidence_id)).fetchone()
            conn.execute("INSERT INTO review_events(entity_type,entity_id,action,actor,note,changes) VALUES('assessment',%s,'create',%s,%s,%s)",
                (row['id'],body.actor,body.note,Jsonb({'after':dict(row)},dumps=lambda v:__import__('json').dumps(v,default=str))))
            return get_record(conn,'assessment',row['id'])
    except IntegrityError: raise HTTPException(422,'Invalid assessment evidence; no changes saved')

@app.get('/',include_in_schema=False)
def review_page():
    return FileResponse(ROOT/'wain/static/index.html',headers={
        'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
        'X-Content-Type-Options':'nosniff'})

@app.get('/review/queue')
def review_queue(kind:str='product',status:str|None='pending',q:str=Query('',max_length=100),
                 limit:int=Query(40,ge=1,le=100),offset:int=Query(0,ge=0)):
    if kind not in TABLES: raise HTTPException(404,'Unknown review entity')
    if status is not None and status not in {'pending','reviewed','conflict','accepted','rejected','all'}:
        raise HTTPException(422,'Unknown review status')
    join=sql.SQL('JOIN pages p ON p.id=r.page_id') if kind in {'evidence','candidate'} else sql.SQL('JOIN evidence e ON e.id=r.evidence_id JOIN pages p ON p.id=e.page_id')
    with connect() as conn:
        rows=conn.execute(sql.SQL('''SELECT r.*,p.global_page,p.printed_page FROM {} r {} WHERE
            (%s::text IS NULL OR r.review_status=%s) AND (%s='' OR strpos(lower(to_jsonb(r)::text),lower(%s))>0)
            ORDER BY p.global_page,r.id LIMIT %s OFFSET %s''').format(sql.Identifier(TABLES[kind]),join),
            (None if status=='all' else status,status,q,q,limit,offset)).fetchall()
    return {'items':rows,'entity':kind}

@app.get('/review/{kind}/{entity_id}')
def review_record(kind:str,entity_id:int):
    try:
        with connect() as conn: return get_record(conn,kind,entity_id)
    except ReviewError as exc: raise HTTPException(exc.status,str(exc))

@app.post('/review/{kind}/{entity_id}')
def save_review(kind:str,entity_id:int,action:ReviewAction,request:Request):
    # Local tool, not an authenticated multi-user deployment. Block cross-origin browser mutations.
    require_local_review(request)
    try:
        with connect() as conn: return apply_review(conn,kind,entity_id,action)
    except ReviewError as exc: raise HTTPException(exc.status,str(exc))
    except IntegrityError: raise HTTPException(422,'Edit violates a data constraint; no changes saved')

class Gender(str,Enum):
    male='male'
    female='female'
    none='none'

@app.get('/health')
def health():
    with connect() as conn:
        conn.execute('SELECT 1')
    return {'database':'ok'}

@app.get('/stats')
def statistics():
    with connect() as conn: return stats(conn)

@app.get('/products')
def products(q:str=Query('',max_length=100),contact_count:int|None=Query(None,gt=0),
    category:str|None=None,gender:Gender|None=None,termination:str|None=None,
    min_voltage:float|None=Query(None,gt=0,allow_inf_nan=False),
    min_current:float|None=Query(None,gt=0,allow_inf_nan=False),
    include_pending:bool=False,limit:int=Query(30,ge=1,le=100)):
    with connect() as conn:
        return search_products(conn,q,contact_count,category,gender.value if gender else None,
            termination,min_voltage,min_current,include_pending,limit)

@app.get('/products/{product_id}')
def product(product_id:int):
    with connect() as conn: row=product_details(conn,product_id)
    if not row: raise HTTPException(404,'Product not found')
    return row

@app.get('/candidates')
def candidates(q:str=Query('',max_length=100),global_page:int|None=Query(None,ge=1,le=1424),
               limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
    with connect() as conn:
        rows=conn.execute('''SELECT c.*,p.global_page,p.printed_page FROM product_candidates c
            JOIN pages p ON p.id=c.page_id WHERE (%s='' OR strpos(lower(coalesce(c.model_candidate,'')),lower(%s))>0
            OR strpos(c.order_number_candidate,replace(%s,' ',''))>0)
            AND (%s::integer IS NULL OR p.global_page=%s)
            ORDER BY p.global_page,c.id LIMIT %s OFFSET %s''',(q,q,q,global_page,global_page,limit,offset)).fetchall()
    return {'items':rows,'candidate_only':True,'can_finalize':False}

@app.get('/pages/search')
def pages_search(q:str=Query(min_length=1,max_length=200),limit:int=Query(20,ge=1,le=100)):
    with connect() as conn:
        rows=conn.execute('''SELECT p.global_page,p.printed_page,d.filename,p.ocr_status,
            ts_headline('english',coalesce(p.ocr_text,p.native_text),websearch_to_tsquery('english',%s),
                'StartSel=[,StopSel=],MaxWords=50,MinWords=15') AS excerpt
            FROM pages p JOIN documents d ON d.id=p.document_id
            WHERE to_tsvector('english',coalesce(p.ocr_text,p.native_text)) @@ websearch_to_tsquery('english',%s)
            ORDER BY p.global_page LIMIT %s''',(q,q,limit)).fetchall()
    return {'items':rows,'review_status':'unreviewed_ocr','notice':'Check original page images before using OCR values.'}

@app.get('/pages/{global_page}')
def page(global_page:int):
    with connect() as conn:
        row=conn.execute('''SELECT p.global_page,p.local_page,p.printed_page,p.ocr_status,p.ocr_engine,
            p.ocr_text,d.filename,d.sha256 FROM pages p JOIN documents d ON d.id=p.document_id
            WHERE global_page=%s''',(global_page,)).fetchone()
    if row is None: raise HTTPException(404,'Page not found')
    return row

@app.get('/pages/{global_page}/image')
def page_image(global_page:int,dpi:int=Query(120,ge=72,le=200)):
    with connect() as conn:
        row=conn.execute('''SELECT p.local_page,d.source_path FROM pages p
            JOIN documents d ON d.id=p.document_id WHERE global_page=%s''',(global_page,)).fetchone()
    if row is None: raise HTTPException(404,'Page not found')
    with fitz.open(row['source_path']) as pdf:
        data=pdf[row['local_page']-1].get_pixmap(dpi=dpi).tobytes('png')
    return Response(data,media_type='image/png')

@app.get('/evidence/{evidence_id}')
def evidence(evidence_id:int):
    with connect() as conn:
        row=conn.execute('''SELECT e.*,p.global_page,p.printed_page,d.filename FROM evidence e
            JOIN pages p ON p.id=e.page_id JOIN documents d ON d.id=p.document_id WHERE e.id=%s''',
            (evidence_id,)).fetchone()
    if row is None: raise HTTPException(404,'Evidence not found')
    return row
