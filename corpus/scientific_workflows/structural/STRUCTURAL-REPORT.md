# Pinned source structural baseline

Repository: K-Dense-AI/scientific-agent-skills
Commit: 92ace75ac21efe19a620434e0ca4e356081fe807

Result: 177 SKILL.md files; 675 explicit inline relative Markdown link occurrences outside fenced code; 673 targets exist in the complete pinned Git tree. The two raw missing targets are literal `url` placeholders in parenthetical citation-format examples (exa-search line 53 and parallel-web line 57). Contextual review excludes both. **Zero confirmed broken packaged references in this scope.**

This is not a scan of all dependencies, tool contracts, code-span file paths, external URLs, link anchors, reference-style Markdown links, executable correctness, or semantic instruction compatibility.

## Reproduction

Use a clean existing checkout at the pinned commit. No source scripts are executed by the scanner.

`python scan_explicit_links.py --checkout /path/to/scientific-agent-skills --output link-scan.json`

The scanner validates HEAD and a clean tracked working tree, requires exactly 177 tracked skills from git ls-tree (ignoring untracked files), reads their text, and compares normalized local link targets to Git's tracked path inventory. It does not install packages or contact services. Independently inspect raw candidates; the two exclusions and source lines are retained in link-scan.json.

## Files

- scan_explicit_links.py: independently written structural scanner.
- link-scan.json: original result plus contextual exclusion decisions.
- link-scan-reproduced.json: second raw reproduction of identical counts/candidates.
- source-inventory.json: 177 paths, captured SHA256, canonical SHA256 and Git blob SHA; all canonical Git blobs verified.
- tree.json: complete 3,497-entry Git tree; truncated=false.
- selected-source-manifest.json: 12 workflow-selected sources and license notes.
- neutral-cases.json: separately frozen 13-case, three-family workflow packet; this scan does not determine those outcomes.

Source captures written through apply_patch gained one terminal newline; provenance records this reversible transform and verifies each canonical Git blob. No instruction-bearing text or line locations changed. Raw source files are kept outside the product repository. Per-skill licenses vary; do not distribute them all under the root MIT license.

The workflow packet distinguishes constructed deployments/controls from documentation-only observational cases. It is not a recorded production user-traffic corpus or evidence of a naturally occurring source defect. Independent readers found a possible missing DOI-check prerequisite in the literature-review scenarios after freeze; preserve that qualification rather than editing the frozen inputs.

## Scanner boundary regression

python -m unittest -v test_scan_explicit_links

Passed: an untracked extra skill leaves the denominator and results unchanged; changing a tracked skill rejects the checkout. The public scanner requires --checkout and has no internal workspace default. After correction, rerunning its scan core against the captured pinned tree yields exactly the same 177/675/673 counts and two candidates.
