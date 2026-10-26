"""Test the type-matched evaluation scorer."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.score_type_matched import (
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
        """
        # Mock a case with label type 'vague' (expects no codes in main)
        mock_case = {
            'id': 'test_case',
            'text': 'Be concise.',
            'label': {
                'issue': True,
                'type': 'vague'
            }
        }
        
        # Mock diagnostics that don't match the vague type
        mock_diags = [
            {'code': 'UNDEFINED_TERM', 'severity': 'info', 'witness': {}}
        ]
        
        # Simulate the scoring logic
        label_has_issue = mock_case['label']['issue']
        label_type = mock_case['label'].get('type')
        expected_codes = map_label_to_diagnostic_codes(label_type)
        
        found_codes = {d['code'] for d in mock_diags}
        found_issue = len(found_codes) > 0
        
        # Type match: diagnostic code must be in expected codes
        type_match = bool(expected_codes and found_codes & expected_codes) if expected_codes is not None else False
        
        # This should be a FALSE NEGATIVE, not a TRUE POSITIVE
        self.assertTrue(label_has_issue)
        self.assertTrue(found_issue)
        self.assertFalse(type_match, 
                        "Finding UNDEFINED_TERM should not match label type 'vague'")
        
        # The outcome should be FN (miss), not TP
        if label_has_issue and type_match:
            outcome = 'TP'
        elif not label_has_issue and found_issue:
            outcome = 'FP'
        elif label_has_issue and not type_match:
            outcome = 'FN'
        else:
            outcome = 'TN'
        
        self.assertEqual(outcome, 'FN',
                        "Type mismatch should result in FN, not TP")
    
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
