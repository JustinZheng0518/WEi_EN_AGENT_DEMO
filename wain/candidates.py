"""Conservative staging extraction; these are not verified product records."""
import hashlib
import re
from .db import connect

ORDER=re.compile(r'(?<![\d.])(\d{3})\s*(\d{3})\s*(\d{3})\s*(\d{4})(?!\d)')
MODEL=re.compile(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:[-/][A-Za-z0-9.()]+)+)')

def parse_line(line):
    previous_end=0
    for match in ORDER.finditer(line):
        prefix=line[previous_end:match.start()]
        possible=MODEL.findall(prefix)
        model=possible[-1] if possible else None
        yield {'model_candidate':model,'order_number_candidate':''.join(match.groups()),'source_line':line}
        previous_end=match.end()


def extract(conn):
    inserted=0
    for page in conn.execute("SELECT id,ocr_text FROM pages WHERE ocr_status='done' ORDER BY global_page").fetchall():
        for line in page['ocr_text'].splitlines():
            digest=hashlib.sha256(line.encode()).hexdigest()
            for candidate in parse_line(line):
                result=conn.execute('''INSERT INTO product_candidates(page_id,line_hash,model_candidate,
                    order_number_candidate,source_line,extractor_version) VALUES(%s,%s,%s,%s,%s,'line-order-v1')
                    ON CONFLICT DO NOTHING RETURNING id''',
                    (page['id'],digest,candidate['model_candidate'],candidate['order_number_candidate'],line)).fetchone()
                inserted+=bool(result)
    return {'new_candidates':inserted,'review_status':'pending'}

if __name__=='__main__':
    import json
    with connect() as conn: print(json.dumps(extract(conn)))
