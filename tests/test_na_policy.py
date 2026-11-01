import json
import pytest
import psycopg

from test_database import db
from wain.characteristics import describe, compare
from wain.db import ROOT
from wain.migrations import migrate
from wain.review import ReviewAction, ReviewError, apply_review
from wain.selection import SelectionRequest


def product(db):
    return db.execute("SELECT * FROM products WHERE model='HA-010-M'").fetchone()


def test_legacy_state_migrates_to_na_with_audit_and_review_preserved(db):
    # Simulate the already-applied 001 schema; immutable 001 itself is not edited.
    sql=(ROOT/'migrations/001_component_features.sql').read_text()
    db.execute('ALTER TABLE product_specifications DROP CONSTRAINT specifications_value_state_check')
    db.execute(sql[sql.index('ALTER TABLE product_specifications ADD CONSTRAINT specifications_value_state_check'):sql.index('CREATE FUNCTION validate_component_specification(')])
    function=sql[sql.index('CREATE FUNCTION validate_component_specification('):sql.index('CREATE FUNCTION check_component_specification()')]
    db.execute(function.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
    db.execute("DELETE FROM schema_migrations WHERE version='002_na_availability'")
    p=product(db)
    row=db.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,state_reason,evidence_id,review_status)
        VALUES(%s,'stripping_length','mm','unknown','Exact HA stripping instruction unavailable',%s,'pending') RETURNING *''',
        (p['id'],p['evidence_id'])).fetchone()
    migrate(db)
    after=db.execute('SELECT * FROM product_specifications WHERE id=%s',(row['id'],)).fetchone()
    assert after=={**row,'value_state':'NA'}
    event=db.execute("SELECT * FROM review_events WHERE entity_id=%s AND action='normalize_na'",(row['id'],)).fetchone()
    assert event['changes']['before']['value_state']=='unknown'
    assert event['changes']['after']['value_state']=='NA'
    migrate(db)
    assert db.execute("SELECT count(*) n FROM review_events WHERE action='normalize_na'").fetchone()['n']==1
    assert db.execute("SELECT count(*) n FROM product_specifications WHERE value_state='unknown'").fetchone()['n']==0


@pytest.mark.parametrize('state,value,reason',[
    ('unknown',None,'legacy unavailable state'),
    ('NA',7.5,'NA must not have a numeric value'),
    ('NA',None,None),
])
def test_database_rejects_old_state_or_invalid_na(db,state,value,reason):
    p=product(db)
    with pytest.raises(psycopg.IntegrityError):
        with db.transaction():
            db.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,value_number,state_reason,evidence_id)
                VALUES(%s,'stripping_length','mm',%s,%s,%s,%s)''',(p['id'],state,value,reason,p['evidence_id']))


def test_current_api_fields_and_comparison_have_na_not_legacy_state(db):
    p=product(db)
    value=describe(db,p['id'],True)
    stripping=next(f for f in value['fields'] if f['code']=='stripping_length')
    assert stripping['state']=='NA' and stripping['availability_reason']=='not_recorded'
    db.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,state_reason,evidence_id)
        VALUES(%s,'stripping_length','mm','NA','No confirmed process value',%s)''',(p['id'],p['evidence_id']))
    value=describe(db,p['id'],True)
    stripping=next(f for f in value['fields'] if f['code']=='stripping_length')
    assert stripping['observations'][0]['display_value']=='NA'
    other=db.execute("SELECT id FROM products WHERE model='HA-010-F'").fetchone()['id']
    result=compare(db,[p['id'],other],True)
    assert 'different_or_na' in result and 'unknown' not in json.dumps(result,default=str)


def test_na_and_not_applicable_remain_distinct_and_review_cannot_save_legacy_state(db):
    p=product(db)
    s=db.execute("SELECT * FROM product_specifications WHERE product_id=%s AND parameter='rated_current'",(p['id'],)).fetchone()
    with pytest.raises(ReviewError,match='Invalid value state'):
        apply_review(db,'specification',s['id'],ReviewAction(decision='save',actor='test',note='test',expected_version=0,
            edits={'value_state':'unknown','value_number':None,'state_reason':'Unavailable'}))
    assert SelectionRequest(voltage=24,current=3,wire_mm2='NA',cable_diameter_mm='na',ambient_c=' NA ').wire_mm2 is None
    from psycopg.types.json import Jsonb
    for state in ['NA','not_applicable']:
        db.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,state_reason,conditions,evidence_id)
            VALUES(%s,'stripping_length','mm',%s,'Explicit test context',%s,%s)''',
            (p['id'],state,Jsonb({'test_context':state}),p['evidence_id']))
    values=describe(db,p['id'],True)
    observations=next(f for f in values['fields'] if f['code']=='stripping_length')['observations']
    assert {o['value_state'] for o in observations}=={'NA','not_applicable'}
