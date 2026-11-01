import copy
import json
from pathlib import Path

import psycopg
import pytest

from test_database import db
from test_ha010_seed import companion_pages
from test_ha_series import sources
from wain.ha010_seed import seed_ha010
from wain.ha_series import import_series
from wain.ha_reconcile import ReconciliationError, apply_plan, check_sources, make_plan, proposal, write_report
from wain.review import ReviewAction, apply_review


@pytest.fixture
def catalog(db):
    companion_pages(db);seed_ha010(db);sources(db);import_series(db)
    # Fixture source identities match the checked manifest; no original PDFs are needed by CI.
    for source in proposal()['sources']:
        start=source['global_page']-source['page_in_pdf']+1
        # All references to the same document need the same range and identity.
        document=db.execute('SELECT id FROM documents WHERE sha256=%s',(source['pdf_sha256'],)).fetchone()
        if document is None:
            document=db.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
                VALUES(%s,%s,'/nonexistent-test-source.pdf',%s,%s,%s) RETURNING id''',
                (source['pdf_sha256'],source['pdf_file'],start,start+49,50)).fetchone()
        old=db.execute('SELECT id FROM pages WHERE global_page=%s',(source['global_page'],)).fetchone()
        if old:
            db.execute('UPDATE pages SET document_id=%s,local_page=%s WHERE id=%s',
                (document['id'],source['page_in_pdf'],old['id']))
        else:
            db.execute('''INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt)
                VALUES(%s,%s,%s,595,842)''',(document['id'],source['page_in_pdf'],source['global_page']))
    return db


def counts(conn):
    return {name:conn.execute(f'SELECT count(*) AS n FROM {name}').fetchone()['n']
            for name in ['products','product_specifications','product_relations','evidence','review_events','ingestion_runs']}


def originals(conn):
    return {name:conn.execute(f'SELECT * FROM {name} ORDER BY id').fetchall()
            for name in ['products','product_specifications','product_relations','evidence','review_events','assembly_assessments']}


def test_plan_is_read_only_and_complete(catalog):
    before=counts(catalog)
    plan=make_plan(catalog)
    assert counts(catalog)==before
    assert plan['summary']=={'existing_identity':79,'new_identity':8,'equivalent':922,
                             'new_fact':90,'new_unknown':20,'requires_review':4,'schema_gap':5}
    assert len(proposal()['products'])==87 and len(proposal()['facts'])==1041
    assert len(plan['sources'])==20
    assert make_plan(catalog)['plan_digest']==plan['plan_digest']
    assert not plan['can_finalize']


def test_additions_are_pending_idempotent_and_preserve_all_original_rows(catalog):
    before=originals(catalog)
    p=make_plan(catalog)
    result=apply_plan(catalog,p['plan_digest'],verify_files=False)
    assert result['added']=={'products':8,'known_facts':90,'unknowns':20}
    after=originals(catalog)
    for name,rows in before.items():
        after_by_id={r['id']:r for r in after[name]}
        assert all(after_by_id[r['id']]==r for r in rows),name
    assert counts(catalog)['products']==88 and counts(catalog)['product_specifications']==1149
    assert catalog.execute("SELECT count(*) n FROM products WHERE review_status<>'pending'").fetchone()['n']==0
    assert catalog.execute("SELECT count(*) n FROM product_relations WHERE relation='mates_with'").fetchone()['n']==0
    post=make_plan(catalog)
    assert post['summary']=={'existing_identity':87,'equivalent':1032,'requires_review':4,'schema_gap':5}
    second=apply_plan(catalog,post['plan_digest'],verify_files=False)
    assert second['added']=={}
    assert counts(catalog)['product_specifications']==1149


def test_previously_reviewed_identity_and_parameter_are_preserved(catalog):
    p=catalog.execute("SELECT * FROM products WHERE model='HA-010-M'").fetchone()
    s=catalog.execute("SELECT * FROM product_specifications WHERE product_id=%s AND parameter='rated_current'",(p['id'],)).fetchone()
    for eid in {p['evidence_id'],s['evidence_id']}:
        apply_review(catalog,'evidence',eid,ReviewAction(decision='approve',actor='test',note='Synthetic fixture only',expected_version=0))
    for kind,row in [('product',p),('specification',s)]:
        apply_review(catalog,kind,row['id'],ReviewAction(decision='approve',actor='test',note='Synthetic fixture only',expected_version=0))
    before=originals(catalog);plan=make_plan(catalog)
    apply_plan(catalog,plan['plan_digest'],verify_files=False)
    after=originals(catalog)
    for name,rows in before.items():
        actual={r['id']:r for r in after[name]}
        assert all(actual[r['id']]==r for r in rows)


def test_identity_conflict_blocks_related_facts_without_renaming(catalog):
    catalog.execute("UPDATE products SET model='user-corrected-name' WHERE order_number='1210100110001'")
    plan=make_plan(catalog)
    assert plan['summary']['identity_conflict']==1 and plan['summary']['blocked_identity']>0
    apply_plan(catalog,plan['plan_digest'],verify_files=False)
    assert catalog.execute("SELECT model FROM products WHERE order_number='1210100110001'").fetchone()['model']=='user-corrected-name'
    assert not catalog.execute("SELECT id FROM products WHERE model='HA-010-M'").fetchone()


def test_model_collision_does_not_create_a_second_order(catalog):
    catalog.execute("UPDATE products SET model='H3A-SE-2B-M20' WHERE model='HA-010-M'")
    plan=make_plan(catalog)
    assert any(e['status']=='identity_conflict' and e['proposed']['order_number']=='1100035101002' for e in plan['entries'])
    apply_plan(catalog,plan['plan_digest'],verify_files=False)
    assert catalog.execute("SELECT count(*) n FROM products WHERE model='H3A-SE-2B-M20'").fetchone()['n']==1


def test_value_and_condition_conflicts_are_kept_not_overwritten(catalog):
    pid=catalog.execute("SELECT id FROM products WHERE model='HA-003-M'").fetchone()['id']
    catalog.execute("UPDATE product_specifications SET value_number=11 WHERE product_id=%s AND parameter='rated_current'",(pid,))
    catalog.execute("UPDATE product_specifications SET conditions='{\"different\":true}' WHERE product_id=%s AND parameter='wire_cross_section_min'",(pid,))
    before=originals(catalog);plan=make_plan(catalog)
    assert plan['summary']['requires_review']==5
    assert plan['summary']['condition_difference']==1
    apply_plan(catalog,plan['plan_digest'],verify_files=False)
    after=originals(catalog)
    assert all({r['id']:r for r in after['product_specifications']}[s['id']]==s for s in before['product_specifications'])


def test_stale_plan_rejected_even_when_only_source_text_changes(catalog):
    plan=make_plan(catalog);before=counts(catalog)
    catalog.execute("UPDATE evidence SET quotation=quotation || ' test correction' WHERE id=(SELECT min(id) FROM evidence)")
    with pytest.raises(ReconciliationError,match='Plan changed'):
        apply_plan(catalog,plan['plan_digest'],verify_files=False)
    assert counts(catalog)==before


def test_source_hash_or_page_mapping_mismatch_blocks_all_writes(catalog):
    data=copy.deepcopy(proposal());data['sources'][0]['pdf_sha256']='0'*64
    before=counts(catalog)
    with pytest.raises(ReconciliationError,match='source mapping'):
        make_plan(catalog,data)
    assert counts(catalog)==before


def test_changed_pdf_bytes_are_detected_before_apply(catalog,tmp_path):
    bad=tmp_path/'changed.pdf';bad.write_bytes(b'changed source')
    catalog.execute('''UPDATE documents SET source_path=%s WHERE id=(SELECT document_id FROM pages WHERE global_page=64)''',(str(bad),))
    plan=make_plan(catalog);before=counts(catalog)
    with pytest.raises(ReconciliationError,match='PDF bytes changed'):
        apply_plan(catalog,plan['plan_digest'])
    assert counts(catalog)==before


def test_constraint_failure_rolls_back_new_products_evidence_and_all_facts(catalog):
    data=copy.deepcopy(proposal())
    target=next(s for s in data['facts'] if s['model']=='HA-003-M' and s['parameter']=='stripping_length')
    target['value_number']=-1
    plan=make_plan(catalog,data);before=counts(catalog)
    with pytest.raises(psycopg.errors.CheckViolation):
        apply_plan(catalog,plan['plan_digest'],data,verify_files=False)
    assert counts(catalog)==before


def test_unknowns_do_not_fill_v2_or_ha002_with_guessed_numbers(catalog):
    plan=make_plan(catalog);apply_plan(catalog,plan['plan_digest'],verify_files=False)
    assert catalog.execute("SELECT contact_count,pe_contacts FROM products WHERE model='HA-002-MS'").fetchone()==dict(contact_count=None,pe_contacts=None)
    rows=catalog.execute('''SELECT s.* FROM product_specifications s JOIN products p ON p.id=s.product_id
        WHERE p.model='HA-004-M-V2' AND s.parameter IN ('wire_cross_section_min','wire_cross_section_max')''').fetchall()
    assert len(rows)==2 and all(r['value_state']=='unknown' and r['value_number'] is None and r['state_reason'] for r in rows)
    torque=catalog.execute('''SELECT s.* FROM product_specifications s JOIN products p ON p.id=s.product_id
        WHERE p.model='HA-004-M-V2' AND s.parameter='tightening_test_torque' ''').fetchone()
    assert torque['value_state']=='known' and torque['value_number']==.25
    # The unresolved disagreement is reported, not replaced by a fabricated approval or unknown override.
    assert make_plan(catalog)['summary']['requires_review']==4


def test_report_has_no_private_paths_and_glands_keep_motion_conditions(catalog,tmp_path):
    before=make_plan(catalog);applied=apply_plan(catalog,before['plan_digest'],verify_files=False);after=make_plan(catalog)
    write_report(before,after,applied,tmp_path)
    text='\n'.join(p.read_text() for p in tmp_path.iterdir())
    assert 'source_path' not in text and '/nonexistent' not in text
    assert (tmp_path/'ha-reconciliation-diff.csv').read_text().startswith('\ufeff')
    rows=catalog.execute('''SELECT s.conditions,s.value_number FROM product_specifications s JOIN products p ON p.id=s.product_id
        WHERE p.model='WNA-M25(D9-16)' AND s.parameter='limiting_temperature_max' ''').fetchall()
    assert {(r['conditions']['motion'],int(r['value_number'])) for r in rows}=={('static',100),('dynamic',80)}


def test_navigation_assigns_all_new_families_without_claiming_approval(catalog):
    from test_catalog import contents
    from wain.catalog import import_inventory, summary, sections
    plan=make_plan(catalog);apply_plan(catalog,plan['plan_digest'],verify_files=False)
    contents(catalog);import_inventory(catalog)
    report=summary(catalog)
    assert report['sample_products_assigned']==88 and report['sample_products_unassigned']==0
    assert report['all_products_entered'] is False
    entries={e['code']:e for e in sections(catalog)}
    for code in ['ENCLOSURE_3A','ENCLOSURE_16A','ENCLOSURE_32A']:
        assert entries[code]['sample_products']==2
        assert entries[code]['reviewed_product_identities']==0
