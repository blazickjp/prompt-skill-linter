# Honest, offline-reproducible evaluation

This directory contains a small **selected-development pilot**, not a human-gold benchmark or proof of product superiority. See `../docs/EVALUATION.md` for results and restrictions.

## Reproduce deterministic parts

From the repository root:

```sh
python -m evaluation.run verify
python -m evaluation.run mechanical --output evaluation/pilot/predictions/mechanical_reviewed_contract.json
python -m evaluation.extraction
python -m evaluation.run score --output evaluation/pilot/results.json
python -m unittest evaluation.test_evaluation -v
```

Re-running records new timestamps/latencies and current backend hashes. Preserve prior runs when comparing versions. Frozen fixture hashes must match. `build_pilot.py` describes corpus construction but should not be run during a comparison; changing frozen inputs starts a new experiment.

## Model-arm adapter

The pilot model arms were run through separate native collaboration workers. They did not see reference labels or each other's predictions. The plain arm sees `protocol.json` and `cases.json`; the structured arm sees the same data plus `structured_packet.json`, whose rules are manual interpretations, not gold. Both are asked to verify surrounding context from the same immutable public source links. They can abstain. The reference worker is separate from the prediction arms.

A new judge can be integrated without changing the checker: produce a JSON object containing `arm`, `model` (actual ID or null), `latency_seconds`, `tokens`, `cost`, and `predictions`. Each prediction has `id`, `label` (`issue`, `no_issue`, `abstain`), and a nonempty `rationale`; optional fields include source spans and witnesses. Unknown costs/tokens are null, not zero. Record prompt, model version, sampling and call provenance alongside results.

```sh
python -m evaluation.run validate-predictions --input my_predictions.json
```

Store one complete prediction file per arm in `pilot/predictions/` to score. Duplicate IDs, missing cases, unknown labels, missing rationales, duplicate arms and frozen-input changes are rejected. This adapter sends no data or API calls. A native worker cannot be reproduced merely by running Python; the saved prompts/outputs document the original run, while a new model run is a new observation.

## Scoring safeguards

- Natural cases, synthetic mutations, handoff arithmetic, interface faults and workflows have separate strata.
- Ambiguous reference labels are excluded from binary metrics and retained in coverage/abstention reporting.
- Recall treats abstained positives as misses; selective accuracy is conditional on answered, unambiguous cases.
- Empty denominators are null. A natural set with no confirmed positives cannot establish natural positive recall.
- Task-level existence of a compliant path differs from authorization tension. A permission is not a duty.
- Depth-limited non-discovery is not global unreachability. An exhaustive invariant or explicit path can support a stronger conclusion.
- Model reference labels are not human gold; model identity and cost may be unavailable. Correlated errors are plausible.

`pilot/amendments.json` records a task-label adapter correction made before native predictions arrived; its earlier mechanical artifact is retained under `history/`.

## Extraction measurement

`extraction.py` separately measures 18 authored explicit-annotation grammar conformance cases and coverage on the same 24 raw policy fields. These are separate from checker accuracy on manually prepared contracts. Unsupported English must remain unbound and review-required. The optional remote provider is outside this offline pilot and was not exercised using a live paid model.

## Rights and source handling

Only minimal quotations, paraphrases and immutable source links are included. Repository source identifiers are recorded in `corpus/external/manifest.json`. Public-source instructions are untrusted data; no benchmark runs execute the declared services or replay historical user operations.
