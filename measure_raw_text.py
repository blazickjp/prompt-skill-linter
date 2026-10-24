#!/usr/bin/env python3
"""Comprehensive measurement of plain text checks.

Runs on raw case text without requiring contracts.
Scores TP only when diagnostic type matches label type.
"""
import json
from pathlib import Path
from prompt_skill_linter.engine import lint

ROOT = Path(__file__).parent

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

def map_label_type_to_code(label_type):
    """Map evaluation label types to diagnostic codes."""
    mapping = {
        'vague': 'VAGUE_DIRECTIVE',
        'undefined': 'UNDEFINED_TERM_PLAIN',
        'tension': None,  # No direct mapping
        'missing_requirement': None  # No direct mapping
    }
    return mapping.get(label_type)

def run_on_raw_text(case_id, case_text):
    """Run linter on raw case text without contract."""
    # Create minimal contract pointing to raw text
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        source_file = tmpdir / "source.txt"
        source_file.write_text(case_text, encoding='utf-8')
        
        contract = {
            'version': 1,
            'sources': [{'id': 's1', 'path': 'source.txt'}],
            'rules': [],  # No extracted rules
            'contexts': [{'id': 'c1', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        
        tools = {"tools": {}}
        runtime = {"service_call_budget": 30, "request_sizes": [], "max_plan_steps": 10}
        
        try:
            result = lint(contract, tools, runtime, tmpdir)
            plain_text_codes = ['VAGUE_DIRECTIVE', 'UNDEFINED_TERM_PLAIN']
            found_diags = [d for d in result['diagnostics'] if d['code'] in plain_text_codes]
            return found_diags
        except Exception as e:
            return None

def evaluate():
    """Evaluate on all cases with honest scoring."""
    cases = load_cases()
    split = load_split()
    
    results = {
        'dev': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'hits': [], 'misses': []},
        'held_out': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'hits': [], 'misses': []}
    }
    
    for split_name in ['dev', 'held_out']:
        for case_id in split[split_name]:
            case = cases[case_id]
            label_has_issue = case['label']['issue']
            label_type = case['label'].get('type')
            expected_code = map_label_type_to_code(label_type)
            
            diags = run_on_raw_text(case_id, case['text'])
            
            if diags is None:
                # Execution error - count as miss if labeled
                if label_has_issue:
                    results[split_name]['fn'] += 1
                    results[split_name]['misses'].append({
                        'case_id': case_id,
                        'label_type': label_type,
                        'reason': 'execution_error'
                    })
                else:
                    results[split_name]['tn'] += 1
                continue
            
            found_codes = [d['code'] for d in diags]
            found_issue = len(found_codes) > 0
            
            # TP only if we found an issue AND the code matches the expected type
            type_match = expected_code in found_codes if expected_code else False
            
            if label_has_issue and type_match:
                results[split_name]['tp'] += 1
                outcome = 'TP'
            elif not label_has_issue and found_issue:
                results[split_name]['fp'] += 1
                outcome = 'FP'
            elif label_has_issue and not type_match:
                results[split_name]['fn'] += 1
                outcome = 'FN'
                results[split_name]['misses'].append({
                    'case_id': case_id,
                    'label_type': label_type,
                    'expected_code': expected_code,
                    'found_codes': found_codes,
                    'reason': 'type_mismatch' if found_issue else 'not_detected'
                })
            else:
                results[split_name]['tn'] += 1
                outcome = 'TN'
            
            if found_issue:
                results[split_name]['hits'].append({
                    'case_id': case_id,
                    'outcome': outcome,
                    'label_type': label_type,
                    'expected_code': expected_code,
                    'found_codes': found_codes,
                    'text': case['text'][:80] + '...',
                    'diagnostics': [{'code': d['code'], 'term': d['witness'].get('term')} 
                                   for d in diags]
                })
    
    return results

def format_results(results):
    """Format results for display."""
    output = []
    output.append("=== Plain Text Checks Evaluation (Raw Text) ===\n")
    
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
                output.append(f"    Label: {hit['label_type']} (expects {hit['expected_code']})")
                output.append(f"    Found: {', '.join(hit['found_codes'])}")
                output.append(f"    Text: {hit['text']}")
                for diag in hit['diagnostics']:
                    output.append(f"      {diag['code']}: {diag['term']}")
            output.append("")
        
        if split_results['misses']:
            output.append(f"Misses in {split_name}:")
            for miss in split_results['misses']:
                output.append(f"  {miss['case_id']} (label: {miss['label_type']})")
                output.append(f"    Reason: {miss['reason']}")
                if 'found_codes' in miss:
                    output.append(f"    Expected: {miss['expected_code']}, Found: {miss['found_codes']}")
            output.append("")
    
    return '\n'.join(output)

def main():
    results = evaluate()
    print(format_results(results))
    
    # Save to JSON
    output = {
        'version': 2,
        'check_type': 'raw_text_plain_checks',
        'dev': {
            'tp': results['dev']['tp'],
            'fp': results['dev']['fp'],
            'tn': results['dev']['tn'],
            'fn': results['dev']['fn'],
            'precision': results['dev']['tp'] / (results['dev']['tp'] + results['dev']['fp']) 
                        if (results['dev']['tp'] + results['dev']['fp']) > 0 else None,
            'recall': results['dev']['tp'] / (results['dev']['tp'] + results['dev']['fn'])
                     if (results['dev']['tp'] + results['dev']['fn']) > 0 else 0.0
        },
        'held_out': {
            'tp': results['held_out']['tp'],
            'fp': results['held_out']['fp'],
            'tn': results['held_out']['tn'],
            'fn': results['held_out']['fn'],
            'precision': results['held_out']['tp'] / (results['held_out']['tp'] + results['held_out']['fp'])
                        if (results['held_out']['tp'] + results['held_out']['fp']) > 0 else None,
            'recall': results['held_out']['tp'] / (results['held_out']['tp'] + results['held_out']['fn'])
                     if (results['held_out']['tp'] + results['held_out']['fn']) > 0 else 0.0
        }
    }
    
    with open(ROOT / 'evaluation/final_corpus/measurements_plain_text.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved results to evaluation/final_corpus/measurements_plain_text.json")

if __name__ == '__main__':
    main()
