"""Read-only browser smoke test. Run with `uv run --with playwright --no-project python -m scripts.check_ui`."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

base=os.environ.get('WAIN_TEST_URL','http://127.0.0.1:8001')
out=Path('.local');out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('WAIN_CHROMIUM','/usr/bin/chromium'),
                              headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1500,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base)
    page.fill('#query','HA-010');page.click('#load')
    expect(page.locator('#queue button').first).to_contain_text('HA-010')
    page.locator('#queue button').first.click()
    expect(page.locator('#sourceImage')).to_be_visible()
    expect(page.locator('#sourceImage')).to_have_js_property('complete',True)
    assert page.locator('#sourceImage').evaluate('(e)=>e.naturalWidth')>0
    page.click('#approve');expect(page.locator('#message')).to_contain_text('审核人')
    page.screenshot(path=str(out/'review-ui.png'),full_page=True)
    page.click('#selectionTab')
    for name,value in [('wire_mm2','1'),('cable_diameter_mm','8'),('ambient_c','25')]:
        page.fill(f'[name="{name}"]',value)
    page.click('#selectionForm button[type="submit"]')
    expect(page.locator('#selectionResult h2')).to_have_text('方案待确认')
    assert page.locator('#selectionResult table tr').count()==6
    page.screenshot(path=str(out/'selection-ui.png'),full_page=True)
    page.fill('[name="current"]','17');page.click('#selectionForm button[type="submit"]')
    expect(page.locator('#selectionResult h2')).to_have_text('方案不符合条件')
    page.fill('[name="current"]','3');page.select_option('[name="termination"]','crimp')
    page.fill('[name="quantity"]','2');page.click('#selectionForm button[type="submit"]')
    expect(page.locator('#selectionResult h2')).to_have_text('方案待确认')
    expect(page.locator('#selectionResult table tr')).to_have_count(8)
    rows=page.locator('#selectionResult table tr').all_text_contents()
    assert any('公压接端子' in row and '20' in row for row in rows),rows
    assert any('母压接端子' in row and '20' in row for row in rows),rows
    page.locator('.engineering summary').click()
    page.fill('#assessmentActor','browser-validation-only')
    page.fill('#assessmentNote','Check that stale inputs cannot create an assessment')
    page.fill('[name="quantity"]','3')
    page.click('#createAssessment')
    expect(page.locator('#assessmentMessage')).to_contain_text('重新生成报告')
    page.fill('[name="quantity"]','2')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('()=>document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(out/'selection-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('Chromium passed: review search, source image, reviewer validation, normal/pending, overcurrent rejection, crimp counts, stale-scope guard, mobile layout; no business writes')
