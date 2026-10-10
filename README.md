# Prompt and Skill Linter

A local verification Studio and Python CLI for **reviewed instruction contracts**. It finds reproducible specification problems before agent execution. It does not score prompt quality, certify arbitrary-English interpretations, execute declared tool calls, or guarantee runtime compliance.

## Launch the local Studio

Python 3.10+, with no runtime dependencies or API key required:

```sh
python -m pip install --no-deps --no-build-isolation .
prompt-skill-linter serve
```

Open http://127.0.0.1:8765. Or launch directly from this checkout with `python -m prompt_skill_linter serve`.

The Studio provides source intake and reviewed extraction, source-linked diagnostics, finite-state workflow paths, scoped CNF truth tables, deletion-checked cores, explicit repair what-if, contract differences and replay ZIPs. Three built-in examples demonstrate bulk capacity, three-way rule composition and compliant refusal. The core Studio and analysis run locally. Model-assisted extraction is optional, off by default and not live-validated.

Offline extraction handles explicit annotation lines such as `REQUIRE approved=true` and `CLAUSE approved | !upload`. Other English remains visibly untranslated. An optional OpenAI structured-candidate adapter requires local environment configuration, explicit source/cost opt-in and mandatory review; only mocked integration tests have run. See [API and extraction modes](docs/API.md).

## Reproduce the CLI finding

```sh
python -m prompt_skill_linter examples/bulk.contract.json \
  --tools examples/tools.json --runtime examples/runtime.json
python -m unittest discover -s tests -v
python scripts/reproduce.py
```

Expected: `UNREACHABLE_COMPLETION` at **151 nodes (32 calls)** and **184 nodes (38 calls)** under a 30-call budget; 150 nodes passes the lower-bound check. The affected advertised range is 151–200. Exit status 1 is expected because findings exist. Increased-budget controls cover 151/32, 184/38 and 200/40.

**A lower-bound pass does not guarantee completion.** Retrieval, failures, retries and extra polls may require more calls. Controls explicitly replace the budget requirement.

For JSON and an inspectable contract:

```sh
python -m prompt_skill_linter examples/bulk.contract.json \
  --tools examples/tools.json --runtime examples/runtime.json \
  --format json --output /tmp/report.json --contract-out /tmp/reviewed-contract.json
```

Exit codes: 0 = no error-level findings in checked inputs (warnings/incomplete coverage may remain); 1 = error-level findings; 2 = malformed, unsupported or inaccessible input. No result certifies all source instructions.

## Inputs and outputs

- Prompt/skill source files are read through `sources[].path`, relative to the contract file. Every rule's line span and full quoted lines are checked byte-for-text after universal newline handling. Path traversal outside that directory is rejected.
- The author-reviewed JSON contract declares interpretations, priority, conditions, skills, scope, modality, exceptions, actions, assumptions and resources. The original source text is preserved separately; exact quote fidelity is not semantic fidelity.
- A tool manifest declares tool IDs, argument names, required arguments and informational capabilities.
- A runtime JSON file supplies request sizes, call budget and optional planning depth.
- Output includes the validated contract, classed diagnostics, witnesses, source spans, priorities, assumptions, explicit requirement-changing repair suggestions for resource findings, regression contexts and coverage limits.
- `--baseline previous-report.json` computes added/resolved diagnostic identities. This is a snapshot comparison, not a semantic equivalence proof; use JSON output to inspect its regression field.

See [contract semantics](docs/contracts.md), the machine-readable [schema](prompt_skill_linter/contract.schema.json), [complete user handoff](docs/HANDOFF.md), [research/evaluation protocol](docs/research.md), and [status report](docs/STATUS.md).

## Three diagnostic classes

| Class | Implemented scope | Meaning |
|---|---|---|
| Exact | Unknown declared tool/skill names; invalid/missing argument names; missing or inactive skill dependencies; synthetic bulk integer lower bounds | Exact relative to the supplied declarations; does not establish their faithful translation |
| Model-based | Same-scope Boolean obligations; explicit hierarchy and exceptions; shadowing; finite action reachability and declared fallback; bounded-search exhaustion | Conditional on the reviewed abstraction, contexts and stated search bounds |
| Semantic warning | Author-supplied uncertain-interpretation annotations | A review request, never an established contradiction |

Bulk constraints use exact integer arithmetic, not a pairwise shortcut: at n=151 each pair has a witness and the triple is infeasible. Minimal cores are only labeled minimal after checking removal of each included constraint. A 400-node test verifies the checker does not incorrectly insist all three are necessary in every case.

Hierarchy is resolved before Boolean conflicts. Permissions do not demand actions; preferences are nonbinding. Only explicitly enumerated coactive skills and contexts are analyzed. An unreachable advertised goal with a reachable, author-declared compliant refusal is `UNSUPPORTED_WORKFLOW`, not contradictory effective instructions. Unsupported semantics must be rejected or left for review.

## Evaluation status

The initial external seed contains five observations from three pinned repositories, including three executable hand-encoded cases. The expanded frozen pilot has 24 cases, including 8 natural cases from 5 independently maintained repositories; natural evidence remains separate from synthetic mutations and controls. Blind model review is recorded with uncertainty and an unresolved disagreement; these are **not human gold labels**. The OpenHands source remains ambiguous even though one manual abstraction collides. A CLI model error is a statement about that abstraction.

A provisional matched native-model pilot and separate extraction measurements are documented in [the evaluation report](docs/EVALUATION.md), with unresolved ambiguity and explicit coverage limits. Held-out human ground truth, live-provider accuracy, production usefulness and any superiority claim remain unavailable. No paid model calls, production updates or historical tool replays are performed.

## Intentional limits

No validated arbitrary-English extraction, general SMT solver, unconstrained temporal logic, arbitrary conditional expressions, retry/failure model, dynamic skill discovery, argument type checker, automatic policy repair, automatic specificity inference, or inferred fallback compliance. Explicit CNF and finite-state models are bounded and isolated by documented fragment guards. Dependency diagnostics currently point to JSON declarations rather than a source-prose span and explicitly disclose that provenance gap. Read `docs/contracts.md` before interpreting a result.

## Product and scientific documentation

[Acceptance gates](docs/PRODUCT.md) · [Architecture](docs/ARCHITECTURE.md) · [Model card and soundness envelope](docs/MODEL_CARD.md) · [Local API](docs/API.md) · [Release notes](CHANGELOG.md)

This repository is private. No open-source license has been selected. Version 1.0 passed [all four release CI jobs](https://github.com/blazickjp/prompt-skill-linter/actions/runs/38062286853), including three Python versions, installed-wheel assets and 17 headless-browser user journeys. See [the acceptance scope](docs/PRODUCT.md).
