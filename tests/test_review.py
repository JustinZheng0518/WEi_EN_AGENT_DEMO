from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from wain import api
from wain.review import ReviewAction,ReviewError,apply_review,get_record
from test_database import db

def action(decision='approve',version=0,edits=None):
    return ReviewAction(decision=decision,actor='test-reviewer',note='Checked source in test fixture',
                        expected_version=version,edits=edits or {})

def product(db): return db.execute("SELECT * FROM products WHERE model='HA-010-MC'").fetchone()

def test_identity_requires_evidence_and_edits_are_audited(db):
    p=product(db)
    with pytest.raises(ReviewError,match='evidence first'): apply_review(db,'product',p['id'],action())
    apply_review(db,'evidence',p['evidence_id'],action())
    reviewed=apply_review(db,'product',p['id'],action())
    assert reviewed['record']['review_status']=='reviewed'
    assert reviewed['history'][0]['actor']=='test-reviewer'
    assert reviewed['history'][0]['changes']['before']['review_status']=='pending'
    with pytest.raises(ReviewError,match='reload'): apply_review(db,'product',p['id'],action())

def test_source_change_invalidates_identity_and_parameters(db):
    p=product(db)
    apply_review(db,'evidence',p['evidence_id'],action())
    apply_review(db,'product',p['id'],action())
    source=get_record(db,'evidence',p['evidence_id'])
    apply_review(db,'evidence',p['evidence_id'],action('save',source['version'],{'quotation':'Corrected source quotation'}))
    current=get_record(db,'product',p['id'])
    assert current['record']['review_status']=='pending'
    assert current['history'][0]['action']=='invalidate'
    assert current['version']>0

def test_parameter_review_is_independent_and_identity_edit_invalidates(db):
    p=product(db)
    for eid in [p['evidence_id'],db.execute("SELECT evidence_id FROM product_specifications WHERE product_id=%s AND parameter='rated_current'",(p['id'],)).fetchone()['evidence_id']]:
        apply_review(db,'evidence',eid,action())
    reviewed=apply_review(db,'product',p['id'],action())
    spec=db.execute("SELECT * FROM product_specifications WHERE product_id=%s AND parameter='rated_current'",(p['id'],)).fetchone()
    assert spec['review_status']=='pending'
    apply_review(db,'specification',spec['id'],action())
    apply_review(db,'product',p['id'],action('save',reviewed['version'],{'housing_size':'10A corrected'}))
    assert get_record(db,'specification',spec['id'])['record']['review_status']=='pending'

def test_unapproved_dependency_or_invalid_edits_cannot_be_saved(db):
    p=product(db)
    with pytest.raises(ReviewError): apply_review(db,'product',p['id'],action('save',edits={'order_number':'bad'}))
    assert product(db)['order_number']==p['order_number']
    with pytest.raises(ReviewError): apply_review(db,'product',p['id'],action('save',edits={'review_status':'reviewed'}))
    with pytest.raises(ReviewError): apply_review(db,'evidence',p['evidence_id'],action('save',edits={'region':[0,0,2,1]}))

def test_http_review_and_cross_origin_protection(db,monkeypatch):
    @contextmanager
    def same(): yield db
    monkeypatch.setattr(api,'connect',same)
    c=TestClient(api.app)
    assert c.get('/').status_code==200
    assert c.get('/static/app.js').status_code==200
    assert c.get('/review/queue?kind=product').json()['items']
    p=product(db); path=f"/review/evidence/{p['evidence_id']}"
    body=action().model_dump()
    assert c.post(path,json=body).status_code==403
    assert c.post(path,json=body,headers={'X-Wain-Review':'1','Origin':'https://foreign.example'}).status_code==403
    assert c.post(path,json=body,headers={'X-Wain-Review':'1'}).status_code==200
    assert c.post(path,json=body,headers={'X-Wain-Review':'1'}).status_code==409
