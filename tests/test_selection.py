from contextlib import contextmanager
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from wain import api
from wain.ha010_seed import seed_ha010
from wain.selection import SelectionRequest,select
from wain.review import apply_review,ReviewAction
from test_database import db
from test_ha010_seed import companion_pages

@pytest.fixture
def catalog(db):
    companion_pages(db);seed_ha010(db)
    return db

def request(**changes):
    return SelectionRequest(voltage=24,current=3,wire_mm2=1,cable_diameter_mm=8,ambient_c=25,**changes)

def fully_audited_fixture(conn,req):
    """Synthetic data confined to a rolled-back test schema; never actual product approval."""
    conn.execute("UPDATE evidence SET review_status='reviewed',reviewed_by='synthetic-test-only',reviewed_at=now()")
    conn.execute("UPDATE products SET review_status='reviewed'")
    conn.execute("UPDATE product_specifications SET review_status='reviewed'")
    conn.execute("UPDATE product_relations SET review_status='reviewed'")
    report=select(conn,req);ids=report['scope']['products']
    eid=conn.execute('SELECT id FROM evidence LIMIT 1').fetchone()['id']
    for src,dst,kind in [('male_insert','female_insert','mates_with'),('male_insert','hood','uses_housing'),
        ('female_insert','panel_housing','uses_housing'),('hood','panel_housing','mates_with'),('hood','cable_entry','requires_accessory')]:
        conn.execute('''INSERT INTO product_relations(source_product_id,target_product_id,relation,evidence_id,review_status)
            VALUES(%s,%s,%s,%s,'reviewed')''',(ids[src],ids[dst],kind,eid))
    findings={
        'derating':{'capacity_a':16,'voltage_v':250},
        'mechanical_sealing':{k:True for k in ['thread_compatible','thread_engagement','seal_complete','locking_compatible','ip65_verified','all_accessories_accounted_for']},
        'pe_termination':{'pe_complete':True},
        'pinout_mounting':{k:True for k in ['pinout_verified','polarization_verified','mounting_clearance']}}
    for code,facts in findings.items():
        conn.execute('''INSERT INTO assembly_assessments(check_code,scope,findings,evidence_id,review_status)
            VALUES(%s,%s,%s,%s,'reviewed')''',(code,Jsonb(report['scope']),Jsonb({**facts,'synthetic_test_only':True}),eid))
    return report['scope'],eid

def test_real_pending_data_cannot_finalize(catalog):
    report=select(catalog,request())
    assert report['status']=='needs_confirmation'
    assert report['can_finalize'] is False
    assert len(report['bom'])==5
    assert all(row['product_id'] for row in report['bom'])
    assert any(c['code']=='assessment_mechanical_sealing' and c['status']=='needs_confirmation' for c in report['checks'])

@pytest.mark.parametrize('parameter,code',[
    ('limiting_temperature_min','temperature_male_insert'),
    ('wire_cross_section_min','range_male_insert'),
    ('rated_current','male_insert_rated_current'),
])
def test_explicit_unknown_fact_never_passes_even_with_reviewed_test_scope(catalog,parameter,code):
    req=request()
    scope,_=fully_audited_fixture(catalog,req)
    catalog.execute('''UPDATE product_specifications SET value_state='NA',value_number=NULL,
        state_reason='Synthetic regression: exact value unresolved'
        WHERE product_id=%s AND parameter=%s''',(scope['products']['male_insert'],parameter))
    result=select(catalog,req)
    assert result['can_finalize'] is False
    assert any(c['code']==code and c['status']=='needs_confirmation' for c in result['checks'])

def test_unknown_spring_stripping_process_blocks_otherwise_reviewed_test_scope(catalog):
    req=request(termination='spring')
    scope,eid=fully_audited_fixture(catalog,req)
    assert select(catalog,req)['can_finalize'] is True
    catalog.execute('''INSERT INTO product_specifications(product_id,parameter,unit,value_state,state_reason,
        evidence_id,review_status) VALUES(%s,'stripping_length','mm','NA',
        'HA-specific spring stripping instruction still missing',%s,'reviewed')''',(scope['products']['male_insert'],eid))
    result=select(catalog,req)
    assert result['can_finalize'] is False
    assert any(c['code']=='na_male_insert_stripping_length' and c['status']=='needs_confirmation' for c in result['checks'])

@pytest.mark.parametrize('changes,code',[
    ({'current':17},'male_insert_rated_current'),({'wire_mm2':.5},'range_male_insert'),
    ({'ambient_c':150},'temperature_male_insert'),({'cable_diameter_mm':30},'component_cable_entry'),
    ({'contacts':8},'scope'),({'components':{'hood':None}},'component_hood'),
    ({'components':{'hood':999999}},'component_hood')])
def test_failed_conditions_are_explicit(catalog,changes,code):
    data={'voltage':24,'current':3,'wire_mm2':1,'cable_diameter_mm':8,'ambient_c':25,**changes}
    report=select(catalog,SelectionRequest(**data))
    assert report['status']=='failed'
    assert any(c['code']==code and c['status']=='failed' for c in report['checks'])

