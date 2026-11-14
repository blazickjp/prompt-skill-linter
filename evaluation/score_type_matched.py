#!/usr/bin/env python3
"""Type-matched evaluation scorer for the prompt-skill-linter.

Scores diagnostics from main's engine against the 32-case evaluation corpus.
A hit is a TP only when the diagnostic type matches the label type.

This scorer is generalized to work with whatever diagnostics main's engine
emits, not specific plain-text check codes.
"""
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from prompt_skill_linter.engine import lint

ROOT = Path(__file__).parent.parent

# Label-to-diagnostic-code mapping table
# Each entry maps a label type to the set of diagnostic codes that would
# correctly identify that issue type.
LABEL_TO_CODES = {
    # Vague directives: currently no diagnostic in main's engine
    'vague': set(),
    
    # Undefined terms: UNDEFINED_TERM from vocabulary checks
    'undefined': {'UNDEFINED_TERM'},
    
    # Tension between rules: INCOMPATIBLE_OBLIGATIONS, AXIOM_CONFLICT
    'tension': {'INCOMPATIBLE_OBLIGATIONS', 'AXIOM_CONFLICT'},
    
    # Missing requirements: several diagnostics could catch this
    # INCOMPLETE_SOURCE_COVERAGE suggests untranslated requirements
    'missing_requirement': {'INCOMPLETE_SOURCE_COVERAGE'},
}


def load_cases():
    """Load all evaluation cases."""
    cases_dir = ROOT / "evaluation/final_corpus/cases"
    cases = {}
    for f in sorted(cases_dir.glob("*.json")):
        with open(f) as fp:
            case = json.load(fp)
            cases[case['id']] = case
    return cases


def load_split():
    """Load dev/held-out split."""
    with open(ROOT / "evaluation/final_corpus/split.json") as f:
        return json.load(f)


def map_label_to_diagnostic_codes(label_type):
    """Map evaluation label types to expected diagnostic codes.
    
    Returns:
        set of diagnostic codes, or None if no mapping exists
    """
    return LABEL_TO_CODES.get(label_type, None)


def run_linter_on_case(case_id):
    """Run linter on a case using its corpus contract.
    
    Args:
        case_id: The case identifier (e.g., 'anthropic_01')
    
    Returns:
        List of diagnostics
    
    Raises:
        Exception: If linting fails for any reason
    """
    contracts_dir = ROOT / "evaluation/final_corpus/contracts"
    contract_file = contracts_dir / f"{case_id}.contract.json"
    
    if not contract_file.exists():
        raise FileNotFoundError(f"Contract file not found: {contract_file}")
    
    with open(contract_file) as f:
        contract = json.load(f)
    
    manifest = {"tools": {}}
    runtime = {
        "service_call_budget": 30,
        "request_sizes": [],
        "max_plan_steps": 10
    }
    
    result = lint(contract, manifest, runtime, contracts_dir)
    return result.get('diagnostics', [])


def evaluate():
    """Evaluate on all cases with type-matched scoring.
    
    Scoring rule: A wrong-code diagnostic on a labeled case counts as both
    FN (missed the right type) and FP (wrong-type hit).
    """
    cases = load_cases()
    split = load_split()
    
    results = {
        'dev': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'hits': [], 'misses': []},
        'held_out': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'hits': [], 'misses': []},
        'execution_errors': []
    }
    
    for split_name in ['dev', 'held_out']:
        for case_id in split[split_name]:
            case = cases[case_id]
            label_has_issue = case['label']['issue']
            label_type = case['label'].get('type')
            expected_codes = map_label_to_diagnostic_codes(label_type) if label_type else None
            
            try:
                diags = run_linter_on_case(case_id)
            except Exception as e:
                results['execution_errors'].append({
                    'case_id': case_id,
                    'split': split_name,
                    'error': str(e)
                })
                # Don't count as TN/FN, just skip
                continue
            
            # Get diagnostic codes from results
            found_codes = {d['code'] for d in diags}
            found_issue = len(found_codes) > 0
            
            # Type-matched scoring: TP only if diagnostic code matches expected code
            type_match = bool(expected_codes and found_codes & expected_codes) if expected_codes is not None else False
            
            if label_has_issue and type_match:
                # Correct diagnostic type for a labeled case: TP
                results[split_name]['tp'] += 1
                outcome = 'TP'
            elif label_has_issue and found_issue and not type_match:
                # Wrong-code diagnostic on a labeled case: both FN and FP
                results[split_name]['fn'] += 1
                results[split_name]['fp'] += 1
                outcome = 'FN+FP'
                results[split_name]['misses'].append({
                    'case_id': case_id,
                    'label_type': label_type,
                    'expected_codes': list(expected_codes) if expected_codes else [],
                    'found_codes': list(found_codes),
                    'reason': 'type_mismatch'
                })
            elif label_has_issue and not found_issue:
                # No diagnostic on a labeled case: FN only
                results[split_name]['fn'] += 1
                outcome = 'FN'
                results[split_name]['misses'].append({
                    'case_id': case_id,
                    'label_type': label_type,
                    'expected_codes': list(expected_codes) if expected_codes else [],
                    'found_codes': list(found_codes),
                    'reason': 'not_detected'
                })
            elif not label_has_issue and found_issue:
                # Diagnostic on an unlabeled case: FP
                results[split_name]['fp'] += 1
                outcome = 'FP'
            else:
                # No diagnostic on an unlabeled case: TN
                results[split_name]['tn'] += 1
                outcome = 'TN'
            
            if found_issue:
                results[split_name]['hits'].append({
                    'case_id': case_id,
                    'outcome': outcome,
                    'label_type': label_type,
                    'expected_codes': list(expected_codes) if expected_codes else [],
                    'found_codes': list(found_codes),
                    'text': case['text'][:80] + ('...' if len(case['text']) > 80 else ''),
                    'diagnostics': [{'code': d['code'], 
                                    'severity': d['severity'],
                                    'witness': d.get('witness', {})} 
                                   for d in diags]
                })
    
    return results


