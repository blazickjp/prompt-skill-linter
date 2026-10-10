# Model card: reviewed-contract verification v1

## Intended use

A local specification workbench for authors of prompts and composed skills. It identifies mechanical problems in explicit declarations and conditional problems in reviewed finite models. It provides source-linked witnesses, inspected core reductions, hypothetical repairs and replay bundles. It is not a general English theorem prover, agent safety certification, compliance auditor or production-agent executor.

## Scientific basis and what is actually implemented

1. **Integer lower bounds.** The bulk fragment decides feasibility of three monotone inequalities over nonnegative integers by constructing the coordinate-wise minimum satisfying the active lower bounds. If that point violates an upper sum bound, every other candidate does too. Integer arithmetic avoids rounding errors. Deletion checks establish subset minimality only for the represented constraints.
2. **Propositional satisfiability.** Explicit CNF clauses use recursive branching and unit propagation, a small DPLL-style decision procedure. The [Davis, Logemann and Loveland paper](https://web.stanford.edu/class/cs357/DPLL62.pdf) is the foundational reference. This implementation is not an industrial SAT solver: it does not implement clause learning, proof logging or general SMT theories.
3. **Finite-state reachability.** BFS traverses deterministic prerequisite/effect transitions and records shortest action-count paths. The [Clarke, Emerson and Sistla finite-state verification paper](https://ix.cs.uoregon.edu/~michal/Classes/04u/fsv/readings/ClarkeEmersonSistla-86.pdf) provides broader model-checking context. This product implements reachability only, not that paper's full temporal-logic procedure, fairness, probabilistic transitions or concurrent interleavings.
4. **Extraction/checking separation.** Exact quote matching is a provenance check, not semantic validation. Candidates require review; omissions remain visible. See `docs/research.md` for WIRE's separate scope and the empirical evaluation protocol.

These are established techniques applied to narrow explicit contracts. We claim no new solver algorithm or measured superiority over strong model judges.

## Soundness envelope

A result is conditional on the contract, source interpretation, tool manifest, runtime snapshot and enumerated activation contexts. Hierarchy is resolved for supported Boolean/action fragments; explicit conditions and exceptions are equality maps. Permissions are not obligations. Contexts absent from the input are not quantified over.

CNF constraints are scoped, active requirements at one priority; mixed-priority formulas are rejected. A literal cannot simultaneously participate in a CNF and Boolean-effect fragment in the same active scope. Resource rules cannot also act as Boolean/action/tool-call clauses. These restrictions avoid pretending independent fragments are a complete joint semantics.

Reachability includes only declared actions. Missing tool IDs or invalid argument names make the corresponding declared action unavailable; tools are never called. The fallback action must be explicitly asserted compliant by the author. A compliant refusal can remain reachable while the advertised business goal is unavailable. That is not by itself contradictory effective instructions.

## Bounds and abstention

- Contract: up to 256 rules, 16 explicit contexts and 8 workflows.
- Boolean comparison work: at most 4,096 same-surface pairs.
- CNF: up to 64 active clauses per scope, 32 literals per clause, 24 distinct variables, 20,000 search nodes per solve and 100,000 cumulative nodes for core inspection.
- Planner: up to 64 actions, configurable depth 0–100 (default 20), at most 2,000 distinct states per analysis; graph display capped at 200 nodes/edges/blocked-action entries.
- Truth table display: at most 12 variables and 64 rows; truncation is explicit.
- HTTP: two concurrent requests, 2 MB request body, 32 source documents and 1.5 MB combined text. Offline extraction caps each source at 5,000 lines and at most 256 candidate rules.

A solver/planner cutoff yields unknown/incomplete diagnostics, never an impossibility proof. A reduced core is labeled minimal only if every recorded removal solve returns a satisfying witness. An arithmetic or model pass is not a completion guarantee.

## Extraction modes

Offline mode reliably maps only the documented line annotation grammar. It does not understand arbitrary English. Other text is preserved as untranslated evidence; accepting no candidates does not make that text clean.

The optional OpenAI adapter proposes inferred Boolean candidates under structured output constraints and verifies quotes before review. It sends data only after explicit opt-in, uses an environment-held key and fixed official endpoint, and is tested with mocked responses. No live provider validation or accuracy claim is made. Model omissions and unsupported lines remain incomplete coverage. A user approving a mistaken interpretation can still produce an incorrect source-level conclusion.

## Evaluation evidence

Unit/property/adversarial tests cover solver witness validity, bounds, hierarchy, permissions, exceptions, coactivation, source integrity, input errors, workflow feasibility, extraction omissions, explicit what-if changes and HTTP safety. Independently maintained real sources and synthetic cases are separated. The provisional matched native-model pilot and its unresolved labels belong in `docs/EVALUATION.md`; model agreement is not human gold.

Do not compare a mechanical checker given curated contracts against a judge given incomplete prose and call that an end-to-end advantage. Extraction coverage/fidelity, checking correctness and full-pipeline accuracy must be measured separately.

## Known risks and unsupported constructs

Semantic mistranslation, omitted context, implicit exceptions, ambiguous entity aliases, real runtime tool behavior, tool argument types, side effects, retries, failures, loops beyond bounds, temporal liveness and resource interaction across fragments are not fully modeled. Source excerpts may omit important surrounding instructions. Schema validity and exact quoting cannot resolve those risks.

The local server is designed for a single trusted user, not hostile local processes or public hosting. It has no account authentication, persistent database or multi-user authorization. It must remain on loopback. Browser-origin checks reduce cross-site attacks but do not defend against malware already running as the user. Exported source text remains untrusted data.