def test_missing_input_is_not_guessed(catalog):
    report=select(catalog,SelectionRequest(voltage=24,current=3,termination='crimp'))
    assert report['status']=='needs_confirmation'
    assert report['scope']['products']['cable_entry'] is None
    assert report['scope']['products']['male_contacts'] is None
    assert len(report['bom'])==7

def test_crimp_quantities_and_pack_rounding(catalog):
    report=select(catalog,request(termination='crimp',quantity=2))
    by_role={row['role']:row for row in report['bom']}
    assert by_role['male_contacts']['quantity']==20
    assert by_role['female_contacts']['quantity']==20
    assert by_role['hood']['quantity']==2
    assert by_role['male_contacts']['suggested_purchase_quantity']==100
    assert by_role['male_contacts']['pack_quantity_reviewed'] is False
    assert report['assembly_tools']
    assert any(c['code']=='assessment_pe_termination' and c['status']=='needs_confirmation' for c in report['checks'])

def test_fully_reviewed_synthetic_case_can_pass_but_scope_changes_cannot(catalog):
    req=request()
    fully_audited_fixture(catalog,req)
    report=select(catalog,req)
    assert report['status']=='passed',report['checks']
    assert report['can_finalize'] is True
    assert all(c['status']=='passed' for c in report['checks'])
    assert select(catalog,request(quantity=2))['can_finalize'] is False

def test_fact_edit_invalidates_engineering_assessments(catalog):
    req=request();fully_audited_fixture(catalog,req)
    row=catalog.execute("SELECT id FROM product_specifications WHERE parameter='rated_current' LIMIT 1").fetchone()
    apply_review(catalog,'specification',row['id'],ReviewAction(decision='save',actor='test-reviewer',note='Changed a supporting fact',expected_version=0,edits={'value_number':15}))
    assert catalog.execute("SELECT count(*) AS n FROM assembly_assessments WHERE review_status='reviewed'").fetchone()['n']==0
    assert select(catalog,req)['can_finalize'] is False

def test_latest_conflict_overrides_old_approval(catalog):
    req=request();scope,eid=fully_audited_fixture(catalog,req)
    catalog.execute("INSERT INTO assembly_assessments(check_code,scope,findings,evidence_id,review_status) VALUES('derating',%s,'{}',%s,'conflict')",(Jsonb(scope),eid))
    assert select(catalog,req)['status']=='failed'

def test_unlisted_required_accessory_blocks_otherwise_approved_assembly(catalog):
    req=request();scope,eid=fully_audited_fixture(catalog,req)
    target=catalog.execute("SELECT id FROM products WHERE model='TL01'").fetchone()['id']
    catalog.execute("""INSERT INTO product_relations(source_product_id,target_product_id,relation,evidence_id,review_status)
        VALUES(%s,%s,'requires_accessory',%s,'reviewed')""",(scope['products']['hood'],target,eid))
    report=select(catalog,req)
    assert report['can_finalize'] is False
    assert any(row['product_id']==target and row['quantity'] is None for row in report['bom'])

def test_http_selection_and_creation_safety(catalog,monkeypatch):
    @contextmanager
    def same(): yield catalog
    monkeypatch.setattr(api,'connect',same)
    c=TestClient(api.app)
    r=c.post('/selection/ha010',json=request().model_dump())
    assert r.status_code==200 and not r.json()['can_finalize']
    assert c.post('/selection/ha010',json={'voltage':24,'current':0}).status_code==422
    assert c.post('/selection/ha010',json={'voltage':24,'current':3,'components':{'invented':1}}).status_code==422
    eid=catalog.execute('SELECT id FROM evidence LIMIT 1').fetchone()['id']
    body={'check_code':'derating','scope':r.json()['scope'],'findings':{'capacity_a':16,'voltage_v':250},
          'evidence_id':eid,'actor':'test-reviewer','note':'Needs engineering check'}
    assert c.post('/review/assessments',json=body).status_code==403
    saved=c.post('/review/assessments',json=body,headers={'X-Wain-Review':'1'})
    assert saved.status_code==200 and saved.json()['record']['review_status']=='pending'
    ids=r.json()['scope']['products']
    relation={'source_product_id':ids['male_insert'],'target_product_id':ids['female_insert'],'relation':'mates_with',
              'evidence_id':eid,'actor':'test-reviewer','note':'Candidate relation, not yet approved'}
    assert c.post('/review/relations',json=relation).status_code==403
    created=c.post('/review/relations',json=relation,headers={'X-Wain-Review':'1'})
    assert created.status_code==200 and created.json()['record']['review_status']=='pending'
    assert c.post('/review/relations',json=relation,headers={'X-Wain-Review':'1'}).status_code==422

@pytest.mark.parametrize('case',json.loads((Path(__file__).resolve().parents[1]/'examples/ha010_cases.json').read_text()))
def test_documented_catalog_cases(catalog,case):
    report=select(catalog,SelectionRequest(**case['request']))
    assert report['status']==case['expected_status']
    assert len(report['bom'])==case['expected_bom_rows']
    assert report['can_finalize'] is False
