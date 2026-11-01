"""Catalog navigation, separate from verified products and application recommendations."""
import argparse
import json
import re
from collections import defaultdict,Counter
from pathlib import Path
from .db import ROOT,connect,initialize

DATA=ROOT/'data/catalog_sections.json'
LABEL=re.compile(r'^P?(\d{2}[A-Z]?)-(\d{2,3}(?:\.\d+)*)$')
FOOTER=re.compile(r'(?<![A-Za-z0-9])P?(\d{2}[A-Z]?)-(\d{2,3}(?:\.\d+)*)(?![A-Za-z0-9])')

def label_parts(label):
    match=LABEL.fullmatch(label)
    if not match: raise ValueError('Invalid printed page label: '+str(label))
    return match[1],tuple(int(n) for n in match[2].split('.'))

def normalize(label):
    label_parts(label)
    return label.removeprefix('P')

def load_data(path=DATA):
    data=json.loads(Path(path).read_text())
    groups=data['groups'];rows=data['sections']
    codes={g['code'] for g in groups}
    if len(codes)!=len(groups) or len({r['code'] for r in rows})!=len(rows):
        raise ValueError('Duplicate catalog codes')
    seen_families=set()
    for row in rows:
        a,start=label_parts(row['start']);b,end=label_parts(row['end'])
        if a!=b or start>end or row['group'] not in codes or row['source'] not in (5,6,7):
            raise ValueError('Invalid catalog range or source: '+row['code'])
        if row['batch'] not in (1,2,3): raise ValueError('Invalid engineering batch')
        for family in row.get('families',[]):
            if family in seen_families: raise ValueError('Sample family assigned to multiple entries: '+family)
            seen_families.add(family)
    return data

