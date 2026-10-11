# Prompt and Skill Linter

A local verification Studio and Python CLI for **reviewed instruction contracts**. It finds reproducible specification problems before agent execution. It does not score prompt quality, certify arbitrary-English interpretations, execute declared tool calls, or guarantee runtime compliance.

This **1.2.0.dev0 local research build** adds separate trace-trigger coverage and
reviewed flat-record field-presence checks. It is an unpublished successor to
the frozen v1.1 work; historical evaluation artifacts are unchanged. Read the
[research extension scope and evidence](docs/RESEARCH_EXTENSIONS.md) and
[research decisions](docs/RESEARCH_AGENDA.md). No perplexity score or behavioral
robustness heuristic is enabled.

## Launch the local Studio

Python 3.10+, with no runtime dependencies or API key required:

```sh
python -m pip install --no-deps --no-build-isolation .
prompt-skill-linter serve
```

Open http://127.0.0.1:8765. Or launch directly from this checkout with `python -m prompt_skill_linter serve`.

The Studio provides source intake and reviewed extraction, source-linked diagnostics, finite-state workflow paths, scoped CNF truth tables, deletion-checked cores, explicit repair what-if, contract differences and replay ZIPs. Three built-in examples demonstrate bulk capacity, three-way rule composition and compliant refusal. The core Studio and analysis run locally. Model-assisted extraction is optional, off by default and not live-validated.

Offline extraction handles explicit annotation lines such as `REQUIRE approved=true` and `CLAUSE approved | !upload`. Other English remains visibly untranslated. An optional OpenAI structured-candidate adapter requires local environment configuration, explicit source/cost opt-in and mandatory review; only mocked integration tests have run. See [API and extraction modes](docs/API.md).

### Use an existing coding assistant

Version 1.1 adds an optional local MCP bridge: `python -m prompt_skill_linter.mcp_server`.
Your existing host model can propose source-grounded contracts, show the mapping
and omissions for review, then invoke the deterministic checker. No separate API
key or provider call is required by this bridge; normal host usage terms still
apply. Setup is explicit, with no automatic client configuration. See the
[host setup and review workflow](docs/agent-host.md).

Explicit action-trace assertions also check per-run invocation caps and current
verification after edits, independently of the workflow's own state flags. They
return a shortest unsafe trace, exhaustive finite safety, or UNKNOWN. An unsafe
allowed path does not make a safe completion impossible. See [trace semantics](docs/contracts.md).

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

The [13-case scientific-workflow evaluation](corpus/scientific_workflows/README.md)
adds three real documented workflow families, two independent native review arms,
source-pinned extraction audit, and explicit deployment controls. It found two
defects in model-authored transition abstractions, corrected them, and added
post-audit trace regressions. Both native arms answered 9/13 cases; the conservative
checker answered 4/13 and kept unsupported-source warnings. No upstream source
contradiction or advantage over model review was established.

## Cross-provider strict mode validation (prototype)

Tool argument schemas can be checked for compatibility with OpenAI Structured Outputs and Anthropic strict tool use. All checks run offline using rules grounded in official provider documentation; no API calls are made.

```sh
python3 -m prompt_skill_linter examples/bulk.contract.json \
  --tools examples/tools_with_schema.json --runtime examples/runtime.json \
  --strict-mode openai,anthropic --format json
```

Use `--strict-mode all` to check all providers, or specify a comma-separated list like `openai,anthropic`. Omit the flag to skip strict mode checks.

The checker flags schemas that won't be accepted or enforced under each provider's strict mode, and warns when providers diverge. For example, OpenAI rejects `oneOf` and requires all properties to be in the `required` array, while Anthropic rejects `minimum`/`maximum` and recursive schemas. Each diagnostic points to the schema path and suggests a fix.

### Worked example

Input manifest (`examples/tools_with_schema.json`):

```json
{
  "tools": {
    "get_weather": {
      "arguments": ["location", "units"],
      "required": ["location"],
      "schema": {
        "type": "object",
        "properties": {
          "location": {"type": "string", "minLength": 1},
          "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
        },
        "required": ["location"],
        "additionalProperties": false
      }
    }
  }
}
```

Command:

```sh
python3 -m prompt_skill_linter examples/bulk.contract.json \
  --tools examples/tools_with_schema.json --runtime examples/runtime.json \
  --strict-mode all
```

Output excerpt:

```
[exact/error] STRICT_MODE_INCOMPATIBLE
  Context: {"provider": "openai", "tool": "get_weather"}
  Witness: {"description": "All properties in an object must be listed in required array (missing: units)", "rule_id": "all_properties_required", "schema_path": "$.properties"}
  Repair (changes tool_schema): Add all property keys to the "required" array

[exact/error] STRICT_MODE_INCOMPATIBLE
  Context: {"provider": "openai", "tool": "get_weather"}
  Witness: {"description": "minLength is not supported in strict mode", "rule_id": "unsupported_minLength", "schema_path": "$.properties.location"}
  Repair (changes tool_schema): Remove minLength constraint
```

Provider rules are stored in `prompt_skill_linter/provider_rules/{openai,anthropic}.json` with doc URLs and check dates.

## Intentional limits

No validated arbitrary-English extraction, general SMT solver, unconstrained temporal logic, arbitrary conditional expressions, retry/failure model, dynamic skill discovery, argument type checker, automatic policy repair, automatic specificity inference, or inferred fallback compliance. Explicit CNF and finite-state models are bounded and isolated by documented fragment guards. Dependency diagnostics currently point to JSON declarations rather than a source-prose span and explicitly disclose that provenance gap. Read `docs/contracts.md` before interpreting a result.

## Product and scientific documentation

[Acceptance gates](docs/PRODUCT.md) · [Architecture](docs/ARCHITECTURE.md) · [Model card and soundness envelope](docs/MODEL_CARD.md) · [Local API](docs/API.md) · [Release notes](CHANGELOG.md)

The host-assisted 1.1 release candidate has a separate [real-workflow acceptance
checklist](docs/REAL_WORKFLOW_ACCEPTANCE.md). Its local evidence does not inherit
the earlier release's remote CI pass; final publication must verify the new snapshot.

This repository is private. No open-source license has been selected. Version 1.0 passed [all four release CI jobs](https://github.com/blazickjp/prompt-skill-linter/actions/runs/38062286853), including three Python versions, installed-wheel assets and 17 headless-browser user journeys. See [the acceptance scope](docs/PRODUCT.md).
