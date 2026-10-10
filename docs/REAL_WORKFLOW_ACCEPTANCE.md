# Host-assisted workflow release acceptance

This extends the previously accepted local 1.0 product. It is not acceptance of
an arbitrary-English verifier, live scientific execution, or a paid provider.
The checklist below is updated only from verified final-snapshot evidence.

## Required evidence

- [x] Restore the preceding release reproducibly: all 155 files match the Git
  blobs at `b6a478105f7648b62087469944d80bb22af0e63a`.
- [x] Establish the clean baseline: 89 backend tests, 7 evaluation tests and
  40 frozen pilot files pass.
- [x] Preserve action source spans and abstraction assumptions in workflow
  reports, with exact-quote validation and visible gaps for legacy actions.
- [x] Add a reusable offline, review-gated, source-frozen workflow runner with
  separate natural/deployment/synthetic strata and unknown outcomes.
- [x] Freeze at least three documented real workflow families with provenance,
  complete selected source files, deployment assumptions and exclusions.
- [x] Freeze independent native reference labels before revealing extraction
  or checker results; preserve review disagreements rather than relabeling to
  fit the implementation.
- [x] Audit native extraction and retain original candidates separately from
  any accepted projection or later correction.
- [x] Compare a separate blind plain native-model review with the deterministic
  checker; report all cases, coverage, abstentions and limitations.
- [x] Verify the optional host adapter's protocol, explicit review boundary,
  malformed-input handling and no-execution behavior.
- [x] Run final backend/evaluation tests, source freezes, deterministic replay,
  JavaScript checks and installed-wheel smoke after integration.
- [ ] Publish the exact tested snapshot and verify required CI, including the
  existing browser journeys. A local test pass is not a remote CI pass.

## Runnable local workflow

The released Studio and CLI remain usable without a model account or API key:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install .
prompt-skill-linter --help
prompt-skill-linter serve
```

Open the loopback address printed by the server. Import source text, inspect
candidate interpretations, explicitly accept only the supported interpretation,
and run the checker. Plain English that was not translated remains visible;
it is never converted into an implicit clean result. Source text and declared
tool names are inert data.

CLI exit status 0 means no error-level findings, not complete coverage. Warning
diagnostics and incomplete translation may still exist. CI users must inspect
the JSON `coverage.incomplete` and warning count when those should block a build;
the default CLI exit policy remains backward-compatible.

The optional host-model adapter lets a compatible coding-agent host propose
contracts using its existing model. See `agent-host.md` for its exact command
and review workflow. This is a convenience
integration, not evidence that model interpretation is correct or free of the
host service's own usage limits. No client settings are changed automatically.

Reproduce the real-workflow deterministic evidence after the corpus is frozen:

```sh
python -m evaluation.scientific_workflows verify
python -m evaluation.scientific_workflows mechanical --output /tmp/workflows.json
```

## Remaining limitations

- Native model extraction and labels are provisional, selected-development
  observations, not independent human gold or a representative benchmark.
- A finite path is conditional on the reviewed preconditions/effects and the
  stated deployment. Type lineage, numerical/data validity, human attestations
  and scientific correctness are not inferred or certified.
- All modeled actions are deterministic. Only enumerated contexts and search
  bounds are checked. Unknown prerequisites must not silently become false.
- Successful analysis of a projection does not validate omitted source text.
- No paid OpenAI provider calls, live-provider accuracy/cost study, hosted
  deployment or actual scientific tool execution are included in this release.
- Native model calls are documented observations. Re-running Python reproduces
  deterministic checking/scoring, not the original stochastic model call.
- MCP protocol smoke tests do not demonstrate interoperability with every host;
  any host that was not actually exercised must be listed as untested.

Acceptance concerns a reliable local host-assisted review-and-check workflow,
not a guarantee that every composed skill set is satisfiable or executable.

## Evidence summary for final snapshot review

- Three workflow families, 13 frozen cases; 47/47 raw quote/hash checks and
  271/271 action/rule span checks. Original native inputs and sparse replay
  derivatives are explicitly separated and original candidates rehydrate exactly.
- Two native arms: 4 issue, 5 no_issue, 4 abstain each. Conservative checker:
  4 issue, 9 abstain; all global full-source checks remain incomplete. No natural
  positive recall or superiority claim is available.
- Two extraction-model flaws corrected after independent review. The new trace
  monitors reproduce them only as declared post-audit regressions. Independent
  bounded enumeration covers 4,320 exhaustive small models and 1,000 seeded
  randomized comparisons; no source scientific actions were executed.
- Official MCP SDK 1.26.0 and 1.29.0 subprocess interoperability passed. Client
  product-specific setup UI remains untested; the runtime has no MCP dependency.
- Remote publication/current-commit CI is the remaining external release gate.

Final local verification: 161 backend/security/trace/corpus tests, 7 evaluation
tests, 40 historical and 64 scientific frozen files, seeded trace oracle, structural
scanner boundary regression, compileall and JavaScript state tests passed.
The rebuilt installed 1.1 wheel passed its final smoke: trace module, MCP adapter,
Studio assets and canonical analysis all load and work outside the checkout.
