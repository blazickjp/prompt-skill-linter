# Prototype status

Verified locally on October 10, 2026, Python 3.12.14.

## Completed

- End-to-end source + reviewed contract + tool manifest + runtime CLI.
- Strict accepted-contract schema; exact quoted-line verification; inspectable contract export.
- Exact reference/argument/dependency checks and dedicated synthetic integer-resource checks.
- Conditional same-scope Boolean hierarchy, modality, exception and coactivation checks.
- Bounded deterministic workflow reachability with explicitly declared fallback handling.
- JSON/readable diagnostics with witness, provenance, interpretation, assumptions, responsible rules, regression context and resource repair suggestions that identify changed requirements.
- Four reproducible synthetic run configurations, with JSON and readable reports in `corpus/synthetic/`.
- External research corpus and evidence in `corpus/external/`, kept distinct from synthetic cases.
- Full supplied handoff retained in `docs/HANDOFF.md`.

## Verification

- `python -m unittest discover -s tests -v`: **39 passed**.
- `python scripts/reproduce.py`: all four run configurations matched expected results.
- `python -m compileall -q prompt_skill_linter tests scripts`: passed.
- Independent adversarial review checked hierarchy after shadowing, integer precision, conditional resource rejection, permission modality, advertisement activation and entity isolation. Reported no remaining blocker within documented scope.
- Independent wheel installation with `pip --no-deps --no-build-isolation --target ... .`: succeeded, packaged schema present, installed CLI ran outside the checkout and produced expected bulk finding exit status 1.
- Installed external `jsonschema` library independently validated the shipped JSON Schema and four contract fixtures. This is a development cross-check, not a runtime dependency.
- Ruff/pytest are not installed in the environment. No Ruff result is claimed; unittest supplies the test runner. Compilation is not style linting.

## Observed arithmetic

| Request | Budget | Lower bound | Result |
|---|---:|---:|---|
| 150 | 30 | 30 | Lower-bound pass |
| 151 | 30 | 32 | UNREACHABLE_COMPLETION |
| 184 | 30 | 38 | UNREACHABLE_COMPLETION |
| 151 | 32 | 32 | Lower-bound pass |
| 184 | 38 | 38 | Lower-bound pass |
| 200 | 40 | 40 | Lower-bound pass |

The advertised infeasible range under budget 30 is 151–200. At 151, each pair of the three constraints is satisfiable but the triple is not. Core removal witnesses are serialized. Nothing here guarantees completion at the passing boundary.

## Research and evaluation limits

Five pinned-source observations across three independently maintained repositories; three executable hand-encoded contracts. Separate blind model review and disagreements are recorded, not treated as human gold. The OpenHands natural source is ambiguous even though its particular abstraction contains a Boolean collision. Full-policy extraction and implied-exception reasoning remain unimplemented.

No matched strong-judge versus structured-evidence-judge versus mechanical-checker evaluation has run. No extraction precision/recall, independently adjudicated whole-pipeline false-positive/miss rates, diagnostic-usefulness score, realistic coverage estimate, model/API cost/latency comparison or superiority claim is available. The research protocol enumerates these remaining milestones. Synthetic/unit passing counts are implementation checks, not these missing evaluation metrics.

The prototype has no external credentials, paid model calls, tool execution, live updates or historical update-call replays. It uses no inaccessible historical artifacts as evidence. Remote creation/publication is coordinated separately by the parent task and is not established by this local status file.

Local repository initialized on branch `main` without creating an author identity, commit or remote push. `git diff --check` passed on the deliverable sources. The source archive omits Git metadata, caches, environment directories, package-build intermediates and credentials.
