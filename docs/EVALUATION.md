# Evaluation: measured pilot, bounded claims

Snapshot: 2026-10-10. This is a **selected development pilot with native-model reference labels**, not human-gold accuracy, a representative benchmark, or a demonstrated advantage over a strong judge.

## Main result

The plain and structured-evidence native judge arms each agree with all **23 unambiguous reference cases**, abstaining on the same remaining case. The mechanical arm agrees on all **17 unambiguous cases it answers**, but abstains on six cases and emits a conditional model conflict on the source-ambiguous case. **There is no observed accuracy improvement from the checker or structured evidence in this pilot.**

The reference has 9 issue, 14 no-issue and 1 ambiguous/abstained labels. Every positive issue case is synthetic. The eight natural cases contain no adjudicated positive issue, so natural positive recall is undefined.

| Arm | Reference-positive agreement / 9 | False positives / 14 reference negatives | Coverage / 24 | Agreement on answered unambiguous cases |
|---|---:|---:|---:|---:|
| Plain native judge | 9/9 | 0/14 | 23/24 (95.8%) | 23/23 |
| Native judge + structured evidence | 9/9 | 0/14 | 23/24 (95.8%) | 23/23 |
| Mechanical checker on reviewed contracts | 9/9 | 0/14 | 18/24 (75.0%) | 17/17 |

Mechanical coverage includes one answer on an excluded ambiguous reference. Its six abstentions are reference-negative: five missing reviewed natural contracts and one depth-truncated workflow. In natural cases alone its coverage is 3/8, with two unambiguous compatible results and one source-ambiguous model conflict. These distinctions matter more than a headline perfect precision number.

Precision, recall and selective agreement are 1.0 where denominators permit, but these are agreement with provisional model-derived references on a small, intentionally inspectable set. They do not establish real-world accuracy or equivalence. Structured evidence supplied no measurable benefit on these cases. Native model identity/version was not exposed, so this is a native-model baseline, **not a verified frontier/strong-model comparison**. Shared-family and correlated errors are plausible.

Machine-readable per-case results, strata, denominators and exclusions: `evaluation/pilot/results.json`.

## Inputs and independence

The protocol and 24 cases were frozen before predictions; SHA-256 records are in `evaluation/pilot/freeze.json`. The set contains:

- 8 source-linked natural cases from OpenHands, mini-SWE-agent, Anthropic PDF skills, OpenAI Codex, and Gemini CLI
- 8 explicitly disclosed mutations of instruction themes
- 4 synthetic bulk-capacity boundary/control cases from the user handoff
- 2 synthetic interface mismatch cases
- 2 synthetic workflow reachability/bound cases

Natural sources are pinned to exact public commits. Both judge arms receive identical policy, task, tools, runtime and abstention options and verify the same full relevant source context. The structured arm additionally receives the manual finite interpretations; these are fallible evidence, not gold labels. A separate reference worker reviewed the same tasks without predictions. All model workers are distinct isolated task contexts; this does not guarantee different underlying models or independent errors.

The natural tasks are scoped instruction interactions, not complete deployed agent configurations. Empty supplemental tool dictionaries do not establish absence of actual tools; deployment-wide completion feasibility is unmeasured. The checker uses manually reviewed partial contracts for 19 cases and abstains on five absent contracts. It is therefore a **downstream reviewed-contract comparison**, not a full raw-source pipeline contest. Cases and encodings were constructed by the evaluation author, separately from the engine author; eight natural cases originate in five external repositories. Synthetic cases remain author-designed and are never counted as natural findings. No live service operation or historical user update was executed.

One mechanical label-adapter correction was made after initial local smoke: an exhaustive unreachable workflow is an issue even if its diagnostic severity is warning. The earlier artifact and amendment are preserved. Inputs and reference labels did not change. See `evaluation/pilot/amendments.json`.

## Extraction is a separate bottleneck

The offline provider matches **18/18 authored explicit-annotation grammar tests**, with exact source quotes and zero unreviewed binding rules. These are syntax-conformance tests, not NLP accuracy.

Across the same **24 raw policy-text fields**, it yields **zero binding translations** and hence **100% end-to-end abstention**. English instructions remain untranslated/review-only. This is safe behavior but a substantial capability limit: offline operation is an annotation/reviewed-contract analyzer, not an automatic natural-language prompt verifier.

Results: `evaluation/pilot/extraction_results.json`. Natural-language semantic precision/recall are null because no binding English translations were made. The optional remote extraction adapter has not been exercised using a live provider in this evaluation; mocked transport/validation tests are not model-quality evidence.

### Separate native-model extraction pilot

A fresh native worker extracted six source fragments held out from the feasibility-case snippets, using supplied action vocabulary and context hints. A separate native reference annotator produced nine atoms. **All 9 predicted atoms match those references** in action identity, exact quoted fragment/local lines, modality, conditions and exceptions. This is model-reference agreement on a small hinted set, not unrestricted extraction accuracy or full-policy recall. Source families overlap the feasibility pilot. The extractor could not retrieve Codex context for two fragments and relied on supplied context; Gemini and Anthropic context were independently read.

A real schema problem emerged: `binding_supported` was underspecified. The reference used it for structural representability after review; the predictor used it for verified executable grounding and conservatively marked every atom false. Agreement on that field was 2/9. This is an **interpretation disagreement, not seven established extraction errors**. Before acceptance, the predicted interpretations provide no analysis-ready bindings, so downstream probes abstain.

