def stats(conn):
    counts={}
    for table in ('documents','pages','product_families','products','product_specifications',
                  'evidence','product_relations','assembly_templates','assembly_requirements','product_candidates',
                  'product_source_occurrences','catalog_arrangements'):
        counts[table]=conn.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n']
    counts['ocr']={row['ocr_status']:row['n'] for row in conn.execute(
        'SELECT ocr_status,count(*) AS n FROM pages GROUP BY ocr_status').fetchall()}
    counts['product_review']={row['review_status']:row['n'] for row in conn.execute(
        'SELECT review_status,count(*) AS n FROM products GROUP BY review_status').fetchall()}
    counts['final_selection_ready']=False
    return counts


def search_products(conn,q='',contact_count=None,category=None,gender=None,termination=None,
                    min_voltage=None,min_current=None,include_pending=False,limit=30):
    conditions=[]; params=[]
    if not include_pending:
        conditions.append("p.review_status='reviewed'")
        conditions.append("EXISTS (SELECT 1 FROM evidence e WHERE e.id=p.evidence_id AND e.review_status='reviewed')")
    if q:
        conditions.append("(strpos(lower(p.model),lower(%s))>0 OR strpos(p.order_number,replace(%s,' ',''))>0)")
        params.extend([q,q])
    for column,value in [('contact_count',contact_count),('category',category),('gender',gender),('termination',termination)]:
        if value is not None:
            conditions.append(f'p.{column}=%s'); params.append(value)
    for parameter,value in [('rated_voltage',min_voltage),('rated_current',min_current)]:
        if value is not None:
            conditions.append('''EXISTS (SELECT 1 FROM product_specifications s WHERE s.product_id=p.id
                AND s.parameter=%s AND s.value_state='known' AND s.value_number>=%s'''+
                ('' if include_pending else " AND s.review_status='reviewed' AND EXISTS (SELECT 1 FROM evidence e WHERE e.id=s.evidence_id AND e.review_status='reviewed')")+')')
            params.extend([parameter,value])
    where=' AND '.join(conditions) or 'true'
    rows=conn.execute(f'''SELECT p.*,f.code AS family FROM products p JOIN product_families f ON f.id=p.family_id
        WHERE {where} ORDER BY p.model,p.order_number LIMIT %s''',params+[limit]).fetchall()
    return {'items':rows,'candidate_only':True,
        'notice':'Rating filters find nominal candidates only. Operating conditions, derating and compatibility still require validation.'}


def product_details(conn,product_id):
    product=conn.execute('SELECT * FROM products WHERE id=%s',(product_id,)).fetchone()
    if product is None: return None
    product['specifications']=conn.execute('''SELECT s.*,p.global_page,p.printed_page FROM product_specifications s
        JOIN evidence e ON e.id=s.evidence_id JOIN pages p ON p.id=e.page_id WHERE product_id=%s
        ORDER BY parameter''',(product_id,)).fetchall()
    product['identity_display']={key:product[key] if product[key] is not None else 'NA'
                                 for key in ['contact_count','pe_contacts','housing_size','termination','gender']}
    for specification in product['specifications']:
        value=specification['value_number'] if specification['value_number'] is not None else specification['value_text']
        specification['display_value']='NA' if value is None else value
    product['relations']=conn.execute('''SELECT r.*,p.model AS target_model FROM product_relations r
        JOIN products p ON p.id=r.target_product_id WHERE source_product_id=%s ORDER BY p.model''',(product_id,)).fetchall()
    product['evidence']=conn.execute('''SELECT e.*,p.global_page,p.printed_page,d.filename FROM evidence e
        JOIN pages p ON p.id=e.page_id JOIN documents d ON d.id=p.document_id WHERE e.id=%s''',
        (product['evidence_id'],)).fetchone()
    product['can_finalize']=False
    product['source_occurrences']=conn.execute('''SELECT o.source_scope,o.context_label,o.source_model,
        o.source_order_number,o.evidence_id,p.global_page,p.printed_page FROM product_source_occurrences o
        JOIN evidence e ON e.id=o.evidence_id JOIN pages p ON p.id=e.page_id
        WHERE o.product_id=%s ORDER BY p.global_page''',(product_id,)).fetchall()
    return product
