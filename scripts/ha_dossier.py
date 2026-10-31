"""Build the bounded HA catalog dossier without opening or changing a database."""
import argparse
import copy
import csv
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINATION = {'screw': '螺钉', 'crimp': '压接', 'spring': '普通弹簧', 'spring_quick_in': 'Quick-in'}


def load_data(root=ROOT):
    chapter = json.loads((root / 'data/ha_series.json').read_text())
    supplement = json.loads((root / 'data/ha_dossier_supplement.json').read_text())
    return chapter, supplement


def build(chapter, supplement):
    """Expand explicit catalog rows into pending dossiers, never compatibility approvals."""
    profiles = supplement['profiles']
    models = {}
    for row in chapter['inserts']:
        p = copy.deepcopy(row)
        small = row['model'].startswith(('HA-002', 'HA-003', 'HA-004'))
        p['parameters'] = copy.deepcopy(profiles[row['profile']])
        p['electrical'] = {
            'source_page': 73, 'standard': 'EN 61984', 'pollution_degree': 3,
            'rated_current_a': 10 if small else 16,
            'rated_voltage_v': None if small else 250,
            'conductor_ground_v': 230 if small else None,
            'conductor_conductor_v': 400 if small else None,
            'alternative_marking': '10A 250V 4kV 3' if small else '16A 250V/400V 4kV 2 (污染等级2)',
            'ul_voltage_v': 600, 'impulse_voltage_kv': 4,
            'condition': 'IEC电位关系、替代标识、污染等级2和UL额定分开；AC/DC及降额未批准',
        }
        p['material'] = {'insert': 'polycarbonate', 'contact': 'copper alloy', 'ul94': 'V0',
                         'limiting_temperature_c': [-40, 125], 'mating_cycles_min': 500,
                         'insulation_resistance_min_ohm': 10**10, 'source_page': 73}
        p['contact_resistance_max_mohm'] = 3 if row['termination'] == 'spring_quick_in' else 1
        p['optional_coding'] = [copy.deepcopy(c) for c in chapter['coding'] if row['model'] in c['suitable']]
        p['contact_candidates'] = [c['model'] for c in supplement['contacts']
                                   if row['termination'] == 'crimp' and c['gender'] == row['gender']]
        p['drawing_references'] = [
            {'page': page, 'region': [.68, .14, .95, .85 if page == 74 else .54],
             'row_label': row['model'], 'view': '目录该订货行对应视图；大规格含接线端观察的针位及裸芯体开孔',
             'all_numeric_dimensions_transcribed': False,
             'condition': '裸芯体开孔不是底座开孔；需逐视图核对，不从图中比例量取'}
            for page in row['pages']]
        p['open_issue_ids'] = [i['id'] for i in supplement['issues']
                               if not i['models'] or row['model'] in i['models']]
        p.update(review_status='pending', engineering_status='needs_confirmation')
        models[row['model']] = p

    routes = []
    shells = {s['size']: s for s in supplement['shell_candidates']}
    for definition in supplement['route_definitions']:
        route = copy.deepcopy(definition)
        endpoints = [models[m] for side in ('male_models', 'female_models') for m in route[side]]
        for side, gender in [('male_models', 'male'), ('female_models', 'female')]:
            if not route[side] or any(models[m]['gender'] != gender for m in route[side]):
                raise ValueError('Wrong endpoint gender: ' + route['id'])
        if len({p['termination'] for p in endpoints}) != 1 or len({p['profile'] for p in endpoints}) != 1:
            raise ValueError('Mixed termination/variant: ' + route['id'])
        male_count = None if any(models[m]['count'] is None for m in route['male_models']) else sum(models[m]['count'] for m in route['male_models'])
        female_count = None if any(models[m]['count'] is None for m in route['female_models']) else sum(models[m]['count'] for m in route['female_models'])
        if male_count != female_count:
            raise ValueError('Endpoint counts differ: ' + route['id'])
        route['ordinary_contacts_per_endpoint'] = male_count
        route['termination'] = endpoints[0]['termination']
        route['insert_components'] = [dict(model=p['model'], order=p['order'], quantity_per_connection=1,
                                            source_pages=p['pages']) for p in endpoints]
        route['shell_candidates'] = copy.deepcopy(shells[route['housing_size']])
        nominal_thread = route['shell_candidates']['hood']['thread_marking']
        route['gland_candidates'] = [g['model'] for g in supplement['gland_candidates']
                                     if g['thread'].split('x')[0] == nominal_thread]
        route['selected_gland'] = None
        route['crimp_contacts_per_gender'] = male_count if route['termination'] == 'crimp' else None
        route['crimp_rule'] = '仅普通接点全装时按每性别数量；不含PE；接触件型号须按线径/镀层选定' if route['termination'] == 'crimp' else '不另购压接接触件；PE及导线端头工艺另核对'
        route['tool_models'] = [t['model'] for t in supplement['tools']] if route['termination'] == 'crimp' else []
        route['pe_assembly_count_verified'] = None
        route['optional_coding'] = sorted({c['model'] for p in endpoints for c in p['optional_coding']})
        route['open_issue_ids'] = sorted({i for p in endpoints for i in p['open_issue_ids']})
        if len(route['male_models']) == 2:
            route['open_issue_ids'] = sorted(set(route['open_issue_ids']) | {'HA032-PE'})
        route['unselected_supply'] = ['外部线缆', '面板内导线', '设备端子', 'PE接地材料', '安装紧固件', '密封/接头随件', '按需求的保护盖/编码件']
        route.update(status='needs_confirmation', can_finalize=False,
                     grouping_basis='目录同变体订货行分组与规格引用；不是已审核配对关系',
                     public_selection_supported=route['id'] in {'HA010-SCREW', 'HA010-CRIMP', 'HA010-SPRING'})
        routes.append(route)

    result = dict(version=1, prepared_on=supplement['prepared_on'],
                  scope='2025英文目录HA本章72–79页的全部芯体及18种变体链路资料；标准金属侧进线到面板壳体候选；非全部壳体SKU或工程批准',
                  database_changed=False, all_parameters_complete=False, all_pairs_verified=False,
                  can_finalize=False, models=list(models.values()), routes=routes,
                  contacts=copy.deepcopy(supplement['contacts']), tools=copy.deepcopy(supplement['tools']),
                  coding=copy.deepcopy(chapter['coding']), shell_candidates=copy.deepcopy(supplement['shell_candidates']),
                  gland_candidates=copy.deepcopy(supplement['gland_candidates']),
                  issues=copy.deepcopy(supplement['issues']), sources=copy.deepcopy(supplement['sources']))
    validate(result, chapter)
    return result


