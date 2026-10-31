"""Checked ordering-row transcription for one bounded catalog chapter, with explicit gaps."""
import argparse
import csv
import json
import re
from decimal import Decimal
from pathlib import Path
from psycopg.types.json import Jsonb
from .db import ROOT,connect,initialize

DATA=ROOT/'data/ha_series.json'
CHAPTER='ha-chapter-2025'
ISSUE_ZH={
 'ha002-contact-definition':'订货行明确列出 HA-002，但页头仅列 3/4+PE，技术页接点清单也未列 2；普通接点数与 PE 数需进一步确认。',
 'ha004-v2-wire-range':'技术页单独给出了 HA-003-V2 的线径范围，但未单独说明 HA-004-V2；不把其他款的上限套用过来。',
 'ha032-not-a-single-sku':'HA-032 是两组 16 接点芯体的编排，实际订货行是 HA-016 基础款及 (17-32) 编号半组；没有独立 HA-032 订货号。',
 'drawing-axes-and-mounting':'已保留尺寸图和开孔图来源，数值尺寸的轴向、安装状态和逐项录入仍待核对。',
 'no-engineering-approval':'降额曲线、真实配对、PE、外壳及密封仍需独立工程审核；目录转录不等于批准。'}

class ImportConflict(ValueError): pass

def manifest(path=DATA):
    data=json.loads(Path(path).read_text())
    inserts=data['inserts']
    if len({p['model'] for p in inserts})!=len(inserts) or len({p['order'] for p in inserts})!=len(inserts):
        raise ValueError('Duplicate HA identity')
    for p in inserts+data['coding']+data['referenced_tools']:
        if not re.fullmatch(r'\d{13}',p['order']): raise ValueError('Invalid order number')
    for p in inserts:
        if not p['pages'] or set(p['pages'])-set(range(74,79)) or p['gender'] not in {'male','female'}:
            raise ValueError('Invalid insert source or gender')
        if p['termination'] not in {'screw','crimp','spring','spring_quick_in'}:
            raise ValueError('Invalid termination')
    if len(inserts)!=data['expected']['insert_skus'] or sum(len(r['pages']) for r in inserts)!=data['expected']['insert_ordering_rows']:
        raise ValueError('HA insert row count does not match the checked source manifest')
    return data

