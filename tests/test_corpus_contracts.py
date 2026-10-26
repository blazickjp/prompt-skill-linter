"""Test that evaluation corpus contracts are valid."""
import json
import unittest
from pathlib import Path

from prompt_skill_linter.engine import lint


class TestCorpusContracts(unittest.TestCase):
    """Verify evaluation corpus contracts can be validated."""
    
    def test_all_corpus_contracts_have_active_skills(self):
        """All corpus contracts must have active_skills field in contexts."""
        corpus_dir = Path(__file__).parent.parent / 'evaluation/final_corpus/contracts'
        contracts = list(corpus_dir.glob('*.json'))
        self.assertGreater(len(contracts), 0, "No contracts found")
        
        for contract_file in contracts:
            with open(contract_file) as f:
                contract = json.load(f)
            
            # Check that all contexts have active_skills
            for ctx in contract.get('contexts', []):
                self.assertIn('active_skills', ctx, 
                             f"{contract_file.name}: context {ctx.get('id')} missing active_skills")
                self.assertIsInstance(ctx['active_skills'], list,
                                    f"{contract_file.name}: active_skills must be a list")
    
    def test_corpus_contracts_validate_without_error(self):
        """All 32 corpus contracts should validate and lint without any errors.
        
        This test ensures that the active_skills fix allows the linter to run
        on evaluation corpus contracts. It fails without the fix.
        """
        corpus_dir = Path(__file__).parent.parent / 'evaluation/final_corpus'
        contracts_dir = corpus_dir / 'contracts'
        cases_dir = corpus_dir / 'cases'
        
        # Prepare minimal manifest and runtime
        manifest = {"tools": {}}
        runtime = {
            "service_call_budget": 30,
            "request_sizes": [],
            "max_plan_steps": 10
        }
        
        # Test all 32 contracts
        errors = []
        for case_file in sorted(cases_dir.glob('*.json')):
            case_id = case_file.stem
            contract_file = contracts_dir / f"{case_id}.contract.json"
            
            with open(contract_file) as f:
                contract = json.load(f)
            
            # This should not raise any exception at all
            try:
                result = lint(contract, manifest, runtime, contracts_dir)
                self.assertIsInstance(result, dict)
                self.assertIn('diagnostics', result)
            except Exception as e:
                errors.append((case_id, str(e)))
        
        if errors:
            error_msg = "\n".join([f"  {case_id}: {err}" for case_id, err in errors])
            self.fail(f"Failed to lint {len(errors)} contracts:\n{error_msg}")


if __name__ == '__main__':
    unittest.main()
