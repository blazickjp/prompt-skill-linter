# Architecture

Browser Studio → same-origin local HTTP API → source normalization → reviewed contract validation → independent bounded analysis fragments → source-linked report → explicit what-if/diff/export.

- `web/`: dependency-free browser application; no CDN or telemetry. Static assets are copied into installed wheels.
- `server.py`: loopback routing, origin/host/content-type checks, request/concurrency limits, static security headers and safe error envelopes.
- `service.py`: stateless bundle materialization, report formatting, examples, field diffs, hypothetical edits, explorer and reproducible ZIP export.
- `extraction.py`: deterministic annotation candidates, untranslated-prose evidence and explicit acceptance.
- `provider.py`: optional fixed-endpoint Responses API adapter; local environment configuration, per-request consent, exact-span verification and mandatory review. Offline default.
- `schema.py` and `contract.schema.json`: the accepted versioned shape; a small validator for its used keywords, independently cross-checked against a standards implementation in development.
- `engine.py`: provenance, references, obligations, fragment guards, diagnostics and conditional interpretation boundaries.
- `sat.py`: bounded CNF search and audited deletion cores.
- `planner.py`: bounded prerequisite/effect graph exploration and paths.
- `cli.py`: readable/JSON reports, contract export, report baseline comparison and Studio launcher.
- `evaluation/`, `corpus/`: frozen cases, provisional labels, measured outputs and explicit research limitations; no tool replay.

No source file authorizes a command. Source text is written only into a fresh temporary directory under validated relative paths, read as UTF-8, and removed. API exports regenerate analysis rather than accepting fabricated caller-supplied reports. No source history is stored server-side. The browser may retain its current in-memory workspace; provider keys never reach it.

The fragments deliberately reject unsupported cross-representation assumptions rather than silently combine incompatible semantics. Their reports share a common schema and UI, but that does not make them a unified unrestricted theory solver.
