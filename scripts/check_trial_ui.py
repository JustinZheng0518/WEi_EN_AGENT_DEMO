"""Read-only online and portable trial browser acceptance; no review writes."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('WAIN_TEST_URL', 'http://127.0.0.1:8001')
out = Path('.local'); out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('WAIN_CHROMIUM', '/usr/bin/chromium'),
                                headless=True, args=['--no-sandbox'])
    # Managed Chromium blocks file:// by policy. Serve the exact portable artifact;
    # assert it makes no subsequent network requests rather than changing that policy.
    for mode, url in [('online', base), ('offline', base + '/demo')]:
        page = browser.new_page(viewport={'width': 1500, 'height': 1000}, accept_downloads=True)
        errors = []; network = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: network.append(request.url))
        page.goto(url)
        expect(page.locator('#modeLabel')).to_have_text('数据库已连接' if mode == 'online' else '离线数据快照')
        expect(page.locator('#emptyState')).to_be_visible()
        page.click('[data-example="normal"]'); page.click('#runButton')
        expect(page.locator('#resultBanner')).to_contain_text('仍需确认')
        expect(page.locator('.bom-item')).to_have_count(5)
        with page.expect_download() as download:
            page.click('#exportButton')
        exported = Path(download.value.path()).read_text(encoding='utf-8-sig')
        assert '待确认' in exported and 'false' in exported
        page.click('#sourcesTab')
        expect(page.locator('#sourcesView')).to_contain_text('文件第')
        if mode == 'online':
            assert page.locator('#sourcesView a').count() > 0
        else:
            assert page.locator('#sourcesView a').count() == 0
        page.click('#bomTab')
        page.screenshot(path=str(out / f'trial-{mode}-desktop.png'), full_page=True)
        page.fill('#current', '4')
        expect(page.locator('#staleMessage')).to_be_visible()
        expect(page.locator('#exportButton')).to_be_disabled()
        page.click('[data-example="overcurrent"]'); page.click('#runButton')
        expect(page.locator('#resultBanner')).to_contain_text('不符合')
        expect(page.locator('#checksView')).to_contain_text('17')
        page.click('[data-example="crimp"]'); page.click('#runButton')
        expect(page.locator('#resultBanner')).to_contain_text('仍需确认')
        expect(page.locator('.bom-item')).to_have_count(7)
        for role in ['公压接端子', '母压接端子']:
            expect(page.locator('.bom-item').filter(has_text=role).locator('.quantity')).to_contain_text('20')
        page.click('[data-example="missing"]'); page.click('#runButton')
        expect(page.locator('#resultBanner')).to_contain_text('仍需确认')
        expect(page.locator('#bomView')).to_contain_text('待选定')
        page.click('#checksTab'); expect(page.locator('#checksView')).to_contain_text('线')
        # Unsupported requests must not leave the previous BOM usable.
        page.fill('#contacts', '8'); page.click('#runButton')
        expect(page.locator('#emptyState')).to_contain_text('超出当前试验范围')
        expect(page.locator('#resultContent')).to_be_hidden()
        page.fill('#requestText', 'M12 8针 24V 3A 螺钉')
        page.click('#parseButton'); page.click('#runButton')
        expect(page.locator('#formMessage')).to_contain_text('本版仅支持')
        expect(page.locator('#resultContent')).to_be_hidden()
        page.fill('#requestText', '24V 3A 10针 螺钉')
        page.click('#parseButton'); page.click('#runButton')
        expect(page.locator('#formMessage')).to_contain_text('请先确认')
        page.check('#ambiguityConfirmed'); page.click('#runButton')
        expect(page.locator('#resultBanner')).to_contain_text('仍需确认')
        page.fill('#requestText', '<img src=x onerror=alert(1)> 24V')
        page.click('#runButton')
        expect(page.locator('#formMessage')).to_contain_text('描述已修改')
        assert page.locator('img[src="x"]').count() == 0
        page.click('[data-example="normal"]'); page.click('#runButton')
        expect(page.locator('#resultBanner')).to_contain_text('仍需确认')
        if mode == 'online':
            page.route('**/selection/ha010', lambda route: route.fulfill(
                status=503, content_type='application/json', body='{"detail":"测试服务不可用"}'))
            page.fill('#current', '4'); page.click('#runButton')
            expect(page.locator('#formMessage')).to_contain_text('测试服务不可用')
            expect(page.locator('#exportButton')).to_be_disabled()
            page.unroute('**/selection/ha010')
            page.click('#runButton')
            expect(page.locator('#staleMessage')).to_be_hidden()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('()=>document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(out / f'trial-{mode}-mobile.png'), full_page=True)
        page.click('#helpButton'); expect(page.locator('#helpDialog')).to_be_visible()
        page.click('#closeHelp')
        assert not errors, errors
        if mode == 'offline':
            assert network == [base + '/demo'], network
        page.close()
    browser.close()
print('Chromium passed online + self-contained HTML over HTTP (no secondary requests): normal/pending, CSV, sources, stale results, 17A rejection, crimp counts, missing inputs, unsupported scope, ambiguity, safe text, help, mobile; no business writes. file:// not tested: managed browser policy blocks it.')