def import_series(conn,path=DATA):
    data=manifest(path)
    needed=[p['page'] for p in data['pages']]+[p['page'] for p in data['referenced_tools']]
    pages={r['global_page']:r for r in conn.execute('SELECT * FROM pages WHERE global_page=ANY(%s)',(needed,)).fetchall()}
    if set(pages)!=set(needed): raise ValueError('Import all HA source pages and referenced tool pages first')
    base=conn.execute("SELECT count(*) AS n FROM products WHERE model IN ('TL01','TL02G','CESM-0.37','CEGF-4.0')").fetchone()['n']
    if base!=4: raise ValueError('Run the base pilot seed before the full HA chapter import')
    with conn.transaction():
        families={r['code']:r['id'] for r in conn.execute('SELECT id,code FROM product_families').fetchall()}
        families['CODING']=conn.execute("""INSERT INTO product_families(code,name,category)
            VALUES('CODING','Coding elements explicitly listed in HA ordering tables','accessory')
            ON CONFLICT(code) DO UPDATE SET code=excluded.code RETURNING id""").fetchone()['id']
        def ev(key,page,region,quote):
            existing=conn.execute('SELECT * FROM evidence WHERE evidence_key=%s',(key,)).fetchone()
            if existing:
                if existing['page_id']!=pages[page]['id'] or existing['region']!=region or existing['quotation']!=quote:
                    raise ImportConflict('Evidence changed; use the review workflow: '+key)
                return existing['id']
            return conn.execute('''INSERT INTO evidence(evidence_key,page_id,region,quotation,method)
                VALUES(%s,%s,%s,%s,'visual_transcription') RETURNING id''',
                (key,pages[page]['id'],Jsonb(region),quote)).fetchone()['id']
        technical=ev('ha-full-technical',73,[.08,.15,.49,.82],
            'HA-002/HA-003/HA-004: 10A, conductor-ground 230V, conductor-conductor 400V; or 10A 250V 4kV 3. '
            'HA-010/HA-016: 16A 250V, pollution degree 3; pollution degree 2 also 250V/400V. '
            'UL rated voltage 600V; impulse voltage 4kV; polycarbonate; -40 to +125 degC; UL94 V0; '
            'mating cycles >=500; copper alloy contacts; contact resistance <=1mOhm. '
            'Screw .75-1.5mm2 (HA-003/004), .75-2.5mm2 (HA-010/016), .75-2.5mm2 (HA-003-M/F-V2); '
            'crimp .14-4mm2; spring .14-2.5mm2; Quick-in .5-2.5mm2, AWG20-14, strip 10+/-0.5mm, resistance <=3mOhm.')
        derating=ev('ha-full-derating',73,[.52,.15,.94,.87],
            'Current carrying is limited by maximum temperature of materials for inserts and contacts including terminals; '
            'curves depend on wire gauge and ambient temperature; DIN EN 60512-5. No numeric curve interpolation has been approved.')
        def region(page,kind):
            if kind=='contact': return [.28,.56,.68,.81]
            if kind=='tool': return [.28,.81,.68,.94]
            if kind=='coding': return [.28,.43,.68,.64]
            return [.28,.14,.68,.53] if page>75 else [.28,.14,.68,.85]
        def row_ev(model,order,page,kind):
            return ev(f'ha-row-{page}-{order}',page,region(page,kind),model+'; Order No. '+order)
        def product(row,family,category,evidence_id):
            values={'model':row['model'],'order_number':row['order'],'category':category,
                    'gender':row.get('gender','none'),'termination':row.get('termination'),
                    'contact_count':row.get('count'),'pe_contacts':row.get('pe'),'housing_size':row.get('housing')}
            existing=conn.execute('SELECT * FROM products WHERE order_number=%s',(row['order'],)).fetchone()
            if existing:
                if any(existing[k]!=v for k,v in values.items()) or existing['family_id']!=families[family]:
                    raise ImportConflict('Existing product differs; no overwrite: '+row['model'])
                return existing['id']
            return conn.execute('''INSERT INTO products(family_id,model,order_number,category,gender,termination,
                contact_count,pe_contacts,housing_size,evidence_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (families[family],*values.values(),evidence_id)).fetchone()['id']
        def spec(pid,key,eid,number=None,text=None,unit=None,conditions=None):
            cond=conditions or {}
            existing=conn.execute('SELECT * FROM product_specifications WHERE product_id=%s AND parameter=%s AND conditions=%s',
                (pid,key,Jsonb(cond))).fetchone()
            expected=Decimal(str(number)) if number is not None else None
            if existing:
                if existing['value_number']!=expected or existing['value_text']!=text or existing['unit']!=unit:
                    raise ImportConflict('Existing parameter differs; no overwrite: '+str(pid)+' '+key)
                return
            conn.execute('''INSERT INTO product_specifications(product_id,parameter,value_number,value_text,unit,conditions,evidence_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''',(pid,key,expected,text,unit,Jsonb(cond),eid))
        def occurrence(pid,model,order,page,kind,scope=CHAPTER):
            evidence_id=row_ev(model,order,page,kind)
            source_key=f'{scope}:{page}:{order}'
            old=conn.execute('SELECT * FROM product_source_occurrences WHERE source_key=%s',(source_key,)).fetchone()
            if old and (old['product_id']!=pid or old['evidence_id']!=evidence_id or old['source_model']!=model or old['source_order_number']!=order):
                raise ImportConflict('Existing occurrence differs; no overwrite: '+source_key)
            conn.execute('''INSERT INTO product_source_occurrences(source_key,product_id,evidence_id,source_scope,
                context_label,source_model,source_order_number) VALUES(%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING''',(source_key,pid,evidence_id,scope,
                'HA-032 arrangement' if page==78 else 'HA chapter' if scope==CHAPTER else 'Referenced tool',model,order))
            return evidence_id
        ids={}
        for row in data['inserts']:
            page=row['pages'][0];identity=row_ev(row['model'],row['order'],page,'insert')
            pid=product(row,'HA','insert',identity);ids[row['model']]=pid
            for p in row['pages']: occurrence(pid,row['model'],row['order'],p,'insert')
            small=row['model'].startswith(('HA-002','HA-003','HA-004'))
            cond={'standard':'EN 61984','pollution_degree':3,'requires_derating_check':True}
            spec(pid,'rated_current',technical,number=10 if small else 16,unit='A',conditions=cond)
            if small:
                for key,value in [('rated_voltage_conductor_ground',230),('rated_voltage_conductor_conductor',400)]:
                    spec(pid,key,technical,number=value,unit='V',conditions={'standard':'EN 61984','pollution_degree':3,'requires_derating_check':True})
                spec(pid,'alternative_voltage_marking',technical,text='10A 250V 4kV 3',conditions={'requires_actual_marking_confirmation':True})
            else: spec(pid,'rated_voltage',technical,number=250,unit='V',conditions=cond)
            for key,value,unit in [('rated_impulse_voltage',4000,'V'),('rated_voltage_ul',600,'V'),
                ('limiting_temperature_min',-40,'degC'),('limiting_temperature_max',125,'degC')]:
                spec(pid,key,technical,number=value,unit=unit,
                     conditions={'standard':'UL','not_interchangeable_with_IEC_rating':True} if key=='rated_voltage_ul' else {})
            spec(pid,'insulation_resistance_min',technical,number=10**10,unit='Ohm',conditions={'comparison':'>='})
            spec(pid,'mechanical_mating_cycles_min',technical,number=500,unit='cycles',conditions={'comparison':'>='})
            for key,text in [('material','polycarbonate'),('contact_material','copper alloy'),('flammability_ul94','V0')]:
                spec(pid,key,technical,text=text)
            spec(pid,'standard_pack_quantity',identity,number=row['pack'],unit='pcs')
            spec(pid,'derating_reference',derating,text='See HA current-carrying curves; numerical capacity requires engineering evaluation')
            drawing=ev(f'ha-drawing-{page}',page,[.68,.14,.95,.85],
                'Original dimension drawings and panel cutouts for the ordering rows; view axes and mounting state require separate interpretation.')
            spec(pid,'drawing_reference',drawing,text=f'Physical page {page}; numeric outline/cutout dimensions not yet transcribed')
            profile=row['profile'];wire=None;awg=None
            if profile=='small_screw': wire=(.75,1.5);awg='18-16'
            elif profile=='small_screw_v2_003': wire=(.75,2.5)
            elif profile in {'small_spring','large_spring'}: wire=(.14,2.5);awg='26-14'
            elif profile=='small_quick_in': wire=(.5,2.5);awg='20-14'
            elif profile=='large_screw': wire=(.75,2.5);awg='18-14'
            elif profile=='large_crimp': wire=(.14,4);awg='26-12'
            if wire:
                spec(pid,'wire_cross_section_min',technical,number=wire[0],unit='mm2')
                spec(pid,'wire_cross_section_max',technical,number=wire[1],unit='mm2')
            if awg: spec(pid,'wire_awg_range',technical,text=awg)
            if row['termination']=='screw':
                spec(pid,'tightening_test_torque',technical,number=.25 if small else .5,unit='Nm',
                     conditions={'variant_confirmation_required':True} if small and 'V2' in row['model'] else {})
            if row['termination']=='spring_quick_in':
                spec(pid,'stripping_length',technical,number=10,unit='mm',conditions={'tolerance_mm':.5})
            spec(pid,'contact_resistance_max',technical,number=3 if row['termination']=='spring_quick_in' else 1,unit='mOhm')
            if '/B' in row['model']: spec(pid,'wiring_variant',identity,text='/B stands for wiring with cable protecting; see printed page 00-09')
            if '(17-32)' in row['model']: spec(pid,'contact_numbering',identity,text='17-32; one 16-contact half, not a standalone 32-contact insert')
            housing='15-06 to 15-16.1' if small else '15-21 to 15-24' if '(17-32)' in row['model'] else '15-17 to 15-18.1' if row['count']==10 else '15-19 to 15-20'
            spec(pid,'housing_catalog_reference',identity,text=housing,
                 conditions={'configuration':'HA-032 arrangement'} if '(17-32)' in row['model'] else {})
        for row in data['coding']:
            first=row_ev(row['model'],row['order'],row['pages'][0],'coding')
            pid=product(row,'CODING','accessory',first);ids[row['model']]=pid
            for page in row['pages']: occurrence(pid,row['model'],row['order'],page,'coding')
            spec(pid,'standard_pack_quantity',first,number=row['pack'],unit='pcs')
            for model in row['suitable']:
                proof_page=74 if model.endswith('V2') else 75
                proof=ev('ha-coding-'+model,proof_page,[.07,.42,.95,.68],
                    row['model']+'; Suitable for '+('HA-003-M/F-V2' if model.endswith('V2') else 'HA-003-MQ/FQ' if '003' in model else 'HA-004-MQ/FQ'))
                conn.execute('''INSERT INTO product_relations(source_product_id,target_product_id,relation,conditions,evidence_id)
                    VALUES(%s,%s,'optional_accessory',%s,%s) ON CONFLICT DO NOTHING''',
                    (ids[model],pid,Jsonb({'purpose':'coding/pokayoke','not_automatically_required':True}),proof))
        for prefix in ['CESM','CESF','CEGM','CEGF']:
            for gauge in ['0.37','0.50','0.75','1.0','1.5','2.5','3.0','4.0']:
                model=prefix+'-'+gauge
                contact=conn.execute('SELECT * FROM products WHERE model=%s',(model,)).fetchone()
                if not contact: raise ImportConflict('Missing exact referenced contact '+model)
                for page in [76,77,78]: occurrence(contact['id'],model,contact['order_number'],page,'contact')
                wire_ev=ev('ha-contact-wire-table',76,[.68,.65,.95,.80],
                    'Contact wire gauge/AWG/identification and stripping length table; all listed stripping lengths 7.5mm; '
                    'when wire gauge is less than 0.75mm2, better to use auxiliary pin assembly tool TL15.')
                spec(contact['id'],'stripping_length',wire_ev,number=7.5,unit='mm')
                spec(contact['id'],'wire_awg_range',wire_ev,text={'0.37':'26-22','0.50':'20','0.75':'18','1.0':'18','1.5':'16','2.5':'14','3.0':'12','4.0':'12'}[gauge])
                spec(contact['id'],'identification_grooves',wire_ev,text={'0.37':'no groove','0.50':'no groove','0.75':'1 groove','1.0':'1 groove','1.5':'2 grooves','2.5':'3 grooves','3.0':'wide groove','4.0':'no groove'}[gauge])
                for row in data['inserts']:
                    if row['termination']=='crimp' and row['gender']==contact['gender']:
                        # Preserve existing pilot rows; new numbered halves carry the same explicit wire-gauge prerequisite.
                        old=conn.execute("SELECT id FROM product_relations WHERE source_product_id=%s AND target_product_id=%s AND relation='uses_contact'",
                            (ids[row['model']],contact['id'])).fetchone()
                        if not old:
                            conn.execute('''INSERT INTO product_relations(source_product_id,target_product_id,relation,conditions,evidence_id)
                                VALUES(%s,%s,'uses_contact',%s,%s)''',(ids[row['model']],contact['id'],Jsonb({'requires_wire_gauge_check':True}),row_ev(model,contact['order_number'],row['pages'][0],'contact')))
        for model in ['TL02G','TL01']:
            tool=conn.execute('SELECT * FROM products WHERE model=%s',(model,)).fetchone()
            for page in [76,77,78]: occurrence(tool['id'],model,tool['order_number'],page,'tool')
        for row in data['referenced_tools']:
            proof=ev('ha-referenced-tool-'+row['model'],row['page'],row['region'],row['model']+'; '+row['order']+'; '+row['application'])
            pid=product(row,'TOOLS','tool',proof)
            conn.execute('''INSERT INTO product_source_occurrences VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (f'ha-referenced-tool-2025:{row["page"]}:{row["order"]}',pid,proof,'ha-referenced-tool-2025','Referenced tool',row['model'],row['order']))
            spec(pid,'standard_pack_quantity',proof,number=1,unit='pcs')
            spec(pid,'tool_application',proof,text=row['application'])
        arrangement=ev('ha032-arrangement',78,[.06,.04,.95,.55],
            'HA-032; 250V 16A 32+PE; size 32A; ordering rows list HA-016 base and HA-016(17-32) halves. Technical page states 32(2x16)+PE.')
        for gender,base in [('male','M'),('female','F')]:
            for variant,suffix in [('screw',base),('screw_cable_protecting',base+'/B'),('crimp',base+'C')]:
                code=f'HA032-{gender}-{variant}'
                conn.execute('''INSERT INTO catalog_arrangements(code,label,description,evidence_id,declared_contact_count,housing_reference)
                    VALUES(%s,'HA-032',%s,%s,32,'size 32A; 15-21 to 15-24') ON CONFLICT DO NOTHING''',
                    (code,'One '+gender+' endpoint using two numbered 16-contact halves; not an independently orderable SKU or approved BOM',arrangement))
                for ending,position in [('', '1-16'),('(17-32)','17-32')]:
                    conn.execute('INSERT INTO catalog_arrangement_components VALUES(%s,%s,1,%s) ON CONFLICT DO NOTHING',
                        (code,ids['HA-016-'+suffix+ending],position))
        # Preserve previously checked page labels; stop on unexpected values instead of replacing them.
        for item in data['pages']:
            current=pages[item['page']]['printed_page']
            if current not in (None,item['printed']): raise ImportConflict('Printed page differs: '+str(item['page']))
            conn.execute('UPDATE pages SET printed_page=%s WHERE id=%s AND printed_page IS NULL',(item['printed'],pages[item['page']]['id']))
        result=coverage(conn,data)
        if result['chapter_ordering_rows_recorded']!=data['expected']['chapter_ordering_rows'] or result['chapter_unique_skus_present']!=data['expected']['chapter_unique_skus']:
            raise ImportConflict('Source row reconciliation failed')
        return result

def coverage(conn,data=None):
    data=data or manifest()
    rows=conn.execute('''SELECT o.*,p.model,p.review_status,pe.review_status AS identity_evidence_status,pg.global_page FROM product_source_occurrences o
        JOIN products p ON p.id=o.product_id JOIN evidence e ON e.id=o.evidence_id
        JOIN evidence pe ON pe.id=p.evidence_id
        JOIN pages pg ON pg.id=e.page_id WHERE o.source_scope=%s ORDER BY pg.global_page,p.model''',(CHAPTER,)).fetchall()
    expected={r['order'] for r in data['inserts']}
    actual={r['source_order_number'] for r in rows if r['source_order_number'] in expected}
    issues=[{**item,'detail_zh':ISSUE_ZH.get(item['code'],item['detail'])} for item in data['issues']]
    return {'scope':data['scope'],'ha_insert_skus_expected':len(expected),'ha_insert_skus_present':len(actual),
        'chapter_ordering_rows_expected':data['expected']['chapter_ordering_rows'],
        'chapter_ordering_rows_recorded':len(rows),'chapter_unique_skus_expected':data['expected']['chapter_unique_skus'],
        'chapter_unique_skus_present':len({r['product_id'] for r in rows}),
        'missing_insert_orders':sorted(expected-actual),'ha032_is_orderable_sku':False,
        'catalog_arrangements':conn.execute('SELECT count(*) AS n FROM catalog_arrangements').fetchone()['n'],
        'reviewed_chapter_product_identities':len({r['product_id'] for r in rows if r['review_status']=='reviewed' and r['identity_evidence_status']=='reviewed'}),
        'all_parameters_complete':False,'all_pairs_verified':False,'issues':issues}

def export(conn):
    data=manifest();report=coverage(conn,data)
    target=ROOT/'.local/exports';target.mkdir(parents=True,exist_ok=True)
    (target/'ha_coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    entries=conn.execute('''SELECT p.*,e.quotation,pg.global_page FROM products p JOIN product_families f ON f.id=p.family_id
        JOIN evidence e ON e.id=p.evidence_id JOIN pages pg ON pg.id=e.page_id WHERE f.code='HA' ORDER BY p.model''').fetchall()
    with (target/'ha_inserts.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=['model','order_number','gender','termination','contact_count','pe_contacts','housing_size','review_status','global_page'])
        writer.writeheader();writer.writerows({k:r[k] for k in writer.fieldnames} for r in entries)
    lines=['# HA 系列型号录入与缺项核对','',
        '范围：2025 英文目录文件第 72–79 页；这是本章节订货表的转录覆盖，不是全目录或工程批准。',
        '',f'- HA 芯体：{report["ha_insert_skus_present"]}/{report["ha_insert_skus_expected"]} 个独立订货号。',
        f'- 章节订货表：{report["chapter_ordering_rows_recorded"]}/{report["chapter_ordering_rows_expected"]} 行（跨页重复保留）。',
        f'- 章节内不同订货号：{report["chapter_unique_skus_present"]}/{report["chapter_unique_skus_expected"]}，包含 36 个芯体、32 个端子、2 个编码件和 2 个工具。',
        '- 另跟随原文引用转录 TL02、TL15 两个工具，来源为文件第 1399、1396 页。',
        '- 所有新增身份、参数及关系保持待审核；行数核对通过不能代替逐项审核。',
        '', '## 型号清单','',
        '| 型号 | 订货号 | 普通接点 / PE | 端接 | 本章节出现页（文件页） |',
        '| --- | --- | --- | --- | --- |']
    for row in data['inserts']:
        count='待确认' if row['count'] is None else str(row['count'])
        pe='待确认' if row['pe'] is None else str(row['pe'])
        lines.append(f'| {row["model"]} | {row["order"]} | {count} / {pe} | {row["termination"]} | {", ".join(map(str,row["pages"]))} |')
    lines.extend(['','## 关键处理','',
        '- HA-002 的普通接点及 PE 数不根据型号数字猜测，暂留空。',
        '- Quick-in 使用独立端接类型 `spring_quick_in`，其线径、剥线长度和接触电阻不套用普通弹簧参数。',
        '- 230V 导体对地、400V 导体对导体、替代标识及 UL 600V 分开保存，不合并成一个最大电压。',
        '- HA-032 保存为六个待核对的两半芯体编排（两种性别 × 三种端接变体），没有创建虚构 HA-032 产品或订货号。',
        '- 编码件仅保存原文明确声明的适用关系，且是可选附件，不擅自认定必须使用。',
        '- 相同端子和工具在多页重复出现时保留每页来源，但只创建一个产品。',
        '', '## 仍需核对',''])
    for issue in report['issues']: lines.append('- '+issue['code']+'：'+issue['detail_zh']+f'（来源文件第 {issue["page"]} 页）')
    lines.extend(['','数值尺寸轴向/安装状态、厂家批准、降额曲线数字化及真实完整搭配仍未确认，不宣称参数或选型全部完成。',''])
    (ROOT/'docs/ha-coverage.md').write_text('\n'.join(lines))
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['import','report','export']);args=parser.parse_args()
    with connect() as conn:
        if args.command=='import': initialize(conn);result=import_series(conn)
        elif args.command=='export': result=export(conn)
        else: result=coverage(conn)
        print(json.dumps(result,ensure_ascii=False,default=str))

if __name__=='__main__':main()
