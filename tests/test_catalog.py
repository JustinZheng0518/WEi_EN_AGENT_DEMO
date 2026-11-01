from contextlib import contextmanager
import copy
import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from wain import api
from wain.catalog import load_data,label_parts,import_inventory,collect_labels,sections,summary
from test_database import db

def contents(db):
    for n in [5,6,7]:
        did=db.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
            VALUES(%s,'contents.pdf','/nonexistent',%s,%s,1) RETURNING id''',(str(n).zfill(64),n,n)).fetchone()['id']
        db.execute('INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt) VALUES(%s,1,%s,595,842)',(did,n))

def test_contents_transcription_has_distinct_kinds_and_no_priority_claim():
    data=load_data()
    assert len(data['sections'])==73
    assert len(data['groups'])==13
    rows={r['code']:r for r in data['sections']}
    assert rows['HC_INSERTS']['group']=='rectangular_inserts'
    assert rows['HC_ENCLOSURES']['group']=='enclosures'
    assert rows['PART_NUMBER_INDEX']['kind']=='reference'
    assert rows['HD_HDD']['kind']=='series_group'
    assert rows['HA']['source']==5
    assert label_parts('P29-08.8.1')==('29',(8,8,1))

def test_import_does_not_create_products_or_approvals_and_repeats_safely(db):
    contents(db)
    before=db.execute('SELECT count(*) AS n FROM products').fetchone()['n']
    import_inventory(db);import_inventory(db)
    report=summary(db)
    assert report['contents_entries']==73
    assert report['sales_priority']=='NA'
    assert report['all_products_entered'] is False
    assert report['sample_products_assigned']==before==48
    assert report['sample_products_unassigned']==0
    assert report['entries_with_samples']==3
    assert db.execute("SELECT count(*) AS n FROM products WHERE review_status='reviewed'").fetchone()['n']==0
    ha=next(r for r in sections(db) if r['code']=='HA')
    assert ha['sample_products']==14 and ha['sample_status']=='partial_sample'
    assert next(r for r in sections(db) if r['code']=='HE')['sample_products']==0

def test_missing_source_and_changed_inventory_are_rejected(db,tmp_path):
    with pytest.raises(ValueError,match='pages 5'): import_inventory(db)
    contents(db);import_inventory(db)
    data=load_data();data['sections'][0]['title_en']='changed without migration'
    path=tmp_path/'changed.json';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='migration explicitly'):
        with db.transaction(): import_inventory(db,path)
    assert next(r for r in sections(db) if r['code']=='HA')['title_en']=='HA Series-the slim inserts'

def test_footer_labels_are_candidates_not_an_invented_page_offset(db,tmp_path):
    contents(db);import_inventory(db)
    artifact=tmp_path/'ocr.json'
    artifact.write_text(json.dumps({'height':1000,'words':[
        {'text':'01-01','top':'100'}, # a body reference must not locate this page
        {'text':'01-07','top':'960'}]}))
    db.execute('UPDATE pages SET ocr_artifact=%s WHERE global_page=77',(str(artifact),))
    collect_labels(db);collect_labels(db)
    ha=next(r for r in sections(db) if r['code']=='HA')
    assert ha['start_candidates']==[]
    assert ha['end_candidates']==[77]
    assert ha['location_status']=='partial_anchors'
    assert next(r for r in sections(db) if r['code']=='PART_NUMBER_INDEX')['location_status']=='unlocated'
    assert db.execute('SELECT count(*) AS n FROM catalog_page_labels').fetchone()['n']==4 # three existing labels, one new OCR observation

def test_duplicate_footer_anchors_are_explicitly_ambiguous(db):
    contents(db);import_inventory(db)
    for n in [73,76]:
        db.execute("INSERT INTO catalog_page_labels SELECT id,'01-01','ocr_footer_candidate' FROM pages WHERE global_page=%s",(n,))
    ha=next(r for r in sections(db) if r['code']=='HA')
    assert ha['location_status']=='ambiguous'
    assert ha['start_candidates']==[73,76]

def test_navigation_queries_and_http_filtering(db,monkeypatch):
    contents(db);import_inventory(db)
    @contextmanager
    def same(): yield db
    monkeypatch.setattr(api,'connect',same)
    c=TestClient(api.app)
    assert c.get('/catalog/summary').json()['contents_entries']==73
    rows=c.get('/catalog/sections',params={'group':'rectangular_inserts'}).json()['items']
    assert len(rows)==15
    assert {r['code'] for r in c.get('/catalog/sections',params={'q':'M12'}).json()['items']} >= {'M12_A','M12_B'}
    assert c.get('/catalog/sections',params={'q':"' OR 1=1 --"}).json()['items']==[]
