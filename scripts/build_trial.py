"""Create one self-contained HTML trial using a sanitized current catalog projection."""
import json
from pathlib import Path
from wain.db import ROOT,connect
from wain.trial import snapshot

def build(data):
    base=ROOT/'wain/static/trial'
    html=(base/'index.html').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/trial/trial.css">','<style>'+(base/'trial.css').read_text()+'</style>')
    for name in ['core.js','trial.js']:
        script=(base/name).read_text().replace('</script','<\\/script')
        html=html.replace('<script src="/static/trial/'+name+'"></script>','<script>'+script+'</script>')
    payload=json.dumps(data,ensure_ascii=False,default=lambda v:float(v)).replace('<','\\u003c')
    html=html.replace('<script id="trialData" type="application/json">null</script>',
                      '<script id="trialData" type="application/json">'+payload+'</script>')
    html=html.replace('<title>', '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; connect-src \'none\'; base-uri \'none\'">\n<title>',1)
    return html

if __name__=='__main__':
    with connect() as conn:data=snapshot(conn)
    target=ROOT/'demo/index.html';target.parent.mkdir(exist_ok=True)
    target.write_text(build(data),encoding='utf-8')
    print(f'Built {target}: {len(data["products"])} projected sample products; no database files, credentials or PDFs')
