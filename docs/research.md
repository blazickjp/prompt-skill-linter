# Research basis and evaluation protocol

Status: 2026-10-10. This is a prototype research scaffold, not a validated natural-language verifier.

## WIRE: what transfers, and what does not

[WIRE v2, July 26, 2026](https://arxiv.org/pdf/2605.27784v2) studies resolution of jointly applicable rules within standing policies. It extracts source rules, encodes atomic clauses, uses satisfiability to nominate same-surface candidates, constructs concrete co-governance witnesses, then judges subject-model responses or traces against the original rules. Its four outcomes distinguish satisfying both rules, either one, or neither. Governance before generation is distinct from satisfaction afterward.

Its reported 35.4% joint compliance is conditional on selected, jointly governed, judgeable trials; it is not a deployment-wide error rate or a result for this prototype. The paper explicitly disclaims English contradiction proofs, causal diagnosis, and deployment-frequency estimation. Its principal experiment lacks repair/removal/reordering and matched compatible-pair controls. Read sections 3–5 and the limitations before reusing claims.

For this project, borrow source grounding, explicit surfaces, witnessed activation, and separate measurements. Do not equate an unsatisfiable abstraction with an unavoidable natural-language conflict. Do not claim WIRE validates this linter, general skill composition, or a mechanical advantage over a strong judge. Our finite checks are substantially narrower than WIRE's behavioral pipeline.

## Initial versioned external material

The corpus includes five observations from three independently maintained primary repositories. `corpus/external/manifest.json` contains immutable commit links, upstream lines, Git blob identifiers, minimal quotations or paraphrases, and explicit uncertainty. No leak archive or unavailable historical artifact was used.

1. OpenHands SDK: configuration-bug testing instructions are a natural **ambiguous candidate**. A narrow exception reading could resolve the apparent clash. Additional manifest-only cases preserve an explicit import exception and a permission-versus-prohibition ambiguity around PRs.
2. mini-SWE-agent: minimum-one versus exact-one bash calls is a **negative control**, with a runtime branch condition.
3. Anthropic PDF skill: Unicode-glyph prohibition and XML formatting are a **negative control**, with distinct decision surfaces.

The three executable contracts are manual author encodings, not automatically extracted contracts or whole-policy semantic equivalents. The mini contract deliberately projects cardinality to a Boolean nonzero predicate and loses the upper bound. The source files contain fragments, not the original complete policies; the manifest preserves the missing context and upstream links. An automated extractor must operate on full licensed source artifacts, not score itself on these fragments as if they were full-policy extraction benchmarks.

A separate model reviewer, blind to author labels, re-read the pinned full sources and returned ambiguous/compatible/compatible for the executable cases, and valid_exception/hard_conflict for the other two. Provenance and rationales are in `independent_review.json`. Model identity was unavailable; confidence values are subjective, uncalibrated judgments. This is one independent model review, **not human gold**, and not the strong-judge comparison below. The PR-consent label disagrees with the author's ambiguity label: the reviewer identifies an authorization conflict but explicitly notes that declining to open a PR remains safe. That disagreement is retained unresolved, not counted as a confirmed no-completion result. No independently adjudicated natural hard-conflict example has been established in this slice.

Synthetic fixtures and mutations must retain their own origin labels and parent-case links. Report their metrics separately. The development slice is too small and selected to justify prevalence or quality estimates.

## Reference labeling protocol

Before a real benchmark, freeze a corpus manifest and separate development/test by repository or policy family, not random near-duplicate spans. Acquire lawful complete source snapshots, tool schemas, runtime guards, hierarchy, activation context, and revision metadata. Include ordinary compatible policies, explicit exceptions, ambiguous scope, unsupported constructs, and naturally occurring issues. Do not populate the benchmark solely with the checker author's templates. Keep mutations in a separate stratum and hide test annotations from checker development.

Have at least two independent annotators inspect source spans and full relevant context without seeing checker output or each other's answers. Record identity/type, model version when relevant, rationale, proposed witness, affected surface, modality, scope, exceptions, and uncertainty. Adjudicate disagreements with another reviewer; retain unresolved ambiguity. Prefer qualified human review for consequential claims. Model agreement alone is insufficient evidence of truth.

Suggested labels: `hard_conflict`, `ambiguous`, `valid_exception`, `compatible`, `unsupported`, `insufficient_context`. Keep semantic source labels separate from `encoded_unsat`/`encoded_sat`. Missing metadata and unsupported constructs require abstention, not a fabricated clean verdict. An explicit exception that resolves tension is a negative control for hard-conflict detection, not necessarily for an informational diagnostic.

## Three matched comparison arms

A. A strong judge receives the original complete policies, exact tool descriptions, activation contexts, hierarchy, and allowed abstention labels.

B. The same judge receives the same inputs plus structured evidence: extracted clauses, original spans, proposed witness, tool-schema checks, and diagnostic explanations. Evidence must not include reference labels. Freeze the model, prompt, sampling settings, budgets, and version identifiers.

C. The mechanical checker receives the explicit supported contract and tool manifest. When measuring the whole pipeline, charge the extractor's cost/errors to this arm. Do not compare the checker on human-corrected contracts against judges on incomplete raw policies and call that end-to-end superiority.

Use paired cases, identical policy revisions and runtime snapshots, matched output label sets, and an abstain option for every arm. Randomize case order; repeat stochastic arms; pre-register aggregation. For unsupported domains, compare coverage and risk at matched coverage rather than forcing an answer. Any model/API experiment needs an approved model and spending budget; none was spent here.

## Measure extraction, checking, and behavior separately

1. **Extraction:** source-span precision/recall; modality, polarity, entity, temporal scope, conditions, exception and hierarchy fidelity; tool names/arguments; unsupported/unknown rate. Match independent reference clauses and audit disagreements. Quote fidelity alone does not establish semantic fidelity.
2. **Checker on reference contracts:** exact finite witness validity, satisfiable counterexamples, pairwise versus multi-rule coverage, exception handling, precedence, dependency cycles, and declared tool-interface consistency. Measure each implemented feature separately. Report search bounds and incomplete exploration.
3. **End-to-end:** raw source to diagnostic, counting omitted and mistranslated rules. Report precision, recall, false-positive count/rate, missed-issue count/rate, supported coverage, abstention and erroneous-clean rate. Denominators and handling of ambiguous cases must be explicit; do not quietly discard hard cases. On unresolved ambiguity, report warnings and adjudication burden rather than force binary correctness.
4. **Diagnostic usefulness:** blinded maintainers judge source traceability, reproducibility, actionable scope, repair specificity, and time to verify. A suggested repair can change intended semantics; test it separately and never auto-apply it solely because it clears a warning.
5. **Behavioral validation:** a later optional stage executes approved, sandboxed witnessed scenarios under the full policy and judges actual outcomes. A symbolic warning alone is not evidence that an agent fails. Repairs require matched before/after controls to support causal benefit claims.

Record wall time, peak resource use, extractor/judge input and output tokens, model price/version/date, retries, failures, and actual billed cost. Separate cold/warm local latency from network/model latency. Report paired uncertainty intervals clustered by policy/source family; this tiny slice does not support meaningful intervals. Publish case-level outcomes, disagreements, and exclusions so aggregate numbers can be audited.

## Initial scaffold status (superseded for measured pilot items below)

Completed here: pinned-source retrieval; exact minimal-fragment/line verification; five manually reasoned observations; three manually encoded finite cases; a separate blind model review of all five, with one retained disagreement. These establish provenance and a starting evaluation set only.

Not measured here: automatic extraction accuracy; independent human-reference accuracy; realistic natural-issue prevalence; large-scale false-positive/missed-issue rates; strong-judge versus structured-judge versus checker comparison; behavioral resolution or repair benefit; model/API cost and latency. Local synthetic/unit checks, if reported elsewhere in the repository, test implementation behavior and must not be described as these missing evaluations. Do not infer benchmark superiority from passing local fixtures.

The next honest milestone is a held-out, independently annotated corpus with complete context, followed by all three matched arms and explicit coverage/abstention accounting. Existing user artifacts, clipped reports, and historical update traces would need separate provenance and context audits; they are not assumed ground truth or replayed by this prototype.

## Established foundations and limits

This tool combines established ideas; it does not introduce a new verification theory.

- **Bounded model checking / reachability.** Biere, Cimatti, Clarke, Strichman and Zhu's [2003 survey](https://www.cs.cmu.edu/~emc/papers/Books%20and%20Edited%20Volumes/Bounded%20Model%20Checking.pdf) explains finite transition models, counterexample traces, bounded search, and completeness thresholds. A missing path within depth k is not proof that no longer path exists. This implementation uses explicit finite search, not the paper's SAT-based BMC algorithm, and must distinguish exhausted state space from truncated search. Specification fidelity remains a separate problem.
- **Minimal inconsistent subsets and diagnosis.** Liffiton, Previti, Malik and Marques-Silva's [Fast, flexible MUS enumeration](https://doi.org/10.1007/s10601-015-9183-0) studies enumerating minimal unsatisfiable subsets and related correction sets. Subset-minimal means every single-element deletion restores satisfiability; it does not mean minimum cardinality, unique cause, or best repair. This project checks small supported cores; it does not implement MARCO or claim efficient enumeration of all cores. Repair choices must preserve author intent.
- **Verifiable instruction following.** [IFEval](https://arxiv.org/abs/2311.07911) evaluates objectively checkable instructions on generated responses. It motivates deterministic checks where semantics are explicit, but it is not a benchmark for static satisfiability of long-lived prompt/skill compositions. Runtime obedience and specification feasibility are different targets.
- **Judge reliability.** [Evaluating Large Language Models at Evaluating Instruction Following](https://arxiv.org/abs/2310.07641) makes evaluator quality itself an empirical question. A model label is not an independent oracle merely because it appears in a separate JSON file. Our native-model reference labels, repeated-family correlations, unknown model versions, and lack of human adjudication limit what the pilot can establish.

The expanded selected-development pilot, frozen inputs, baseline artifacts and measured results are documented in `docs/EVALUATION.md` and `evaluation/pilot/`. Those later runs supersede the earlier scaffold's not-yet-run status only for the explicitly measured pilot; they do not establish general superiority or end-to-end natural-language verification.
