#!/usr/bin/env python3
"""Debug why anthropic_02 isn't being caught."""
import json
from pathlib import Path
from prompt_skill_linter.engine import lint
import re

ROOT = Path("/workspace")
contract_path = ROOT / "evaluation/final_corpus/contracts/anthropic_02.contract.json"

# Load contract
with open(contract_path) as f:
    contract = json.load(f)

# Get the quote
quote = contract['rules'][0]['source']['quote']
print(f"Quote: {quote}")
print()

# Test pattern matching
print("Testing capitalized terms pattern:")
for match in re.finditer(r'\b([A-Z][a-z]+)\s*[-:]\s*[a-z]', quote):
    print(f"  Found: {match.group(1)}")
print()

# Test criteria pattern
cap_terms = []
for match in re.finditer(r'\b([A-Z][a-z]+)\s*[-:]\s*[a-z]', quote):
    cap_terms.append(match.group(1))

for term in cap_terms:
    criteria_pattern = rf'\b{re.escape(term)}\s*[-:]\s*'
    if re.search(criteria_pattern, quote):
        print(f"  {term} matches criteria pattern")
print()

# Now run the actual linter
tools = {"tools": {}}
runtime = {"service_call_budget": 30, "request_sizes": [], "max_plan_steps": 10}

try:
    result = lint(contract, tools, runtime, contract_path.parent)
    plain_text_diags = [d for d in result['diagnostics'] if d['code'] in ['VAGUE_DIRECTIVE', 'UNDEFINED_TERM_PLAIN']]
    print(f"Plain text diagnostics: {len(plain_text_diags)}")
    for d in plain_text_diags:
        print(f"  {d['code']}: {d['witness'].get('term')} - {d['witness'].get('reason')}")
except Exception as e:
    print(f"Error: {e}")
