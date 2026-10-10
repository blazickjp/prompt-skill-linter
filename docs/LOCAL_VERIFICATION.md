# Local verification: 1.2.0.dev0

Date: 2026-10-10. Status: **LOCAL-TESTED / REMOTE-CI-PENDING**.

This development build has not been published or run in remote CI. Local tests
passed within the reviewed finite-model scope. Browser acceptance is blocked
before launch, so no browser-pass or visual-validation claim is made.

## Passed checks

- **214 core unit/integration tests**, preserving the prior 161 tests and adding
  53 field-presence, coverage, corpus and provenance regressions.
- **7 legacy evaluation tests**; historical pilot freeze verifies 40 files and
  scientific-workflow freeze verifies 64 files / 13 cases.
- **16 separately frozen new cases**, with 23 verified source/license/input files:
  one natural conditional candidate, one real field-presence control, 14
  synthetic controls. They are implementation examples, not a benchmark.
- Existing **1,000-case independent trace oracle**, explicit-link structural test,
  byte compilation, JavaScript syntax and focused state-unit tests.
- Independent review: **40,800 concrete field/adapter cases**, **82,944 trace,
  bound and prohibition combinations**, **25 integration tests**, **6 CLI cases**,
  ten manual-premise mutations and a combined-scope control. Every original
  safety-result field matched the frozen checker on those trace comparisons.
- Source/wheel isolation: installed `1.2.0.dev0` wheel imported outside the checkout;
  static Studio assets, legacy built-in example, manual/helper fields, source
  jump metadata and safe-plus-neutral trigger coverage all passed smoke checks.
- All **237 frozen original source hashes** remain unchanged. Existing corpus,
  pilot and historical result files remain byte-identical in the successor.
  Legacy synthetic regeneration was run in a temporary copy to preserve them.

Independent review found and corrected: an unknown skill silently disabling a
field edge; mixed exact/uncertain demands hiding incomplete coverage; synthetic
open/optional producers retaining contradictory natural assumptions; and wording
that overstated adapter overwrite detection for open records. Regression tests
cover each case. No unresolved extension semantic/provenance blocker remained.

## Commands

From this source tree, the principal repeatable commands are:

```sh
python -m unittest discover -s tests -v
python -m unittest evaluation.test_evaluation -v
python -m evaluation.run verify
python -m evaluation.scientific_workflows verify
python -m evaluation.scientific_workflows mechanical --output /tmp/scientific-workflows.json
python -m evaluation.research_extensions verify
python -m evaluation.research_extensions reproduce --output /tmp/research-extensions.json
python scripts/review_trace_oracle.py
python corpus/scientific_workflows/structural/test_scan_explicit_links.py
python -m compileall -q prompt_skill_linter tests scripts evaluation
node web/tests/test_state.js
find web -name '*.js' -print0 | xargs -0 -n1 node --check
python -m pip wheel --no-deps --no-build-isolation . --wheel-dir /tmp/linter-wheel
python -m pip install --no-deps --target /tmp/linter-installed /tmp/linter-wheel/*.whl
```

The wheel smoke must import from the installed target while outside this
checkout. `scripts/reproduce.py` also passed on a temporary copy; by design it
regenerates synthetic report files, so run it in a disposable checkout if retaining
historical report bytes is important.

## Blocked and pending

`python web/tests/test_ui.py --browser /usr/bin/chromium` could not start Chromium:
its required process-singleton `socket()` returned `Operation not permitted`.
One approved out-of-process-sandbox retry had the same environment limitation.
No browser test case ran. Two new browser cases are included for manual/helper
field imports and neutral unreachable-trigger diagnostics; they require a normal
browser-capable environment. Focused JavaScript tests are not equivalent to this
browser suite.

The remote Python-version matrix and browser jobs are pending. Live model
provider behavior, task execution, deployed outcomes, precision/recall on a
held-out natural corpus, and behavioral repair benefit were not measured.

`DEVELOPMENT_VERIFICATION.json` records command status and key artifact hashes.
`DEVELOPMENT_FREEZE.json` hashes portable source files while excluding itself,
caches, builds, installed packages, browser artifacts and generated outputs.
No unverified-license review-text dataset or external study script is included.
