from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from wain import api
from wain.ha_series import manifest,import_series,coverage,ImportConflict
from wain.service import product_details
from test_database import db

def sources(db):
    for number in [72,74,75,78,79,1396,1399]:
        did=db.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
            VALUES(%s,'fixture.pdf','/nonexistent',%s,%s,1) RETURNING id''',(str(number).zfill(64),number,number)).fetchone()['id']
        db.execute('INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt) VALUES(%s,1,%s,595,842)',(did,number))

def sku(db,model): return db.execute('SELECT * FROM products WHERE model=%s',(model,)).fetchone()

def specs(db,model):
    return {r['parameter']:r for r in db.execute('SELECT * FROM product_specifications WHERE product_id=%s',(sku(db,model)['id'],)).fetchall()}

def test_all_ordering_rows_are_reconciled_without_duplicate_products(db):
    sources(db);result=import_series(db)
    assert result['ha_insert_skus_present']==36
    assert result['chapter_ordering_rows_recorded']==147
    assert result['chapter_unique_skus_present']==72
    assert not result['missing_insert_orders']
    assert result['all_parameters_complete'] is False
    assert result['all_pairs_verified'] is False
    assert db.execute('SELECT count(*) AS n FROM products').fetchone()['n']==74 # 48 original + 26 new, no enclosure seed here
    assert db.execute("SELECT count(*) AS n FROM products WHERE review_status<>'pending'").fetchone()['n']==0
    before=db.execute('SELECT count(*) AS n FROM product_specifications').fetchone()['n']
    assert import_series(db)==result
    assert db.execute('SELECT count(*) AS n FROM product_specifications').fetchone()['n']==before
    row=sku(db,'HA-016-M')
    seen=product_details(db,row['id'])['source_occurrences']
    assert [r['global_page'] for r in seen]==[77,78]

def test_unknown_contact_counts_and_wire_ranges_are_preserved(db):
    sources(db);import_series(db)
    assert sku(db,'HA-002-MS')['contact_count'] is None
    assert sku(db,'HA-002-MS')['pe_contacts'] is None
    assert 'wire_cross_section_min' not in specs(db,'HA-004-M-V2')
    assert float(specs(db,'HA-003-M-V2')['wire_cross_section_max']['value_number'])==2.5
    assert float(specs(db,'HA-003-M')['wire_cross_section_max']['value_number'])==1.5

def test_quick_in_does_not_inherit_normal_spring_values(db):
    sources(db);import_series(db)
    normal=specs(db,'HA-003-MS');quick=specs(db,'HA-003-MQ')
    assert sku(db,'HA-003-MQ')['termination']=='spring_quick_in'
    assert float(normal['wire_cross_section_min']['value_number'])==.14
    assert float(quick['wire_cross_section_min']['value_number'])==.5
    assert quick['stripping_length']['value_number']==10
    assert quick['stripping_length']['conditions']['tolerance_mm']==.5
    assert quick['contact_resistance_max']['value_number']==3

def test_voltage_standards_and_references_are_not_collapsed(db):
    sources(db);import_series(db)
    small=specs(db,'HA-003-M');large=specs(db,'HA-010-M')
    assert 'rated_voltage' not in small
    assert small['rated_voltage_conductor_ground']['value_number']==230
    assert small['rated_voltage_conductor_conductor']['value_number']==400
    assert large['rated_voltage']['value_number']==250
    assert large['rated_voltage_ul']['value_number']==600
    assert large['rated_voltage_ul']['conditions']['not_interchangeable_with_IEC_rating'] is True

def test_ha032_is_a_numbered_arrangement_not_a_fake_sku(db):
    sources(db);import_series(db)
    assert not sku(db,'HA-032')
    assert sku(db,'HA-016-M(17-32)')['contact_count']==16
    assert sku(db,'HA-016-M(17-32)')['housing_size'] is None
    assert db.execute('SELECT count(*) AS n FROM catalog_arrangements').fetchone()['n']==6
    assert db.execute('SELECT count(*) AS n FROM catalog_arrangement_components').fetchone()['n']==12
    assert db.execute('SELECT max(quantity) AS n FROM catalog_arrangement_components').fetchone()['n']==1
    assert db.execute("SELECT count(*) AS n FROM product_relations WHERE relation='mates_with'").fetchone()['n']==0

def test_existing_reviews_survive_and_conflicting_edits_are_not_overwritten(db):
    sources(db)
    p=sku(db,'HA-010-M')
    db.execute("UPDATE products SET review_status='reviewed' WHERE id=%s",(p['id'],))
    db.execute("UPDATE evidence SET review_status='reviewed',reviewed_by='test-only',reviewed_at=now() WHERE id=%s",(p['evidence_id'],))
    import_series(db)
    assert sku(db,'HA-010-M')['review_status']=='reviewed'
    assert coverage(db)['reviewed_chapter_product_identities']==1
    db.execute("UPDATE product_specifications SET value_number=99 WHERE product_id=%s AND parameter='rated_current'",(p['id'],))
    with pytest.raises(ImportConflict,match='no overwrite'):
        import_series(db)
    assert specs(db,'HA-010-M')['rated_current']['value_number']==99

def test_coding_and_tools_have_exact_source_numbers_without_approval(db):
    sources(db);import_series(db)
    assert sku(db,'CODE-Q3')['order_number']=='1980020050034'
    assert sku(db,'TL02')['order_number']=='1980010010001'
    assert sku(db,'TL15')['order_number']=='1980010000026'
    rows=db.execute("SELECT conditions,review_status FROM product_relations WHERE relation='optional_accessory'").fetchall()
    assert len(rows)==6
    assert all(r['conditions']['not_automatically_required'] and r['review_status']=='pending' for r in rows)

def test_missing_sources_and_changed_identities_fail_atomically(db):
    with pytest.raises(ValueError,match='source pages'):import_series(db)
    sources(db)
    db.execute("UPDATE products SET model='user-edited-model' WHERE model='HA-010-M'")
    before=db.execute('SELECT count(*) AS n FROM products').fetchone()['n']
    with pytest.raises(ImportConflict,match='no overwrite'):import_series(db)
    assert db.execute('SELECT count(*) AS n FROM products').fetchone()['n']==before
    assert not sku(db,'HA-003-M')
    assert sku(db,'user-edited-model')

def test_coverage_http_distinguishes_rows_parameters_and_approvals(db,monkeypatch):
    sources(db);import_series(db)
    @contextmanager
    def same():yield db
    monkeypatch.setattr(api,'connect',same)
    client=TestClient(api.app)
    result=client.get('/series/ha/coverage').json()
    assert result['ha_insert_skus_present']==36
    assert result['reviewed_chapter_product_identities']==0
    assert result['all_parameters_complete'] is False
    assert len(client.get('/products',params={'q':'HA-','include_pending':True,'limit':100}).json()['items'])==36
