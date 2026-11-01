"""Generate reviewable project tracking files from one versioned progress source. No DB writes."""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/project_progress.json'
STATUS={'done':'已完成（限定验收范围）','in_progress':'进行中 / 部分完成','todo':'待做','blocked':'外部条件阻塞','ongoing':'持续维护'}
DATA_STATUS={'done_in_scope':'本章范围已登记','reviewed_in_scope':'限定范围已审核','approved_in_scope':'限定工况已批准',
             'partial':'部分完成','todo':'待做','not_applicable':'不适用'}

def validate(data,catalog):
    if data['release_stage'] not in {'development','pilot','production'}: raise ValueError('Invalid release stage')
    tasks=data['tasks'];ids={t['id'] for t in tasks};phases={p['id'] for p in data['phases']}
    if len(ids)!=len(tasks): raise ValueError('Duplicate task ID')
    for t in tasks:
        if t['id'].rsplit('-',1)[0] not in phases or t['status'] not in STATUS:
            raise ValueError('Invalid phase/status: '+t['id'])
        if not t.get('acceptance') or set(t.get('depends_on',[]))-ids:
            raise ValueError('Missing acceptance/unknown dependency: '+t['id'])
        if t['status']=='done' and not t.get('evidence'): raise ValueError('Completed task needs evidence: '+t['id'])
        if t['status']=='blocked' and not t.get('blocker'): raise ValueError('Blocked task needs a reason: '+t['id'])
        for evidence in t.get('evidence',[]):
            if not (ROOT/evidence).is_file(): raise ValueError('Evidence file missing: '+evidence)
    by_id={t['id']:t for t in tasks}
    def visit(task,stack):
        if task in stack: raise ValueError('Cyclic dependency: '+task)
        for dependency in by_id[task].get('depends_on',[]): visit(dependency,stack|{task})
    for task in ids: visit(task,set())
    if set(data['next_tasks'])-ids: raise ValueError('Unknown next task')
    if any(by_id[k]['status']=='done' for k in data['next_tasks']): raise ValueError('Next task is already complete')
    entries={s['code'] for s in catalog['sections']}
    if set(data['catalog_overrides'])-entries: raise ValueError('Unknown catalog tracking code')
    if len(entries)!=data['snapshot']['catalog_entries']: raise ValueError('Catalog entry count differs from snapshot')
    if len(catalog['groups'])!=data['snapshot']['catalog_groups']: raise ValueError('Catalog group count differs from snapshot')
    if sum(r['sku_entered'] for r in data['catalog_overrides'].values())!=data['snapshot']['products']:
        raise ValueError('Assigned sample counts do not reconcile with product snapshot')
    for code,row in data['catalog_overrides'].items():
        for field in ['identity','parameters','review','compatibility']:
            if row[field] not in DATA_STATUS: raise ValueError('Invalid catalog tracking status: '+code)
        if row.get('engineering','todo') not in DATA_STATUS: raise ValueError('Invalid engineering tracking status: '+code)
        if row.get('sku_total_in_scope') is not None and row['sku_entered']>row['sku_total_in_scope']:
            raise ValueError('Entered SKU count exceeds scoped denominator: '+code)

def cell(value): return str(value).replace('|','\\|').replace('\n','<br>')
def refs(task): return '、'.join(f'[{p}](../{p})' for p in task.get('evidence',[])) or '待补交付证据'

