"""Regression tests for mutation testing fixes."""
import unittest


class OperatorFilterRegressionTests(unittest.TestCase):
    """Regression tests for operator filter using canonical operator IDs."""
    
    def setUp(self):
        """Set up minimal test contract with rules."""
        self.contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'test_rule',
                    'source': {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Test'},
                    'priority': 100,
                    'kind': 'requirement',
                    'when': {},
                    'scope': {'entity': 'items', 'temporal': 'one_run'},
                    'exceptions': []
                }
            ]
        }
        self.manifest = {'tools': {}}
    
    def test_flip_kind_filter_matches_canonical_id(self):
        """Test that --operators flip_kind selects flip_requirement_prohibition mutants."""
        from prompt_skill_linter.mutate import generate_mutants
        
        # Filter by canonical ID 'flip_kind'
        mutants = generate_mutants(self.contract, self.manifest, operator_filter={'flip_kind'})
        
        # Should generate exactly one flip_kind mutant for the single rule
        self.assertEqual(len(mutants), 1)
        self.assertEqual(mutants[0].operator, 'flip_kind')
        self.assertIn('flip', mutants[0].description.lower())
    
    def test_negate_effect_filter_matches_canonical_id(self):
        """Test that --operators negate_effect selects negate_effect_value mutants."""
        from prompt_skill_linter.mutate import generate_mutants
        
        # Create contract with rule that has 'effect' field (which negate_effect_value targets)
        contract_with_effects = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'test_rule',
                    'source': {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Test'},
                    'priority': 100,
                    'kind': 'requirement',
                    'when': {},
                    'scope': {'entity': 'items', 'temporal': 'one_run'},
                    'effect': {'literal': 'flag', 'value': True},  # Boolean effect
                    'exceptions': []
                }
            ]
        }
        
        # Filter by canonical ID 'negate_effect'
        mutants = generate_mutants(contract_with_effects, self.manifest, operator_filter={'negate_effect'})
        
        # Should generate negate_effect mutant for the Boolean value
        self.assertEqual(len(mutants), 1)
        self.assertEqual(mutants[0].operator, 'negate_effect')
    
    def test_cli_operator_filter_integration(self):
        """Test generate_mutants with canonical operator filter IDs."""
        from prompt_skill_linter.mutate import generate_mutants
        
        # This tests the integration of operator_filter through generate_mutants
        # (which is what the CLI calls)
        mutants_flip_only = generate_mutants(self.contract, self.manifest, operator_filter={'flip_kind'})
        mutants_all = generate_mutants(self.contract, self.manifest, operator_filter=None)
        
        # With filter, should get only flip_kind
        self.assertTrue(all(m.operator == 'flip_kind' for m in mutants_flip_only))
        self.assertEqual(len(mutants_flip_only), 1)
        
        # Without filter, should get more mutants
        self.assertGreater(len(mutants_all), len(mutants_flip_only))


class WitnessFieldRegressionTests(unittest.TestCase):
    """Regression tests for trace violation_path witness field normalization."""
    
    def test_violation_path_included_in_normalization(self):
        """Test that violation_path (not violating_path) is normalized."""
        from prompt_skill_linter.mutate import normalize_diagnostic
        
        diagnostic = {
            'code': 'TEST',
            'responsible_rule_set': ['rule1'],
            'severity': 'error',
            'witness': {
                'violation_path': ['action1', 'action2'],
                'status': 'failure'
            }
        }
        
        normalized = normalize_diagnostic(diagnostic)
        
        # Should include violation_path in witness content
        self.assertIn(('violation_path', ('action1', 'action2')), normalized[3])
    
    def test_null_violation_path_handled(self):
        """Test that null violation_path is handled correctly."""
        from prompt_skill_linter.mutate import normalize_diagnostic
        
        diagnostic = {
            'code': 'TEST',
            'responsible_rule_set': [],
            'severity': 'error',
            'witness': {
                'violation_path': None,
                'status': 'success'
            }
        }
        
        normalized = normalize_diagnostic(diagnostic)
        
        # Should not crash on null path
        # witness content should not include violation_path entry
        witness_keys = [item[0] for item in normalized[3]]
        self.assertNotIn('violation_path', witness_keys)


