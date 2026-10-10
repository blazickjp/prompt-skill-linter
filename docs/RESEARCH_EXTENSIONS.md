# Research-backed extension: coverage and field presence

Research date: 2026-10-10. Build: **1.2.0.dev0, local and unpublished**.

Two narrow additions were selected because their required declarations and
witnesses fit the existing bounded, provenance-first checker. This is an
implementation study, not evidence of overall prompt-linter accuracy or improved
agent behavior. The frozen v1.1 source/corpus artifacts are retained unchanged in
the prior working copy; this successor does not rewrite its historical results.

## 1. Trigger reachability is separate from safety

Beer, Ben-David, Eisner and Rodeh explain why a valid property may be uninformative
when its antecedent cannot hold, and motivate nontrivial witnesses for valid
properties. That principle supports checking whether an assertion's event can
occur. The implementation does **not** implement their general ACTL vacuity
algorithm or establish every form of non-vacuity. [Author-hosted abstract](https://research.ibm.com/publications/efficient-detection-of-vacuity-in-temporal-model-checking),
[Formal Methods in System Design 18, 141–163 (2001), DOI](https://doi.org/10.1023/A:1008779610539).

For each active assertion, define its trigger set as:

- `action_count`: the union of its explicitly counted action IDs;
- `freshness`: its explicitly guarded action IDs. Refresh/invalidate events alone
  do not trigger the guarded property.

`trace_checks[].status` continues to mean `safe`, `violated`, or `unknown`, with
exactly the existing safety semantics. Its independent `trigger_coverage` reports:

- `reachable`: a shortest enabled event prefix in `first_trigger_path`;
- `unreachable`: exhaustive absence from the enabled transition model;
- `unknown`: absence cannot be concluded under the bound or unresolved policy.

A witness already found stays reachable if later safety exploration hits a
limit. An enabled no-op counts, even if its destination state was visited before.
The violating event itself also counts. Forbidden and schema-unavailable actions
do not count. Preconditions and remove-then-add effects remain authoritative;
workflow goals do not terminate these explicit runs.

There is a subtle boundary case: at depth zero, an initially fresh guarded no-op
can be exhaustively safe because its state transition closes a known loop. The
same configured zero-event bound admits no event witness, so trigger coverage
is unknown. Seeing an enabled edge beyond the bound never lengthens a reported
witness beyond that bound.

Safe plus unreachable yields `TRACE_TRIGGER_UNREACHABLE`, severity `info`. This
can reveal a mistaken precondition or ineffective test, but intentional disabled
optional actions and a zero-count policy can be valid. It is never relabeled a
safety error. Inactive workflows continue to be skipped, with no implied coverage
claim. Unknown coverage on an otherwise safe assertion is informational and
marks the report incomplete; unknown safety retains its existing warning.

The implementation inspects the safety checker's enabled edges directly. It
does not use the planner's display-limited graph or change its state budgets.

## 2. Reviewed flat-record field-presence compatibility

The distinction between declared properties, required properties, and an open
or closed object is standard. JSON Schema's official object documentation makes
clear that declaring a property does not by itself require it, and that extra
properties are allowed unless constrained. We borrow this distinction, **not**
general JSON Schema implication, subtyping, or value validation. [Official object
reference](https://json-schema.org/understanding-json-schema/reference/object).

A `field_contracts` entry describes **one reviewer-declared data edge** in its
fixed entity and temporal scope. Its producer says which literal top-level keys
are required or optional and whether additional keys are possible. Its consumer
says which keys it requires or reads optionally. Sequential, source-grounded
`copy` and `rename` adapters are explicit. All producer, consumer and adapter
spans must match local source lines exactly. Exact quote fidelity does not prove
semantic fidelity.

The result is conditional field presence:

| Consumer demand | Producer after adapters | Result for that key |
|---|---|---|
| Required | Guaranteed present | Compatible, including an open record |
| Required | Optional | Unknown |
| Required | Undeclared, closed record | Incompatible |
| Required | Undeclared, open record | Unknown |
| Optional | Missing | Compatible for presence only |

A definite missing key yields `REQUIRED_FIELD_NOT_PRODUCED`, an exact set-relation
finding under the reviewed closed-record declaration. It is not a proof that an
agent fails, that a whole skill is impossible, or that the source prose is a hard
contradiction. A mixed result retains both definite missing and uncertain keys;
report coverage remains incomplete while any demand is unresolved.

Activation uses existing typed equality conditions, explicit skill membership,
and exceptions. Missing condition/exception facts give unknown, never inactive.
An unknown declared skill is invalid input rather than a silent disabled check.
No instruction priority is invented. The edge's scope is fixed by the reviewer;
any permission resolution and the actual occurrence of consumption remain stated
assumptions, not a computed workflow reachability result.

Adapters map known keys to targets absent from the currently declared key sets. Copies keep the source; renames
remove it; optional origins remain optional. Chained adapters are processed in
order. Declared-key overwrites, unknown source keys, identity operations, and
arbitrary code are rejected. Hidden target collisions in an open record and
value preservation are not analyzed. No implicit `link`/`detailsUrl` synonym is assumed.

### Pinned natural candidate: the manual `gh-fix-ci` branch

At `openai/skills` commit `49f948faa9258a0c61caceaf225e179651397431`, the manual
fallback requests seven JSON fields including `link` (canonical source line 40),
then refers to `detailsUrl` to obtain a run ID (line 42). The CLI's pinned
`prCheckFields` list exposes `link`, with JSON registration at line 123. [Skill
lines 39–44](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/gh-fix-ci/SKILL.md#L39-L44),
[CLI definition at commit ec5b5120](https://github.com/cli/cli/blob/ec5b512045db67e5a2a4ff4a1b02660b2fb24390/pkg/cmd/pr/checks/checks.go#L23-L33),
[official command reference](https://cli.github.com/manual/gh_pr_checks#json-fields).

The candidate is deliberately conditional: the manual branch is selected, a
failing item is consumed, the requested projection succeeds, `detailsUrl` denotes
a literal record property, and no undeclared alias or adapter intervenes. Under
that reviewed closed record, the missing key is `detailsUrl`. If the phrase is
instead understood as shorthand for `link`, this declaration does not establish
a source defect. No real failing output was captured or replayed.

### Real helper control, with its own scope

The preferred helper accepts either input spelling and creates a **new** base
result containing `name`, `detailsUrl`, `runId`, and `jobId`. Later branches add
other keys, so the control uses an open producer with those guaranteed fields.
It does not claim every raw CLI key survives. Its own printer reads `detailsUrl`
inside an explicit guard, with a separate fixed scope from the manual branch.
[Helper construction](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/gh-fix-ci/scripts/inspect_pr_checks.py#L244-L252),
[guarded printer](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/gh-fix-ci/scripts/inspect_pr_checks.py#L465-L466).

The control is compatible for key presence. It does not establish a nonempty URL,
a valid run ID, successful commands, useful logs, or correctness of the preferred
workflow as a whole. Hypothetical copy, rename, and corrected-key controls are
separately labeled synthetic, not attributed to the upstream implementation.

## Reproduction and evidence boundaries

`corpus/research_extensions/` contains 16 selected development cases: 1 natural
conditional candidate, 1 natural helper field-presence control, and 14 synthetic
controls. Its 23 frozen files include source byte hashes, original Git blob IDs,
license texts, canonical line spans and reviewed bundles. Sources are retained as
inert text; no upstream script, CLI command, tool call, API or model executes.

```sh
python -m evaluation.research_extensions verify
python -m evaluation.research_extensions reproduce --output /tmp/research-extensions.json
python -m unittest discover -s tests -v
python -m unittest evaluation.test_evaluation -v
```

The offline runner checks source SHA-256 and Git blob hashes, license presence,
bundle/source identity, and every declared expected result. It never rewrites
historical corpora. Unit tests include an independent enumeration of 864 small
field-presence declarations and 400 bounded raw-action-prefix models, plus
activation, scope, provenance, bounds, adapters and mutation controls. These are
implementation controls, not independent natural examples or precision/recall
measurements. No behavioral repair benefit or deployed failure rate is claimed.

## Deliberately outside this release

- General temporal-logic vacuity, liveness, fairness, unavoidable failure, or a
  claim that every reachable assertion is substantively useful.
- General schema/type compatibility, nested paths, array cardinality, field value
  correctness, success/error variants, inference from arbitrary English, or
  implicit adapter discovery.
- Source truth, actual execution/authorization, prompt-injection detection, or
  guarantees that the manually accepted abstraction is faithful.
- Perplexity scores, static robustness heuristics, and model-based test execution.

### Try the cases in the Studio

1. Run `python -m prompt_skill_linter serve` from this checkout and open the
   printed loopback URL in your browser.
2. Choose **Import** and select
   `corpus/research_extensions/bundles/GH-MANUAL.json`. The source-linked finding
   identifies the conditional missing `detailsUrl` property and its assumptions.
3. Import `GH-HELPER.json` from the same folder to see its compatible key-presence
   control. Import `TRACE-DISABLED-ZERO.json` for safe-plus-unreachable information,
   or `TRACE-ZERO-BOUND.json` for safe safety status with unknown trigger coverage.
4. Export the JSON report to inspect every `field_checks` or `trigger_coverage`
   entry. No source-declared code or command runs during import or analysis.

The bundles contain reviewed declarations; importing them is not automatic
natural-language extraction. Exports preserve the input for offline replay.