def validate(data, chapter):
    models = {p['model']: p for p in data['models']}
    if len(models) != 36 or {p['order'] for p in models.values()} != {p['order'] for p in chapter['inserts']}:
        raise ValueError('HA identity coverage changed')
    if len(data['routes']) != 18 or len({r['id'] for r in data['routes']}) != 18:
        raise ValueError('Missing/duplicate route')
    covered = {p['model'] for r in data['routes'] for p in r['insert_components']}
    if covered != set(models):
        raise ValueError('Route coverage differs from identities')
    page_ids = {s['global_page'] for s in data['sources']}
    if len(page_ids) != len(data['sources']):
        raise ValueError('Duplicate source page')
    products = list(models.values()) + data['contacts'] + data['tools'] + data['coding'] + data['gland_candidates']
    products += [s[k] for s in data['shell_candidates'] for k in ('hood', 'housing')]
    for p in products:
        if not re.fullmatch(r'\d{13}', p['order']):
            raise ValueError('Bad order: ' + p['model'])
    issues = {i['id'] for i in data['issues']}
    if len(issues) != len(data['issues']) or any(i['status'] != 'open' for i in data['issues']):
        raise ValueError('Issue status changed without review')
    for model in data['models']:
        if not set(model['open_issue_ids']) <= issues:
            raise ValueError('Unknown model issue')
        if not set(model['pages']) <= page_ids:
            raise ValueError('Unknown model source')
        if model['parameters']['source_page'] not in page_ids or model['parameters']['stripping_source_page'] not in page_ids | {None}:
            raise ValueError('Unknown parameter source')
    for item in data['issues']:
        if not set(item['models']) <= set(models) or not set(item['source_pages']) <= page_ids:
            raise ValueError('Unknown issue model/source')
    for route in data['routes']:
        if route['can_finalize'] or route['status'] != 'needs_confirmation':
            raise ValueError('Dossier must not approve a route')
    if len(data['contacts']) != 32 or len({p['order'] for p in data['contacts']}) != 32:
        raise ValueError('Contact coverage differs')


