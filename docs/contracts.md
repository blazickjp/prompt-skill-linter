# Contract v1 semantics

The normative accepted shape is `prompt_skill_linter/contract.schema.json`. Runtime uses a dependency-free validator for exactly the schema keywords present in that file, not a general-purpose JSON Schema library. Unknown contract/rule/runtime/tool fields fail closed. Source files must be UTF-8, located within the contract directory, and have exact quoted full line spans.

## Modality and hierarchy

A rule has an ID, source, integer priority (larger wins), literal scope `{entity, temporal}`, optional skill conjunction, equality-map `when`, and exception equality maps. Conditions use three-valued evaluation. Known type-equal facts establish true; a known mismatching conjunct establishes false; otherwise missing facts leave applicability unknown. Unknown exceptions are not assumed absent. Binding checks abstain with source-linked UNRESOLVED_ACTIVATION diagnostics when missing facts can change applicability. All skills on a rule must be explicitly active. Any matching exception disables the rule. There is no inference from installed skills, text similarity, or presumed precedence/specificity.

`effect: {literal: "x", value: true}` means:
- requirement: x must be true;
- prohibition: x may not be true, so x must be false;
- permission: x may be true, without requiring it;
- preference: nonbinding; not used to establish unsatisfiability.

This polarity convention also applies to value=false. Only identical literal, entity and temporal scope are compared. Rules are processed high priority first. An effective higher binding rule shadows a lower opposite binding rule. A higher explicit permission can defeat a lower prohibition of the permitted value. An already shadowed rule cannot shadow another rule. Same-priority contrary binding rules form a conditional collision. Permission alone never creates a binding conflict. These are deliberately small explicit semantics, not a complete implementation of any platform's hierarchy.

Boolean collision minimality is checked in the effective two-constraint model: remove either and assign the remaining required Boolean value. It is not a claim that deleting the corresponding prose rule from a larger policy cannot reactivate other rules. Context enumeration is supplied by the author; unlisted contexts are not checked.

## Exact resource fragment

`bulk_model` is a dedicated synthetic monotone integer fragment:

- `capacity * s >= n`
- `p >= s`
- `s + p <= runtime.service_call_budget`
- s,p are nonnegative integers.

The model requires three distinct, unconditional requirement rule IDs plus an unconditional advertisement rule. Conditional resource constraints, exceptions or skill-dependent arithmetic are rejected rather than resolved speculatively. Mapped resource rules must share the advertisement’s exact scope and cannot also carry Boolean effects, action permissions/prohibitions or tool-call fragments. This fragment is not a general resource solver and does not interpret other rule effects as resource constraints.

For any enabled subset, the smallest s is ceil(n/capacity) if coverage is enabled, otherwise zero; the smallest p is s if polling is enabled, otherwise zero. If this canonical point violates an enabled upper budget bound, every feasible coverage/poll point does too. Integer ceiling avoids floating-point error. Core deletion uses this exact subset decision procedure. Pairwise witnesses and inequalities are preserved separately. Responsible rule sets use distinct IDs. The advertised-range arithmetic intersects the infeasible suffix with the declared advertised range. Requests outside that range can be arithmetically checked but are not thereby claimed advertised.

There must be at least one explicit positive integer request size. Increasing runtime budget is an explicit replacement for the budget constraint in controls. Tool capability text and original prose are not automatically proven equivalent to the resource model.

## Workflow fragment

Actions have IDs, required positive facts, added facts and removed facts. Preconditions are conjunctions, states are finite sets, and actions are deterministic. The goal is a conjunction. BFS explores at most the configured depth (default 20, maximum 100) and 2,000 distinct states. A cutoff gives `PLAN_BOUND_EXHAUSTED`, not an impossibility proof. No-call-cost optimality is claimed by this planner.

The referenced advertisement rule must be active. `forbid_action` is valid only on a prohibition; `allow_action` only on a permission. Restrictions and permissions must share the advertisement's entity and temporal scope. A higher explicit allow can defeat a lower forbid. Actions with unsupported modalities are rejected. No implicit action aliases, applicability to another entity, or derived permissions exist.

If no goal path exists, the checker tests an explicitly declared `compliant_fallback` action for reachability. This declaration is a reviewer's assertion, not a proof that refusal meets every prose obligation. Reachable fallback yields `UNSUPPORTED_WORKFLOW`; no modeled fallback yields `MISSING_FALLBACK_PATH`. Neither code by itself asserts that effective instructions are contradictory. Reachability does not integrate arbitrary Boolean obligations or tool argument semantics; it is a separate declared fragment.

