"""Reproduce the new, separately frozen research development controls offline.

This runner only reads inert source snapshots and calls the local checker. It
never imports, compiles, executes, or contacts anything named in those sources.
Historical corpora and reports are not rewritten; optional output is explicit.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from evaluation.scientific_workflows import local_path, read
from prompt_skill_linter.service import analyze

DEFAULT = Path(__file__).resolve().parents[1] / 'corpus/research_extensions'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(directory=DEFAULT):
    root = Path(directory)
    hashes = read(root / 'freeze.json')['sha256']
    if not hashes or 'manifest.json' not in hashes:
        raise ValueError('A frozen research manifest is required.')
    for name, expected in hashes.items():
        if digest(local_path(root, name)) != expected:
            raise ValueError('Frozen research input differs: ' + name)
    manifest = read(root / 'manifest.json')
    ids = set()
    for source in manifest['sources']:
        if source['path'] not in hashes or source['license_file'] not in hashes:
            raise ValueError('Source bytes and license must be frozen.')
        data = local_path(root, source['path']).read_bytes()
        actual_blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual_blob != source['git_blob']:
            raise ValueError('Pinned Git blob differs: ' + source['path'])
    for case in manifest['cases']:
        if case['id'] in ids:
            raise ValueError('Duplicate research case ID.')
        ids.add(case['id'])
        if case['origin'] not in ('natural_candidate', 'natural_control', 'synthetic_control'):
            raise ValueError('Research case origin must remain explicit.')
        if case['bundle'] not in hashes:
            raise ValueError('Case bundle is not frozen.')
        bundle = read(local_path(root, case['bundle']))
        if bundle['contract']['interpretation']['status'] != 'accepted':
            raise ValueError('Only explicitly reviewed projections can be reproduced.')
        for source in bundle['contract']['sources']:
            if source['path'] not in hashes or bundle['sources'][source['id']] != local_path(root, source['path']).read_text(encoding='utf-8'):
                raise ValueError('Bundle source differs from pinned bytes: ' + source['id'])
    return {'verified_files': len(hashes), 'cases': len(ids), 'manifest': manifest}


def reproduce(directory=DEFAULT):
    root = Path(directory)
    verified = verify(root)
    cases = []
    for case in verified['manifest']['cases']:
        report = analyze(read(local_path(root, case['bundle'])))
        if case['family'] == 'field_presence':
            result = report['field_checks'][0]
            observed = {'status': result['status'], 'error_count': report['summary']['error']}
            if 'missing_required_fields' in case['expected']:
                observed['missing_required_fields'] = result.get('missing_required_fields', [])
        elif case['family'] == 'trace_trigger':
            result = report['trace_checks'][0]
            observed = {'status': result['status'], 'trigger_status': result['trigger_coverage']['status'],
                        'first_trigger_path': result['trigger_coverage']['first_trigger_path'],
                        'error_count': report['summary']['error']}
        else:
            raise ValueError('Unsupported research case family.')
        if observed != case['expected']:
            raise AssertionError({'case': case['id'], 'expected': case['expected'], 'observed': observed})
        cases.append({'id': case['id'], 'origin': case['origin'], 'family': case['family'],
                      'result': observed, 'diagnostic_codes': [d['code'] for d in report['diagnostics']],
                      'bundle_digest': report['bundle_digest'], 'passed': True})
    return {'version': 1, 'input_freeze_sha256': digest(root / 'freeze.json'),
            'verified_files': verified['verified_files'], 'cases': cases,
            'counts_by_origin': dict(sorted(Counter(c['origin'] for c in cases).items())),
            'scope': verified['manifest']['scope'], 'limitations': verified['manifest']['limitations']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'reproduce'))
    parser.add_argument('--directory', type=Path, default=DEFAULT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = (verify(args.directory) if args.command == 'verify' else reproduce(args.directory))
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    else:
        print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
