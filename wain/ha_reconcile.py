"""Source-checked HA dossier diff and additive pending-only import. Never overwrite facts."""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path

from psycopg.types.json import Jsonb
from .db import ROOT, connect
from scripts.ha_dossier import build, load_data


class ReconciliationError(ValueError):
    pass


def canonical(value):
    def encode(obj):
        if isinstance(obj,Decimal):
            return str(obj.normalize())
        raise TypeError(type(obj).__name__)
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=encode)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def proposal():
    """Map explicit dossier facts to existing canonical fields, without parsing model digits."""
    chapter,supplement=load_data()
    dossier=build(chapter,supplement)
    products=[]; facts=[]
    def product(row,category,family,page,gender='none',termination=None,count=None,pe=None,size=None):
        p=dict(model=row['model'],order_number=row['order'],category=category,family=family,
               gender=gender,termination=termination,contact_count=count,pe_contacts=pe,housing_size=size,
               source_page=page,quotation=row['model']+'; Order No. '+row['order'])
        products.append(p)
        return p
    def fact(p,code,value,page,unit=None,conditions=None,reason=None,quote=None):
        facts.append(dict(order_number=p['order_number'],model=p['model'],parameter=code,
            value_number=value if isinstance(value,(int,float,Decimal)) else None,
            value_text=value if isinstance(value,str) else None,unit=unit,conditions=conditions or {},
            value_state='NA' if value is None else 'known',state_reason=reason,
            source_page=page,quotation=quote or f'{code}: {value}; '+p['quotation']))
    technical=('HA technical data: HA-002/003/004 10A, conductor-ground 230V, conductor-conductor 400V; '
        'HA-010/016 16A 250V, pollution degree 3; UL 600V; impulse 4kV; '
        'polycarbonate, copper alloy, -40 to +125 degC; see specific termination rows and derating curves.')
    cond={'standard':'EN 61984','pollution_degree':3,'requires_derating_check':True}
    for row in dossier['models']:
        p=product(row,'insert','HA',row['pages'][0],row['gender'],row['termination'],row['count'],row['pe'],row['housing'])
        e=row['electrical']; sp=row['parameters']
        fact(p,'rated_current',e['rated_current_a'],73,'A',cond,quote=technical)
        if e['rated_voltage_v'] is not None:
            fact(p,'rated_voltage',e['rated_voltage_v'],73,'V',cond,quote=technical)
        else:
            for field,value in [('rated_voltage_conductor_ground',e['conductor_ground_v']),('rated_voltage_conductor_conductor',e['conductor_conductor_v'])]:
                fact(p,field,value,73,'V',cond,quote=technical)
            fact(p,'alternative_voltage_marking','10A 250V 4kV 3',73,conditions={'requires_actual_marking_confirmation':True},quote=technical)
        for code,value,unit,conditions in [
            ('rated_voltage_ul',600,'V',{'standard':'UL','not_interchangeable_with_IEC_rating':True}),
            ('rated_impulse_voltage',4000,'V',{}),('limiting_temperature_min',-40,'degC',{}),
            ('limiting_temperature_max',125,'degC',{}),('insulation_resistance_min',10**10,'Ohm',{'comparison':'>='}),
            ('mechanical_mating_cycles_min',500,'cycles',{'comparison':'>='})]:
            fact(p,code,value,73,unit,conditions,quote=technical)
        for code,value in [('material','polycarbonate'),('contact_material','copper alloy'),('flammability_ul94','V0')]:
            fact(p,code,value,73,quote=technical)
        fact(p,'standard_pack_quantity',row['pack'],p['source_page'],'pcs')
        for i,code in enumerate(['wire_cross_section_min','wire_cross_section_max']):
            fact(p,code,sp['wire_mm2'][i] if sp['wire_mm2'] else None,73,'mm2',
                 reason=sp['notes'] if sp['wire_mm2'] is None else None,
                 quote='Screw: HA-003/004 0.75-1.5mm2; HA-003-M/F-V2 and HA-010/016 0.75-2.5mm2; crimp 0.14-4; spring 0.14-2.5; Quick-in 0.5-2.5mm2.')
        fact(p,'wire_awg_range',sp['awg'].replace('–','-') if sp['awg'] else None,73,
             reason=sp['notes'] if sp['awg'] is None else None,quote='HA technical table AWG rows; variants must be confirmed separately.')
        if row['termination']=='screw':
            fact(p,'tightening_test_torque',sp['torque_nm'],73,'Nm',
                 {'variant_confirmation_required':True} if 'V2' in row['model'] else {},
                 reason=sp['notes'] if sp['torque_nm'] is None else None,
                 quote='Tightening/Test torque: 0.25Nm (HA-003/004) or 0.5Nm (HA-010/016); no separate V2 torque row.')
        strip_cond={'tolerance_mm':.5} if row['termination']=='spring_quick_in' else (
            {'scope':'ordinary_crimp_contacts_only','requires_contact_selection':True} if row['termination']=='crimp' else {})
        strip_page=sp['stripping_source_page'] or (69 if row['termination']=='spring' else 64)
        fact(p,'stripping_length',sp['stripping_mm'],strip_page,'mm',strip_cond,
             reason=sp['notes'] if sp['stripping_mm'] is None else None,
             quote={64:'Screw terminal table: HA-003/HA-004 stripping 4.5mm; HA-010/HA-016/HA-032 stripping 7.5mm; V2 not separately listed.',
                    69:'Spring terminal table lists HE/HVE and other named inserts; no HA-specific stripping length is confirmed here.',
                    73:'Spring terminal (Quick-in): stripping length 10 +/- 0.5mm.',
                    76:'Listed 16A crimp contacts: stripping length 7.5mm; PE construction must be verified separately.'}[strip_page])
        fact(p,'contact_resistance_max',row['contact_resistance_max_mohm'],73,'mOhm',quote='Contacts resistance <=1mOhm; Quick-in <=3mOhm.')
        if '/B' in row['model']:
            fact(p,'wiring_variant','/B stands for wiring with cable protecting; see printed page 00-09',p['source_page'])
        if '(17-32)' in row['model']:
            fact(p,'contact_numbering','17-32; one 16-contact half, not a standalone 32-contact insert',p['source_page'])

    for row in dossier['contacts']:
        p=product(row,'contact','CE',76,row['gender'],'crimp')
        fact(p,'rated_current',16,76,'A',{'requires_derating_check':True})
        for code,value,unit in [('standard_pack_quantity',100,'pcs'),('plating',row['plating'],None),
            ('wire_cross_section_min',row['wire_mm2'][0],'mm2'),('wire_cross_section_max',row['wire_mm2'][1],'mm2'),
            ('stripping_length',7.5,'mm'),('wire_awg_range',row['awg'].replace('–','-'),None),
            ('identification_grooves',{'无槽':'no groove','1槽':'1 groove','2槽':'2 grooves','3槽':'3 grooves','宽槽':'wide groove'}[row['grooves']],None)]:
            fact(p,code,value,76,unit)
    referenced={r['model']:r for r in chapter['referenced_tools']}
    tool_text={
        'TL02G':'10A/16A crimping tool 0.14-4mm2; not suitable for 16A 0.37mm2 contact; HA chapter specifies TL02 for 0.14-0.37mm2.',
        'TL01':'Contact removal tool for 16A crimp contacts.'}
    for row in dossier['tools']:
        page=1399 if row['model'] in {'TL02','TL02G'} else 1396
        p=product(row,'tool','TOOLS',page)
        fact(p,'standard_pack_quantity',1,page,'pcs')
        text=referenced[row['model']]['application'] if row['model'] in referenced else tool_text[row['model']]
        fact(p,'tool_application',text,page)
    for row in dossier['coding']:
        p=product(row,'accessory','CODING',row['pages'][0])
        fact(p,'standard_pack_quantity',row['pack'],p['source_page'],'pcs')
    for group in dossier['shell_candidates']:
        for role,category in [('hood','hood'),('housing','housing')]:
            row=group[role]; page=row['source_page']
            p=product(row,category,'H'+group['size'],page,size=group['size'])
            fact(p,'standard_pack_quantity',1,page,'pcs')
            fact(p,'ip_rating','IP65',page,conditions={'requires_assembled_sealing_verification':True})
            if role=='hood':
                fact(p,'entry_thread_designation',row['thread_marking'],page)
                fact(p,'locking_geometry','4B' if group['size']=='32A' else '2B',page)
                fact(p,'entry_direction','side',page)
            else:
                variant={'3A':'1L/W','10A':'1L/SC','16A':'1L/SC','32A':'2L/SC'}[group['size']]
                fact(p,'mounting','bulkhead',page)
                fact(p,'locking_variant',variant,page,
                     conditions={'order_confirmation_required':True})
    for row in dossier['gland_candidates']:
        p=product(row,'cable_entry','WNA',1401)
        for code,value,unit in [('standard_pack_quantity',1,'pcs'),('entry_thread_designation',row['thread'],None),
            ('cable_diameter_min',row['cable_diameter_mm'][0],'mm'),('cable_diameter_max',row['cable_diameter_mm'][1],'mm'),
            ('thread_length',row['thread_length_mm'],'mm'),('sealing','Nylon and NBR; O-sealing required for stated IP rating',None),
            ('material','Nickel-plate brass',None)]:
            fact(p,code,value,1401,unit)
        fact(p,'ip_rating','IP68',1401,conditions={'requires_assembled_sealing_verification':True},quote='Degree of protection: IP68 (with O-sealing).')
        for mode,key in [('static','static_temperature_c'),('dynamic','dynamic_temperature_c')]:
            for i,bound in enumerate(['min','max']):
                fact(p,'limiting_temperature_'+bound,row[key][i],1401,'degC',{'motion':mode},
                     quote='Temperature range: Stat -40 to +100 degC; Dyn -20 to +80 degC.')
        # Visible in the dossier, but not registered in migration 001: retain as a schema gap.
        fact(p,'wrench_size',row['wrench_sw_mm'],1401,'mm')
    if len({p['order_number'] for p in products})!=len(products):
        raise ReconciliationError('Duplicate proposed identity')
    keys=[(s['order_number'],s['parameter'],canonical(s['conditions'])) for s in facts]
    if len(set(keys))!=len(keys):
        raise ReconciliationError('Duplicate proposed parameter/condition')
    return dict(products=products,facts=facts,sources=dossier['sources'],open_issues=dossier['issues'],
                input_digest=digest({'chapter':chapter,'supplement':supplement,'mapper_version':2}))


