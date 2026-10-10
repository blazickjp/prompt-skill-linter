# Public-source corpus slice

Eight cases from five separately maintained public repositories, pinned to commits retrieved on 2026-10-10. Three cases have executable **manual finite encodings**. This is a deliberately small development slice, not a representative benchmark or independent gold set.

`manifest.json` preserves source URL, commit, Git blob SHA, original line coordinates, exact minimal fragments where needed, author interpretation, limitations, and independent-review slots. Local `.excerpt.txt` line numbers differ from upstream line numbers; both are recorded. Fragments are not full instructions and must not be treated as full-policy replacements. Full upstream artifacts are not redistributed. Anthropic's PDF skill declares a proprietary license.

- `openhands_config_bug.json`: candidate overlap in testing duties; intended-exception interpretation remains plausible.
- `mini_call_count.json`: compatible lower-bound and exact-count wording, projected to a Boolean lower bound.
- `pdf_subscript.json`: prohibition of Unicode glyphs and use of XML markup concern distinct representations.
- The import-placement exception and PR-consent ambiguity are manifest-only cases, not executable checker fixtures.

Natural observations, ambiguous candidates, valid exceptions, and negative controls are explicit categories. There are no verified natural hard-conflict labels here. Synthetic mutations belong in `examples/synthetic`, must carry synthetic provenance, and must never inflate the count of natural issues.

The author wrote the finite encodings and proposed labels. A separate blind model reviewer inspected the original five cases; see `independent_review.json`. The expanded eight-case set is also included in the frozen task-level pilot under `evaluation/pilot/`. The PR-consent case has an unresolved author/reviewer disagreement. Even reviewed labels are not human gold. The later provisional task-level native-model pilot and extraction coverage measurement are recorded in `docs/EVALUATION.md`; no behavioral rollout or general superiority test is claimed.

See `docs/research.md` for the evaluation protocol and honest status boundaries.
