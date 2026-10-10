"""Offline, source-pinned workflow evaluation; never calls models or source tools.

Input catalog and accepted finite projections are frozen separately from model
predictions. No label can silently turn an unreviewed extraction into evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import time

from prompt_skill_linter.schema import unique_object
from prompt_skill_linter.service import analyze
from evaluation.run import metric_slice, validate_predictions, write

DEFAULT = Path(__file__).resolve().parents[1] / 'corpus/scientific_workflows'
ORIGINS = {'natural', 'synthetic_control', 'deployment_probe'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_path(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('Corpus paths must be nonempty relative paths.')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Corpus paths must stay within the corpus directory.')
    root = Path(root).resolve()
    result = (root / name).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Corpus symlinks must stay within the corpus directory.')
    return result


def verify(directory=DEFAULT):
    root = Path(directory)
    frozen = read(root / 'freeze.json')
    hashes = frozen.get('sha256')
    if not isinstance(hashes, dict) or not hashes or 'catalog.json' not in hashes:
        raise ValueError('A nonempty freeze with catalog.json is required.')
    for name, expected in hashes.items():
        path = local_path(root, name)
        if not isinstance(expected, str) or len(expected) != 64 or not path.is_file() or digest(path) != expected:
            raise ValueError('Frozen input differs: ' + name)
    catalog = read(root / 'catalog.json')
    cases = catalog.get('cases')
    if catalog.get('version') != 1 or not isinstance(cases, list) or not cases:
        raise ValueError('Expected version 1 catalog with nonempty cases.')
    seen = set()
    for case in cases:
        cid = case.get('id')
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError('Cases require unique nonempty IDs.')
        seen.add(cid)
        if case.get('origin') not in ORIGINS or not isinstance(case.get('family'), str):
            raise ValueError('Cases require family and explicit origin stratum.')
        if case.get('query') != 'completion_reachability':
            raise ValueError('Unsupported query; this adapter only evaluates completion reachability.')
        review = case.get('review', {})
        if review.get('status') not in ('accepted_projection', 'partial', 'abstain'):
            raise ValueError('Each case requires an explicit extraction review status.')
        if not isinstance(review.get('rationale'), str) or not review['rationale'].strip():
            raise ValueError('Each extraction review requires its rationale.')
        bundle_name = case.get('bundle')
        if review['status'] == 'accepted_projection' and not bundle_name:
            raise ValueError('Accepted projection requires a frozen bundle.')
        if bundle_name:
            if bundle_name not in hashes:
                raise ValueError('Bundle must be included in the input freeze.')
            bundle = read(local_path(root, bundle_name))
            if review['status'] == 'accepted_projection' and bundle.get('contract', {}).get('interpretation', {}).get('status') != 'accepted':
                raise ValueError('Accepted projection cannot analyze an unaccepted candidate.')
        for required in case.get('evidence_files', []):
            local_path(root, required)
            if required not in hashes:
                raise ValueError('Referenced evidence must be frozen: ' + required)
    return {'verified_files': len(hashes), 'cases': len(cases), 'catalog': catalog}


def classify(report):
    """Classify only finite completion support, never an arbitrary prose policy."""
    checks = report.get('workflow_checks', [])
    codes = {d['code'] for d in report.get('diagnostics', [])}
    if not checks:
        return 'abstain', 'No active, supported workflow was analyzed.'
    if any(c.get('status') == 'unknown' for c in checks) or any('ACTIVATION' in code or 'BOUND' in code or 'UNKNOWN' in code for code in codes):
        return 'abstain', 'Activation or exploration is unresolved; non-discovery is not impossibility.'
    if any(c.get('status') == 'unreachable' and c.get('search_exhaustive') for c in checks):
        return 'issue', 'At least one requested completion has no path in the exhaustive reviewed finite projection; this is not a prose contradiction.'
    if any(c.get('status') != 'reachable' for c in checks):
        return 'abstain', 'No conclusive completion result for every active workflow.'
    # A separate Boolean/CNF or exact declaration error means an apparent path
    # cannot establish the complete modeled policy, even though it is displayed.
    if report.get('summary', {}).get('error'):
        return 'abstain', 'A path exists but other modeled errors prevent a whole-projection no-issue judgment.'
    semantic = [d for d in report.get('diagnostics', []) if d.get('class') == 'semantic_warning' and d['code'] != 'INCOMPLETE_SOURCE_COVERAGE']
    if semantic:
        return 'abstain', 'Unresolved modeled semantics prevent a definitive projection judgment.'
    return 'no_issue', 'An explicit completion path exists for each active workflow in the reviewed projection; omitted prose remains outside this result.'


def mechanical(directory=DEFAULT):
    root = Path(directory)
    verified = verify(root)
    predictions = []
    reports = {}
    started = time.perf_counter()
    for case in verified['catalog']['cases']:
        start = time.perf_counter()
        entry = {k: case[k] for k in ('id', 'family', 'origin')}
        entry.update(tokens=None, cost=None, coverage_scope='reviewed_projection',
                     global_source_check='abstain: full-source compatibility and scientific correctness are not certified')
        if case['review']['status'] != 'accepted_projection':
            entry.update(label='abstain', rationale=case['review']['rationale'], codes=[], source_coverage=None)
        else:
            report = analyze(read(local_path(root, case['bundle'])))
            label, rationale = classify(report)
            entry.update(label=label, rationale=rationale, codes=[d['code'] for d in report['diagnostics']],
                         source_coverage=report.get('coverage'), bundle_digest=report['bundle_digest'],
                         workflows=[{k: c.get(k) for k in ('workflow', 'context_id', 'status', 'goal_path', 'fallback_path', 'search_exhaustive', 'bounds')} for c in report['workflow_checks']])
            reports[case['id']] = report
        entry['latency_seconds'] = time.perf_counter() - start
        predictions.append(entry)
    package = Path(__file__).resolve().parents[1] / 'prompt_skill_linter'
    return {'version': 1, 'arm': 'mechanical_reviewed_projection', 'model': None,
            'input_freeze_sha256': digest(root / 'freeze.json'),
            'backend_sha256': {p.name: digest(p) for p in sorted(package.glob('*.py'))},
            'adapter_sha256': digest(__file__), 'latency_seconds': time.perf_counter() - started,
            'tokens': None, 'cost': None, 'predictions': predictions, 'reports': reports,
            'limitations': ['Conditional finite projections, not automatic English verification.',
                            'Source exclusions do not disappear when a projected path is found.',
                            'Source/model preparation and review latency are excluded.',
                            'No paid API or source-declared tool was executed.']}


def score(directory, mechanical_data, model_data, references, additional_models=()):
    root = Path(directory)
    cases = verify(root)['catalog']['cases']
    if mechanical_data.get('input_freeze_sha256') != digest(root / 'freeze.json'):
        raise ValueError('Mechanical predictions were not produced from this frozen input snapshot.')
    ids = {c['id'] for c in cases}
    refs = references.get('labels', [])
    refmap = {r['id']: r for r in refs}
    if len(refs) != len(ids) or set(refmap) != ids or any(r.get('label') not in ('issue', 'no_issue', 'abstain') for r in refs):
        raise ValueError('References must label every case exactly once.')
    arms = {}
    def measured_slice(selected, predictions):
        result = metric_slice(selected, predictions, refmap)
        counts = result['counts']
        tp, tn, fp, fn = (counts.get(k, 0) for k in ('tp', 'tn', 'fp', 'fn'))
        def divide(a, b):
            return a / b if b else None
        result.update(selective_false_positive_rate=divide(fp, fp + tn),
                      positive_coverage=divide(tp + fn, counts.get('reference_positive', 0)),
                      negative_coverage=divide(tn + fp, counts.get('reference_negative', 0)),
                      population_false_alarm_rate=result['false_positive_rate'],
                      false_positive_rate_denominator='all reference negatives including abstentions; not measured specificity')
        return result
    for data in (mechanical_data, model_data, *additional_models):
        validate_predictions(data, ids)
        arm = data.get('arm')
        if not isinstance(arm, str) or not arm or arm in arms:
            raise ValueError('Distinct named arms are required.')
        pred = {p['id']: p for p in data['predictions']}
        arms[arm] = {'all': measured_slice(cases, pred),
                     'by_origin': {origin: measured_slice([c for c in cases if c['origin'] == origin], pred) for origin in sorted({c['origin'] for c in cases})},
                     'by_family': {family: measured_slice([c for c in cases if c['family'] == family], pred) for family in sorted({c['family'] for c in cases})},
                     'model': data.get('model'), 'cost': data.get('cost'), 'tokens': data.get('tokens')}
    return {'version': 1, 'input_freeze_sha256': digest(root / 'freeze.json'), 'arms': arms, 'limitations': [
        'Selected development corpus, native-model reference labels, correlated errors possible; no human gold.',
        'Finite reviewed projections and raw-source model review have different preparation costs and coverage.',
        'Natural findings are separate from synthetic controls and deployment probes.',
        'No superiority conclusion or live scientific execution validation follows from these scores.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'mechanical', 'score'])
    parser.add_argument('--directory', type=Path, default=DEFAULT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--mechanical', type=Path)
    parser.add_argument('--model', type=Path, nargs='+')
    parser.add_argument('--references', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'verify':
        result = {k: v for k, v in verify(args.directory).items() if k != 'catalog'}
    elif args.command == 'mechanical':
        result = mechanical(args.directory)
    else:
        if not all((args.mechanical, args.model, args.references)):
            parser.error('score requires --mechanical, --model and --references')
        models = [read(path) for path in args.model]
        result = score(args.directory, read(args.mechanical), models[0], read(args.references), models[1:])
    if args.output:
        write(args.output, result)
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
