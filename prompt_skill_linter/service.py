"""Stateless local application API. Uploaded source contents are inert text."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from .cli import render
from .engine import ContractError, lint
from .sat import truth_table


def normalize_bundle(bundle):
    if not isinstance(bundle, dict) or any(k not in bundle for k in ('contract', 'sources', 'tools', 'runtime')):
        raise ContractError('Bundle requires contract, sources, tools and runtime.')
    result = {key: deepcopy(bundle[key]) for key in ('contract', 'sources', 'tools', 'runtime')}
    if not isinstance(result['contract'], dict) or not isinstance(result['sources'], dict):
        raise ContractError('contract and sources must be objects.')
    if len(result['sources']) > 32:
        raise ContractError('At most 32 source documents are supported.')
    total = 0
    for sid, text in result['sources'].items():
        if not isinstance(sid, str) or not isinstance(text, str):
            raise ContractError('Sources must map source IDs to UTF-8 text.')
        total += len(text.encode('utf-8'))
    if total > 1_500_000:
        raise ContractError('Combined source text exceeds 1.5 MB.')
    paths = set()
    for source in result['contract'].get('sources', []):
        if not isinstance(source, dict) or not isinstance(source.get('path'), str) or source.get('id') not in result['sources']:
            raise ContractError('Every declared source must have supplied text and a relative path.')
        path = source['path']
        parts = PurePosixPath(path).parts
        if not path or path.startswith('/') or '\\' in path or ':' in path or '\x00' in path or any(p in ('..', '.', '') or p.startswith('.') for p in path.split('/')) or not parts:
            raise ContractError('Source paths must be safe relative paths without traversal, drive letters or URLs.')
        if path in paths or any(path.startswith(other + '/') or other.startswith(path + '/') for other in paths):
            raise ContractError('Source paths must be unique and cannot overlap files/directories.')
        reserved = {'bundle.json', 'report.json', 'report.txt', 'contract.json', 'tools.json', 'runtime.json', 'README.txt'}
        if path.split('/')[0] in reserved:
            raise ContractError('Source path collides with a reserved export artifact.')
        paths.add(path)
    return result


def analyze(bundle):
    bundle = normalize_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix='prompt-skill-linter-') as directory:
        root = Path(directory)
        for source in bundle['contract'].get('sources', []):
            path = root / source['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(bundle['sources'][source['id']], encoding='utf-8')
        report = lint(bundle['contract'], bundle['tools'], bundle['runtime'], root)
    report['analysis_status'] = 'findings' if report['summary']['error'] else ('incomplete' if report['coverage'].get('incomplete') else ('findings' if report['summary']['warning'] else 'no_findings_in_scope'))
    report['report_text'] = render(report)
    report['bundle_digest'] = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    report['analysis_notice'] = 'Only explicitly modeled contexts and features were checked. Unsupported or omitted prose is not certified.'
    return report


def contract_diff(before, after):
    before, after = normalize_bundle(before), normalize_bundle(after)
    changes = []

    def walk(a, b, path):
        if type(a) is not type(b):
            changes.append({'path': path, 'before': a, 'after': b})
        elif isinstance(a, dict):
            for key in sorted(a.keys() | b.keys()):
                if key not in a or key not in b:
                    changes.append({'path': path + '/' + key, 'before': a.get(key), 'after': b.get(key), 'operation': 'add' if key not in a else 'remove'})
                else:
                    walk(a[key], b[key], path + '/' + key)
        elif isinstance(a, list) and isinstance(b, list) and a and b and all(isinstance(x, dict) and isinstance(x.get('id'), str) for x in a + b):
            walk({x['id']: x for x in a}, {x['id']: x for x in b}, path)
        elif a != b:
            changes.append({'path': path, 'before': a, 'after': b})
    walk(before, after, '')
    return {'changes': changes, 'count': len(changes), 'semantic_equivalence_proven': False}


def report_diff(before, after):
    def key(d):
        return json.dumps([d['code'], sorted(d['responsible_rule_set']), d['triggering_context']], sort_keys=True)
    old, new = {key(d): d for d in before['diagnostics']}, {key(d): d for d in after['diagnostics']}
    return {'introduced': [new[k] for k in sorted(new.keys() - old.keys())],
            'resolved': [old[k] for k in sorted(old.keys() - new.keys())],
            'changed': [{'before': old[k], 'after': new[k]} for k in sorted(old.keys() & new.keys()) if old[k] != new[k]],
            'notice': 'Diagnostic identities and evidence are compared; this is not semantic equivalence.'}


def what_if(bundle, changes):
    original = normalize_bundle(bundle)
    modified = deepcopy(original)
    if not isinstance(changes, list) or not 1 <= len(changes) <= 32:
        raise ContractError('A what-if needs 1–32 explicit changes.')
    changed = []
    for change in changes:
        if not isinstance(change, dict) or set(change) - {'target', 'field', 'value', 'id'}:
            raise ContractError('Unsupported change shape.')
        target, field = change.get('target'), change.get('field')
        if target == 'runtime' and field in ('service_call_budget', 'max_plan_steps', 'request_sizes'):
            modified['runtime'][field] = deepcopy(change.get('value'))
            requirement = modified['contract'].get('bulk_model', {}).get('constraint_rules', {}).get('budget') if field == 'service_call_budget' else None
            changed.append({'requirement_id': requirement, 'target': target, 'field': field, 'value': change.get('value'), 'notice': 'Explicit scenario/requirement replacement; original source text is unchanged.'})
        elif target == 'rule' and field in ('priority', 'kind', 'effect', 'exceptions', 'when', 'clause'):
            matches = [r for r in modified['contract']['rules'] if r['id'] == change.get('id')]
            if len(matches) != 1:
                raise ContractError('Rule change refers to an unknown ID.')
            matches[0][field] = deepcopy(change.get('value'))
            changed.append({'requirement_id': change['id'], 'target': target, 'field': field, 'value': change.get('value'), 'notice': 'Reviewed interpretation changed; source prose has not been edited to match.'})
        else:
            raise ContractError('Unsupported what-if target or field; no change was applied.')
    modified['contract'].setdefault('assumptions', []).append('WHAT-IF ONLY: explicit requirement/interpretation changes are hypothetical and do not rewrite source prose.')
    before, after = analyze(original), analyze(modified)
    return {'before': before, 'after': after, 'diff': report_diff(before, after), 'contract_diff': contract_diff(original, modified),
            'changed_requirements': changed, 'bundle': modified, 'applied_to_original': False}


def counterexample_explorer(bundle, workflow_id=None, context_id=None):
    report = analyze(bundle)
    if workflow_id is not None:
        matches = [c for c in report['workflow_checks'] if c['workflow'] == workflow_id and (context_id is None or c['context_id'] == context_id)]
        if not matches:
            raise ContractError('No active workflow matches the requested ID/context.')
        return {'workflows': matches, 'notice': report['analysis_notice']}
    from .engine import active, activation_status
    tables = []
    for context in report['contract']['contexts']:
        if context_id is not None and context['id'] != context_id:
            continue
        groups = {}
        for rule in report['contract']['rules']:
            if 'clause' in rule and active(rule, context):
                key = (rule['scope']['entity'], rule['scope']['temporal'])
                groups.setdefault(key, []).append(rule)
        for scope, rules in groups.items():
            unresolved = [r for r in report['contract']['rules'] if 'clause' in r and activation_status(r, context) == 'unknown' and (r['scope']['entity'], r['scope']['temporal']) == scope]
            if unresolved:
                tables.append({'context_id': context['id'], 'scope': dict(zip(('entity', 'temporal'), scope)), 'rule_ids': [r['id'] for r in rules + unresolved], 'status': 'unknown', 'reason': 'unresolved_activation', 'rows': [], 'variables': [], 'truncated': False})
                continue
            tables.append({'context_id': context['id'], 'scope': dict(zip(('entity', 'temporal'), scope)),
                           'rule_ids': [r['id'] for r in rules], **truth_table([r['clause'] for r in rules])})
    return {'truth_tables': tables, 'resource_checks': report['resource_checks'], 'notice': report['analysis_notice']}


def export_bundle(bundle):
    bundle = normalize_bundle(bundle)
    source_mapping = []
    for index, source in enumerate(bundle['contract']['sources'], 1):
        original_path = source['path']
        source['path'] = f'source_text/source-{index:04d}.txt'
        source_mapping.append({'source_id': source['id'], 'original_path': original_path, 'export_path': source['path']})
    report = analyze(bundle)  # Recompute against inert exported filenames; never trust a supplied report.
    output = io.BytesIO()
    entries = {'source_mapping.json': json.dumps(source_mapping, indent=2), 'bundle.json': json.dumps(bundle, indent=2), 'report.json': json.dumps(report, indent=2),
               'report.txt': report['report_text'], 'contract.json': json.dumps(bundle['contract'], indent=2),
               'tools.json': json.dumps(bundle['tools'], indent=2), 'runtime.json': json.dumps(bundle['runtime'], indent=2),
               'README.txt': 'Run: python -m prompt_skill_linter contract.json --tools tools.json --runtime runtime.json\nSources are inert data. A pass does not certify full-policy correctness.\n'}
    for source in bundle['contract']['sources']:
        if source['path'] in entries:
            raise ContractError('Source path collides with an export artifact name.')
        entries[source['path']] = bundle['sources'][source['id']]
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in sorted(entries.items()):
            archive.writestr(name, text)
    return output.getvalue()


def examples():
    return json.loads(Path(__file__).with_name('data').joinpath('examples.json').read_text(encoding='utf-8'))
