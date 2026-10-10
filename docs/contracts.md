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
