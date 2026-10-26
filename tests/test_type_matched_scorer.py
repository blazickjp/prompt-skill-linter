"""Test the type-matched evaluation scorer."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.score_type_matched import (
    LABEL_TO_CODES,
    map_label_to_diagnostic_codes,
    evaluate,
    load_cases,
    load_split
)


class TestTypeMatchedScorer(unittest.TestCase):
    """Test that the scorer requires type matching for TP."""
    
    def test_label_to_code_mapping_is_explicit(self):
        """The label-to-code mapping must be explicit and documented."""
        # All known label types should have a mapping
        known_types = ['vague', 'undefined', 'tension', 'missing_requirement']
        
        for label_type in known_types:
            codes = map_label_to_diagnostic_codes(label_type)
            self.assertIsNotNone(codes, 
                               f"Label type '{label_type}' must have a mapping")
            self.assertIsInstance(codes, set,
                                f"Mapping for '{label_type}' must be a set")
    
    def test_type_mismatch_is_not_tp(self):
        """A diagnostic that doesn't match the label type is not a TP.
        
        This test ensures type-matched scoring: finding ANY diagnostic is not
        sufficient for a TP; the diagnostic CODE must match the label TYPE.
        
        This test calls evaluate() with run_linter_on_case patched to return
        a wrong-code diagnostic, and verifies it's scored as FN, not TP.
        """
        # Find a case with label type 'vague' (expects no codes in main)
        cases = load_cases()
        split = load_split()
        
        # cursor_03 has label type 'vague' in dev split
        test_case_id = 'cursor_03'
        self.assertEqual(cases[test_case_id]['label']['type'], 'vague')
        self.assertIn(test_case_id, split['dev'])
        
        # Mock run_linter_on_case to return a wrong diagnostic
        # (UNDEFINED_TERM instead of something that matches 'vague')
        def mock_run_linter(case_id):
            if case_id == test_case_id:
                # Return UNDEFINED_TERM diagnostic (wrong type for 'vague')
                return [
                    {'code': 'UNDEFINED_TERM', 'severity': 'info', 'witness': {}}
                ]
            # For other cases, return empty (no diagnostics)
            return []
        
        with patch('evaluation.score_type_matched.run_linter_on_case', side_effect=mock_run_linter):
            results = evaluate()
        
        # The case should be counted as FN (miss), not TP
        # Because UNDEFINED_TERM doesn't match the expected codes for 'vague' (which is empty set)
        self.assertEqual(results['dev']['tp'], 0, 
                        "Wrong diagnostic type should not count as TP")
        
        # Check that cursor_03 specifically is in misses with type_mismatch
        cursor_03_misses = [m for m in results['dev']['misses'] if m['case_id'] == test_case_id]
        self.assertEqual(len(cursor_03_misses), 1,
                        f"{test_case_id} should be in misses")
        self.assertEqual(cursor_03_misses[0]['reason'], 'type_mismatch',
                        f"{test_case_id} should be type_mismatch, not TP")
    
    def test_baseline_matches_measurements_json(self):
        """The scorer should reproduce the baseline metrics.
        
        This test verifies that our scorer produces the same baseline results
        as documented in evaluation/final_corpus/measurements.json.
        """
        # Load the baseline from measurements.json
        measurements_file = Path(__file__).parent.parent / 'evaluation/final_corpus/measurements.json'
        with open(measurements_file) as f:
            baseline = json.load(f)
        
        # Run the scorer
        results = evaluate()
        
        # Should have zero execution errors
        self.assertEqual(len(results['execution_errors']), 0,
                        "Should have no execution errors on any case")
        
        # Compare dev metrics
        self.assertEqual(results['dev']['tp'], baseline['dev']['tp'],
                        "Dev TP should match baseline")
        self.assertEqual(results['dev']['fp'], baseline['dev']['fp'],
                        "Dev FP should match baseline")
        self.assertEqual(results['dev']['tn'], baseline['dev']['tn'],
                        "Dev TN should match baseline")
        self.assertEqual(results['dev']['fn'], baseline['dev']['fn'],
                        "Dev FN should match baseline")
        
        # Compare held-out metrics
        self.assertEqual(results['held_out']['tp'], baseline['held_out']['tp'],
                        "Held-out TP should match baseline")
        self.assertEqual(results['held_out']['fp'], baseline['held_out']['fp'],
                        "Held-out FP should match baseline")
        self.assertEqual(results['held_out']['tn'], baseline['held_out']['tn'],
                        "Held-out TN should match baseline")
        self.assertEqual(results['held_out']['fn'], baseline['held_out']['fn'],
                        "Held-out FN should match baseline")


if __name__ == '__main__':
    unittest.main()
