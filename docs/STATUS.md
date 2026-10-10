# Local product status

Updated October 10, 2026. Version 1.0.0 is a release candidate pending current-commit integrated CI/browser confirmation.

## Implemented

- Dependency-free local Studio and CLI; source intake, offline annotation candidates, explicit acceptance, corrected interpretation editing and untranslated/omitted coverage.
- Exact source/tool/argument/dependency checks, dedicated integer lower bound, scoped Boolean hierarchy, tri-state activation and explicit exceptions.
- Bounded CNF search with checked deletion cores and scope-separated truth tables.
- Bounded prerequisite/effect workflow paths/graphs, unavailable tool actions, compliant refusal and explicit unknown outcomes.
- Hypothetical named-requirement repairs, contract/evidence diffs and replay ZIPs with inert generated source filenames.
- Optional fixed-endpoint OpenAI structured candidates, environment-only key, per-request source/cost opt-in and mandatory review. Live-provider integration remains unrun.
- Strict local API boundaries, origin/host guards, body/concurrency/compute limits, inert source processing, no telemetry or historical tool execution.
- Scientific model card, versioned independent-source corpus, provisional matched native-model pilot and separate extraction evidence.

## Local verification, latest working tree

- `python -m unittest discover -s tests -q`: **84 passed**.
- `python -m unittest evaluation.test_evaluation -q`: **7 passed**.
- `python -m evaluation.run verify`: **40 frozen files verified**.
- Compilation and `git diff --check`: passed.
- Wheel build/install outside the checkout: packaged Studio assets and real bulk analysis passed.
- Independent reviewer additionally checked seeded SAT and planner cases, API attacks and source/export boundaries. Review findings have dedicated regressions.

The first published CI snapshot passed all three Python-version/package jobs and the adversarial browser suite. Its happy-path browser suite exposed a test-only CSP wait issue; that test uses locator assertions now, without weakening the security policy. Current-commit browser rerun is still required. Local rendered Chromium is blocked by the execution environment; browser evidence comes from normal GitHub Actions runners, not a bypass.

Ruff is unavailable locally. Compilation, tests and whitespace checks are not represented as a Ruff pass.

## Canonical arithmetic

150 nodes need at least 30 calls; 151 need 32; 184 need 38. At budget 30 the advertised infeasible range is 151–200. Every pair of the 151-node constraints is satisfiable while their conjunction is not. Increasing the budget to 32/38/40 passes the lower-bound controls for 151/184/200 respectively. None is a completion guarantee.

## Evaluation limits

Consult `docs/EVALUATION.md` for exact case-level results and reference uncertainty. The pilot is selected development evidence with native-model labels, synthetic positive issues, human-ground-truth gaps and bounded checker coverage. It is not a superiority result. Offline extraction does not translate arbitrary English; optional-provider mocks do not validate live model quality.

The complete supplied handoff remains in `docs/HANDOFF.md`. Product release gates are in `docs/PRODUCT.md`; publication and current CI evidence are coordinated separately.
