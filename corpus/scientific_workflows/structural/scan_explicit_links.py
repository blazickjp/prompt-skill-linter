"""Conservative source-integrity scan; reads only a clean pinned checkout."""
import argparse
import json
import posixpath
import re
import subprocess
from pathlib import Path

PINNED_COMMIT = '92ace75ac21efe19a620434e0ca4e356081fe807'
EXPECTED_SKILLS = 177


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args], text=True)


def inspect_checkout(checkout):
    commit = git(checkout, 'rev-parse', 'HEAD').strip()
    if commit != PINNED_COMMIT:
        raise ValueError('Checkout must be at pinned commit')
    if git(checkout, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('Tracked working tree must be clean')
    # -z preserves unusual filenames; -t includes all tracked directory entries.
    paths = set(git(checkout, 'ls-tree', '-rz', '-t', '--name-only', 'HEAD').rstrip('\0').split('\0'))
    skills = sorted(p for p in paths if re.fullmatch(r'skills/[^/]+/SKILL\.md', p))
    if len(skills) != EXPECTED_SKILLS:
        raise ValueError(f'Expected {EXPECTED_SKILLS} tracked skill files; found {len(skills)}')
    return paths, skills


def scan(checkout, paths, skills):
    results = []
    counts = {'skills': 0, 'explicit_relative_links': 0, 'existing': 0, 'excluded': 0}
    for rel in skills:
        counts['skills'] += 1
        fenced = False
        for i, line in enumerate((checkout / rel).read_text().splitlines(), 1):
            if re.match(r'^\s*(```|~~~)', line):
                fenced = not fenced
                continue
            if fenced:
                continue
            for match in re.finditer(r'(?<!!)\[[^\]\n]+\]\(([^\s)]+)(?:\s+[^)]*)?\)', line):
                target = match.group(1).strip('<>')
                if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith(('#', '/', '//')):
                    continue
                target = target.split('#')[0].split('?')[0]
                if not target or re.search(r'[{}<>*$]', target):
                    counts['excluded'] += 1
                    continue
                counts['explicit_relative_links'] += 1
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
                if resolved in paths:
                    counts['existing'] += 1
                else:
                    results.append({'source': rel, 'line': i, 'text': line, 'target': target, 'resolved': resolved,
                                    'source_url': f'https://github.com/K-Dense-AI/scientific-agent-skills/blob/{PINNED_COMMIT}/{rel}#L{i}'})
    return {'commit': PINNED_COMMIT, 'tree_truncated': False,
            'method': 'Pinned tracked skills only. Heuristic explicit inline relative Markdown links outside fenced code; excludes images, schemes, anchors, absolute paths and obvious templates. Compare normalized targets with complete tracked Git tree; raw candidates require contextual review.',
            'counts': counts, 'raw_candidates': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('link-scan.json'))
    args = parser.parse_args()
    try:
        paths, skills = inspect_checkout(args.checkout)
        report = scan(args.checkout, paths, skills)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