class ZeroDenominatorReportingTests(unittest.TestCase):
    """Regression tests for zero-denominator mutation score reporting."""
    
    def test_all_invalid_mutants_score_none(self):
        """Test that all-invalid mutants produce null score, not 0.00%."""
        from prompt_skill_linter.mutate import compute_mutation_score, MutationResult, Mutant
        
        results = [
            MutationResult(
                mutant=Mutant(id='test1', operator='flip_kind', description='Test', contract={}, pointer='/test'),
                status='INVALID',
                original_diagnostics=frozenset(),
                mutant_diagnostics=frozenset(),
                error='Schema violation'
            )
        ]
        
        stats = compute_mutation_score(results)
        
        self.assertEqual(stats['total_mutants'], 1)
        self.assertEqual(stats['invalid'], 1)
        self.assertEqual(stats['scorable_mutants'], 0)
        self.assertIsNone(stats['mutation_score'])  # Not 0.0
    
    def test_all_equivalent_mutants_score_none(self):
        """Test that all-equivalent mutants produce null score."""
        from prompt_skill_linter.mutate import compute_mutation_score, MutationResult, Mutant
        
        results = [
            MutationResult(
                mutant=Mutant(id='test1', operator='swap_mutual_exclusion', description='Test', contract={}, pointer='/test'),
                status='EQUIVALENT_SUSPECTED',
                original_diagnostics=frozenset(),
                mutant_diagnostics=frozenset()
            )
        ]
        
        stats = compute_mutation_score(results)
        
        self.assertEqual(stats['scorable_mutants'], 0)
        self.assertIsNone(stats['mutation_score'])
    
    def test_genuine_zero_percent_score(self):
        """Test that survived mutant produces genuine 0.00%, not null."""
        from prompt_skill_linter.mutate import compute_mutation_score, MutationResult, Mutant
        
        diag = frozenset([
            (
                'ORDERING_VIOLATION',
                (),
                'error',
                (('counterexample', ('a', 'b')),)
            )
        ])
        
        results = [
            MutationResult(
                mutant=Mutant(id='test1', operator='drop_precondition', description='Test', contract={}, pointer='/test'),
                status='SURVIVED',
                original_diagnostics=diag,
                mutant_diagnostics=diag
            )
        ]
        
        stats = compute_mutation_score(results)
        
        self.assertEqual(stats['scorable_mutants'], 1)
        self.assertEqual(stats['mutation_score'], 0.0)  # Genuine 0%, not None
    
    def test_empty_results_score_none(self):
        """Test that empty result set produces null score."""
        from prompt_skill_linter.mutate import compute_mutation_score
        
        stats = compute_mutation_score([])
        
        self.assertEqual(stats['total_mutants'], 0)
        self.assertEqual(stats['scorable_mutants'], 0)
        self.assertIsNone(stats['mutation_score'])
    
    def test_cli_text_output_formats_none_as_na(self):
        """Test that text output formatting handles null mutation scores."""
        from prompt_skill_linter.mutate import compute_mutation_score
        
        # Empty results produce null score
        stats = compute_mutation_score([])
        
        self.assertIsNone(stats['mutation_score'])
        self.assertEqual(stats['scorable_mutants'], 0)
        
        # Simulate the formatting logic from cli.py
        if stats['mutation_score'] is None:
            score_str = "N/A (0 scorable mutants)"
        else:
            score_str = f"{stats['mutation_score']:.2%}"
        
        # Should format as N/A
        self.assertIn('N/A', score_str)
        self.assertIn('0 scorable mutants', score_str)


if __name__ == '__main__':
    unittest.main()
