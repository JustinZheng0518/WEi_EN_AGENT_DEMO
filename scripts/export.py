"""Export reviewable rows and API schemas; never export credentials."""
import csv
import json
import base64
from html import escape
import pymupdf as fitz
from pathlib import Path
from wain.api import app
from wain.db import ROOT,connect
from wain.service import stats

folder=ROOT/'.local/exports'
folder.mkdir(parents=True,exist_ok=True)

def csv_value(value):
    if isinstance(value,(dict,list)):
        value=json.dumps(value,ensure_ascii=False)
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'"+value
    return value

with connect() as conn:
    for table in ['documents','pages','products','product_specifications','evidence','product_relations','product_candidates','assembly_assessments','review_events','product_source_occurrences','catalog_arrangements','catalog_arrangement_components']:
        ordering={'product_source_occurrences':'source_key','catalog_arrangements':'code',
                  'catalog_arrangement_components':'arrangement_code,product_id'}.get(table,'id')
        rows=conn.execute(f'SELECT * FROM {table} ORDER BY {ordering}').fetchall()
        if rows:
            with (folder/f'{table}.csv').open('w',newline='',encoding='utf-8-sig') as stream:
                writer=csv.DictWriter(stream,fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows({k:csv_value(v) for k,v in row.items()} for row in rows)
    summary=stats(conn)
    (folder/'stats.json').write_text(json.dumps(summary,indent=2))
    audit=conn.execute('''SELECT count(*) AS pilot_rows,
        count(*) FILTER(WHERE EXISTS(SELECT 1 FROM product_candidates c
            WHERE c.page_id=e.page_id AND c.order_number_candidate=p.order_number)) AS order_found,
        count(*) FILTER(WHERE EXISTS(SELECT 1 FROM product_candidates c WHERE c.page_id=e.page_id
            AND c.order_number_candidate=p.order_number AND c.model_candidate=p.model)) AS model_and_order_found
        FROM products p JOIN evidence e ON e.id=p.evidence_id''').fetchone()
    (folder/'pilot_ocr_audit.json').write_text(json.dumps(audit,indent=2))
    pilot=conn.execute('''SELECT p.model,p.order_number,p.category,p.contact_count,p.pe_contacts,p.termination,
        p.review_status,pg.global_page,pg.printed_page FROM products p JOIN evidence e ON e.id=p.evidence_id
        JOIN pages pg ON pg.id=e.page_id ORDER BY p.category,p.model''').fetchall()
    headers=list(pilot[0]) if pilot else []
    table='<tr>'+''.join('<th>'+escape(k)+'</th>' for k in headers)+'</tr>'
    for row in pilot:
        table+='<tr>'+''.join('<td>'+escape(str(v) if v is not None else '未知')+'</td>' for v in row.values())+'</tr>'
    sources=''
    for source in conn.execute('''SELECT p.global_page,p.local_page,p.printed_page,d.source_path
        FROM pages p JOIN documents d ON d.id=p.document_id WHERE p.global_page IN (73,76,77)
        ORDER BY p.global_page''').fetchall():
        with fitz.open(source['source_path']) as pdf:
            png=pdf[source['local_page']-1].get_pixmap(dpi=140).tobytes('png')
        sources+=f'<h3>文件页序 {source["global_page"]} / 印刷编号 {escape(source["printed_page"])}</h3>'
        sources+='<img style="max-width:100%;width:1000px" alt="产品目录原文" src="data:image/png;base64,'+base64.b64encode(png).decode()+'">'
    report='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>WAIN 数据库检查报告</title>
    <style>body{font:16px system-ui;margin:36px;line-height:1.6;color:#172b4d}table{border-collapse:collapse;font-size:13px}
    td,th{padding:8px;border:1px solid #ddd}th{background:#eef5fa}pre{background:#f5f7fa;padding:16px}</style>
    <h1>WAIN 英文目录数据库</h1><p>文件索引覆盖 1424 页。下列产品为样板转录数据，全部待独立审核。
    OCR 候选是来源行的出现次数，不能当作不同型号的数量。当前尚不能输出已验证的完整 BOM。</p>
    <h2>数据库统计</h2><pre>'''+escape(json.dumps(summary,ensure_ascii=False,indent=2))+'''</pre>
    <h2>样板产品</h2><p>global_page 为整本文件页序，printed_page 为原文印刷编号；两者不能互换。</p><table>'''+table+'''</table>
    <h2>样板 OCR 对照</h2><p>对照基准为本次视觉转录，不是独立专家审核；该结果不能代表全目录准确率。</p><pre>'''+escape(json.dumps(audit,indent=2))+'''</pre>
    <h2>原文页面</h2>'''+sources+'''<h2>下一步</h2><p>核验型号与订货号；审核额定参数及降额条件；补齐外壳、进线附件、配对证据，
    继续完成真实组合的工程审核。当前已提供资料审核和 HA-010 候选 BOM 检查，实际组合仍待确认，尚未接入大模型。</p></html>'''
    (folder/'report.html').write_text(report,encoding='utf-8')
(folder/'openapi.json').write_text(json.dumps(app.openapi(),indent=2))
print(folder)
