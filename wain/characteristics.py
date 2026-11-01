"""Category-aware feature inspection and comparison. Never inherit or approve facts."""
import json
from decimal import Decimal


class CharacteristicError(ValueError):
    pass


def definitions(conn, category=None):
    return conn.execute('''SELECT d.*,c.category,c.expected,c.when_termination
        FROM characteristic_definitions d JOIN category_characteristics c ON c.characteristic=d.code
        WHERE (%s::text IS NULL OR c.category=%s) ORDER BY c.category,d.feature_group,d.code''',
        (category,category)).fetchall()


def describe(conn, product_id, include_pending=False):
    p = conn.execute('''SELECT p.*,f.code AS family_code,e.review_status AS evidence_status,
        pg.global_page FROM products p JOIN product_families f ON f.id=p.family_id
        JOIN evidence e ON e.id=p.evidence_id JOIN pages pg ON pg.id=e.page_id WHERE p.id=%s''',
        (product_id,)).fetchone()
    if p is None:
        return None
    identity_ready = p['review_status']=='reviewed' and p['evidence_status']=='reviewed'
    if not include_pending and not identity_ready:
        raise CharacteristicError('Product identity/source is unreviewed; use include_pending for catalog inspection')
    rows = conn.execute('''SELECT s.*,e.review_status AS evidence_status,pg.global_page
        FROM product_specifications s JOIN evidence e ON e.id=s.evidence_id
        JOIN pages pg ON pg.id=e.page_id WHERE s.product_id=%s ORDER BY s.parameter,s.id''',
        (product_id,)).fetchall()
    by_parameter = {}
    for row in rows:
        by_parameter.setdefault(row['parameter'],[]).append(row)
    fields = []
    for definition in definitions(conn,p['category']):
        field = {k:definition[k] for k in ['code','label_zh','storage','value_kind','canonical_unit','feature_group']}
        field['expected'] = definition['expected'] and (
            not definition['when_termination'] or p['termination'] in definition['when_termination'])
        if definition['storage']=='identity':
            value = p[definition['code']]
            observation = dict(value=value,value_state='NA' if value is None else 'known',
                conditions={},evidence_id=p['evidence_id'],global_page=p['global_page'],
                review_status=p['review_status'],evidence_status=p['evidence_status'])
            observations = [observation]
        else:
            observations = [{**row,'value':row['value_number'] if row['value_number'] is not None else row['value_text']}
                            for row in by_parameter.get(definition['code'],[])
                            if include_pending or (row['review_status']=='reviewed' and row['evidence_status']=='reviewed')]
        for observation in observations:
            observation['display_value'] = 'NA' if observation['value'] is None else observation['value']
        field['observations'] = observations
        if not observations:
            field['state'] = 'NA'
            field['availability_reason'] = 'unreviewed' if by_parameter.get(definition['code']) else 'not_recorded'
        elif any(o['review_status']=='conflict' or o['evidence_status']=='conflict' for o in observations):
            field['state'] = 'conflict'
        elif all(o['value_state']=='known' for o in observations):
            field['state'] = 'known'
        else:
            states = {o['value_state'] for o in observations}
            field['state'] = next(iter(states)) if len(states)==1 else 'mixed'
        field['reviewed'] = bool(observations) and identity_ready and all(
            o['review_status']=='reviewed' and o['evidence_status']=='reviewed' for o in observations)
        fields.append(field)
    return dict(product_id=p['id'],model=p['model'],order_number=p['order_number'],category=p['category'],
                family=p['family_code'],include_pending=include_pending,fields=fields,
                missing_or_unresolved=[f['code'] for f in fields if f['expected'] and f['state']!='known'],
                candidate_only=True,can_finalize=False)


def _signature(field):
    if field is None or field['state']!='known':
        return None
    signatures = []
    for row in field['observations']:
        value = row['value']
        if isinstance(value,(Decimal,int,float)) and not isinstance(value,bool):
            value = str(Decimal(str(value)).normalize())
        signatures.append(json.dumps([value,row['conditions']],ensure_ascii=False,sort_keys=True))
    # Match full sets of conditional facts; never take max values or union wire ranges.
    return (field['storage'],field['value_kind'],field['canonical_unit'],tuple(sorted(signatures)))


def compare(conn, product_ids, include_pending=False):
    if len(product_ids)<2 or len(product_ids)>20 or len(set(product_ids))!=len(product_ids):
        raise CharacteristicError('Compare 2–20 distinct product IDs')
    products = [describe(conn,pid,include_pending) for pid in product_ids]
    if any(p is None for p in products):
        raise CharacteristicError('Product not found')
    lookup = [{f['code']:f for f in p['fields']} for p in products]
    codes = sorted(set().union(*(set(fields) for fields in lookup)))
    common = []; different = []
    for code in codes:
        fields = [fields.get(code) for fields in lookup]
        first = next(f for f in fields if f is not None)
        item = dict(code=code,label_zh=first['label_zh'],canonical_unit=first['canonical_unit'],
                    by_product=[dict(product_id=p['product_id'],field=f,
                                     applicability='defined_for_category' if f else 'not_defined_for_category')
                                for p,f in zip(products,fields)])
        signatures = [_signature(f) for f in fields]
        if signatures[0] is not None and all(s==signatures[0] for s in signatures):
            item['all_reviewed'] = all(f['reviewed'] for f in fields)
            common.append(item)
        else:
            different.append(item)
    return dict(products=[{k:p[k] for k in ['product_id','model','order_number','category','family']} for p in products],
                common_in_this_comparison=common,different_or_na=different,include_pending=include_pending,
                compatibility_inferred=False,can_finalize=False,
                notice='Shared values only describe these explicit SKUs under identical conditions; they do not establish inheritance, mating, interchangeability or assembly approval.')
