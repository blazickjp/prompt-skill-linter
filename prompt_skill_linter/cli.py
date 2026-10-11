"""Offline command-line interface; never executes declared tool calls."""
import argparse
import json
from pathlib import Path
import sys

from .engine import ContractError, lint
from .schema import unique_object
from .mutate import generate_mutants, classify_mutant, compute_mutation_score, MutationResult


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


def run_mutation_testing(contract, manifest, runtime, root, max_mutants=None, operator_filter=None, output_format='text'):
    """Run mutation testing and return results."""
    from .engine import validate
    
    original_report = lint(contract, manifest, runtime, root)
    mutants = generate_mutants(contract, manifest, max_mutants, operator_filter)
    
    results = []
    for mutant in mutants:
        # First, validate the mutant's schema
        try:
            validate(mutant.contract, manifest, runtime, root)
            mutant_is_valid = True
        except Exception:
            mutant_is_valid = False
        
        # Now try to lint it
        if not mutant_is_valid:
            # Schema validation failed - this is an INVALID mutant
            result = MutationResult(
                mutant=mutant,
                status='INVALID',
                original_diagnostics=frozenset(),
                mutant_diagnostics=None,
                error='Schema validation rejected mutant'
            )
        else:
            # Schema is valid, try linting
            try:
                mutant_report = lint(mutant.contract, manifest, runtime, root)
                result = classify_mutant(mutant, original_report, mutant_report)
            except Exception as e:
                # Linting crashed on a schema-valid mutant - this is a CRASHED mutant (linter bug)
                result = MutationResult(
                    mutant=mutant,
                    status='CRASHED',
                    original_diagnostics=frozenset(),
                    mutant_diagnostics=None,
                    error=str(e)
                )
        results.append(result)
    
    stats = compute_mutation_score(results)
    surviving_mutants = [r for r in results if r.status == 'SURVIVED']
    invalid_mutants = [r for r in results if r.status == 'INVALID']
    crashed_mutants = [r for r in results if r.status == 'CRASHED']
    
    if output_format == 'json':
        return json.dumps({
            'statistics': stats,
            'surviving_mutants': [
                {
                    'id': r.mutant.id,
                    'operator': r.mutant.operator,
                    'description': r.mutant.description,
                    'pointer': r.mutant.pointer,
                    'hint': r.hint()
                }
                for r in surviving_mutants
            ],
            'invalid_mutants': [
                {
                    'id': r.mutant.id,
                    'operator': r.mutant.operator,
                    'description': r.mutant.description,
                    'pointer': r.mutant.pointer,
                    'error': r.error
                }
                for r in invalid_mutants
            ],
            'crashed_mutants': [
                {
                    'id': r.mutant.id,
                    'operator': r.mutant.operator,
                    'description': r.mutant.description,
                    'pointer': r.mutant.pointer,
                    'error': r.error
                }
                for r in crashed_mutants
            ]
        }, indent=2) + '\n'
    else:
        lines = ['Contract Mutation Testing Report', '=' * 50, '']
        lines.append(f"Total mutants: {stats['total_mutants']}")
        lines.append(f"Killed: {stats['killed']}")
        lines.append(f"Survived: {stats['survived']}")
        lines.append(f"Equivalent (suspected): {stats['equivalent_suspected']}")
        lines.append(f"Invalid: {stats['invalid']}")
        lines.append(f"Crashed: {stats['crashed']}")
        lines.append(f"Mutation score: {stats['mutation_score']:.2%}")
        lines.append('')
        
        lines.append('Per-operator statistics:')
        lines.append('-' * 50)
        for op, op_stats in sorted(stats['operator_stats'].items()):
            lines.append(f"{op}:")
            lines.append(f"  Total: {op_stats['total']}, Killed: {op_stats['killed']}, "
                        f"Survived: {op_stats['survived']}, Equivalent: {op_stats['equivalent']}, "
                        f"Invalid: {op_stats['invalid']}, Crashed: {op_stats['crashed']}")
        lines.append('')
        
        if surviving_mutants:
            lines.append(f'Surviving mutants ({len(surviving_mutants)}):')
            lines.append('-' * 50)
            for r in surviving_mutants:
                lines.append(f"[{r.mutant.id}] {r.mutant.operator}")
                lines.append(f"  {r.mutant.description}")
                lines.append(f"  Location: {r.mutant.pointer}")
                lines.append(f"  Hint: {r.hint()}")
                lines.append('')
        
        if invalid_mutants:
            lines.append(f'Invalid mutants ({len(invalid_mutants)}):')
            lines.append('-' * 50)
            for r in invalid_mutants:
                lines.append(f"[{r.mutant.id}] {r.mutant.operator}")
                lines.append(f"  {r.mutant.description}")
                lines.append(f"  Location: {r.mutant.pointer}")
                lines.append(f"  Error: {r.error}")
                lines.append('')
        
        if crashed_mutants:
            lines.append(f'Crashed mutants ({len(crashed_mutants)}):')
            lines.append('-' * 50)
            for r in crashed_mutants:
                lines.append(f"[{r.mutant.id}] {r.mutant.operator}")
                lines.append(f"  {r.mutant.description}")
                lines.append(f"  Location: {r.mutant.pointer}")
                lines.append(f"  Error: {r.error}")
                lines.append('')
        
        lines.append('Note: Mutation testing is performed in-memory only.')
        lines.append('No source files or contracts are modified on disk.')
        lines.append('Invalid mutants violate schema constraints and are excluded from the mutation score.')
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
    parser.add_argument('--mutate', action='store_true', help='run contract mutation testing')
    parser.add_argument('--max-mutants', type=int, help='maximum number of mutants to generate')
    parser.add_argument('--operators', help='comma-separated list of operators to include')
    args = parser.parse_args(argv)
    try:
        contract, manifest, runtime = load(args.contract), load(args.tools), load(args.runtime)
        
        if args.mutate:
            operator_filter = set(args.operators.split(',')) if args.operators else None
            output = run_mutation_testing(
                contract, manifest, runtime, Path(args.contract).parent,
                max_mutants=args.max_mutants,
                operator_filter=operator_filter,
                output_format=args.format
            )
            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
            else:
                sys.stdout.write(output)
            return 0
        
        report = lint(contract, manifest, runtime, Path(args.contract).parent)
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
