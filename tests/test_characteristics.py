from contextlib import contextmanager
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from test_database import db
from wain import api
from wain.characteristics import CharacteristicError, compare, describe
from wain.db import ROOT, connect
from wain.migrations import migrate
from wain.review import ReviewAction, apply_review, get_record
from wain.seed import seed


def sku(db, model):
    return db.execute('SELECT * FROM products WHERE model=%s',(model,)).fetchone()


def field(db, model, code):
    return next(f for f in describe(db,sku(db,model)['id'],True)['fields'] if f['code']==code)


@pytest.mark.parametrize('code,number,text,unit',[
    ('rated_current',16,None,'V'),  # correct number, wrong physical unit
    ('rated_current',None,'16A','A'),
    ('standard_pack_quantity',1.5,None,'pcs'),
    ('rated_current',float('nan'),None,'A'),
    ('rated_current',float('inf'),None,'A'),
    ('wire_cross_section_min',0,None,'mm2'),
    ('not_registered_field',1,None,None),
    ('contact_count',10,None,None),  # identity fields cannot be duplicated as specifications
])
def test_database_rejects_malformed_typed_features(db,code,number,text,unit):
    p=sku(db,'HA-010-M')
    with pytest.raises(psycopg.IntegrityError):
        with db.transaction():
            db.execute('''INSERT INTO product_specifications(product_id,parameter,value_number,value_text,unit,conditions,evidence_id)
                VALUES(%s,%s,%s,%s,%s,'{"test":true}',%s)''',(p['id'],code,number,text,unit,p['evidence_id']))


def test_category_and_range_constraints_apply_to_imports_and_edits(db):
    contact=sku(db,'CESM-1.0')
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute('''INSERT INTO product_specifications(product_id,parameter,value_text,evidence_id)
                VALUES(%s,'mounting','bulkhead',%s)''',(contact['id'],contact['evidence_id']))
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute("UPDATE product_specifications SET value_number=2 WHERE product_id=%s AND parameter='wire_cross_section_min'",(contact['id'],))
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute("UPDATE products SET category='tool' WHERE id=%s",(contact['id'],))
    crimp=sku(db,'HA-010-MC')
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute('''INSERT INTO product_specifications(product_id,parameter,value_number,unit,evidence_id)
                VALUES(%s,'tightening_test_torque',0.5,'Nm',%s)''',(crimp['id'],crimp['evidence_id']))


def test_unknown_and_not_applicable_are_not_zero_and_need_reasons(db):
    p=sku(db,'HA-010-M')
    for state,reason in [('NA','Specific stripping instruction not verified'),('not_applicable','No screw operation for this test-only field context')]:
        with db.transaction(force_rollback=True):
            db.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,state_reason,evidence_id)
                VALUES(%s,'stripping_length','mm',%s,%s,%s)''',(p['id'],state,reason,p['evidence_id']))
            f=field(db,'HA-010-M','stripping_length')
            assert f['state']==state and f['observations'][0]['value'] is None
            assert f['observations'][0]['state_reason']==reason
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,evidence_id)
                VALUES(%s,'stripping_length','mm','NA',%s)''',(p['id'],p['evidence_id']))
    assert field(db,'HA-010-M','stripping_length')['state']=='NA'
    assert field(db,'HA-010-M','stripping_length')['availability_reason']=='not_recorded'


def test_explicit_unknown_edit_is_audited_and_does_not_qualify_as_shared_fact(db):
    p=sku(db,'HA-010-M')
    s=db.execute("SELECT * FROM product_specifications WHERE product_id=%s AND parameter='rated_current'",(p['id'],)).fetchone()
    result=apply_review(db,'specification',s['id'],ReviewAction(decision='save',actor='test',note='Exact rating requires clarification',expected_version=0,
        edits={'value_state':'NA','value_number':None,'state_reason':'Exact rating requires clarification'}))
    assert result['history'][0]['changes']['after']['value_state']=='NA'
    report=compare(db,[p['id'],sku(db,'HA-010-F')['id']],True)
    assert 'rated_current' not in {f['code'] for f in report['common_in_this_comparison']}
    assert 'rated_current' in {f['code'] for f in report['different_or_na']}