def roadmap(data):
    lines=['# 项目完整路线图','',f'状态更新：{data["updated_on"]}（{data["timezone"]}）。',
        '',data['goal'],'',
        '本文件由 `data/project_progress.json` 生成；修改进度源后运行 `python scripts/project_progress.py`。',
        '“已完成”只对应该任务写明的验收范围。软件测试、订货号转录、数据审核与真实硬件批准不能互相替代。',
        '不以任务勾选数计算全项目或全目录完成百分比。中文资料属于后续范围，当前先完成英文。',
        '', '## 状态和更新方式','',
        '- 已完成：有可检查的交付和验证证据，且满足本条验收条件。',
        '- 进行中：只完成了一部分；即使功能可演示，数据/工程审核未完成也保持部分状态。',
        '- 待做：尚未开展或尚无完成证据，不自动等同于外部阻塞。',
        '- 外部条件阻塞：必须写明具体缺少的资料、凭证或决策；继续其他独立工作。',
        '- 持续维护：每批更新都要执行，不用一次性勾选成永久完成。',
        '', '## 任务清单','']
    for phase in data['phases']:
        lines.extend(['### '+phase['name'],'',
            '| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |',
            '| --- | --- | --- | --- | --- | --- |'])
        for t in data['tasks']:
            if t['id'].rsplit('-',1)[0]!=phase['id']: continue
            acceptance=t['acceptance']+(' 阻塞：'+t['blocker'] if t.get('blocker') else '')
            title=t['title']+('（后续范围）' if t.get('scope')=='later' else '')
            lines.append('| '+' | '.join([t['id'],STATUS[t['status']],cell(title),cell(acceptance),', '.join(t.get('depends_on',[])) or '—',refs(t)])+' |')
        lines.append('')
    lines.extend(['## 全目录逐条记录','',
        '型号级范围还需跟踪 [73 条目录进度表](series-progress.csv)。其中系列、规格、附件、服务及参考条目不能混为同一种产品验收。',
        '除 HA 本章已建立 36 个芯体订货号基准外，多数类别尚不知道全部 SKU 数量，因此总数一栏保持NA。',
        '', '## 对外试点的最低条件','',
        '必须明确上线系列和工况范围，并满足 REVIEW-05、AGENT-07、APP-04、QA-04、QA-05 和 OPS-06 对应验收。',
        '不要求一次上线所有目录，但必须明确未覆盖的范围；不能把局部试验推广为整本目录可选型。',''])
    return '\n'.join(lines)

def current_status(data):
    s=data['snapshot'];tasks={t['id']:t for t in data['tasks']};counts=Counter(t['status'] for t in data['tasks'])
    metrics=[('原始 PDF',f'{s["pdf_files"]} 份 / {s["pdf_pages"]} 页'),('OCR',f'{s["ocr_pages"]} 页；不是已审核产品数据'),
        ('目录导航',f'{s["catalog_entries"]} 个条目 / {s["catalog_groups"]} 类'),
        ('自动候选',f'{s["ocr_candidate_occurrences"]} 条出现记录，含重复和识别疑点'),
        ('结构化产品',f'{s["products"]} 条；{s["pending_products"]} 条待审核，{s["approved_products"]} 条已批准'),
        ('参数 / 待审核关系',f'{s["specifications"]} 条 / {s["pending_relations"]} 条'),
        ('来源 / 目录编排',f'{s["source_occurrences"]} 条 / {s["catalog_arrangements"]} 个待核对编排'),
        ('HA 本章',f'{s["ha_insert_skus"]} 个芯体；含端子等 {s["ha_chapter_skus"]} 个不同订货号、{s["ha_ordering_rows"]} 行来源'),
        ('最近已记录 pytest 回归',f'{s["last_recorded_passing_tests"]} 项通过；执行范围和时间以快照依据及工作日志为准'),
        ('模型 API / 公开部署 / 真实批准 BOM',' / '.join('已完成限定范围' if s[key] else '未完成'
            for key in ['llm_connected','public_deployment','real_engineering_approved_bom']))]
    lines=['# 当前项目状态与下一步','',f'更新日期：{data["updated_on"]}（{data["timezone"]}）。',
        '',f'本批前源码基线提交：`{data["baseline_commit"][:7]}`。',data['snapshot_basis'],
        '', '## 当前事实','', '| 项目 | 状态 |','| --- | --- |']
    lines.extend('| '+cell(k)+' | '+cell(v)+' |' for k,v in metrics)
    stage={'development':'开发版本','pilot':'限定范围试点','production':'已记录验收范围的生产版本'}[data['release_stage']]
    scope_notice='全目录型号级建库已记录完成，具体审核范围仍须查看逐条清单。' if s['all_catalog_products_entered'] else '全目录型号级建库尚未完成。'
    approval_notice='已存在限定范围真实批准方案，不能自动推广到其他工况。' if s['real_engineering_approved_bom'] else '没有真实工程批准 BOM，不能宣称完整自动选型已验收。'
    lines.extend(['',f'当前阶段：{stage}。{scope_notice}{approval_notice}',
        '', '## 下一批优先任务',''])
    for key in data['next_tasks']:
        t=tasks[key];lines.append(f'- **{key}：{t["title"]}**。验收：{t["acceptance"]}')
    lines.extend(['','这些是工程依赖顺序，不代表销量排名。若后续收到常用型号或销售数据，应调整 BASE-03 和目录排期。',
        '', '## 已知缺口',''])
    lines.extend('- '+gap for gap in data['known_gaps'])
    lines.extend(['','## 计划状态计数（不是完成百分比）',''])
    lines.extend(f'- {STATUS[key]}：{counts[key]} 项。' for key in STATUS)
    lines.extend(['','## 每批工作怎样留进度','',
        '1. 开始前读取本页、[项目记忆](PROJECT_MEMORY.md)、[路线图](ROADMAP.md) 和相关工作日志，核对实际仓库/数据库状态。',
        '2. 更新 `data/project_progress.json` 中实际发生变化的任务、快照、下一步、缺口和目录覆盖；新增任务保留稳定 ID。',
        '3. 有证据才能标完成；录入或测试完成不能代替真实产品/工程批准。指标要取实际查询或可信快照，不能按预期编造。',
        '4. 运行 `python scripts/project_progress.py` 生成本页、路线图和逐条进度表；再运行 `python scripts/project_progress.py --check` 验证一致性。',
        '5. 在 `docs/worklog.md` 追加做了什么、验证结果、遗留缺口和相关提交。历史记录不改写为当前状态。',
        '6. 做与改动匹配的验证；完成后提交推送 GitHub，核对远程提交并告知用户。源码推送不依赖发布云环境。',
        '', '## 统一入口','',
        '- [完整路线图](ROADMAP.md)', '- [73 条目录进度表](series-progress.csv)',
        '- [历史工作日志](worklog.md)', '- [HA 型号及缺项](ha-coverage.md)',
        '- [总目录导航](catalog-map.md)', '- [项目记忆](PROJECT_MEMORY.md)',''])
    return '\n'.join(lines)

