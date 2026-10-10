# Independent contract audit

## Results before checker exposure

- 47/47 raw clause quotations and file SHA256 values match the pinned captured sources.
- 271/271 bundle-rule and action-provenance spans match their embedded original source lines.
- The extraction correctly keeps SCVI counts, SysVI normalized data, human evidence verification, final approval, optional image generation, unchecked drafts and threshold success distinct.
- Exact quotations and schema validity do not prove transition faithfulness. Three offline adversarial traces expose two defects in the extracted finite models. These are extraction-model defects, not established defects in the upstream scientific skills or the checker.
- Original labels are immutable. A separate, pre-checker source-reference amendment changes KD-LR-01 from feasible to ambiguous for the whole requested review. The optional-image projection remains feasible. Curator control IDs were seen before initial labels; independence is checker-blind and source-based, not fully blinded to curation intent. Labels are model-provisional, never human gold.

## Finding A: generation-bound replay

KD-LR-04 permits these actions, all enabled:
1. compare_citations_claims_to_local_sources
2. synthesize_narrative_review
3. generate_first_png
4. generate_first_png
5. generate_first_png

It also permits first generation → first low review → second generation → second low review → replay first low review → second generation again. The low-review action recreates second_generation_permitted; no one-shot first-review token is consumed. Both traces make three generation actions in one represented run. The model still cannot achieve quality_met, so original case reachability is unaffected, but the extracted operational cap is not represented faithfully.

Source: scientific-schematics/SKILL.md L195: “The loop stops when the review passes or is unavailable, or when generation fails. A below-threshold score or an explicit improvement verdict can trigger a second generation; no run makes more than two attempts.”

Recommended derivative: initialize a first-attempt-available token and consume it on generation; produce and consume a first-review-pending token exactly once; grant a second-attempt-available token once and consume it on second generation. Do not allow review replay to replenish attempts. Retain saved image facts separately from consumable control-state tokens. Apply one-run semantics to every generator branch, including unavailable-review fallback, and record that deliberate new runs are outside the modeled case.

## Finding B: stale human verification and audit

KD-WR-01 permits these actions, all enabled:
1. create_evidence_outline
2. draft_manuscript
3. human_reverify_changed_prose
4. run_local_consistency_audits
5. draft_manuscript
6. human_approve_ready_and_remove_banner

The goal is reached while reverification_due remains true: the second draft retains changed_prose_human_verified and local_audits_pass from the prior wording. Redrafting after prior approval would likewise retain ready/banner-removed flags unless invalidated.

Source: scientific-writing/SKILL.md L143–145: “Do not mark a source verified until an accountable human has opened it and confirmed the exact support. After changing wording, re-verify the claim before updating its hash”; evidence_workflow.md L102–105 requires a current matching claim hash and re-verification before replacing it.

Recommended derivative: every wording-changing action removes changed_prose_human_verified, local_audits_pass, submission_ready_true and banner_removed, and restores incomplete/banner state as appropriate. Current local audit should require current human verification (the source’s final audit requires verified sources/current claim hashes). Final approval requires current verification and current audit; approval must remove contradictory false/banner-retained facts. Repeat redraft → reverify → audit → approve should remain possible. Human availability alone remains distinct from actual attestation.

## Finding C: partial review projection

KD-LR-01’s local-source comparison and synthesis path omits the DOI registration step. The original extraction itself acknowledges this ambiguity in README and literature-local-support. Neither optional diagrams nor local copies establish the complete review requirement satisfied.

Source: literature-review/SKILL.md L108 directs DOI registration/metadata checking before claim comparison. references/core_workflow.md L203–224 directs DOI checks through Handle/Crossref; L259 lists completed registration checks. The scenario does not state DOI applicability or cached completed checks. No network is available, but absence of cached checks is unknown rather than false.

Required reporting: whole-question abstain/ambiguous. A separately named local-source-comparison/text-synthesis projection may show a conditional path; never call that full-review no_issue. This is an extraction/evaluation confound, not an upstream source contradiction. Other literature-review projections omit the same full-process verification semantics; do not erase those warnings.

## Other adaptation qualifications

- SCVI fit action says “Scenario declares mechanical fit success.” The packet instead defines mechanical fit/export as its outcome and explicitly disclaims convergence guarantees. Replace that claim with an explicit abstraction assumption of possible mechanical success under supplied resources. No actual fit or success was observed.
- KD-LR-02’s missing key/network already supplies a decisive blocker. Its absent generation_success_declared and public_prompt_authorized tokens must not be reported as independently observed failure/denial facts: those are unstated. A repair that restores key/network still needs an explicit stochastic-success/authorization scope rather than treating unknown outcomes as false.
- Whole-doc untranslated coverage and semantic warnings must remain intact. A reviewer’s acceptance of a finite scenario projection is not permission to strip warnings, treat evidence-only rules as formal predicates, invent live tool schemas, or claim scientific validity.

## Test artifacts

candidate_audit.json contains exact enabled-state traces and 47 quotation/hash checks. span_checks.json contains 271 action/rule span comparisons. audit_candidates.py reproduces the offline audit without executing any upstream skill script, network request, installation, credential operation or paid API call.
