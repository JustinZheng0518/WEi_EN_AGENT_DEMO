"""Resumable local ingestion. Catalog contents are data, never instructions."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pymupdf as fitz
from psycopg.types.json import Jsonb
from .db import ROOT, connect, initialize


def inventory(conn, folder):
    candidates = []
    for path in Path(folder).rglob('*.pdf'):
        match = re.search(r'Catalog_(\d+)-(\d+)(?:_(\d+)-(\d+))?\.pdf$', path.name)
        if not match:
            continue
        a, b, c, d = match.groups()
        start, end = (int(c), int(d)) if c else (int(a), int(b))
        with fitz.open(path) as pdf:
            if len(pdf) != end-start+1:
                raise ValueError(f'Page count mismatch: {path.name}')
            candidates.append((path, start, end, [(p.rect.width, p.rect.height, p.get_text()) for p in pdf]))
    covered = [n for _, a, b, _ in candidates for n in range(a,b+1)]
    if len(covered) != len(set(covered)):
        raise ValueError('Overlapping PDF ranges; choose a directory with one copy of each part')
    if sorted(covered) != list(range(1,1425)):
        raise ValueError('Expected complete catalog coverage: pages 1–1424')
    for path, start, end, pages in sorted(candidates, key=lambda item:item[1]):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        row = conn.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(sha256)
            DO UPDATE SET source_path=excluded.source_path RETURNING id''',
            (digest,path.name,str(path.resolve()),start,end,len(pages))).fetchone()
        for local, (width, height, text) in enumerate(pages,1):
            existing = conn.execute('SELECT document_id FROM pages WHERE global_page=%s',(start+local-1,)).fetchone()
            if existing and existing['document_id'] != row['id']:
                raise ValueError('Different document content for an existing page; explicit version migration required')
            conn.execute('''INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt,native_text)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(document_id,local_page) DO NOTHING''',
                (row['id'],local,start+local-1,width,height,text))
    return {'documents':len(candidates),'pages':len(covered)}


def recognize(page, dpi):
    with fitz.open(page['source_path']) as pdf:
        image = pdf[page['local_page']-1].get_pixmap(dpi=dpi)
        data = image.tobytes('png')
        width,height = image.width,image.height
    for mode in ['3','11']:
        result = subprocess.run(['tesseract','stdin','stdout','-l','eng','--psm',mode,'tsv'],
            input=data,capture_output=True,timeout=120,
            env={**os.environ,'OMP_THREAD_LIMIT':'1'},check=True)
        words=[]
        lines={}
        for row in csv.DictReader(io.StringIO(result.stdout.decode()),delimiter='\t',quoting=csv.QUOTE_NONE):
            if row['level']!='5' or not row.get('text','').strip():
                continue
            word={k:row[k] for k in ('text','conf','left','top','width','height','block_num','par_num','line_num')}
            words.append(word)
            key=tuple(row[k] for k in ('block_num','par_num','line_num'))
            lines.setdefault(key,[]).append(row['text'])
        if words: break
    text='\n'.join(' '.join(values) for values in lines.values())
    artifact=ROOT/'.local/ocr'/f"{page['global_page']:04d}.json"
    artifact.parent.mkdir(parents=True,exist_ok=True)
    engine=f'tesseract-eng-psm{mode}-{dpi}dpi'
    payload={'page':page['global_page'],'engine':engine,
             'dpi':dpi,'width':width,'height':height,'text':text,'words':words}
    temporary=artifact.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False))
    temporary.replace(artifact)
    return text,str(artifact),engine


def ocr(conn, start=1, end=1424, workers=4, dpi=180):
    rows=conn.execute('''SELECT p.*,d.source_path FROM pages p JOIN documents d ON d.id=p.document_id
        WHERE global_page BETWEEN %s AND %s AND ocr_status<>'done' ORDER BY global_page''',(start,end)).fetchall()
    run=conn.execute("INSERT INTO ingestion_runs(stage,status,details) VALUES('ocr','running',%s) RETURNING id",
        (Jsonb({'start':start,'end':end,'dpi':dpi,'workers':workers,'selected':len(rows)}),)).fetchone()['id']
    conn.commit()
    done=failed=0
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(recognize,row,dpi):row for row in rows}
            for future in as_completed(futures):
                page=futures[future]
                try:
                    text,artifact,engine=future.result()
                    if not text.strip():
                        raise ValueError('OCR produced no text; page requires inspection')
                except Exception as exc:
                    failed+=1
                    conn.execute("UPDATE pages SET ocr_status='failed',ocr_error=%s WHERE id=%s",(str(exc)[:1000],page['id']))
                    print(f"FAILED page {page['global_page']}: {exc}",flush=True)
                else:
                    done+=1
                    conn.execute("""UPDATE pages SET ocr_status='done',ocr_text=%s,ocr_artifact=%s,
                        ocr_engine=%s,ocr_error=NULL WHERE id=%s""",(text,artifact,engine,page['id']))
                conn.commit()
                if (done+failed)%25==0 or done+failed==len(rows):
                    print(json.dumps({'completed':done,'failed':failed,'selected':len(rows)}),flush=True)
        conn.execute('UPDATE ingestion_runs SET status=%s,finished_at=now(),details=details || %s WHERE id=%s',
            ('failed' if failed else 'done',Jsonb({'completed':done,'failed':failed}),run))
        conn.commit()
    except BaseException:
        conn.rollback()
        conn.execute("UPDATE ingestion_runs SET status='failed',finished_at=now() WHERE id=%s",(run,))
        conn.commit()
        raise
    return {'completed':done,'failed':failed,'selected':len(rows)}


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    inv=sub.add_parser('inventory'); inv.add_argument('folder')
    rec=sub.add_parser('ocr')
    for flag,default in [('start',1),('end',1424),('workers',4),('dpi',180)]:
        rec.add_argument('--'+flag,type=int,default=default)
    sub.add_parser('seed')
    sub.add_parser('stats')
    args=parser.parse_args()
    with connect() as conn:
        if args.command=='init': initialize(conn); result={'initialized':True}
        elif args.command=='inventory': result=inventory(conn,args.folder)
        elif args.command=='ocr':
            if not 1<=args.start<=args.end<=1424 or not 1<=args.workers<=8 or not 100<=args.dpi<=400:
                parser.error('Invalid range, workers (1–8), or dpi (100–400)')
            result=ocr(conn,args.start,args.end,args.workers,args.dpi)
        elif args.command=='seed':
            from .seed import seed
            result=seed(conn)
        else:
            from .service import stats
            result=stats(conn)
        print(json.dumps(result,ensure_ascii=False,default=str))
        if args.command=='ocr' and result['failed']:
            raise SystemExit(1)

if __name__=='__main__': main()
