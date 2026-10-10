# Constraint Studio frontend

A dependency-free, local-first interface for the Python linter. Start it from
repository root with `python -m prompt_skill_linter serve`; open the printed local
URL. Opening `index.html` directly is unsupported because analysis requires the
same-origin Python API.

## Workflow

- Edit source, normalized rules, tool manifest and runtime separately. Changes
  invalidate the displayed report until rerun; source quotes must stay faithful.
- Explore resource boundaries with node/budget sliders. The displayed arithmetic
  is a preview; Test scenario runs the checker. A budget change explicitly
  replaces that requirement.
- Inspect diagnostics, linked source spans, minimal-core deletion witnesses,
  assumptions, provenance limits and repair trade-offs.
- Pin a report baseline and compare input/evidence changes. Identity comparison
  is not a semantic equivalence claim.
- Start from text using offline annotation extraction. Nothing is accepted by
  default. Ordinary English remains untranslated. Configured remote extraction
  is separately labeled and requires explicit source-transmission/cost consent.
- Explore finite workflow states and blocked actions; search cutoff is unknown.
- Export editable JSON bundles, analysis JSON, readable reports or regression
  cases. Inputs are held in memory, not browser persistent storage.

## Safety and accessibility

All supplied content is rendered via textContent, not HTML. There is no dynamic
code evaluation, arbitrary tool execution, CDN, remote font or analytics. Remote
model access, if configured on the server, is opt-in per extraction request.
Source imports are bounded to 2 MiB. Controls use native labels, buttons and
forms; the layout supports mobile and reduced motion. Ctrl/Command+Enter runs;
Alt+1–4 changes views. Pending analysis disables input-changing controls.

## Tests

`node --check web/app.js` checks JavaScript syntax. Real-browser acceptance tests
are in `web/tests/test_ui.py`; they require the optional Playwright test package and a
working Chromium installation, but neither is a product runtime dependency:

```
python web/tests/test_ui.py --browser /usr/bin/chromium
```

This starts a disposable local server and exercises analysis, controls, repairs,
regressions, malformed JSON recovery, downloads, review-first extraction,
workflow exploration and responsive screenshots. Screenshots are generated under
`web/qa-artifacts/` only after a real browser run. A blocked browser launch is not
a test pass; inspect the test output.
