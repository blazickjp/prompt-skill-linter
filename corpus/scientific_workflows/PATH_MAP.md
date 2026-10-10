# Portable evidence paths

Frozen native records retain their historical input paths to document what each
arm saw. Those temporary locations are not reproduction dependencies:

| Historical input root | Published equivalent |
|---|---|
| `/workspace/shared/kdense-testbed/neutral-cases.json` | `neutral-cases.json` |
| `/workspace/shared/kdense-testbed/coactivation-excerpts.json` | `coactivation-excerpts.json` |
| `/workspace/shared/kdense-testbed/source/` | Full inputs at pinned URLs in `source-manifest.json`; sparse replay evidence is embedded in `candidates/` and `bundles/` |
| `/workspace/shared/kdense-extraction/FREEZE.json` | `original-extraction-freeze.json` (original full-input inventory) |
| `/workspace/shared/kdense-extraction/raw-extraction.json` | `raw-extraction.json` |
| `/workspace/shared/kdense-extraction/workflow-extraction.json` | `original-workflow-extraction.json` |
| `/workspace/shared/kdense-extraction/bundles/` | `candidates/` are excerpt derivatives; use `scripts/rehydrate_workflow_sources.py` plus pinned full sources to reconstruct exact originals |
| `/workspace/shared/kdense-corrected/bundles/` | Reviewed excerpt derivatives in `bundles/`, with exact transformation and original hashes in `derivation.json` / `excerpt-provenance.json` |
| `/workspace/shared/kdense-review/` | Intended audit evidence in `review/`; no scratch directory is required |
| `/workspace/shared/kdense-model/` | `predictions/native_plain/` |
| `/workspace/shared/kdense-structured/` | `predictions/native_structured/` |

Paths above are relative to this corpus directory except the product helper.
Original full candidate inputs, reviewed corrected projections and post-audit
trace demonstrations are distinct evidence stages. No hidden workspace or model
service is needed for deterministic replay; a new native judgment is a new run.
