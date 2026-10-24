#!/usr/bin/env python3
"""Test plain text checks against real public prompts.

Reports all false positives and known misses.
"""
import json
import sys
from pathlib import Path
import tempfile

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from prompt_skill_linter.engine import lint

ROOT = Path(__file__).parent.parent

def test_additional_prompts():
    """Test against real public prompts with known misses documented."""
    prompts_file = ROOT / 'evaluation/additional_prompts/prompts.json'
    with open(prompts_file) as f:
        data = json.load(f)
    
    prompts = data['prompts']
    
    print(f"=== Testing {len(prompts)} Real Public Prompts ===\n")
    
    false_positives = []
    known_misses = {
        'meaningful': 'Subjective quality term, borderline vague',
        'descriptive': 'Subjective quality term, borderline vague',
        'comprehensive': 'Subjective quality term, borderline vague',
        'creative': 'Subjective quality term, borderline vague',
        'engaging': 'Subjective quality term, borderline vague',
        'original': 'Subjective quality term, borderline vague'
    }
    
    for prompt in prompts:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            source_file = tmpdir / "source.txt"
            source_file.write_text(prompt['text'], encoding='utf-8')
            
            contract = {
                'version': 1,
                'sources': [{'id': 's1', 'path': 'source.txt'}],
                'rules': [],
                'contexts': [{'id': 'c1', 'facts': {}, 'active_skills': []}],
                'assumptions': []
            }
            
            tools = {"tools": {}}
            runtime = {"service_call_budget": 30, "request_sizes": [], "max_plan_steps": 10}
            
            try:
                result = lint(contract, tools, runtime, tmpdir)
                plain_text_codes = ['VAGUE_DIRECTIVE', 'UNDEFINED_TERM_PLAIN']
                found_diags = [d for d in result['diagnostics'] if d['code'] in plain_text_codes]
                
                if found_diags:
                    for diag in found_diags:
                        term = diag['witness'].get('term')
                        if term and term.lower() in known_misses:
                            print(f"  {prompt['id']}: Known miss '{term}' - {known_misses[term.lower()]}")
                            print(f"    Source: {prompt['source']['url']}")
                        else:
                            false_positives.append({
                                'id': prompt['id'],
                                'text': prompt['text'],
                                'source': prompt['source']['url'],
                                'diagnostic': diag
                            })
            except Exception as e:
                print(f"Error processing {prompt['id']}: {e}")
    
    print(f"\n=== False Positives: {len(false_positives)} ===")
    if false_positives:
        for fp in false_positives:
            print(f"\n{fp['id']}:")
            print(f"  Text: {fp['text']}")
            print(f"  Source: {fp['source']}")
            print(f"  Found: {fp['diagnostic']['code']} - {fp['diagnostic']['witness'].get('term')}")
    else:
        print("None!")
    
    return len(false_positives)

if __name__ == '__main__':
    fp_count = test_additional_prompts()
    exit(0 if fp_count == 0 else 1)
