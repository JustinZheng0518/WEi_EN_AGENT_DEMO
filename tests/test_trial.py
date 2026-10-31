from contextlib import contextmanager
import json
import subprocess
import pytest
from fastapi.testclient import TestClient
from wain import api
from wain.trial import snapshot
from scripts.build_trial import build
from test_database import db
from test_ha010_seed import companion_pages
from wain.ha010_seed import seed_ha010
from wain.selection import SelectionRequest, select

def test_projection_excludes_private_paths_and_other_series(db):
    companion_pages(db);seed_ha010(db)
    data=snapshot(db)
    assert len(data['products'])==46
    assert data['offline_can_finalize'] is False and data['llm_connected'] is False
    encoded=json.dumps(data,default=str)
    for forbidden in ['source_path','pgpassword','ocr_artifact','reviewed_by']:
        assert forbidden not in encoded
    assert not any(p['model'].startswith('HA-016') for p in data['products'])

def test_portable_html_is_self_contained_and_blocks_network(db):
    companion_pages(db);seed_ha010(db)
    data=snapshot(db)
    html=build(data)
    assert 'script src=' not in html and 'rel="stylesheet"' not in html
    assert "connect-src 'none'" in html
    payload=html.split('<script id="trialData" type="application/json">')[1].split('</script>')[0]
    assert len(json.loads(payload)['products'])==46
    data['products'][0]['model']='</script><script>alert(1)</script>'
    malicious=build(data)
    assert '</script><script>alert(1)' not in malicious
    assert '\\u003c/script' in malicious

def test_home_trial_and_legacy_workbench_routes(db,monkeypatch):
    companion_pages(db);seed_ha010(db)
    @contextmanager
    def same():yield db
    monkeypatch.setattr(api,'connect',same)
    client=TestClient(api.app)
    assert 'WAIN Select' in client.get('/').text
    assert 'catalogPanel' in client.get('/workbench').text
    assert client.get('/static/trial/core.js').status_code==200
    assert len(client.get('/trial/data').json()['products'])==46
    assert "connect-src 'none'" in client.get('/demo').headers['content-security-policy']

@pytest.mark.parametrize('changes',[
    {}, {'current':17}, {'voltage':300}, {'wire_mm2':.5}, {'ambient_c':150},
    {'cable_diameter_mm':30}, {'termination':'crimp','quantity':2},
    {'termination':'crimp','plating':'gold'}, {'entry_direction':'top'},
    {'termination':'spring'}, {'wire_mm2':None,'cable_diameter_mm':None,'ambient_c':None,'termination':'crimp'}
])
def test_offline_nominal_screening_and_bom_match_seeded_server(db,changes):
    """Only candidate identities, quantities and basic reject status; no parity claim for engineering."""
    companion_pages(db);seed_ha010(db)
    req=SelectionRequest(**{
        'voltage':24,'current':3,'wire_mm2':1,'cable_diameter_mm':8,'ambient_c':25, **changes})
    payload=json.dumps({'request':req.model_dump(),'data':snapshot(db)},default=float)
    program="const fs=require('node:fs');const c=require('./wain/static/trial/core.js');const p=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(c.offline(p.request,p.data)));"
    result=subprocess.run(['node','-e',program],input=payload,text=True,capture_output=True,check=True)
    offline=json.loads(result.stdout);online=select(db,req)
    assert offline['can_finalize'] is False
    assert offline['status']==online['status']
    project=lambda r:[(b['role'],b['product_id'],b['quantity']) for b in r['bom']]
    assert project(offline)==project(online)
