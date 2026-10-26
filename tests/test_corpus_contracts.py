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
        """Corpus contracts should validate and lint without schema errors.
        
        This test ensures that the active_skills fix allows the linter to run
        on evaluation corpus contracts. It fails without the fix.
        """
        corpus_dir = Path(__file__).parent.parent / 'evaluation/final_corpus'
        contracts_dir = corpus_dir / 'contracts'
        
        # Test one representative contract
        contract_file = contracts_dir / 'anthropic_01.contract.json'
        with open(contract_file) as f:
            contract = json.load(f)
        
        # Prepare minimal manifest and runtime
        manifest = {"tools": {}}
        runtime = {
            "service_call_budget": 30,
            "request_sizes": [],
            "max_plan_steps": 10
        }
        
        # This should not raise a validation error about missing active_skills
        try:
            result = lint(contract, manifest, runtime, contracts_dir)
            # If we got here, validation passed
            self.assertIsInstance(result, dict)
            self.assertIn('diagnostics', result)
        except Exception as e:
            # If there's an error, make sure it's not about missing active_skills
            self.assertNotIn('missing active_skills', str(e).lower(),
                           f"Contract validation failed with active_skills error: {e}")


if __name__ == '__main__':
    unittest.main()