def check_sources(conn,data,verify_files=False):
    checked=[]; file_hashes={}
    for source in data['sources']:
        row=conn.execute('''SELECT p.id,p.local_page,p.printed_page,d.filename,d.sha256,d.source_path
            FROM pages p JOIN documents d ON d.id=p.document_id WHERE p.global_page=%s''',(source['global_page'],)).fetchone()
        if row is None or (row['filename'],row['sha256'],row['local_page'])!=(source['pdf_file'],source['pdf_sha256'],source['page_in_pdf']):
            raise ReconciliationError('Missing or changed source mapping at page '+str(source['global_page']))
        if row['printed_page'] not in (None,source['printed_page']):
            raise ReconciliationError('Printed page conflict at page '+str(source['global_page']))
        if verify_files:
            path=row['source_path']
            if path not in file_hashes:
                file_hashes[path]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if file_hashes[path]!=source['pdf_sha256']:
                raise ReconciliationError('Source PDF bytes changed at page '+str(source['global_page']))
        checked.append(dict(global_page=source['global_page'],page_id=row['id'],sha256=row['sha256'],
                            filename=row['filename'],local_page=row['local_page']))
    return checked


def fact_value(row):
    return (row['value_state'],None if row['value_number'] is None else Decimal(str(row['value_number'])),
            row['value_text'],row['unit'])


