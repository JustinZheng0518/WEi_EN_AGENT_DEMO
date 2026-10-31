"""Catalog data gates: preserve ambiguity and prevent invented orders/approvals."""
import copy
import csv
import io
import json

import pytest

from scripts.ha_dossier import ROOT, build, load_data, outputs


@pytest.fixture
def dossier():
    return build(*load_data())


def test_full_identity_and_route_coverage(dossier):
    chapter, _ = load_data()
    expected = {(p['model'], p['order']) for p in chapter['inserts']}
    assert {(p['model'], p['order']) for p in dossier['models']} == expected
    assert len(expected) == 36
    assert {p['model'] for r in dossier['routes'] for p in r['insert_components']} == {m for m, _ in expected}
    assert len(dossier['routes']) == 18
    assert not dossier['can_finalize'] and not dossier['database_changed']
    assert all(not r['can_finalize'] for r in dossier['routes'])
    assert all(p['review_status'] == 'pending' for p in dossier['models'])


def test_ha002_contact_and_pe_ambiguity_is_preserved(dossier):
    p = next(p for p in dossier['models'] if p['model'] == 'HA-002-MS')
    assert p['count'] is None and p['pe'] is None
    r = next(r for r in dossier['routes'] if r['id'] == 'HA002-SPRING')
    assert r['ordinary_contacts_per_endpoint'] is None
    assert r['pe_assembly_count_verified'] is None
    assert 'HA002-CONTACTS' in r['open_issue_ids']


def test_v2_does_not_inherit_generic_process_or_other_variants(dossier):
    models = {p['model']: p for p in dossier['models']}
    p3 = models['HA-003-M-V2']['parameters']
    p4 = models['HA-004-M-V2']['parameters']
    assert p3['wire_mm2'] == [.75, 2.5]
    assert p4['wire_mm2'] is None
    assert p3['torque_nm'] is None and p4['torque_nm'] is None
    assert p3['stripping_mm'] is None and p4['stripping_mm'] is None
    assert models['HA-003-M']['parameters']['torque_nm'] == .25
    assert models['HA-003-M']['parameters']['stripping_mm'] == 4.5


def test_quick_in_is_not_ordinary_spring(dossier):
    models = {p['model']: p for p in dossier['models']}
    quick = models['HA-003-MQ']; spring = models['HA-003-MS']
    assert quick['parameters']['wire_mm2'] == [.5, 2.5]
    assert quick['parameters']['stripping_mm'] == 10
    assert quick['contact_resistance_max_mohm'] == 3
    assert spring['parameters']['wire_mm2'] == [.14, 2.5]
    assert spring['parameters']['stripping_mm'] is None
    assert spring['contact_resistance_max_mohm'] == 1
    assert 'HA-SPRING-STRIP' in spring['open_issue_ids']


def test_ha032_is_four_actual_halves_and_pe_is_not_added(dossier):
    assert not any(p['model'].startswith('HA-032') for p in dossier['models'])
    routes = [r for r in dossier['routes'] if r['id'].startswith('HA032')]
    assert len(routes) == 3
    for r in routes:
        assert len(r['insert_components']) == 4
        assert len({p['order'] for p in r['insert_components']}) == 4
        assert all(p['quantity_per_connection'] == 1 for p in r['insert_components'])
        assert r['ordinary_contacts_per_endpoint'] == 32
        assert r['pe_assembly_count_verified'] is None
        assert 'HA032-PE' in r['open_issue_ids']
        assert r['housing_size'] == '32A'


def test_crimp_counts_exclude_pe_and_wire_gauge_is_not_interpolated(dossier):
    for id, n in [('HA010-CRIMP', 10), ('HA016-CRIMP', 16), ('HA032-CRIMP', 32)]:
        r = next(r for r in dossier['routes'] if r['id'] == id)
        assert r['crimp_contacts_per_gender'] == n
        assert r['pe_assembly_count_verified'] is None
    contacts = {p['model']: p for p in dossier['contacts']}
    assert len(contacts) == 32
    assert contacts['CESM-0.37']['wire_mm2'] == [.14, .37]
    assert contacts['CESM-0.50']['wire_mm2'] == [.5, .5]
    assert contacts['CEGF-1.0']['order'] == '1010192200801'
    assert all(p['stripping_mm'] == 7.5 for p in contacts.values())
    assert '不适合' in next(t for t in dossier['tools'] if t['model'] == 'TL02G')['condition']


def test_shells_and_glands_are_unselected_and_thread_specific(dossier):
    for r in dossier['routes']:
        assert r['selected_gland'] is None
        if r['housing_size'] == '32A':
            assert all('M25' in m for m in r['gland_candidates'])
        else:
            assert all('M20' in m for m in r['gland_candidates'])
        assert r['unselected_supply']
    assert all('not_verified_fit' in s['status'] for s in dossier['shell_candidates'])


def test_coding_is_optional_and_only_explicit_models(dossier):
    models = {p['model']: p for p in dossier['models']}
    assert [c['model'] for c in models['HA-003-M-V2']['optional_coding']] == ['CODE-Q3']
    assert [c['model'] for c in models['HA-004-FQ']['optional_coding']] == ['CODE-Q5']
    assert models['HA-004-F-V2']['optional_coding'] == []
    assert models['HA-010-M']['optional_coding'] == []


def test_bad_route_cannot_silently_mix_gender_or_variants():
    chapter, supplement = load_data()
    bad = copy.deepcopy(supplement)
    bad['route_definitions'][0]['female_models'] = ['HA-003-M']
    with pytest.raises(ValueError, match='gender'):
        build(chapter, bad)
    bad = copy.deepcopy(supplement)
    bad['route_definitions'][0]['female_models'] = ['HA-003-F-V2']
    with pytest.raises(ValueError, match='variant'):
        build(chapter, bad)


def test_outputs_match_sources_and_csv_counts(dossier):
    rendered = outputs(dossier)
    for name, text in rendered.items():
        assert (ROOT / name).read_text() == text, name
    for name, count in [('models', 36), ('routes', 18), ('accessories', 43), ('issues', 12)]:
        rows = list(csv.DictReader(io.StringIO(rendered[f'docs/ha-series-{name}.csv'].lstrip('\ufeff'))))
        assert len(rows) == count
    saved = json.loads(rendered['data/ha_series_dossier.json'])
    assert len(saved['sources']) == 20
    assert all(len(s['pdf_sha256']) == 64 for s in saved['sources'])
    assert all(not ref['all_numeric_dimensions_transcribed'] for p in saved['models'] for ref in p['drawing_references'])