def show(value):
    if value is None:
        return '待确认'
    if isinstance(value, list):
        return ' / '.join(map(str, value))
    return str(value)


def table(headers, rows):
    def safe(value):
        return show(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(safe(c) for c in row) + ' |' for row in rows])


def csv_text(headers, rows):
    stream = io.StringIO(newline='')
    w = csv.writer(stream, lineterminator='\n')
    w.writerow(headers)
    w.writerows(rows)
    return '\ufeff' + stream.getvalue()


def outputs(data):
    models = {p['model']: p for p in data['models']}
    model_rows = []
    for p in data['models']:
        e = p['electrical']; spec = p['parameters']
        model_rows.append([p['model'], p['order'], p['gender'], TERMINATION[p['termination']], p['count'], p['pe'],
                           p['housing'] or '仅32A组合内使用，半组自身规格未标', p['pack'],
                           e['rated_current_a'], e['rated_voltage_v'], e['conductor_ground_v'], e['conductor_conductor_v'],
                           e['alternative_marking'], e['ul_voltage_v'], e['impulse_voltage_kv'],
                           show(spec['wire_mm2']), spec['awg'], spec['torque_nm'], spec['stripping_mm'],
                           '±0.5' if p['termination'] == 'spring_quick_in' else '',
                           spec['stripping_source_page'], p['contact_resistance_max_mohm'],
                           show(p['pages']), show([c['model'] for c in p['optional_coding']]),
                           spec['notes'], show(p['open_issue_ids']), '待独立审核/工程确认'])
    route_rows = []
    for r in data['routes']:
        sh = r['shell_candidates']
        components = '; '.join(p['model'] + ':' + p['order'] + '×1' for p in r['insert_components'])
        route_rows.append([r['id'], r['ordinary_contacts_per_endpoint'], TERMINATION[r['termination']], components,
                           r['housing_size'], sh['hood']['model'], sh['hood']['order'], 1,
                           sh['housing']['model'], sh['housing']['order'], 1,
                           show(r['gland_candidates']), '未选定', r['crimp_contacts_per_gender'],
                           r['crimp_rule'], show(r['tool_models']), show(r['optional_coding']),
                           '待确认', show(r['open_issue_ids']), '待确认，不能放行'])
    accessory_rows = []
    for p in data['contacts']:
        accessory_rows.append(['另购压接接触件', p['model'], p['order'], show(p['wire_mm2']),
                               p['plating'], p['stripping_mm'], p['pack'], show(p['source_pages']),
                               '按普通接点全装数；不含PE；仅对应性别的压接芯体候选'])
    for p in data['tools']:
        accessory_rows.append(['工艺工具', p['model'], p['order'], '', '', '', 1, show(p['source_pages']), p['condition']])
    for p in data['coding']:
        accessory_rows.append(['可选编码件', p['model'], p['order'], '', '', '', p['pack'], show(p['pages']), '仅适用：' + show(p['suitable']) + '；数量未确认'])
    for p in data['gland_candidates']:
        accessory_rows.append(['电缆接头候选', p['model'], p['order'], show(p['cable_diameter_mm']) + ' mm外径',
                               '', '', p['pack'], p['source_page'],
                               f'{p["thread"]}；GL={p["thread_length_mm"]} mm；SW={p["wrench_sw_mm"]}；' + p['condition']])
    issue_rows = [[i['id'], i['title'], show(i['models']) if i['models'] else '全部型号/链路',
                   i['required_evidence'], show(i['source_pages']), '未解决'] for i in data['issues']]

    overview = ['# HA 全系列资料与链路总表', '',
        '范围：2025 英文目录 HA 本章（文件第 72–79 页）。本批查看 20 页原图，整理日期：' + data['prepared_on'] + '（America/Denver）。', '',
        '**36 个芯体订货号、18 种变体链路均已纳入资料包；所有型号、关系和总成仍待独立审核与工程确认。** 未把目录整理称为完整自动选型或真实硬件验收。', '',
        '## 交付入口', '',
        '- [36 个型号逐项资料卡](ha-series-models.md)：参数、来源、端接工艺、图纸定位、可选件及缺项。',
        '- [型号参数 CSV](ha-series-models.csv) · [18 条链路 CSV](ha-series-routes.csv) · [43 条附件/工具 CSV](ha-series-accessories.csv) · [问题清单 CSV](ha-series-issues.csv)。CSV 用 Excel 按文本导入，订货号保持文本。',
        '- [完整 JSON](../data/ha_series_dossier.json) · [可编辑补充转录](../data/ha_dossier_supplement.json)；不包含原 PDF、原图或凭证。', '',
        '## 范围和数量口径', '',
        '36 个芯体包括 6 个 (17-32) 编号半组。18 条链路是 15 种普通变体加 3 种 HA-032 组合，属于明确的资料分组，不是 18 个已批准搭配。', '',
        'HA-032 每套含 4 个芯体：公端 1–16 和 17–32 各一个，母端同样两个；不存在独立 HA-032 订货号。32 路压接全装时普通公、母接触件各 32 个，PE 另核实，不能简单把半组 PE 数相加作为总成定义。', '',
        '壳体仅整理四种规格的标准金属侧进线到面板候选，共 8 个订货号；未穷举塑料、EMC、耐腐蚀、高构型、顶进线、电缆对电缆等全部变体。电缆接头按 M20/M25 列 5 个候选，需实际外径和螺纹/密封依据才能选定。', '',
        '这份资料包不扩展原网页选型服务：网页仍限定 HA-010。未将新补充字段或壳体自动导入数据库，也没有新增已批准配对。', '',
        '## 参数与工艺中容易混淆的地方', '',
        '- HA-002/003/004：10 A；230 V 导体对地、400 V 导体对导体。替代标识及 UL 600 V 单独保留，不能统一取最大值。',
        '- HA-010/016：16 A、250 V、污染等级 3；污染等级 2 的 250/400 V 标识另列，实际工况及降额未批准。HA-032 组合页另标 250 V、16 A，但没有独立 HA-032 降额曲线。',
        '- 螺钉普通 HA-003：0.75–1.5 mm²、0.25 N·m；HA-003-V2 线径为 0.75–2.5 mm²，但 V2 扭矩/剥线需变体确认。HA-004-V2 线径保持未知。',
        '- 螺钉 HA-010/016：0.75–2.5 mm²、0.5 N·m；工艺页 00-09 给 HA-003/004 剥线 4.5 mm、HA-010/016/032 为 7.5 mm。通用表未单列 V2；不据此覆盖专用参数或批准 PE 紧固点。',
        '- 普通弹簧：0.14–2.5 mm²；HA 普通弹簧剥线仍未知。00-14 页列的是 HE/HVE 等，不能直接套其 7–9 mm。Quick-in 为 0.5–2.5 mm²、剥线 10±0.5 mm，独立记录。',
        '- 压接接触件：32 个订货号，分公母、银/金镀层、8 档线径；最小档 0.14–0.37 mm²，其余按明确规格，不把相邻规格插值为连续适用。剥线 7.5 mm。',
        '- 0.14–0.37 mm² 按 HA 页选 TL02；工具页明确 TL02G 不适合 16 A、0.37 mm² 接触件。小于 0.75 mm² 推荐 TL15 辅助装针；TL01 用于退针。工具不计入成品数量。',
        '- CODE-Q3 仅列于 HA-003-V2 和 HA-003 Quick-in；CODE-Q5 仅列于 HA-004 Quick-in。不把编码件认定为所有 HA 的必需件。',
        '- 芯体 −40～125 ℃不代表总成范围；接头静态 −40～100 ℃、动态 −20～80 ℃。接头 IP68（with O-sealing）不提升金属壳体总成为 IP68。', '',
        '## 四种壳体规格的候选主件', '',
        table(['规格', '侧进线外壳 / 订货号', '面板底座 / 订货号', '文件页', '入口标识'],
              [[s['size'], s['hood']['model'] + ' / ' + s['hood']['order'],
                s['housing']['model'] + ' / ' + s['housing']['order'],
                show([s['hood']['source_page'], s['housing']['source_page']]), s['hood']['thread_marking']]
               for s in data['shell_candidates']]), '',
        '“3A / 10A / 16A / 32A”在此为壳体规格代号，不是额定电流。每条链路外壳和面板底座候选各 1 个；芯体装配、锁扣与随件仍需核实。', '',
        '## 18 条链路逐项清单', '',
        '下列公母分组来自同变体订货行，暂不固定供电侧和安装性别；不得视为已审核 mates_with。压接接触件数量按一套、普通孔位全装计算，型号需另按线径与镀层选定。', '']
    for route in data['routes']:
        overview += ['### ' + route['id'], '',
                     '- 端接：' + TERMINATION[route['termination']] + '；每端普通接点：' + show(route['ordinary_contacts_per_endpoint']) + '；壳体规格：' + route['housing_size'] + '。',
                     '- 公端：' + '；'.join(m + '（' + models[m]['order'] + '）×1' for m in route['male_models']) + '。',
                     '- 母端：' + '；'.join(m + '（' + models[m]['order'] + '）×1' for m in route['female_models']) + '。',
                     '- 电缆接头候选：' + '、'.join(route['gland_candidates']) + '；尚未选定。',
                     '- ' + (f'普通公、母压接接触件各 {route["crimp_contacts_per_gender"]} 个，PE 另核实；候选工具 TL02/TL02G/TL01/TL15 按条件选用。' if route['termination'] == 'crimp' else route['crimp_rule'] + '。'),
                     '- 可选编码件：' + ('、'.join(route['optional_coding']) if route['optional_coding'] else '本章无此变体的明确编码件适用声明') + '。',
                     '- 待确认：' + '、'.join(route['open_issue_ids']) + '。', '']
    overview += ['## 未解事项与技术确认', '', table(['ID', '事项', '需要取得的依据', '文件页'],
                  [[i['id'], i['title'], i['required_evidence'], show(i['source_pages'])] for i in data['issues']]), '',
                 '所有链路还需确认实际电压、电流、同时载流、线径、外径、温度、用途、防护、公母安装方向、PE、紧固件、密封及随件范围。线缆/面板内导线/设备端子/保护盖等未选定项数量保持未知，不当作不需要。', '',
                 '向厂家或公司技术人员询问时，应带上链路 ID、全部候选订货号及真实工况，要求逐项提供配对、安装图、端接工艺、PE、降额与附件清单依据。本批未对外发送信息。', '',
                 '## 来源与复现', '',
                 table(['文件页', '印刷页', '来源分卷', '分卷内页'],
                       [[s['global_page'], s['printed_page'], s['pdf_file'], s['page_in_pdf']] for s in data['sources']]), '',
                 '本章 72/79 为封面及应用图，不作为新增订货号来源。JSON 保存各分卷 SHA-256；本批所有来源均查看原图，未以 OCR 单独批准事实。', '',
                 '生成：`python scripts/ha_dossier.py`；检查：`python scripts/ha_dossier.py --check`。修改既有资料后应重建并核对；数据审核和真实工程批准继续走审核流程。', '']

    cards = ['# HA 全部 36 个芯体资料卡', '', '[返回系列总表与18条链路](ha-series-dossier.md)。所有字段均为目录转录待审核，未批准实际搭配。', '']
    for p in data['models']:
        e = p['electrical']; spec = p['parameters']
        cards += ['## ' + p['model'], '',
                  table(['字段', '目录记录 / 待确认项'], [
                      ['订货号', p['order']], ['性别 / 端接', p['gender'] + ' / ' + TERMINATION[p['termination']]],
                      ['普通接点 / PE', show(p['count']) + ' / ' + show(p['pe'])],
                      ['壳体规格', p['housing'] or '仅作为HA-032编号半组使用，装配引用32A；不填造半组独立壳体规格'],
                      ['额定电流', str(e['rated_current_a']) + ' A，需降额'],
                      ['IEC电压', f'对地 {e["conductor_ground_v"]} V / 导体间 {e["conductor_conductor_v"]} V' if e['conductor_ground_v'] else str(e['rated_voltage_v']) + ' V；污染等级3'],
                      ['另列标识', e['alternative_marking'] + '；UL 600 V；冲击4 kV；不能混用为最大额定'],
                      ['线径 mm² / AWG', show(spec['wire_mm2']) + ' / ' + show(spec['awg'])],
                      ['螺钉扭矩 N·m', spec['torque_nm']],
                      ['剥线 mm', show(spec['stripping_mm']) + ('±0.5' if p['termination'] == 'spring_quick_in' else '')],
                      ['剥线来源文件页', spec['stripping_source_page']],
                      ['接触电阻上限 mΩ', p['contact_resistance_max_mohm']],
                      ['材料 / 温度', '聚碳酸酯；铜合金接触件；UL94 V0；芯体−40～125℃，非总成温度范围'],
                      ['绝缘 / 寿命', '绝缘电阻≥10¹⁰Ω；机械插拔寿命≥500次；实际环境/试验条件待核对'],
                      ['目录包装量', str(p['pack']) + ' pcs，不等于采购量'],
                      ['工艺备注', spec['notes']], ['身份/图纸文件页', show(p['pages'])],
                      ['参数来源', '73（01-02）；剥线来源另见上行'],
                      ['图纸核对', '按该订货行对应视图核对；坐标区域见JSON，尚未完成全部数值尺寸转录/工程审核'],
                      ['可选编码件', show([c['model'] + ' / ' + c['order'] for c in p['optional_coding']]) or '本章未声明'],
                      ['压接接触件候选', show(p['contact_candidates']) or '此款不另购压接接触件'],
                      ['未解事项', show(p['open_issue_ids'])], ['审核/批准', '待独立审核；没有实际工况工程批准']]), '']

    return {
        'data/ha_series_dossier.json': json.dumps(data, ensure_ascii=False, indent=2) + '\n',
        'docs/ha-series-dossier.md': '\n'.join(overview),
        'docs/ha-series-models.md': '\n'.join(cards),
        'docs/ha-series-models.csv': csv_text(['型号', '订货号（文本）', '性别', '端接', '普通接点', 'PE', '壳体规格/范围', '目录包装量',
            '额定电流A', '额定电压V（污染3）', '导体对地V', '导体间V', '另列标识', 'UL电压V', '冲击kV',
            '线径mm2', 'AWG', '扭矩Nm', '剥线mm', '剥线公差mm', '剥线文件页', '接触电阻上限mOhm',
            '身份文件页', '可选编码件', '工艺备注', '未解事项', '状态'], model_rows),
        'docs/ha-series-routes.csv': csv_text(['链路ID', '每端普通接点', '端接', '芯体清单（每套）', '壳体规格', '外壳候选', '外壳订货号', '外壳数量',
            '底座候选', '底座订货号', '底座数量', '电缆接头候选', '接头选择状态', '全装普通压接件每性别数量', '接触件规则',
            '工具（非成品）', '可选编码件', 'PE总成数量', '未解事项', '状态'], route_rows),
        'docs/ha-series-accessories.csv': csv_text(['类型', '型号', '订货号（文本）', '线径或外径范围', '镀层', '剥线mm', '目录包装量', '文件页', '用途与条件'], accessory_rows),
        'docs/ha-series-issues.csv': csv_text(['ID', '事项', '适用型号', '需要取得的依据', '文件页', '状态'], issue_rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = build(*load_data())
    for name, content in outputs(data).items():
        path = ROOT / name
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != content:
                raise SystemExit('Stale/missing dossier output: ' + name)
        else:
            path.write_text(content, encoding='utf-8')
    print(('Checked' if args.check else 'Generated') + ': 36 models, 18 routes, 43 accessory/tool rows, 12 open issue categories; no database changes or approvals')


if __name__ == '__main__':
    main()