def make_plan(conn,data=None):
    data=data or proposal()
    sources=check_sources(conn,data)
    existing_products=conn.execute('''SELECT p.*,f.code AS family,e.review_status AS evidence_status
        FROM products p JOIN product_families f ON f.id=p.family_id JOIN evidence e ON e.id=p.evidence_id ORDER BY p.id''').fetchall()
    by_order={p['order_number']:p for p in existing_products}
    by_model={}
    for p in existing_products:by_model.setdefault(p['model'],[]).append(p)
    specs=conn.execute('''SELECT s.*,e.review_status AS evidence_status FROM product_specifications s
        JOIN evidence e ON e.id=s.evidence_id ORDER BY s.id''').fetchall()
    spec_index={}; parameter_index={}
    for s in specs:
        spec_index[(s['product_id'],s['parameter'],canonical(s['conditions']))]=s
        parameter_index.setdefault((s['product_id'],s['parameter']),[]).append(s)
    definitions={r['code']:r for r in conn.execute('SELECT * FROM characteristic_definitions').fetchall()}
    applicable={(r['category'],r['characteristic']):r for r in conn.execute('SELECT * FROM category_characteristics').fetchall()}
    entries=[]; statuses={}; public_current={}
    identity_fields=['model','order_number','category','family','gender','termination','contact_count','pe_contacts','housing_size']
    for p in data['products']:
        old=by_order.get(p['order_number'])
        collisions=[r for r in by_model.get(p['model'],[]) if r['order_number']!=p['order_number']]
        status='identity_conflict' if collisions or (old and any(old[k]!=p[k] for k in identity_fields)) else 'existing_identity' if old else 'new_identity'
        current={k:old[k] for k in identity_fields+['id','review_status','evidence_status']} if old else None
        entries.append(dict(kind='product',status=status,proposed=p,current=current,
                            reason='Identity/model/order must match exactly; never rename or overwrite an existing SKU'))
        statuses[p['order_number']]=status; public_current[p['order_number']]=old
    for fact in data['facts']:
        p=next(p for p in data['products'] if p['order_number']==fact['order_number'])
        old_product=public_current[fact['order_number']]
        old=spec_index.get((old_product['id'],fact['parameter'],canonical(fact['conditions']))) if old_product else None
        other=parameter_index.get((old_product['id'],fact['parameter']),[]) if old_product else []
        definition=definitions.get(fact['parameter'])
        mapping=applicable.get((p['category'],fact['parameter']))
        if statuses[fact['order_number']]=='identity_conflict':
            status='blocked_identity';reason='Resolve product identity before binding any parameters'
        elif definition is None or definition['storage']!='specification' or mapping is None:
            status='schema_gap';reason='Field/category not registered; add a new migration before importing'
        elif definition['canonical_unit']!=fact['unit'] or (mapping['when_termination'] and p['termination'] not in mapping['when_termination']):
            status='schema_gap';reason='Canonical unit or termination does not match dictionary'
        elif old:
            if fact_value(old)==fact_value(fact) and (fact['value_state']=='known' or old['state_reason']==fact['state_reason']):
                status='equivalent';reason='Value, state, unit and exact conditions match; keep original evidence and review'
            else:
                status='requires_review';reason='Different value/state under same conditions; preserve the existing record'
        elif other:
            status='condition_difference';reason='Same field exists under different conditions; no automatic merging or duplicate condition assertion'
        else:
            status='new_na' if fact['value_state']=='NA' else 'new_fact'
            reason='Add explicit pending NA, no numeric default' if fact['value_state']=='NA' else 'Missing field with source; add pending only'
        current={k:old[k] for k in ['id','value_number','value_text','unit','conditions','value_state','state_reason','review_status','evidence_status','evidence_id']} if old else None
        # Preserve condition variants in reports without exposing private source paths.
        alternatives=[{k:r[k] for k in ['id','value_number','value_text','unit','conditions','value_state','review_status','evidence_status']} for r in other] if not old else []
        entries.append(dict(kind='specification',status=status,proposed=fact,current=current,other_conditions=alternatives,reason=reason))
    result=dict(scope='HA dossier additive reconciliation; no inferred compatibility or approvals',
                input_digest=data['input_digest'],sources=sources,entries=entries,
                summary=dict(Counter(e['status'] for e in entries)),open_issues=data['open_issues'],can_finalize=False)
    result['database_digest']=digest(dict(products=existing_products,specifications=specs,
        evidence=[r['record'] for r in conn.execute('SELECT to_jsonb(e) AS record FROM evidence e ORDER BY id').fetchall()],
        review_version=conn.execute('SELECT coalesce(max(id),0) AS n FROM review_events').fetchone()['n'],
        definitions=definitions,applicability=[dict(category=k[0],characteristic=k[1],**{x:v for x,v in value.items() if x not in {'category','characteristic'}}) for k,value in sorted(applicable.items())]))
    result['plan_digest']=digest(result)
    return result


