# Research decisions and unimplemented directions

Research date: 2026-10-10. This document separates the two implemented narrow
extensions from hypotheses that still require their own declarations, natural
cases and evaluation. It does not enable model calls or background experiments.

## Decision summary

1. **Implemented:** enabled-event trigger coverage for existing trace monitors.
   Formal vacuity research supports asking whether a passing property can be
   exercised; only the narrow event-reachability question is claimed here.
2. **Implemented:** source-grounded flat-record field-presence compatibility.
   A pinned manual-branch candidate and a separately scoped real helper control
   motivated a small explicit contract. See [extension evidence and limits](RESEARCH_EXTENSIONS.md).
3. **Research only:** prompt perplexity/surprisal, behavioral robustness testing,
   richer policy changes, authorization identity, evidence identity and trust
   propagation. No scores or heuristic diagnostics for these are shipped.

## Perplexity: keep research-only and off by default

A text's likelihood under a fixed scorer, tokenizer and serialization is not the
probability that the target agent will comply. Prompt-only, task-instantiated,
and answer-conditional scores answer different questions. Masked-LM
pseudo-perplexity is not causal perplexity; input probabilities cannot be
replaced by generated-answer log probabilities or a model's guessed number.
[Perplexity measurement documentation](https://huggingface.co/docs/transformers/en/perplexity).

Evidence is mixed and task-dependent. Gonen et al. support within-task selection
among reasonable prompt candidates, while Leidinger et al. find no general
monotone perplexity/accuracy relationship across their systematically varied
prompts. These concern particular models, tasks and instantiated inputs; neither
establishes a universal static quality score for long skill documents.
[Gonen et al., Findings EMNLP 2023](https://aclanthology.org/2023.findings-emnlp.679/),
[Leidinger et al., Findings EMNLP 2023](https://aclanthology.org/2023.findings-emnlp.618/).

Fluent attacks also defeat an equation of low perplexity with safety. AutoDAN
provides one evaluated example of semantically meaningful jailbreaks bypassing
a perplexity defense. A particular attack-filter result does not validate
arbitrary-English injection detection. [Liu et al., ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/f83cb637e159e789f5576ff6848874de-Paper-Conference.pdf).

An exploratory arithmetic check of author-released Perplection artifacts found
aggregate mean-score/accuracy Spearman correlations of -0.536 and -0.786 for
Douban and Waimai, respectively. Each aggregate has **seven templates**, not
thousands of independent prompts. Within-template score/correctness correlations
were weak and mixed in direction (-0.089 to +0.106; -0.137 to +0.169). These are
masked-LM pseudo-perplexities; exact scorer/target checkpoints and original run
settings cannot be established from the selected CSVs. The selected Waimai
artifact mean and accuracy differ from the paper's pilot table, so this is not a
paper replication. It is descriptive evidence about aggregation, not validation
of a linter feature. No new inference was run. [Perplection paper](https://aclanthology.org/2023.acl-long.128/),
[pinned released scores](https://github.com/GeorgeLuImmortal/Perplection_ACL2023/tree/7aba388534475050924fa343787bc9a50118c20f/datasets_ppl_score),
[pinned prediction artifacts](https://github.com/GeorgeLuImmortal/Perplection_ACL2023/tree/7aba388534475050924fa343787bc9a50118c20f/zeroshot_results).

Before considering a local-surprisal review aid, require actual input-token
probabilities, fully pinned scorer/tokenizer/serialization, source consent and
cost bounds, multilingual/code/path/schema controls, family-disjoint held-out
natural defects, simpler exact baselines, document-level false-positive analysis,
and measured reviewer usefulness. Lowering perplexity must not be an automatic
repair objective. Raw third-party review-text datasets and unverified-license
study scripts are not bundled with this product.

## Robustness: test behavior under controlled changes

Published work supports testing sensitivity, not declaring prompts bad based on
length, position, punctuation, or number of requirements. Constraint-order
experiments use measured adherence and conflict-filtered requirements;
FORMATSPREAD varies presentation using a specified grammar. Only demonstrably
independent conjunctions may be reordered, and only presentation-only syntax may
be perturbed without changing the requested behavior. [Zeng et al., ACL Findings
2025](https://aclanthology.org/2025.findings-acl.646/), [Sclar et al., ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/6c0e99d736da621403018ca7b32b1a4d-Paper-Conference.pdf).

Separate real output-contract failures from harmless wording changes. Exact JSON
is a legitimate constraint when explicitly requested; synonym variation is not
necessarily an error on free-text tasks. Evaluator choice can substantially
change apparent sensitivity. [Hua et al., EMNLP 2025](https://aclanthology.org/2025.emnlp-main.1006/).

A future optional testing layer should pin model, tools, decoding, output budget
and fixtures; compare one-factor mutations with unchanged-repeat controls;
measure all-requirement as well as individual pass rates; preserve original
exceptions, roles, chronology and exact strings; and confirm any selected repair
on held-out families. Context placement, total length and irrelevant additions
need separate interventions. No tested-effect sizes for this product are known.

## Instruction interaction: next explicit-model questions

Beyond trigger coverage, useful hypotheses include semantic policy-change and
rule-removal analysis, explicit example/trace conformance, reviewed scope and
capability relations, and reachable traps or possible nontermination. These are
different from existing diagnostic-ID diffs or existential goal reachability.
In particular, one successful path does not prove progress on every path.

WIRE motivates source-grounded co-governance witnesses and separating encoded
contradictions from behavioral evidence. Its selected-trial results do not
establish English contradiction proofs, deployment-wide prevalence, or causal
benefit from removing or reordering rules. [WIRE v2](https://arxiv.org/pdf/2605.27784v2).

Before adding these features, specify the finite semantics and quantifiers;
retain unknown activation and bounded search; require natural source observations,
matched compatible controls, and independent abstraction review; and keep
synthetic mutations distinct from natural discovery.

## Tool and evidence contracts: narrower than security certification

Promising future declared-model questions are:

- **Authorization binding:** approval from an allowed issuer must cover the
  action, target and consequential payload actually used. A generic Boolean
  approval fact cannot authenticate or bind those identities.
- **Evidence subject/execution binding:** a fresh verification of artifact A
  cannot automatically support delivery of B or a different execution attempt.
- **Trust-boundary propagation:** transformations and delegation should preserve
  declared integrity and disclosure restrictions unless an authorized explicit
  endorsement/declassification applies.
- **Evidence-strength preservation:** an acceptance receipt, self-report, valid
  signature, observed readback and complete trace support different predicates;
  relaying a claim does not make it independent evidence.

Relevant primary foundations include [OpenAI Agents SDK approval state guidance](https://openai.github.io/openai-agents-python/human_in_the_loop/#keep-approval-state-on-the-server),
[SLSA verification](https://slsa.dev/spec/v1.2/verifying-artifacts), and
[CaMeL's provenance-based controls](https://arxiv.org/html/2503.18813v2).
These motivate contract designs; their system results do not establish this
linter's performance. No natural defect is established here for these four
unimplemented checks. They must not become regex-based maliciousness scores,
inferred real-world consent, or universal prompt-injection safety claims.
