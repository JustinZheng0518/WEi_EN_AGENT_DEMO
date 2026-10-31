from enum import Enum
import pymupdf as fitz
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from .db import connect
from .service import stats, search_products, product_details

app=FastAPI(title='WAIN Catalog Database',version='0.1.0',
    description='Read-only evidence database. Pending records and OCR text must not be treated as validated selections.')

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
