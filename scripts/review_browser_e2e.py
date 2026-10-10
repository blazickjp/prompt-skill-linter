"""Independent adversarial Studio browser tests.

Run on an ordinary Playwright-enabled runner. No provider calls are made.
This is deliberately separate from the pure-Python unittest discovery suite.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
import threading
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prompt_skill_linter.server import StudioServer
from playwright.sync_api import sync_playwright, expect

ARTIFACTS = ROOT / 'artifacts' / 'browser-review'


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    server = StudioServer(('127.0.0.1', 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_address[1]}'
    results = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(15_000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept())

            def ready():
                page.goto(url)
                expect(page.locator('#run-status')).to_contain_text('2 error-level')
                expect(page.locator('#analyze-btn')).to_be_enabled()

            def run(name, check):
                try:
                    ready()
                    check()
                    assert not errors, f'Uncaught JavaScript errors: {errors}'
                    results.append({'name': name, 'status': 'passed'})
                    print('PASS', name, flush=True)
                except Exception:
                    page.screenshot(path=str(ARTIFACTS / (name + '-failure.png')), full_page=True)
                    results.append({'name': name, 'status': 'failed', 'traceback': traceback.format_exc()})
                    raise

            def pending_analysis_controls():
                pending = []
                page.route('**/api/analyze', lambda route: pending.append(route))
                original = page.locator('#source-editor').input_value()
                page.locator('#analyze-btn').click()
                expect(page.locator('#analyze-btn')).to_be_disabled()
                for selector in ('#source-editor', '#source-select', '#import-btn', '#import-file',
                                 '#new-btn', '#example-select', '#nodes-range', '#budget-range'):
                    expect(page.locator(selector)).to_be_disabled()
                assert pending, 'Analysis request was not held for concurrency check'
                pending.pop().continue_()
                expect(page.locator('#analyze-btn')).to_be_enabled()
                expect(page.locator('#source-editor')).to_have_value(original)
                expect(page.locator('#run-status')).to_contain_text('2 error-level')
                page.unroute('**/api/analyze')
            run('pending-analysis-locks-mutations', pending_analysis_controls)

            def invalid_import_atomic():
                original = page.locator('#source-editor').input_value() + '\nUnsaved reviewer note'
                page.locator('#source-editor').fill(original)
                title = page.locator('#project-name').inner_text()
                page.locator('#import-file').set_input_files({'name': 'invalid.json', 'mimeType': 'application/json',
                    'buffer': json.dumps({'contract': {}, 'sources': {'s': 'malformed'}, 'tools': {}, 'runtime': {}}).encode()})
                expect(page.locator('#notice')).to_contain_text('Import failed')
                expect(page.locator('#source-editor')).to_have_value(original)
                expect(page.locator('#project-name')).to_have_text(title)
                expect(page.locator('#dirty-state')).to_contain_text('Edited')
            run('invalid-import-preserves-workspace', invalid_import_atomic)

            def unsafe_integer_import_rejected():
                bundle = page.request.get(url + '/api/examples').json()['examples'][0]['bundle']
                bundle['runtime']['request_sizes'] = [10**18 + 1]
                bundle['runtime']['service_call_budget'] = 200_000_000_000_000_000
                original = page.locator('#source-editor').input_value()
                page.locator('#import-file').set_input_files({'name': 'unsafe-integers.json', 'mimeType': 'application/json',
                    'buffer': json.dumps(bundle).encode()})
                expect(page.locator('#notice')).to_contain_text(re.compile('safe integer|larger integer|precision', re.I))
                expect(page.locator('#source-editor')).to_have_value(original)
                expect(page.locator('#run-status')).to_contain_text('2 error-level')
            run('unsafe-integer-import-rejected', unsafe_integer_import_rejected)

            def inert_source_html():
                bundle = page.request.get(url + '/api/examples').json()['examples'][0]['bundle']
                sid = bundle['contract']['sources'][0]['id']
                payload = '<img id="source-pwned" src="x" onerror="window.sourcePwned=1"><script>window.sourcePwned=1</script>'
                text = bundle['sources'][sid].rstrip('\n') + '\n' + payload
                bundle['sources'][sid] = text
                line = len(text.splitlines())
                rule = {'id': 'untrusted_source', 'source': {'source_id': sid, 'start_line': line, 'end_line': line, 'quote': payload},
                        'priority': 0, 'kind': 'permission', 'scope': {'entity': 'task', 'temporal': 'run'},
                        'effect': {'literal': 'untrusted', 'value': True}}
                bundle['contract']['rules'].append(rule)
                page.locator('#import-file').set_input_files({'name': 'inert-source.json', 'mimeType': 'application/json', 'buffer': json.dumps(bundle).encode()})
                expect(page.locator('#project-name')).to_have_text('inert-source')
                expect(page.locator('#analyze-btn')).to_be_enabled()
                expect(page.locator('#run-status')).to_contain_text('2 error-level')
                assert page.evaluate('window.sourcePwned') is None
                assert page.locator('#source-pwned').count() == 0
                page.locator('[data-view="contract"]').click()
                expect(page.locator('#contract-rules')).to_contain_text(payload)
                assert page.locator('#source-pwned').count() == 0
            run('uploaded-html-remains-inert', inert_source_html)

            def error_and_recovery():
                page.route('**/api/analyze', lambda route: route.fulfill(status=503, content_type='application/json',
                    body=json.dumps({'error': {'message': 'Injected temporary backend failure'}})))
                page.locator('#analyze-btn').click()
                expect(page.locator('#notice')).to_contain_text('Injected temporary backend failure')
                expect(page.locator('#analyze-btn')).to_be_enabled()
                expect(page.locator('#source-editor')).to_be_enabled()
                page.unroute('**/api/analyze')
                page.locator('#analyze-btn').click()
                expect(page.locator('#notice')).to_be_hidden()
                expect(page.locator('#analyze-btn')).to_be_enabled()
                expect(page.locator('#run-status')).to_contain_text('2 error-level')
            run('backend-error-recovers', error_and_recovery)

            def excluded_prose_remains_incomplete():
                page.locator('#new-btn').click()
                page.locator('#intake-source').fill('REQUIRE complete = true\nYou must never complete this task.')
                page.locator('#extract-btn').click()
                expect(page.locator('#candidate-list [data-candidate]')).to_have_count(2)
                assert page.locator('#candidate-list [data-candidate]:checked').count() == 0
                page.locator('#candidate-list [data-candidate]').first.check()
                page.locator('#accept-btn').click()
                expect(page.locator('#intake-dialog')).not_to_be_visible()
                expect(page.locator('#run-status')).to_contain_text('Incomplete source coverage')
                expect(page.locator('#findings-list')).to_contain_text('Incomplete source coverage')
                with page.expect_download() as capture:
                    page.locator('#export-report-btn').click()
                path = ARTIFACTS / 'incomplete-report.json'
                capture.value.save_as(str(path))
                report = json.loads(path.read_text())
                assert report['analysis_status'] == 'incomplete'
                assert any(d['code'] == 'INCOMPLETE_SOURCE_COVERAGE' for d in report['diagnostics'])
            run('excluded-prose-stays-visible-after-export', excluded_prose_remains_incomplete)

            def stale_report_export_blocked():
                page.locator('#source-editor').fill(page.locator('#source-editor').input_value() + '\nChanged inputs')
                downloads = []
                page.on('download', lambda download: downloads.append(download))
                page.locator('#export-report-btn').click()
                expect(page.locator('#notice')).to_contain_text('earlier input snapshot')
                assert not downloads
            run('stale-report-export-blocked', stale_report_export_blocked)

            ready()
            page.screenshot(path=str(ARTIFACTS / 'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(ARTIFACTS / 'mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), 'Mobile page has horizontal overflow'
            results.append({'name': 'mobile-overflow', 'status': 'passed'})
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (ARTIFACTS / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
