#!/usr/bin/env python3
"""Measure plain text checks on the evaluation corpus."""
import json
from pathlib import Path
from prompt_skill_linter.engine import lint

ROOT = Path(__file__).parent

def load_cases():
    cases_dir = ROOT / "evaluation/final_corpus/cases"
    cases = {}
    for f in sorted(cases_dir.glob("*.json")):
        with open(f) as fp:
            case = json.load(fp)
            cases[case['id']] = case
    return cases

def load_split():
    with open(ROOT / "evaluation/final_corpus/split.json") as f:
        return json.load(f)

def run_linter_on_case(case_id):
    """Run linter on a case and return whether it found an error."""
    contract_path = ROOT / "evaluation/final_corpus/contracts" / f"{case_id}.contract.json"
    
    if not contract_path.exists():
        return False, None
    
    with open(contract_path) as f:
        contract = json.load(f)
    
    tools = {"tools": {}}
    runtime = {"service_call_budget": 30, "request_sizes": [], "max_plan_steps": 10}
    
    try:
        result = lint(contract, tools, runtime, contract_path.parent)
        
        # Check for plain text issues
        plain_text_codes = ['VAGUE_DIRECTIVE', 'UNDEFINED_TERM_PLAIN']
        found_plain_text_issue = any(
            d['code'] in plain_text_codes 
            for d in result['diagnostics']
        )
        
        plain_text_diags = [
            d for d in result['diagnostics'] 
            if d['code'] in plain_text_codes
        ]
        
        return found_plain_text_issue, plain_text_diags
    except Exception as e:
        print(f"Error processing {case_id}: {e}")
        return False, None

def evaluate():
    """Evaluate plain text checks on the corpus."""
    cases = load_cases()
    split = load_split()
    
    results = {
        'dev': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'hits': []},
        'held_out': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'hits': []}
    }
    
    for split_name in ['dev', 'held_out']:
        for case_id in split[split_name]:
            case = cases[case_id]
            label_has_issue = case['label']['issue']
            
            found_issue, diags = run_linter_on_case(case_id)
            
            # Calculate TP/FP/TN/FN
            if label_has_issue and found_issue:
                results[split_name]['tp'] += 1
                outcome = 'TP'
            elif not label_has_issue and found_issue:
                results[split_name]['fp'] += 1
                outcome = 'FP'
            elif label_has_issue and not found_issue:
                results[split_name]['fn'] += 1
                outcome = 'FN'
            else:
                results[split_name]['tn'] += 1
                outcome = 'TN'
            
            # Record hits
            if found_issue:
                hit_info = {
                    'case_id': case_id,
                    'outcome': outcome,
                    'label_type': case['label'].get('type'),
                    'text': case['text'],
                    'diagnostics': []
                }
                
                if diags:
                    for d in diags:
                        hit_info['diagnostics'].append({
                            'code': d['code'],
                            'term': d['witness'].get('term'),
                            'reason': d['witness'].get('reason')
                        })
                
                results[split_name]['hits'].append(hit_info)
    
    return results

def main():
    print("=== Plain Text Checks Evaluation ===\n")
    
    results = evaluate()
    
    for split_name in ['dev', 'held_out']:
        split_results = results[split_name]
        tp, fp, tn, fn = split_results['tp'], split_results['fp'], split_results['tn'], split_results['fn']
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        
        print(f"=== {split_name.upper()} SPLIT ===")
        print(f"TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
        print(f"Precision: {precision:.2f}" if precision is not None else "Precision: N/A (no predictions)")
        print(f"Recall: {recall:.2f}")
        print()
        
        if split_results['hits']:
            print(f"New hits in {split_name}:")
            for hit in split_results['hits']:
                label_type = hit['label_type'] or 'no_label'
                match_str = "✓ MATCH" if hit['outcome'] == 'TP' else "✗ FALSE POSITIVE"
                print(f"  {hit['case_id']} [{hit['outcome']}] (label: {label_type}) {match_str}")
                print(f"    Text: {hit['text'][:80]}...")
                for diag in hit['diagnostics']:
                    print(f"    Found: {diag['code']} - {diag['term']} ({diag['reason'][:60]}...)")
                print()
        else:
            print(f"No hits in {split_name}\n")
    
    # Summary
    print("\n=== SUMMARY ===")
    for split_name in ['dev', 'held_out']:
        split_results = results[split_name]
        tp, fp, tn, fn = split_results['tp'], split_results['fp'], split_results['tn'], split_results['fn']
        print(f"{split_name}: {tp} TP, {fp} FP, {tn} TN, {fn} FN")

if __name__ == '__main__':
    main()