## Provenance and assumptions

All rule-backed diagnostics preserve source spans, rule interpretations, resolved priority numbers, triggering context and assumptions. Manifest/skill-dependency diagnostics lack prose spans in v1 and explicitly report that limitation. Contract assumptions propagate into every diagnostic and readable report. Model-based results carry an explicit statement that a source-prose contradiction has not been proven. Source excerpts may omit context; external corpus manifest and reviewer notes remain authoritative about that limitation.

Repairs do not change files or source requirements automatically. Resource repair suggestions name the altered requirement and require a new review. Regression records are serialized triggering cases; `scripts/reproduce.py` and unit tests execute the bundled controls. `--baseline` compares code + responsible IDs + context only: changed witness arithmetic under the same identity is not reported as a new diagnostic.


## v1 product extensions

An optional interpretation record distinguishes declared, candidate and accepted contracts, records extraction method, excluded IDs, untranslated counts and source spans. Candidate contracts cannot be analyzed. Untranslated or excluded material emits `INCOMPLETE_SOURCE_COVERAGE`, including when zero rules are accepted.

Explicit `clause` rules represent disjunctions of Boolean literals; active clauses are conjoined per exact entity/temporal scope. They must be requirements at one shared priority, and cannot share literals with the Boolean-effect fragment in that scope. The bounded solver emits SAT assignments, conditional UNSAT cores or UNKNOWN. Core reduction has a cumulative 100,000-node budget and only claims minimality after every removal is verified SAT. Scoped truth-table display never merges independent entity/time surfaces.

Workflow actions may include a declared tool_call. Missing tool IDs or invalid/missing argument names make that action unavailable and produce an exact declaration diagnostic. The planner returns paths, blocked actions, visited-state graphs and explicit truncation. No tool is executed.

The API what-if path reports changed requirement IDs, before/after reports and changes to witness evidence as well as diagnostic identity. It never changes the original bundle or silently edits source prose. Detailed limits and the complete supported envelope are in `docs/MODEL_CARD.md`.

## Action evidence for scientific workflows

Actions may carry optional `provenance` with `source_spans` (the same exact
full-line source span shape used by rules) and `assumptions` (strings describing
the abstraction). The engine checks each source ID, safe path, line range and
quote before analysis. Each action supports at most 32 spans and 32 assumptions.
No source text or scientific code is executed.

Workflow checks retain this evidence in `action_provenance`. Workflow failure
diagnostics include it in their witness and explicitly list actions lacking
source evidence. Legacy contracts remain valid, with their evidence limitation
visible. Matching source text does not establish that a Boolean precondition or
effect faithfully represents data types, measurements, human attestations or
biological semantics. These remain reviewed assumptions; provenance changes no
reachability semantics. A source snippet is never treated as a tool permission.

## Independent action-trace assertions

A workflow may optionally declare `trace_assertions`. These are author-reviewed
properties, not predicates inferred from English or automatically extracted by
the model. Each has a unique `id`, exact `source` span, and `assumptions`:

- `action_count`: `actions` lists counted action IDs; `max_count` is the maximum
  total invocations in this one run, including repeated no-op actions.
- `freshness`: `invalidate_actions` makes the independent monitor stale,
  `refresh_actions` makes it fresh, and `guarded_actions` requires it fresh before
  the event. `initially_fresh` must be explicit. The three event roles are disjoint;
  invalidators may be empty. Guard events do not consume freshness.

Each monitor explores the product of workflow facts and its own state. Workflow
`adds`/`removes` cannot reset an invocation count or manufacture verification.
The same resolved restrictions, permissions and unavailable tools determine action
availability as in the planner. An assertion has no intrinsic hierarchy priority.
All allowed prefixes are checked, including after goal completion: **goals do not
terminate runs**. Model an explicit terminal guard if a run must stop there.

`safe` means exhaustive absence of a violation in this finite abstraction;
`violated` carries a shortest violating action trace; `unknown` records a cutoff
or unresolved policy. A violation concerns an allowed unsafe path. It does not
prove that completion is impossible or that an agent must take that path. A
reachable safe completion and an unsafe alternate path may coexist. Witnesses
include assertion/action source evidence, effects, resolved action policy and
`completion_feasibility_not_disproved`. No minimal responsible core is claimed.

