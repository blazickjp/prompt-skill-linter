#!/usr/bin/env python3
"""Test against additional real prompts to find false positives."""
import json
from pathlib import Path
import tempfile
from prompt_skill_linter.engine import lint

# Real prompts from various sources (not in corpus)
ADDITIONAL_PROMPTS = [
    {
        'id': 'external_01',
        'text': 'You are a helpful AI assistant. Respond to user queries with accurate information.'
    },
    {
        'id': 'external_02', 
        'text': 'Generate Python code following PEP 8 style guidelines. Use descriptive variable names.'
    },
    {
        'id': 'external_03',
        'text': 'Translate the following text to French. Maintain the original tone and meaning.'
    },
    {
        'id': 'external_04',
        'text': 'Review this code for security vulnerabilities. Check for SQL injection and XSS.'
    },
    {
        'id': 'external_05',
        'text': 'Create a README file with installation instructions. Include prerequisites and examples.'
    },
    {
        'id': 'external_06',
        'text': 'Summarize this article in 3 sentences. Focus on the main points and conclusions.'
    },
    {
        'id': 'external_07',
        'text': 'Debug this error: TypeError on line 42. Provide explanation and fix.'
    },
    {
        'id': 'external_08',
        'text': 'Write unit tests for this function. Cover edge cases and error handling.'
    },
    {
        'id': 'external_09',
        'text': 'Refactor this code to improve readability. Use meaningful names and add comments.'
    },
    {
        'id': 'external_10',
        'text': 'Analyze this data and create visualizations. Show trends over time.'
    }
]

def test_prompt(prompt_text):
    """Test a prompt and return diagnostics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        source_file = tmpdir / "source.txt"
        source_file.write_text(prompt_text, encoding='utf-8')
        
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
            return found_diags
        except Exception as e:
            return None

def main():
    print("=== Testing Additional Real Prompts ===\n")
    
    false_positives = []
    
    for prompt in ADDITIONAL_PROMPTS:
        diags = test_prompt(prompt['text'])
        
        if diags:
            false_positives.append({
                'id': prompt['id'],
                'text': prompt['text'],
                'diagnostics': [{'code': d['code'], 'term': d['witness'].get('term')} 
                               for d in diags]
            })
    
    if false_positives:
        print(f"Found {len(false_positives)} false positives:\n")
        for fp in false_positives:
            print(f"{fp['id']}:")
            print(f"  Text: {fp['text']}")
            for diag in fp['diagnostics']:
                print(f"    {diag['code']}: {diag['term']}")
            print()
    else:
        print("No false positives found on additional prompts!")
    
    # Also test all 32 corpus cases
    print("\n=== Testing All 32 Corpus Cases ===\n")
    cases_dir = Path('evaluation/final_corpus/cases')
    
    all_fps = []
    for f in sorted(cases_dir.glob("*.json")):
        with open(f) as fp:
            case = json.load(fp)
        
        # Only test cases labeled as no issue
        if not case['label']['issue']:
            diags = test_prompt(case['text'])
            if diags:
                all_fps.append({
                    'id': case['id'],
                    'text': case['text'][:100] + '...',
                    'diagnostics': [{'code': d['code'], 'term': d['witness'].get('term')} 
                                   for d in diags]
                })
    
    if all_fps:
        print(f"Found {len(all_fps)} false positives in corpus:\n")
        for fp in all_fps:
            print(f"{fp['id']}:")
            print(f"  Text: {fp['text']}")
            for diag in fp['diagnostics']:
                print(f"    {diag['code']}: {diag['term']}")
            print()
    else:
        print("No false positives found in corpus cases labeled as no issue!")

if __name__ == '__main__':
    main()