The raw predictions and initial metrics are unchanged. A separately recorded, **post-hoc evaluation-author acceptance demonstration** accepts seven structurally representable prohibitions for synthetic Boolean probes only. On 14 reference-supported probes, reviewed predicted clauses and reference clauses yield the same outcomes. Four additional probes tied to typography/active-voice measurement remain unsupported. This demonstration is not a blind improvement result, production grounding, or human adjudication; its predicates are explicit synthetic observations. See `manual_acceptance.json` for the exact boundary.

The product lesson is to keep structural representability, grounding to declared entities/actions, author acceptance, and eligibility for analysis distinct. No Boolean flag should silently imply an installed detector. Native-worker extraction is **not the product's live provider integration**, which remains unmeasured with a live API.

Artifacts and raw disagreement: `evaluation/extraction_pilot/reference.json`, `predictions.json`, `results.json`, and `manual_acceptance.json`. The batch took 97 seconds; identity, token usage and cost are unknown.

## What the proof artifacts provide

An independent small certificate checker in `evaluation/certificates.py` validates mechanical output properties, separate from judgment accuracy:

- 7/7 reported finite cores pass unsatisfiability and single-rule-removal witness checks
- 11/11 diagnostics carry exact local source spans and regression payloads
- 19/19 repeated runs produce identical reports
- Two bulk diagnostics give independently checked lower bounds, pairwise witnesses and affected range 151–200
- Six repair suggestions name existing requirements they would change
- The depth-cutoff workflow is correctly reported unknown, not globally unreachable

These checks demonstrate reproducibility and inspectable finite certificates. They do not prove that the original English was translated correctly, that repairs preserve the user's intent, or that humans find the diagnostics useful. No maintainer utility/time-to-repair study has been run. Subset-minimal does not mean smallest-cardinality or a unique cause.

Results: `evaluation/pilot/certificate_results.json`.

## Cost and latency

The plain native batch took approximately 134 seconds; the structured batch approximately 137 seconds. These include tool reads and orchestration. Model token usage and dollar cost were not exposed and remain **null**, not zero. No explicit paid API call or API key was used.

Local checker timing is recorded per case and per batch, excludes manual translation/preparation, and is not directly comparable to native batch timing. A reproducible fixed-hardware latency study and live-provider cost comparison have not been performed.

## Reproduce and extend

```sh
python -m evaluation.run verify
python -m evaluation.run mechanical --output evaluation/pilot/predictions/mechanical_reviewed_contract.json
python -m evaluation.extraction
python -m evaluation.certificates
python -m evaluation.score_extraction
python -m evaluation.run score --output evaluation/pilot/results.json
python -m unittest evaluation.test_evaluation -v
```

Saved native predictions can be rescored deterministically; re-running a native model requires a new external judge invocation and creates a new observation. `evaluation/README.md` documents the JSON adapter, access boundaries and metrics. Do not regenerate frozen inputs during an experiment. Future release claims require a larger family-held-out corpus, independent human adjudication, confirmed natural positives, repeated known-model arms, end-to-end extraction measurements and real utility/cost evaluation.

## Source-pinned scientific workflow runner

`python -m evaluation.scientific_workflows` provides a separate offline adapter
for real documented multi-skill workflows. Its catalog records each case's
family, origin (`natural`, `deployment_probe`, `synthetic_control`), advertised
completion question, bundle and independent extraction-review rationale.
`freeze.json` SHA-256 pins the catalog, bundles and referenced evidence files.
Unreviewed candidates are rejected; partial or unsupported projections abstain.
The runner never invokes a scientific tool, retrieves a credential or calls a
paid model API.

A conclusive checker result is about completion in the reviewed finite
projection. It is not a claim about full prose correctness, source-program
execution, or runtime success. Exhaustive unreachability can coexist with a
compliant fallback. Bound exhaustion or unknown activation is an abstention;
a discovered path plus an independent modeled error is also an abstention.
Untranslated source coverage remains attached even when the projected path is
reachable. Scores retain ambiguous references and separate origin and workflow
family. A new native-model call is a new observation, not reproduced by Python.

## Real public prompt corpus (Oct 16 2024)

A **32-case corpus** from diverse public sources measures existing check coverage against natural prompt texts. The corpus is 31% Cursor (10 cases), 25% Anthropic docs (8), 19% LangChain (6), and 25% other OSS (8). All cases have verifiable URLs. Split: 22 dev, 10 held-out (seed 42, fixed).

Contracts hand-written per `evaluation/CORPUS_RUBRIC.md` with modal-verb → modality mapping, consistent scope/priority, and exact source quotes. Commit order on branch `cursor/eval-corpus-1a6e`:
1. Rubric: `26cdad9`
2. Labels (32 cases): `55c017d`
3. Hand-written contracts: `1d9ca11`
4. Measurements: `c020c8d`

Labels committed before contracts; contracts before linter execution.

### Check-only results (hand-written contracts)

| Split | TP | FP | TN | FN | Precision | Recall |
|-------|----|----|----|----|-----------|--------|
| **Dev** | 0 | 0 | 19 | 3 | N/A | 0% |
| **Held-out** | 0 | 0 | 8 | 2 | N/A | 0% |

**Dev misses**: `anthropic_02`, `cursor_03`, `oss_01`. No false positives.

**Interpretation**: Existing checks (conflict, unreachable paths, axiom violations) don't match labeled text-level issues (vague directives, tensions, undefined terms). High specificity (no FPs), but 0% recall shows a check-family gap. The corpus uses natural text; no end-to-end extraction numbers reported because `extraction.extract()` requires explicit `REQUIRE`/`FORBID` annotations absent in these prompts.

**Limitations**: 32 cases insufficient for robust measurement. Check families for vague/ambiguous/undefined patterns needed. Corpus location: `evaluation/final_corpus/`.
