#!/usr/bin/env python3
"""Check why cursor_01 and oss_04 aren't caught."""
import json
from pathlib import Path
import re

ROOT = Path("/workspace")

for case_id in ["cursor_01", "oss_04"]:
    print(f"\n=== {case_id} ===")
    contract_path = ROOT / f"evaluation/final_corpus/contracts/{case_id}.contract.json"
    
    with open(contract_path) as f:
        contract = json.load(f)
    
    quote = contract['rules'][0]['source']['quote']
    print(f"Quote: {quote}")
    
    # Check for ALL_CAPS terms
    common_caps = {'I', 'API', 'URL', 'HTTP', 'HTTPS', 'JSON', 'XML', 'SQL', 'ID', 'UUID', 'CLI', 'UI', 'UX'}
    cap_terms = []
    for match in re.finditer(r'\b[A-Z][A-Z_]+\b', quote):
        term = match.group(0)
        if len(term) >= 2 and term not in common_caps:
            cap_terms.append(term)
    
    print(f"ALL_CAPS terms found: {cap_terms}")
    
    # Check usage patterns
    for term in cap_terms:
        usage_pattern = rf'\b(?:the|must|when|if|as|use|uses|using)\s+{re.escape(term)}\b'
        if re.search(usage_pattern, quote, re.IGNORECASE):
            print(f"  {term} matches usage pattern")
    
    # Check for lowercase terms in colon pattern
    for match in re.finditer(r'\b([a-z]+)\s*:\s*[A-Z][^.;]*(?:[.;]|$)', quote):
        term = match.group(1)
        print(f"Lowercase colon term: {term}")