def series_csv(data,catalog):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
    writer.writerow(['条目代码','分类','目录条目','条目类型','目录来源文件页','印刷页码范围','已登记样板型号数','已知型号基准',
                     '型号清单','参数录入','资料审核','配对与附件','真实工程批准','下一事项/范围限制'])
    groups={g['code']:g['name_zh'] for g in catalog['groups']}
    for row in catalog['sections']:
        override=data['catalog_overrides'].get(row['code'],{})
        reference=row['kind']=='reference';service=row['kind']=='service_group'
        defaults={'identity':'not_applicable' if reference or service else 'todo','parameters':'not_applicable' if reference else 'todo',
                  'review':'todo','compatibility':'not_applicable' if reference or service else 'todo'}
        values={**defaults,**override}
        note=override.get('notes','先建立本章节型号/来源基准，再提取参数与配套并独立审核。')
        if reference:note='按参考资料验收，不按产品 SKU 计数。'+('P33 正文未定位，继续核实版本或补充资料。' if row['code']=='PART_NUMBER_INDEX' else '需逐页整理技术语义。')
        if service:note='按线束服务、装配和供料范围整理，不把说明页计作产品型号。'
        writer.writerow([row['code'],groups[row['group']],row['title_en'],row['kind'],row['source'],row['start']+'～'+row['end'],
            '不适用' if reference or service else override.get('sku_entered',0),
            '不适用' if reference or service else override.get('sku_total_in_scope','NA'),
            *[DATA_STATUS[values[k]] for k in ['identity','parameters','review','compatibility']],
            '不适用' if reference or service else '未批准' if values.get('engineering','todo')=='todo'
            else DATA_STATUS[values['engineering']],note])
    return '\ufeff'+stream.getvalue()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    data=json.loads(SOURCE.read_text());catalog=json.loads((ROOT/'data/catalog_sections.json').read_text())
    validate(data,catalog)
    outputs={'docs/ROADMAP.md':roadmap(data),'docs/STATUS.md':current_status(data),
             'docs/series-progress.csv':series_csv(data,catalog)}
    for filename,content in outputs.items():
        path=ROOT/filename
        if args.check:
            if not path.exists() or path.read_bytes()!=content.encode('utf-8'):
                raise SystemExit('Generated progress file is stale: '+filename)
        else:path.write_bytes(content.encode('utf-8'))
    print(('Checked' if args.check else 'Generated')+f': {len(data["tasks"])} tasks, {len(catalog["sections"])} catalog entries, 3 progress files; no application or database changes')

if __name__=='__main__':main()
