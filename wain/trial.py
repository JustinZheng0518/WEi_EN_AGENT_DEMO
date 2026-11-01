"""Read-only, bounded product projection for the interaction prototype. No credentials/file paths."""
from datetime import datetime,timezone

def snapshot(conn):
    rows=conn.execute('''SELECT p.id,p.model,p.order_number,p.category,p.gender,p.termination,p.contact_count,
        p.pe_contacts,p.housing_size,p.review_status,pg.global_page,pg.printed_page
        FROM products p JOIN product_families f ON f.id=p.family_id
        JOIN evidence e ON e.id=p.evidence_id JOIN pages pg ON pg.id=e.page_id
        WHERE p.model LIKE 'HA-010-%%' OR f.code IN ('CE','H10A','WNA')
        ORDER BY p.id''').fetchall()
    if len(rows)>500: raise ValueError('Trial data projection exceeded its bounded sample size')
    keys=['rated_voltage','rated_current','wire_cross_section_min','wire_cross_section_max',
          'cable_diameter_min','cable_diameter_max','limiting_temperature_min','limiting_temperature_max',
          'standard_pack_quantity','plating','entry_thread_designation']
    for row in rows:
        row['specifications']=conn.execute('''SELECT s.parameter,s.value_number,s.value_text,s.unit,s.conditions,
            s.review_status,s.value_state,s.state_reason,p.global_page FROM product_specifications s JOIN evidence e ON e.id=s.evidence_id
            JOIN pages p ON p.id=e.page_id WHERE s.product_id=%s AND s.parameter=ANY(%s) ORDER BY s.parameter,s.id''',
            (row['id'],keys)).fetchall()
    return {'version':1,'scope':'HA-010 connector-component interaction trial',
            'generated_at':datetime.now(timezone.utc).isoformat(),'products':rows,
            'llm_connected':False,'offline_validation_level':'basic_only','offline_can_finalize':False}