def evidence(conn,source,quote):
    # Content-addressed evidence is inserted only for actual additions, never rewritten.
    region=[.05,.08,.96,.95]
    key='ha-reconcile-v1:'+digest({'page':source['global_page'],'quote':quote,'region':region})
    old=conn.execute('SELECT * FROM evidence WHERE evidence_key=%s',(key,)).fetchone()
    if old:
        if old['page_id']!=source['page_id'] or old['quotation']!=quote or old['region']!=region:
            raise ReconciliationError('Existing import evidence differs; no overwrite')
        return old['id']
    return conn.execute('''INSERT INTO evidence(evidence_key,page_id,region,quotation,method)
        VALUES(%s,%s,%s,%s,'visual_transcription') RETURNING id''',
        (key,source['page_id'],Jsonb(region),quote)).fetchone()['id']


def apply_plan(conn,expected_plan_digest,data=None,verify_files=True):
    data=data or proposal()
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(9237101)')
        # Block concurrent catalog writes, including scripts that do not use the review lock.
        conn.execute('LOCK TABLE products,product_specifications,evidence,product_families,product_source_occurrences,review_events IN SHARE ROW EXCLUSIVE MODE')
        conn.execute('LOCK TABLE documents,pages,characteristic_definitions,category_characteristics IN SHARE MODE')
        check_sources(conn,data,verify_files)
        plan=make_plan(conn,data)
        if plan['plan_digest']!=expected_plan_digest:
            raise ReconciliationError('Plan changed; regenerate the diff before applying')
        pages={r['global_page']:r for r in plan['sources']}
        added=Counter();orders={}
        for entry in plan['entries']:
            if entry['kind']!='product' or entry['status']=='identity_conflict':continue
            p=entry['proposed']
            if entry['status']=='existing_identity':
                orders[p['order_number']]=entry['current']['id'];continue
            family=conn.execute('SELECT id FROM product_families WHERE code=%s',(p['family'],)).fetchone()
            if family is None:
                family=conn.execute('INSERT INTO product_families(code,name,category) VALUES(%s,%s,%s) RETURNING id',
                    (p['family'],p['family']+' catalog companion products','enclosure')).fetchone()
            eid=evidence(conn,pages[p['source_page']],p['quotation'])
            row=conn.execute('''INSERT INTO products(family_id,model,order_number,category,gender,termination,
                contact_count,pe_contacts,housing_size,evidence_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (family['id'],*[p[k] for k in ['model','order_number','category','gender','termination','contact_count','pe_contacts','housing_size']],eid)).fetchone()
            orders[p['order_number']]=row['id'];added['products']+=1
            conn.execute('''INSERT INTO product_source_occurrences(source_key,product_id,evidence_id,source_scope,
                context_label,source_model,source_order_number) VALUES(%s,%s,%s,'ha-dossier-companions-2025',%s,%s,%s)''',
                ('ha-dossier-companions-2025:'+p['order_number'],row['id'],eid,'Standard cable-to-panel companion; compatibility unapproved',p['model'],p['order_number']))
        for entry in plan['entries']:
            if entry['kind']!='specification' or entry['status'] not in {'new_fact','new_na'}:continue
            fact=entry['proposed'];pid=orders[fact['order_number']]
            eid=evidence(conn,pages[fact['source_page']],fact['quotation'])
            conn.execute('''INSERT INTO product_specifications(product_id,parameter,value_number,value_text,unit,
                conditions,evidence_id,value_state,state_reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (pid,fact['parameter'],fact['value_number'],fact['value_text'],fact['unit'],Jsonb(fact['conditions']),eid,fact['value_state'],fact['state_reason']))
            added['na_records' if fact['value_state']=='NA' else 'known_facts']+=1
        details=dict(input_digest=data['input_digest'],plan_digest=plan['plan_digest'],added=dict(added),
                     retained_unresolved={k:v for k,v in plan['summary'].items() if k in {'requires_review','condition_difference','identity_conflict','blocked_identity','schema_gap'}},
                     reviewed_or_overwritten=0)
        conn.execute('''INSERT INTO ingestion_runs(stage,finished_at,status,details)
            VALUES('ha-dossier-reconcile-v1',now(),'done',%s)''',(Jsonb(details),))
        return details


def write_report(before,after,applied=None,folder=ROOT/'docs'):
    folder=Path(folder);folder.mkdir(exist_ok=True,parents=True)
    stream=io.StringIO(newline='');w=csv.writer(stream,lineterminator='\n')
    w.writerow(['类型','状态','型号','订货号（文本）','字段','现有值/状态','资料包值/状态','条件','文件页','原因'])
    for e in before['entries']:
        if e['status'] in {'equivalent','existing_identity'}:continue
        p=e['proposed'];old=e['current']
        w.writerow([e['kind'],e['status'],p['model'],p['order_number'],p.get('parameter','identity'),
                    canonical(old) if old else '',canonical(p) if e['kind']=='product' else canonical({k:p[k] for k in ['value_number','value_text','value_state','state_reason','unit']}),
                    canonical(p.get('conditions',{})),p['source_page'],e['reason']])
    (folder/'ha-reconciliation-diff.csv').write_text('\ufeff'+stream.getvalue())
    lines=['# HA 资料包与数据库差异及补充导入','',
        '对照明确的87个资料包订货号（含36芯体），不是重做全目录OCR或推断配对。原数据库另有一个资料包未列的顶进线外壳，不删除。', '',
        '来源分卷SHA-256、分卷内页码与数据库映射检查通过；实际应用前还核对源PDF字节。所有新增记录均pending，未覆盖旧身份、参数、来源或审核记录。', '',
        '## 差异统计','', '| 分类 | 导入前 | 导入后 |','| --- | --- | --- |']
    for key in sorted(set(before['summary'])|set(after['summary'])):
        lines.append(f'| {key} | {before["summary"].get(key,0)} | {after["summary"].get(key,0)} |')
    if applied:
        lines+=['', '本次实际添加：'+canonical(applied['added'])+'。没有新增或批准适配关系，没有工程批准。']
    lines+=['', 'equivalent只表示与资料包记录对齐，不代表已审核。new_na降为0表示NA占位已写入，新增的20条NA仍待确认，并非问题已解决。']
    lines+=['', '## 仍需复核的逐项差异','', '| 型号 | 字段 | 状态 | 旧值 / 状态 | 资料包值 / 状态 | 文件页 |','| --- | --- | --- | --- | --- | --- |']
    for e in after['entries']:
        if e['status'] not in {'requires_review','condition_difference','identity_conflict','schema_gap','blocked_identity'}:continue
        p=e['proposed'];old=e['current'] or {}
        def cell(value):return str(value).replace('|','\\|').replace('\n',' ')
        lines.append('| '+' | '.join(map(cell,[p['model'],p.get('parameter','identity'),e['status'],
            old.get('value_number') if old.get('value_number') is not None else old.get('value_text',old.get('model','无同条件记录')),
            p.get('value_number') if p.get('value_number') is not None else p.get('value_text') or p.get('value_state',p['model']),p['source_page']]))+' |')
    lines+=['', 'requires_review保留原记录，不自动判断哪一方正确；condition_difference不合并条件或重复断言；schema_gap待新增字段迁移后再导入。', '',
        '## 审核与使用边界','',
        '- 本批只补目录事实和明确NA；HA-002普通/PE接点、HA-004-V2线径、V2工艺等仍待确认。NA没有数值，不等于0或不需要。',
        '- HA-032仍为真实HA-016半组编排；不创建独立HA-032订货号。原有配对/关系及工程结论不增加、不批准。',
        '- 壳体规格、锁扣名称、入口标识仅为产品参数，不证明芯体/壳体或壳体/接头实际适配。',
        '- 线径/剥线的条件保留；压接芯体的7.5mm只针对所列普通压接接触件，不能套给PE。',
        '- 接头温度按static/dynamic分开，不套芯体温度；扳手SW暂列schema_gap，不擅自挪用其他字段。',
        '- 旧批量转录脚本仍针对旧基线；补充后不应盲目重跑以覆盖NA或工艺更正，应先使用此差异工具。', '',
        '[下载逐项差异CSV](ha-reconciliation-diff.csv)。完整导入前后计划和校验摘要保存在本地忽略目录，避免把备份、PDF或私有路径提交Git。', '',
        '## 复现','',
        '只读计划：`python -m wain.ha_reconcile plan`。应用：`python -m wain.ha_reconcile apply --expected-plan <计划摘要>`。',
        '应用前备份；应用会重新核对来源、输入和数据库差异摘要，数据变化则拒绝过期计划。写入在事务内串行执行，任何插入/约束失败则整批回滚。',
        '新家族导航关联使用`python -m wain.catalog import`，随后`python -m wain.catalog export`刷新目录报告；这只同步明确的导航映射，不批准适配。',
        '导入会记录ingestion_runs，但不会覆盖等价记录的证据或审核；重跑不重复插入参数。', '']
    (folder/'ha-reconciliation.md').write_text('\n'.join(lines))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','apply'])
    parser.add_argument('--expected-plan')
    args=parser.parse_args();folder=ROOT/'.local/exports';folder.mkdir(exist_ok=True,parents=True)
    data=proposal()
    with connect() as conn:
        before=make_plan(conn,data)
        if args.command=='plan':
            (folder/'ha-reconciliation-plan.json').write_text(json.dumps(before,ensure_ascii=False,indent=2,default=str)+'\n')
            print(json.dumps({'plan_digest':before['plan_digest'],'summary':before['summary']},ensure_ascii=False));return
        if not args.expected_plan:
            raise SystemExit('Supply --expected-plan from the reviewed read-only plan')
        applied=apply_plan(conn,args.expected_plan,data)
        after=make_plan(conn,data)
    # Success reports are written only after the database transaction commits.
    (folder/'ha-reconciliation-applied.json').write_text(json.dumps(dict(before=before,after=after,applied=applied),ensure_ascii=False,indent=2,default=str)+'\n')
    write_report(before,after,applied)
    print(json.dumps({'added':applied['added'],'remaining':after['summary'],'can_finalize':False},ensure_ascii=False))


if __name__=='__main__':main()