Limits: 8 assertions per workflow, 16 total, 128 assertion/context pairs, 256
facts for traced models, existing planning depth at most 100, at most 2,000 visited
states per assertion, and **20,000 visited product states for the entire lint
request**. Later assertions become UNKNOWN when that aggregate budget is spent.
Source quote matching still does not prove semantic fidelity. Post-audit corpus
examples reproduce known extraction defects and corrected projections; they are
not credited as blind discovery.

## Trigger coverage (1.2 development)

Every analyzed trace assertion additionally returns `trigger_coverage` with
`status`, `trigger_actions`, `first_trigger_path`, `search_exhaustive`,
`cutoff_reasons`, and `scope`. The trigger is a counted or guarded action event,
respectively. `reachable` carries a shortest enabled, in-bound prefix;
`unreachable` requires exhaustive absence; truncated absence is `unknown`.
Enabled no-ops count before successor-state deduplication. Disabled actions do
not count. A witness remains reachable despite later safety cutoff. This result
is independent of `safe`/`violated`/`unknown` safety status and adds no budgets.

Safe-plus-unreachable is informational, including intentional disabled actions
or zero-count policies. Inactive workflows are skipped. A zero-depth guarded
self-loop may be safe while coverage remains unknown, since no event prefix of
length one is admitted. Coverage does not infer arbitrary temporal-logic vacuity.

## Flat-record field presence (1.2 development)

Optional top-level `field_contracts` declares one reviewed producer-to-consumer
edge per entry. Required keys:

- `id`: unique and distinct from rule/trace assertion IDs;
- `scope`: nonempty `entity` and `temporal`, fixed for this edge;
- `producer`: `required_fields`, `optional_fields`, `additional_fields` Boolean,
  and `provenance`;
- `consumer`: `required_fields`, `optional_fields`, and `provenance`;
- `adapters`: ordered list of `{kind: "copy" | "rename", from, to, provenance}`;
- `assumptions`: explicit string list.

Optional `when`, `skills`, and `exceptions` use the existing three-valued
activation model. Unknown conditions or exceptions remain unknown, while a known
inactive context emits no finding. Referenced skills must exist. No priority,
scope subsumption, or automatic policy resolution is inferred for the edge.
The context's consumed-record occurrence is a reviewed assumption, not a computed
transition-model result.

Each `provenance` has 1–32 exact `source_spans` and an `assumptions` list, using the
existing line-span shape. Source, producer, consumer and adapter text are inert.
No default alias, executable transform, nested path, value type or tool call is
inferred. A string such as `a.b` denotes that literal top-level key.

Required producer keys are guaranteed. Optional producer keys may be absent.
An undeclared demanded key is definitely absent only for a closed producer
(`additional_fields: false`). A guaranteed key satisfies presence even for an
open producer. Optional consumer reads impose no presence requirement. Sequential
copies retain the source and renames remove it; optional sources stay optional.
The target must be absent from the currently declared key sets. Undeclared target
collisions in open records and preservation of values are outside this analysis.

`field_checks` returns one result per declaration/context, including inactive
contexts. Statuses are `compatible`, `incompatible`, `unknown`, and `inactive`.
`missing_required_fields` and `uncertain_required_fields` can both be nonempty;
a definite missing field establishes incompatibility without hiding remaining
uncertainty. `REQUIRED_FIELD_NOT_PRODUCED` is exact under the reviewed closed
record; `FIELD_PRESENCE_UNKNOWN` is a warning. Neither establishes workflow
completion, actual failure, authorization, or whole-skill correctness.

Limits: 32 contracts, 256 contract/context pairs, 128 producer and 128 consumer
keys, 32 adapters, 32 provenance spans and assumptions per holder, 256 characters
per key/scope/assumption entry, 32 skill conditions, 32 exception maps, and 32
facts per condition. Required/optional sets must be disjoint and duplicate-free;
unknown fields or types in the declaration schema are rejected. Source limits
and the existing candidate-review requirement still apply.

See `corpus/research_extensions/bundles/GH-MANUAL.json` for a full source-grounded
entry and `GH-HELPER.json` for its separately scoped real control. Hypothetical
adapters and open/optional variants are labeled `SYN-*`, not upstream repairs.