def format_results(results):
    """Format results for display."""
    output = []
    output.append("=== Type-Matched Evaluation (Main Engine) ===\n")
    
    # Report execution errors first if any
    if results['execution_errors']:
        output.append("=== EXECUTION ERRORS ===")
        for err in results['execution_errors']:
            output.append(f"  {err['case_id']} ({err['split']}): {err['error']}")
        output.append("")
    
    for split_name in ['dev', 'held_out']:
        split_results = results[split_name]
        tp, fp, tn, fn = split_results['tp'], split_results['fp'], split_results['tn'], split_results['fn']
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        
        output.append(f"=== {split_name.upper()} SPLIT ===")
        output.append(f"TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
        output.append(f"Precision: {precision:.2f}" if precision is not None else "Precision: N/A")
        output.append(f"Recall: {recall:.2f}")
        output.append("")
        
        if split_results['hits']:
            output.append(f"Hits in {split_name}:")
            for hit in split_results['hits']:
                match_str = "✓" if hit['outcome'] == 'TP' else "✗ FP"
                output.append(f"  {hit['case_id']} [{hit['outcome']}] {match_str}")
                output.append(f"    Label: {hit['label_type']} (expects {hit['expected_codes']})")
                output.append(f"    Found: {', '.join(sorted(hit['found_codes']))}")
                output.append(f"    Text: {hit['text']}")
                for diag in hit['diagnostics'][:3]:  # Show first 3 diagnostics
                    output.append(f"      {diag['code']} ({diag['severity']})")
            output.append("")
        
        if split_results['misses']:
            output.append(f"Misses in {split_name}:")
            for miss in split_results['misses']:
                output.append(f"  {miss['case_id']} (label: {miss['label_type']})")
                output.append(f"    Reason: {miss['reason']}")
                if 'found_codes' in miss:
                    output.append(f"    Expected: {miss['expected_codes']}, Found: {miss['found_codes']}")
            output.append("")
    
    return '\n'.join(output)


def main():
    results = evaluate()
    print(format_results(results))
    
    # Exit non-zero if there were execution errors
    if results['execution_errors']:
        print(f"\n❌ {len(results['execution_errors'])} execution error(s) occurred", file=sys.stderr)
        sys.exit(1)
    
    # Calculate metrics for JSON output
    metrics = {}
    for split_name in ['dev', 'held_out']:
        tp, fp, tn, fn = (results[split_name][k] for k in ['tp', 'fp', 'tn', 'fn'])
        metrics[split_name] = {
            'tp': tp,
            'fp': fp,
            'tn': tn,
            'fn': fn,
            'precision': tp / (tp + fp) if (tp + fp) > 0 else None,
            'recall': tp / (tp + fn) if (tp + fn) > 0 else 0.0
        }
    
    # Save to JSON (use .tmp path so it doesn't dirty the working tree)
    output = {
        'version': 1,
        'scorer_type': 'type_matched_main_engine',
        'label_to_code_mapping': {k: list(v) for k, v in LABEL_TO_CODES.items()},
        **metrics
    }
    
    output_file = ROOT / 'evaluation/scorer_results.tmp.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
        f.write('\n')
    
    print(f"\nSaved results to {output_file.relative_to(ROOT)}")


if __name__ == '__main__':
    main()
