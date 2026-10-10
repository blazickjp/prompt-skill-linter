# Scientific workflow evaluation, October 10, 2026

Pinned upstream: K-Dense-AI/scientific-agent-skills at
`92ace75ac21efe19a620434e0ca4e356081fe807`. This selected-development evaluation
covers three documented families: Scanpy/AnnData/SCVI or SysVI; citation evidence
and scientific writing; literature reviews with optional schematics.

## What was measured

There are 13 scenarios: 6 synthetic controls, 4 deployment probes and 3 natural
underspecified documentation scenarios. They are not captured runtime executions.
The 177 installed skills are not assumed coactive. No biological tool, upstream
script, credential operation, external scientific service or paid API was run.

Two separate native-model arms reviewed the same source-level completion
question. The plain arm saw source/scenario evidence; the structured arm also saw
the frozen original candidate projections. An independent native reviewer froze
reference labels before seeing those contracts or checker results. Its control
IDs had been disclosed during curation, so blinding was incomplete. A separately
recorded pre-checker source amendment changes LR-01 to ambiguous. Labels are
provisional model references, not human gold; model identity/strength, token cost
and native latency could not be verified. Correlated errors remain possible.

Original extraction: 47 clauses, 13 candidate bundles. All 47 clause quotes/hashes
and 271 action/rule spans matched. Exact quotes did **not** establish semantic
faithfulness: independent review found two transition-model defects. The frozen
originals remain distinct from the explicitly logged corrections and excerpts.

## Results and limitations

- Both native arms: 4 issue, 5 no_issue, 4 abstain.
- Conservative checker on reviewed corrected projections: 4 issue, 9 abstain.
  Nine finite projections were accepted: 5 show conditional completion paths and
  4 have exhaustive unreachable goals. Four whole-question cases were withheld.
  Preserved unsupported-semantics warnings prevent the five reachable projections
  from being promoted into clean source-level judgments.
- The four positive cases are constructed deployment probes: missing measured
  counts for SCVI; unavailable human approval; absent network/key for required
  image generation; and two low-quality outputs failing a requested quality goal.
  They are not newly found intrinsic contradictions in upstream skill text.
- All 13 global full-source compatibility/scientific-correctness checks abstain.
  There is no natural-positive reference set, hence no measured natural recall.
- Model coverage is 9/13; conservative checker coverage is 4/13. Selective accuracy
  alone is misleading here. Checker negative-case coverage is zero, so selective
  false-positive rate/specificity is undefined, not demonstrated perfect.
- No superiority result follows. Preparation and review differ across arms;
  deterministic timing excludes extraction, curation and independent review.

`results/comparison.json` keeps every case, ambiguous reference, family and origin
stratum. Population false-alarm rate divides by all reference negatives including
abstentions; `selective_false_positive_rate` divides only by answered negatives
and is null when none were answered. Positive/negative coverage is explicit.

## Useful failures found in extraction

1. Original LR-04 allowed repeated first generation and replay of first review to
   replenish the second-generation token, violating the source's two-attempt cap.
2. Original WR-01 retained human verification and audit tokens after redrafting,
   allowing approval of stale wording.

These are extraction/model defects, discovered by independent native review, not
planner algorithm defects or upstream source bugs. Corrected derivatives consume
one-shot attempt/review tokens and invalidate verification/audit/approval on edits.
All original adverse traces now block; reverify/audit/approve recovery still works.

A narrow product improvement adds independent, explicitly declared action-count
and freshness trace monitors. `post_audit_traces/` shows original violations and
corrected exhaustive safety. This is **post-audit regression evidence**, not a
retroactive blind benchmark win. Goal reachability remains separate from safety
of allowed paths, and bound exhaustion remains UNKNOWN.

LR-01 is an additional scope confound: optional images can be skipped, but a full
review also instructs DOI registration checks. The offline scenario does not say
whether applicable checks were cached. A local text-synthesis path is therefore
not a whole-review no_issue. Both native arms noticed this source-context gap.

## Reproduce

From the product checkout:

```sh
python -m evaluation.scientific_workflows verify
python -m evaluation.scientific_workflows mechanical --output /tmp/mechanical.json
python -m evaluation.scientific_workflows score \
  --mechanical /tmp/mechanical.json \
  --model corpus/scientific_workflows/predictions/native_plain/plain_predictions.json \
          corpus/scientific_workflows/predictions/native_structured/predictions.json \
  --references corpus/scientific_workflows/references.json --output /tmp/comparison.json
python -m unittest discover -s tests -p test_scientific_trace_regressions.py -v
python scripts/review_trace_oracle.py
```

Native outputs are frozen observations. Python replays checking/scoring, not the
original model inference. Frozen hashes cover inputs, not newly timed outputs.

## Source representation and rights

Full selected documents were available to native extraction and review arms. The
published replay bundles contain minimal exact full-line excerpts with omitted
lines replaced by blanks, preserving original line numbers. They are **not the
full original inputs**. `excerpt-provenance.json` retains full captured hashes,
line/nonblank counts, retained lines and original untranslated counts. No coverage
percentage is recomputed from the artificially sparse excerpt denominator.

The upstream root MIT notice is in `K-DENSE-LICENSE.md`. Source frontmatter declares
BSD-3-Clause for Scanpy/AnnData/scvi-tools, without a per-skill license file in the
pinned tree, so complete raw documents are not redistributed here. Pinned URLs,
Git blobs, canonical and captured hashes are in `source-manifest.json`. The known
capture added one newline without moving existing lines.

To reconstruct all 13 original candidate bundles byte-for-byte from your own
local copy of the pinned upstream sources:

```sh
python scripts/rehydrate_workflow_sources.py \
  --source-root /path/to/scientific-agent-skills --output /tmp/original-candidates
```

The helper verifies canonical source hashes/Git blobs and every reconstructed
original bundle hash. It never downloads or executes source code. The recorded
original and derivative hashes are not interchangeable.

A separate structural scan of all 177 pinned skills found 675 explicit relative
Markdown links: 673 existing targets and 2 citation-format `(url)` placeholders;
zero confirmed broken packaged links. This is a heuristic link scan, not semantic
coverage of 177 workflows. See `structural/STRUCTURAL-REPORT.md`.
