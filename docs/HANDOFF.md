# PROJECT HANDOFF: PROMPT AND SKILL LINTER

User request: “Can we create a new repo for this?”

## Objective
Start building a prototype linter for prompts and composed skills. Find situations where applicable instructions conflict, leave no compliant completion path, or advertise support that the available tools and limits cannot provide. The central question is: "Can the agent satisfy the applicable instructions in this supported situation?" Analyze the specification before execution. Produce actionable diagnostics with source rules and concrete triggering cases, rather than a general prompt-quality score.

## First implementation
Build a small CLI that reads prompt/skill files plus a tool manifest and runtime configuration. Produce a contract representation, JSON diagnostics, a readable report, and a reproducible test set. Favor a few reliable checks over broad claims about understanding arbitrary English.

Keep three diagnostic classes distinct:
1. Exact checks: broken tool/skill references, invalid argument names, explicit dependency problems, and resource bounds derived from declared constraints.
2. Model-based checks: incompatible obligations, unreachable completion, shadowed rules, missing fallback paths, and regressions after a rule changes. Results are conditional on the reviewed model and its search bounds.
3. Semantic warnings: ambiguous conditions, unclear scope, vague requirements, and uncertain translation from prose. These are not established errors.

## Contract representation
Include rule IDs, exact source locations and quotes, priority, activation conditions, entity and temporal scope, requirements/prohibitions/permissions/preferences, exceptions, action prerequisites and effects, tool capabilities, and resource limits. Separate declared facts from inferred assumptions. Preserve the original text and let authors inspect and correct the interpretation.

Resolve hierarchy and exceptions before reporting conflicts. Permission is not an obligation. Analyze skills that can actually be active together, not every installed skill at once. A higher-priority restriction may leave an advertised workflow unsupported while still permitting a compliant refusal or continuation. Distinguish that from contradictory effective instructions.

## First executable case
Use an explicitly synthetic bulk-update workflow:
- Advertised support: update all requested nodes, for lists of 1-200 nodes, within one run.
- Each submission handles at most 10 nodes and returns exactly one task.
- Every task must receive at least one separate polling call before completion is reported; each poll handles one task.
- The run is limited to 30 counted service calls.
- No prior tasks, batching shortcuts, alternative update operations, or bulk polling are available in this model.

For 151 nodes, at least ceil(151/10)=16 submissions and 16 polls are required. The lower bound is 32 calls, exceeding 30. The affected advertised input range is 151-200. For the related 184-node example, the minimum is 38 calls.

Encode s and p as nonnegative integers: 10*s >= n; p >= s; s+p <= 30. At n=151, each pair is satisfiable but all three constraints are not. This is a useful test for interactions beyond pairwise contradiction detection.

Report UNREACHABLE_COMPLETION with the request size, lower bound, assumptions, and responsible source rules. Add a 150-node control and increased-budget controls. Passing this lower-bound check does not guarantee completion: schema retrieval, retries, failures, and additional polls can consume more calls.

## Diagnostics and repairs
Every substantive diagnostic should contain its class/severity, source spans, interpreted rules, resolved priorities, triggering context, counterexample or arithmetic witness, and responsible rule set. Call a set minimal only after checking that removing each included constraint eliminates that conflict. Generate a regression case. Suggested repairs must identify the requirement being changed; do not silently weaken a rule to make a proof pass.

## Evaluation
Use a versioned corpus of actual prompts and skills. Keep natural findings separate from clearly labeled synthetic mutations. Obtain independent reference labels, including valid exceptions, ambiguous cases, and negative controls. Avoid constructing the entire benchmark from the checker author's own templates.

Compare a strong judge, a judge with structured evidence, and the mechanical checker using matched policies, tool descriptions, and abstention options. Measure extraction separately from downstream checking, then evaluate the whole pipeline. Report false positives, missed issues, coverage, useful diagnostics, cost, and latency. Do not claim an advantage before measuring it.

Suggested parallel workstreams: Contracts and engine: define the schema and implement the exact/model checks. Corpus and evaluation: assemble independent cases and matched judge baselines. Research and diagnostics: review related work and make findings actionable.

First milestone: an end-to-end CLI run with the 151-node finding, valid controls, several independently sourced real cases, and an honest evaluation report.

## Context and sources
Related research: WIRE, https://arxiv.org/pdf/2605.27784 . Its symbolic stages nominate collision candidates; they do not prove arbitrary English contradictory. Review its scope before adopting its techniques.

Existing conversation artifacts: inspector.html, verification_report.html, and verification_bundle.zip. The audit examined 31 turns in 10 sessions. It includes useful trace contracts but does not demonstrate superiority over a strong judge. The original export contains clipped fields and missing offloaded datasets. Resolve these files if available; do not treat evaluator labels as ground truth or replay historical update calls. They are not required for the first synthetic prototype.

Success means useful, reproducible findings about the stated contracts. A pass does not certify that every sentence was translated correctly or that an agent will obey the instructions at runtime.

---
Transcription of the supplied handoff; headings normalized, requirements retained. Source: user message `Sentinel_314dca97eed0819198a066f19e24a1fc`, October 10, 2026.
