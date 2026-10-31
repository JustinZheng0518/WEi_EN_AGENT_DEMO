import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from wain import api
from wain.db import connect,initialize
from wain.ingest import inventory
from wain.seed import seed
from wain.service import product_details,search_products,stats


@pytest.fixture
def db():
    # Tests use a new schema in a rolled-back transaction, never production tables.
    with connect() as conn:
        namespace='test_'+uuid.uuid4().hex
        conn.execute(psycopg.sql.SQL('CREATE SCHEMA {}').format(psycopg.sql.Identifier(namespace)))
        conn.execute(psycopg.sql.SQL('SET LOCAL search_path TO {}').format(psycopg.sql.Identifier(namespace)))
        initialize(conn)
        for number in [73,76,77]:
            doc=conn.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
                VALUES(%s,'fixture.pdf','/nonexistent',%s,%s,1) RETURNING id''',(str(number).zfill(64),number,number)).fetchone()['id']
            conn.execute('''INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt)
                VALUES(%s,1,%s,595,842)''',(doc,number))
        seed(conn)
        try: yield conn
        finally: conn.rollback()


def test_pilot_import_is_idempotent_and_preserves_review(db):
    before=stats(db)
    db.execute("UPDATE products SET review_status='reviewed' WHERE model='HA-010-MC'")
    seed(db)
    after=stats(db)
    for field in ['products','product_specifications','evidence','product_relations']:
        assert before[field]==after[field]
    assert after['products']==48
    assert after['product_review']['reviewed']==1


def test_pending_products_are_excluded_by_default(db):
    assert search_products(db)['items']==[]
    rows=search_products(db,q='HA-010-MC',include_pending=True)['items']
    assert len(rows)==1
    assert rows[0]['order_number']=='1210100100001'


def test_rating_filter_is_not_compatibility_approval(db):
    assert search_products(db,min_current=17,include_pending=True)['items']==[]
    found=search_products(db,contact_count=10,min_voltage=24,min_current=3,termination='crimp',include_pending=True)
    assert len(found['items'])==2
    assert found['candidate_only'] is True
    for row in found['items']:
        detail=product_details(db,row['id'])
        assert detail['can_finalize'] is False
        assert detail['evidence']['global_page']==76
        current=next(s for s in detail['specifications'] if s['parameter']=='rated_current')
        assert current['conditions']['requires_derating_check'] is True
        assert current['global_page']==73


def test_reviewed_product_does_not_make_pending_specs_reviewed(db):
    db.execute("UPDATE products SET review_status='reviewed' WHERE model='HA-010-MC'")
    assert search_products(db,q='HA-010-MC')['items']==[]
    db.execute("""UPDATE evidence SET review_status='reviewed',reviewed_by='test-reviewer',reviewed_at=now()
        WHERE id=(SELECT evidence_id FROM products WHERE model='HA-010-MC')""")
    assert len(search_products(db,q='HA-010-MC')['items'])==1
    assert search_products(db,q='HA-010-MC',min_current=3)['items']==[]


def test_query_is_parameterized(db):
    assert search_products(db,q="' OR true --",include_pending=True)['items']==[]
    assert stats(db)['products']==48


def test_contact_range_and_pending_relations(db):
    row=search_products(db,q='CESM-0.37',include_pending=True)['items'][0]
    detail=product_details(db,row['id'])
    values={s['parameter']:s['value_number'] for s in detail['specifications']}
    assert float(values['wire_cross_section_min'])==.14
    assert float(values['wire_cross_section_max'])==.37
    insert=search_products(db,q='HA-010-MC',include_pending=True)['items'][0]
    relations=product_details(db,insert['id'])['relations']
    assert len(relations)==16
    assert all(r['review_status']=='pending' for r in relations)
    assert not any(r['relation']=='mates_with' for r in relations)


def test_foreign_keys_and_no_self_compatibility(db):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with db.transaction():
            db.execute("INSERT INTO product_aliases VALUES(999999,'fake','en')")
    p=db.execute('SELECT id,evidence_id FROM products LIMIT 1').fetchone()
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute('''INSERT INTO product_relations(source_product_id,target_product_id,relation,evidence_id)
                VALUES(%s,%s,'mates_with',%s)''',(p['id'],p['id'],p['evidence_id']))


def test_incomplete_inventory_is_rejected(db,tmp_path):
    with pytest.raises(ValueError,match='complete catalog coverage'):
        inventory(db,tmp_path)


def test_http_contract_and_unknown_records(db,monkeypatch):
    @contextmanager
    def same_connection(): yield db
    monkeypatch.setattr(api,'connect',same_connection)
    client=TestClient(api.app)
    assert client.get('/health').json()=={'database':'ok'}
    assert client.get('/products').json()['items']==[]
    response=client.get('/products',params={'q':'HA-010-MC','include_pending':'true'})
    assert response.status_code==200
    pid=response.json()['items'][0]['id']
    assert client.get(f'/products/{pid}').json()['evidence']['printed_page']=='01-04'
    assert client.get('/products/999999').status_code==404
    assert client.get('/pages/999999').status_code==404
    assert client.get('/evidence/999999').status_code==404
    for params in [{'min_current':-1},{'min_current':'nan'},{'limit':101},{'contact_count':0}]:
        assert client.get('/products',params=params).status_code==422


def test_full_text_search_returns_unreviewed_evidence(db,monkeypatch):
    db.execute("UPDATE pages SET ocr_text='HA slim inserts rated current 16A',ocr_status='done' WHERE global_page=76")
    @contextmanager
    def same_connection(): yield db
    monkeypatch.setattr(api,'connect',same_connection)
    result=TestClient(api.app).get('/pages/search',params={'q':'slim inserts'}).json()
    assert result['review_status']=='unreviewed_ocr'
    assert [row['global_page'] for row in result['items']]==[76]
