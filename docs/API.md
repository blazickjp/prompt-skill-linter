# Local API v1

Launch `python -m prompt_skill_linter serve --port 8765`. The server binds only to IPv4 loopback. It serves the Studio and JSON API from the same origin; no separate frontend server or CORS setup is needed. Sources are treated as data, never commands. Stateless operations use a fresh temporary source directory and remove it afterward. No source persistence or telemetry is implemented.

POST requests require `Content-Type: application/json`. The maximum body is 2,000,000 bytes. Host must equal `127.0.0.1:<port>` or `localhost:<port>`; browser Origin must match one of those exact origins. Cross-site fetch metadata and preflights are rejected. Two concurrent analyses are permitted. The local server is not a multi-user or Internet-facing service.

## Bundle

`{contract, sources, tools, runtime}` where contract follows `contract.schema.json`, sources maps each source ID to its complete UTF-8 text, tools is `{tools:{toolId:{arguments:[...],required:[...],capabilities:[...]}}}`, and runtime supplies `service_call_budget`, `request_sizes`, and/or `max_plan_steps`.

Source paths are unique, canonical safe relative paths. Absolute paths, hidden components, traversal, URLs, backslashes, drive paths, file/directory overlap and reserved export-name collisions are rejected. They never authorize reading a local file. Up to 32 documents and 1.5 MB combined source text.

## Routes

- GET `/api/health`: version, local-only status, capabilities and optional provider configuration state. Never returns a key.
- GET `/api/examples`: `{examples:[{id,title,description,bundle}]}`. Built-in bulk, CNF composition and approval/refusal workflow.
- GET `/api/schema`: accepted versioned contract JSON Schema.
- POST `/api/analyze`: body is bundle; returns diagnostics, resource checks, workflow checks with state graphs, constraint checks, summary, coverage, `analysis_status`, `report_text` and deterministic bundle digest. Status is `findings`, `incomplete` or `no_findings_in_scope`, never certified-correct.
- POST `/api/extract`: `{sources:[{id,name,text}],provider:"offline"|"dry_run"|"openai",consent?}`; returns draft, candidates, unsupported spans and provider-request state. Sources are not executed. A draft cannot be analyzed before acceptance.
- POST `/api/accept`: `{draft,accepted_candidate_ids:[...]}`; returns bundle, accepted/excluded IDs and unsupported spans. Revalidates exact source provenance. This explicit review action is not a truth claim.
- POST `/api/what-if`: `{bundle,changes:[{target:"runtime",field:"service_call_budget",value:32}]}`; returns before/after reports, diagnostic and contract diffs, named changed requirements and hypothetical bundle. Runtime fields also support request_sizes and max_plan_steps. Rule target requires id and allows priority, kind, effect, when, exceptions or clause. Changes never mutate the original or rewrite source prose.
- POST `/api/diff`: `{before:bundle,after:bundle}`; returns structured field differences; not semantic equivalence.
- POST `/api/explore`: `{bundle,workflow_id?,context_id?}`; returns matching workflow graph/path results or scope-separated CNF truth tables and resource checks. Display truncation is explicit.
- POST `/api/export`: `{bundle}`; recomputes the report and returns application/zip with bundle, source files, contract/tools/runtime, JSON/readable reports and replay instructions. Exported sources always use generated `source_text/source-NNNN.txt` names; rewritten paths and inert `source_mapping.json` preserve provenance without allowing Python-module/configuration shadowing. Caller-supplied reports are not trusted.

Errors are `{error:{code,message}}`, with 400 for malformed/unsupported input, 403 for host/origin violations, 404 for unknown routes/assets, 413 for body limits, 415 for content type, 429 for concurrency limits and 502 for I/O/provider failure. Errors do not include stack traces or provider bodies.

## Extraction grammar

Offline binding candidates require one complete line:

- `REQUIRE approved=true`
- `FORBID upload=true`
- `PERMIT refuse=true`
- `PREFER concise=true`
- `CLAUSE approved | !upload`

Names are simple identifiers. No implicit condition, scope, specificity or hierarchy is inferred. Other prose is explicitly untranslated; modal prose gets warning-only candidates. Acceptance retains excluded IDs/untranslated counts and emits `INCOMPLETE_SOURCE_COVERAGE` even when no rules were accepted. All candidates remain editable through the bundle's explicit rule representation before analysis.

## Optional model provider

Set `OPENAI_API_KEY` and `LINTER_OPENAI_MODEL` in the local server environment. No browser key field or API to read/write keys exists. Only `https://api.openai.com/v1/responses` is supported. The user must explicitly opt in for each request with consent `{send_sources:true,destination:"https://api.openai.com/v1/responses",acknowledge_cost:true}`. This sends the displayed source texts and schema to OpenAI and can incur API charges. Redirects and environment proxies are refused. `store:false` is requested; it is not a guarantee overriding the provider's data policies.

Responses use `text.format` JSON Schema, then local type/span/quote validation and mandatory review. Unknown/incomplete/refused responses do not become findings. Provider omissions remain incomplete coverage. Live requests were not run during development; mock integration tests do not establish real model accuracy, pricing or account compatibility.

Official references, checked October 10, 2026: [Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create), [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).


Candidate evidence states are separate: `representation_supported` means the candidate fits the implemented grammar/schema, `interpretation_reviewed` records explicit acceptance, and `runtime_grounded` remains false because no live observations or tools are executed. `supported` remains a compatibility alias for representation support only. Reports similarly identify runtime grounding as a declared snapshot, not verified telemetry. Source input objects accept only id/name/text; hidden extra metadata cannot silently enter a provider payload.

## 1.2 development report additions

`/api/analyze`, CLI JSON, local MCP analysis and replay exports share the same
additive contract/report schema. `field_contracts` is optional input; `field_checks`
is an output array even when empty. Each field check identifies its fixed scope,
context, activation, presence-only status, source spans and assumptions; active
checks expose guaranteed/optional output keys, missing/uncertain mandatory reads
and explicit adapter removals. See [contract details](contracts.md).

Existing `trace_checks` retain their safety fields and add `trigger_coverage`,
including a shortest in-bound event prefix when reachable. Coverage may be
unknown while safety is safe, and absence is informational only. Source-linked
findings use the existing generic diagnostic UI. A no-findings result never
certifies arbitrary prose, value correctness or runtime observations.

New codes: `REQUIRED_FIELD_NOT_PRODUCED` (conditional exact error),
`FIELD_PRESENCE_UNKNOWN` (warning), `TRACE_TRIGGER_UNREACHABLE` (information),
`TRACE_TRIGGER_COVERAGE_UNKNOWN` (information with incomplete coverage). Mixed
missing/uncertain field demands keep `coverage.incomplete` true. No extraction
provider support or arbitrary-English detection is added for these declarations.
