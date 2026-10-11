"""Offline command-line interface; never executes declared tool calls."""
import argparse
import json
from pathlib import Path
import sys

from .engine import ContractError, lint
from .schema import unique_object


def load(path):
    if Path(path).stat().st_size > 16_000_000:
        raise ContractError('JSON input exceeds the 16 MB CLI limit.')
    with open(path, encoding='utf-8') as stream:
        value = json.load(stream, object_pairs_hook=unique_object, parse_constant=lambda value: (_ for _ in ()).throw(ContractError('Non-finite JSON numbers are unsupported.')))
    if not isinstance(value, dict):
        raise ContractError(f'{path}: expected a JSON object')
    return value


def render(report):
    summary = report['summary']
    lines = ['Prompt/skill linter: declared-contract analysis',
             f"Errors: {summary['error']}; warnings: {summary['warning']}; information: {summary['info']}"]
    for d in report['diagnostics']:
        lines.append(f"\n[{d['class']}/{d['severity']}] {d['code']}")
        if d.get('interpretation_status'):
            lines.append('  Interpretation: ' + d['interpretation_status'])
        for assumption in d['assumptions']:
            lines.append('  Assumption: ' + assumption)
        for limitation in d.get('provenance_limitations', []):
            lines.append('  Provenance limitation: ' + limitation)
        if d['responsible_rule_set']:
            lines.append('  Rules: ' + ', '.join(d['responsible_rule_set']))
        for src in d['source_spans']:
            lines.append(f"  {src['source_id']}:{src['start_line']}-{src['end_line']}: {src['quote']}")
        lines.append('  Context: ' + json.dumps(d['triggering_context'], sort_keys=True))
        lines.append('  Witness: ' + json.dumps(d['witness'], sort_keys=True))
        for repair in d['repairs']:
            lines.append(f"  Repair (changes {repair['changes_requirement']}): {repair['proposal']}")
    for check in report['resource_checks']:
        w = check['witness']
        lines.append(f"\nResource check n={check['request_size']}: {check['status']}; lower bound {w['lower_bound_calls']}, budget {w['budget']}")
    lines.append('\nA lower-bound pass is not a completion guarantee. Checks apply to the reviewed contract; semantic fidelity to source prose is not certified.')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'serve':
        command = argparse.ArgumentParser(description='Launch the loopback-only Prompt Skill Studio.')
        command.add_argument('--port', type=int, default=8765)
        options = command.parse_args(argv[1:])
        if not 0 <= options.port <= 65535:
            command.error('port must be between 0 and 65535')
        from .server import serve
        serve(options.port)
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract', help='reviewed JSON contract; source paths resolve relative to this file')
    parser.add_argument('--tools', required=True, help='JSON tool manifest')
    parser.add_argument('--runtime', required=True, help='JSON runtime configuration')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    parser.add_argument('--output', help='write report to a file instead of stdout')
    parser.add_argument('--contract-out', help='write the validated, inspectable contract to JSON')
    parser.add_argument('--baseline', help='previous JSON report; add diagnostic-set regressions')
    parser.add_argument('--strict-mode', help='check tool schemas for provider strict mode compatibility (comma-separated: openai,anthropic or "all")')
    args = parser.parse_args(argv)
    try:
        contract, manifest, runtime = load(args.contract), load(args.tools), load(args.runtime)
        strict_providers = None
        if args.strict_mode:
            if args.strict_mode == 'all':
                strict_providers = ['openai', 'anthropic']
            else:
                strict_providers = [p.strip() for p in args.strict_mode.split(',')]
        report = lint(contract, manifest, runtime, Path(args.contract).parent, strict_providers=strict_providers)
        if args.baseline:
            baseline = load(args.baseline)
            def key(d):
                return json.dumps([d['code'], sorted(d['responsible_rule_set']), d['triggering_context']], sort_keys=True)
            previous = {key(d) for d in baseline['diagnostics']}
            current = {key(d) for d in report['diagnostics']}
            report['regressions'] = {'introduced': sorted(current - previous), 'resolved': sorted(previous - current),
                                     'interpretation': 'Diagnostic identity comparison only; not semantic equivalence.'}
        output = json.dumps(report, indent=2, ensure_ascii=False) + '\n' if args.format == 'json' else render(report)
        if args.output:
            Path(args.output).write_text(output, encoding='utf-8')
        else:
            sys.stdout.write(output)
        if args.contract_out:
            Path(args.contract_out).write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
        return 1 if report['summary']['error'] else 0
    except (ContractError, OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        sys.stderr.write(f'Input error: {exc}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