def test_shared_feature_preserves_each_skus_evidence_and_is_not_mating(db):
    ids=[sku(db,m)['id'] for m in ['HA-010-M','HA-010-F']]
    report=compare(db,ids,True)
    current=next(f for f in report['common_in_this_comparison'] if f['code']=='rated_current')
    assert not current['all_reviewed']
    assert [p['product_id'] for p in current['by_product']]==ids
    assert all(p['field']['observations'][0]['evidence_id'] for p in current['by_product'])
    assert 'gender' in {f['code'] for f in report['different_or_na']}
    assert not report['compatibility_inferred'] and not report['can_finalize']


def test_same_number_under_different_conditions_is_not_common(db):
    ids=[sku(db,m)['id'] for m in ['HA-010-M','HA-010-F']]
    db.execute("UPDATE product_specifications SET conditions=conditions || '{\"standard\":\"different-test-standard\"}' WHERE product_id=%s AND parameter='rated_current'",(ids[1],))
    report=compare(db,ids,True)
    assert 'rated_current' not in {f['code'] for f in report['common_in_this_comparison']}


def test_cross_category_applicability_is_not_an_invented_zero(db):
    ids=[sku(db,m)['id'] for m in ['HA-010-MC','CESM-1.0']]
    report=compare(db,ids,True)
    voltage=next(f for f in report['different_or_na'] if f['code']=='rated_voltage')
    assert voltage['by_product'][1]['field'] is None
    assert voltage['by_product'][1]['applicability']=='not_defined_for_category'
    with pytest.raises(CharacteristicError,match='unreviewed'):
        compare(db,ids)


def test_reviewed_unknown_still_is_not_a_numeric_rating(db):
    p=sku(db,'HA-010-M')
    s=db.execute("SELECT * FROM product_specifications WHERE product_id=%s AND parameter='rated_current'",(p['id'],)).fetchone()
    db.execute("UPDATE product_specifications SET value_state='NA',value_number=NULL,state_reason='test unknown',review_status='reviewed' WHERE id=%s",(s['id'],))
    from wain.service import search_products
    assert search_products(db,q=p['order_number'],min_current=1,include_pending=True)['items']==[]


def test_migration_upgrades_legacy_rows_without_changing_facts_or_reviews():
    from psycopg import sql
    with connect() as conn:
        namespace='legacy_'+uuid.uuid4().hex
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(namespace)))
        conn.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(namespace)))
        try:
            conn.execute((ROOT/'schema.sql').read_text())
            for n in [73,76,77]:
                did=conn.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
                    VALUES(%s,'fixture.pdf','/nonexistent',%s,%s,1) RETURNING id''',(str(n).zfill(64),n,n)).fetchone()['id']
                conn.execute('INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt) VALUES(%s,1,%s,595,842)',(did,n))
            seed(conn)
            p=sku(conn,'HA-010-M')
            conn.execute("UPDATE products SET review_status='reviewed' WHERE id=%s",(p['id'],))
            before_products=conn.execute('SELECT * FROM products ORDER BY id').fetchall()
            before_specs=conn.execute('SELECT * FROM product_specifications ORDER BY id').fetchall()
            migrate(conn);migrate(conn)
            assert conn.execute('SELECT * FROM products ORDER BY id').fetchall()==before_products
            after=conn.execute('SELECT * FROM product_specifications ORDER BY id').fetchall()
            assert [{k:v for k,v in s.items() if k not in {'value_state','state_reason'}} for s in after]==before_specs
            assert all(s['value_state']=='known' and s['state_reason'] is None for s in after)
            assert conn.execute('SELECT count(*) AS n FROM schema_migrations').fetchone()['n']==2
        finally:
            conn.rollback()


def test_schema_and_comparison_http_are_read_only(db,monkeypatch):
    @contextmanager
    def same():yield db
    monkeypatch.setattr(api,'connect',same)
    client=TestClient(api.app)
    assert len(client.get('/component-schema').json()['categories'])==10
    ids=[sku(db,m)['id'] for m in ['HA-010-M','HA-010-F']]
    assert client.post('/products/compare',json={'product_ids':ids}).status_code==422
    r=client.post('/products/compare',json={'product_ids':ids,'include_pending':True})
    assert r.status_code==200 and not r.json()['can_finalize']
    assert client.post('/products/compare',json={'product_ids':[ids[0],ids[0]],'include_pending':True}).status_code==422
    assert client.get(f'/products/{ids[0]}/characteristics?include_pending=true').status_code==200
    assert client.get('/products/999999/characteristics?include_pending=true').status_code==404
    assert db.execute('SELECT count(*) AS n FROM review_events').fetchone()['n']==0
