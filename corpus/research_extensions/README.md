# Separately frozen research-extension development cases

This corpus is independent of the frozen v1.1 evaluations. It contains:

- `GH-MANUAL`: one natural **conditional** manual-fallback field mismatch candidate;
- `GH-HELPER`: one real normalized-helper field-presence control, in its own scope;
- eight `SYN-*` field controls and six `TRACE-*` event-coverage controls, all synthetic.

The labels are reviewed development projections, not human gold or observed
runtime outcomes. A compatible helper control means only key presence; no URL,
run-ID, tool-success or whole-workflow conclusion follows. The manual candidate
assumes a literal property read, successful closed projection, an active consumed
failing item, and no implicit alias.

Run from the repository root:

```sh
python -m evaluation.research_extensions verify
python -m evaluation.research_extensions reproduce --output /tmp/research-extensions.json
```

`freeze.json` records SHA-256 for 23 source, license, bundle and manifest files.
`manifest.json` records original commit/path/Git blob metadata and expected
results. The runner verifies embedded source identity and exact provenance while
performing offline analysis only. It does not import or execute the inert Python,
Go or shell instructions in `sources/` and makes no network/model/tool calls.

`openai/skills` source is covered by the included per-skill Apache-2.0 license.
`cli/cli` source carries the included MIT license and GitHub copyright notice.
Source file names ending `.txt` are deliberately inert snapshots, not runnable
package modules. Historical corpus files are not overwritten.

See [the technical scope, evidence and limits](../../docs/RESEARCH_EXTENSIONS.md).