def import_inventory(conn,path=DATA):
    data=load_data(path)
    pages={r['global_page']:r['id'] for r in conn.execute('SELECT id,global_page FROM pages WHERE global_page IN (5,6,7)').fetchall()}
    if set(pages)!={5,6,7}: raise ValueError('Import original contents pages 5–7 first')
    for group in data['groups']:
        conn.execute('''INSERT INTO catalog_groups(code,name_zh,purpose_zh) VALUES(%s,%s,%s)
            ON CONFLICT DO NOTHING''',(group['code'],group['name_zh'],group['purpose_zh']))
    for row in data['sections']:
        values={'code':row['code'],'group_code':row['group'],'kind':row['kind'],'title_en':row['title_en'],
                'summary_zh':row['summary_zh'],'printed_start':normalize(row['start']),'printed_end':normalize(row['end']),
                'source_page_id':pages[row['source']],'engineering_batch':row['batch'],'catalog_version':data['catalog_version']}
        old=conn.execute('SELECT * FROM catalog_sections WHERE code=%s',(row['code'],)).fetchone()
        if old and any(old[k]!=v for k,v in values.items()):
            raise ValueError('Existing catalog entry differs; review migration explicitly: '+row['code'])
        conn.execute('''INSERT INTO catalog_sections(code,group_code,kind,title_en,summary_zh,printed_start,printed_end,
            source_page_id,source_quote,engineering_batch,catalog_version)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (row['code'],row['group'],row['kind'],row['title_en'],row['summary_zh'],normalize(row['start']),normalize(row['end']),
             pages[row['source']],row['title_en']+'; '+row['start']+' ~ '+row['end'],row['batch'],data['catalog_version']))
        for family in row.get('families',[]):
            conn.execute('INSERT INTO catalog_family_links VALUES(%s,%s) ON CONFLICT DO NOTHING',(row['code'],family))
    return {'groups':len(data['groups']),'contents_entries':len(data['sections']),
            'notice':'Navigation only; no products or approvals created. Sales priority: NA.'}

def collect_labels(conn):
    allowed={label_parts(r['start'])[0] for r in load_data()['sections']}
    count=0;unavailable=[]
    for row in conn.execute('SELECT id,global_page,printed_page,ocr_artifact FROM pages ORDER BY global_page').fetchall():
        labels=set()
        if row['printed_page'] and LABEL.fullmatch(row['printed_page']):
            labels.add((normalize(row['printed_page']),'existing_page_label'))
        path=Path(row['ocr_artifact']) if row['ocr_artifact'] else None
        if path and path.is_file():
            artifact=json.loads(path.read_text())
            footer=' '.join(w['text'] for w in artifact['words'] if float(w['top'])/artifact['height']>.91)
            for chapter,page in FOOTER.findall(footer):
                if chapter in allowed: labels.add((chapter+'-'+page,'ocr_footer_candidate'))
        else: unavailable.append(row['global_page'])
        for label,method in labels:
            conn.execute('INSERT INTO catalog_page_labels VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(row['id'],label,method))
            count+=1
    return {'observed_labels':count,'missing_ocr_artifacts':unavailable,
            'notice':'Footer matches are navigation candidates, not audited page coverage. Existing labels are preserved.'}

def sections(conn,group=None,q=''):
    rows=conn.execute('''SELECT s.*,g.name_zh AS group_name,g.purpose_zh,p.global_page AS contents_global_page,
        (SELECT count(*) FROM products pr JOIN product_families f ON f.id=pr.family_id
         JOIN catalog_family_links l ON l.product_family_code=f.code WHERE l.section_code=s.code) AS sample_products,
        (SELECT count(*) FROM products pr JOIN product_families f ON f.id=pr.family_id
         JOIN catalog_family_links l ON l.product_family_code=f.code WHERE l.section_code=s.code
         AND pr.review_status='reviewed') AS reviewed_product_identities
        FROM catalog_sections s JOIN catalog_groups g ON g.code=s.group_code JOIN pages p ON p.id=s.source_page_id
        ORDER BY p.global_page,s.source_page_id,s.code''').fetchall()
    # Preserve contents order using the checked-in source order, not lexicographic chapter ordering.
    order={r['code']:i for i,r in enumerate(load_data()['sections'])}
    rows.sort(key=lambda r:order.get(r['code'],len(order)))
    observations=conn.execute('''SELECT l.*,p.global_page FROM catalog_page_labels l JOIN pages p ON p.id=l.page_id''').fetchall()
    by_label=defaultdict(set);existing=defaultdict(set)
    for item in observations:
        by_label[item['printed_label']].add(item['global_page'])
        if item['method']=='existing_page_label': existing[item['printed_label']].add(item['global_page'])
    result=[]
    for row in rows:
        chapter,low=label_parts(row['printed_start']);_,high=label_parts(row['printed_end'])
        matching=set()
        for label,global_pages in by_label.items():
            c,n=label_parts(label)
            if c==chapter and low<=n<=high: matching.update(global_pages)
        row['start_candidates']=sorted(existing.get(row['printed_start']) or by_label[row['printed_start']])
        row['end_candidates']=sorted(existing.get(row['printed_end']) or by_label[row['printed_end']])
        a=row['start_candidates'];b=row['end_candidates']
        row['location_status']='ambiguous' if len(a)>1 or len(b)>1 or (a and b and a[0]>b[0]) else 'anchors_found' if a and b else 'partial_anchors' if matching else 'unlocated'
        row['footer_matched_page_count']=len(matching)
        row['sample_status']='partial_sample' if row['sample_products'] else 'not_structured'
        row['sales_priority']='NA'
        row['engineering_batch_basis']='Dependency-first work suggestion; not sales importance or a customer requirement'
        if group and row['group_code']!=group: continue
        if q and q.casefold() not in (row['code']+' '+row['title_en']+' '+row['summary_zh']).casefold(): continue
        result.append(row)
    return result

def summary(conn):
    rows=sections(conn)
    total=conn.execute('SELECT count(*) AS n FROM products').fetchone()['n']
    assigned=conn.execute('''SELECT count(DISTINCT p.id) AS n FROM products p JOIN product_families f ON f.id=p.family_id
        JOIN catalog_family_links l ON l.product_family_code=f.code''').fetchone()['n']
    return {'contents_entries':len(rows),'groups':len({r['group_code'] for r in rows}),
            'contents_source_pages':[5,6,7],'entries_with_samples':sum(bool(r['sample_products']) for r in rows),
            'sample_products_assigned':assigned,'sample_products_unassigned':total-assigned,
            'location_counts':dict(Counter(r['location_status'] for r in rows)),
            'unlocated_entries':[r['code'] for r in rows if r['location_status']=='unlocated'],
            'sales_priority':'NA','all_products_entered':False,
            'notice':'Contents navigation and partial sample counts; no SKU denominator, completion percentage or verified compatibility is implied.'}

def export(conn):
    rows=sections(conn);report=summary(conn)
    target=ROOT/'.local/exports';target.mkdir(parents=True,exist_ok=True)
    (target/'catalog_inventory.json').write_text(json.dumps({'summary':report,'items':rows},ensure_ascii=False,indent=2,default=str))
    lines=['# 英文目录系列与类别导航','',
           '由 `python -m wain.catalog export` 生成。来源：2025 英文目录，文件第 5–7 页。',
           '','这里统计总目录的导航条目，包括系列、规格类别、接口、服务和参考内容，不等于产品型号数或全部内部子系列。',
           '用途说明是目录标题的中文解释，不是行业认证、兼容结论或型号级应用批准。',
           '','## 当前范围与缺口','',
           f'- 共 {report["contents_entries"]} 个总目录条目、{report["groups"]} 个导航分类。',
           f'- 当前 {report["sample_products_assigned"]} 条样板产品已关联到相应导航类别，仍只覆盖部分型号。',
           '- 页脚定位是 OCR 候选；锚点找到不代表中间每页或全部产品已核对。不会用统一页码偏移补造定位。',
           '- 总目录引用 P33-01～P33-40 零件编号索引，目前未定位到正文；已上传文件末尾为文件第 1423 页的 32-28 和第 1424 页封底。应进一步确认目录版本或补充资料。',
           '- 所有条目的业务重要性/销售优先级NA；总目录不能证明 HA 或其他系列是主销系列。',
           '','## 建议录入顺序（工程依赖，不代表销量）','',
           '1. 先完善现有 HA 样板及共用端子、外壳、附件、工具/进线接头，形成可复用的数据规范。',
           '2. 再处理 HE、HD/HDD 等基础芯体条目，同时建立圆形接口技术词汇；这是实施建议，须按后续业务需求调整。',
           '3. 其他系列按实际客户需求排期；HM 内部模块、圆形编码、特殊产品均需进一步拆分和逐型号核对。',
           '','## 按总目录分类列出','']
    for code in dict.fromkeys(r['group_code'] for r in rows):
        entries=[r for r in rows if r['group_code']==code]
        lines.extend(['### '+entries[0]['group_name'],'',entries[0]['purpose_zh'],'',
            '| 条目 | 特点/用途说明 | 印刷页码范围 | 目录来源（文件页） | 样板产品数 | 页码定位 |',
            '| --- | --- | --- | --- | ---: | --- |'])
        labels={'anchors_found':'两端锚点已匹配，仍是定位候选','partial_anchors':'部分页脚匹配，待核对','unlocated':'未定位','ambiguous':'定位冲突，待核对'}
        for r in entries:
            lines.append(f'| {r["title_en"]} | {r["summary_zh"]} | {r["printed_start"]}～{r["printed_end"]} | {r["contents_global_page"]} | {r["sample_products"]} | {labels[r["location_status"]]} |')
        lines.append('')
    lines.extend(['## 数量解释','',
        '“样板产品数”按明确的产品家族映射统计；一个型号不会因多页重复出现而增加。0 表示该条目尚无已关联结构化样板，不代表目录没有产品。',
        '存在少量样板也不等于系列已录全。型号总数尚未核清，因此不计算完成百分比。产品身份已审核也不等于所有参数和适配关系已审核。',''])
    (ROOT/'docs/catalog-map.md').write_text('\n'.join(lines))
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['import','labels','export','summary']);args=parser.parse_args()
    with connect() as conn:
        if args.command=='import': initialize(conn);result=import_inventory(conn)
        elif args.command=='labels': result=collect_labels(conn)
        elif args.command=='export': result=export(conn)
        else: result=summary(conn)
        print(json.dumps(result,ensure_ascii=False,default=str))

if __name__=='__main__':main()
