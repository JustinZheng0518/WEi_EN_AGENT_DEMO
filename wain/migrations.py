"""Transactional additive migrations. Existing identities, facts and reviews are preserved."""
import hashlib
import json
from .db import ROOT


def migrate(conn):
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(9237101)')
        conn.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())''')
        path = ROOT / 'migrations/001_component_features.sql'
        dictionary = ROOT / 'data/component_schema.json'
        checksum = hashlib.sha256(path.read_bytes() + dictionary.read_bytes()).hexdigest()
        old = conn.execute('SELECT checksum FROM schema_migrations WHERE version=%s', (path.stem,)).fetchone()
        if old:
            if old['checksum'] != checksum:
                raise ValueError('Applied migration changed; add a new migration instead of overwriting it')
            return
        conn.execute(path.read_text())
        definitions = json.loads(dictionary.read_text())
        for category in definitions['categories']:
            conn.execute('INSERT INTO component_categories VALUES(%s,%s,%s)',
                         (category['code'], category['label_zh'], category['description']))
        for field in definitions['fields']:
            conn.execute('''INSERT INTO characteristic_definitions(code,label_zh,storage,value_kind,canonical_unit,
                feature_group,minimum,minimum_exclusive,paired_parameter,bound_role)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', tuple(field[k] for k in
                    ['code','label_zh','storage','value_kind','canonical_unit','feature_group','minimum',
                     'minimum_exclusive','paired_parameter','bound_role']))
            for category in field['categories']:
                conn.execute('INSERT INTO category_characteristics VALUES(%s,%s,%s,%s)',
                             (category,field['code'],field['expected'],field['when_termination']))
        # Validate existing rows in place, without updating facts, evidence, or review versions.
        conn.execute('ALTER TABLE products VALIDATE CONSTRAINT products_category_definition_fk')
        conn.execute('ALTER TABLE product_specifications VALIDATE CONSTRAINT specifications_parameter_definition_fk')
        conn.execute('''SELECT validate_component_specification(product_id,parameter,value_number,value_text,
            unit,conditions,value_state,state_reason) FROM product_specifications''')
        conn.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)', (path.stem,checksum))


if __name__ == '__main__':
    from .db import connect, initialize
    with connect() as conn:
        initialize(conn)
        print('Schema migration verified; existing product facts and review decisions preserved')
