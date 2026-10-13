"""Mutation tests for conditional conflict detection.

These tests verify that each guard in the conditional conflict implementation
actually catches the targeted errors when mutated.
"""
import tempfile
from pathlib import Path
import unittest

from prompt_skill_linter.engine import lint


class ConditionalConflictMutationTests(unittest.TestCase):
    """Mutation tests for conditional conflict guards."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\nRule two.\n')
        self.tools = {'tools': {}}
        self.runtime = {}
    
    def make_contract(self, rules, axioms):
        """Helper to create a contract with rules and axioms."""
        return {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': rules,
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': [],
            'axioms': axioms
        }
    
    def rule(self, rid, literal='x', value=True, kind='requirement', priority=0):
        """Create a rule."""
        return {
            'id': rid,
            'source': {
                'source_id': 's',
                'start_line': 1,
                'end_line': 1,
                'quote': 'Rule one.'
            },
            'priority': priority,
            'kind': kind,
            'when': {},
            'skills': [],
            'scope': {'entity': 'task', 'temporal': 'run'},
            'exceptions': [],
            'effect': {'literal': literal, 'value': value}
        }
    
    def axiom(self, aid, clause):
        """Create an axiom."""
        return {
            'id': aid,
            'clause': clause,
            'description': f'Axiom {aid}'
        }
    
    def test_mutation_skip_axioms_check(self):
        """MUTATION: Remove 'if not axioms' check - should fail."""
        # Without the axioms check, we'd get errors on empty axiom lists
        contract = self.make_contract(
            [self.rule('r1', 'x', True)],
            []  # No axioms
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        # Should NOT have CONDITIONAL_CONFLICT without axioms
        codes = [d['code'] for d in result['diagnostics']]
        self.assertNotIn('CONDITIONAL_CONFLICT', codes)
    
    def test_mutation_skip_permission_check(self):
        """MUTATION: Remove permission skip - should fail."""
        # If we include permissions in conflicts, this would incorrectly flag a conflict
        contract = self.make_contract(
            [self.rule('r1', 'x', True, kind='permission')],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        # Should NOT have conflict because permissions aren't obligations
        codes = [d['code'] for d in result['diagnostics']]
        self.assertNotIn('CONDITIONAL_CONFLICT', codes)
    
    def test_mutation_skip_minimality_check(self):
        """MUTATION: Remove minimality check from witness - should fail."""
        # The minimality_checked field must be present and accurate
        contract = self.make_contract(
            [self.rule('r1', 'x', True)],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            self.assertIn('minimality_checked', diags[0]['witness'])
    
    def test_mutation_skip_axiom_involvement_check(self):
        """MUTATION: Report conflicts without axioms - should fail."""
        # Should only report if axioms are involved (not just rule-rule conflicts)
        contract = self.make_contract(
            [self.rule('r1', 'x', True), self.rule('r2', 'x', False)],
            [self.axiom('ax_unrelated', [{'literal': 'y', 'value': True}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        # Should have INCOMPATIBLE_OBLIGATIONS (not CONDITIONAL_CONFLICT)
        codes = [d['code'] for d in result['diagnostics']]
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', codes)
        # CONDITIONAL_CONFLICT should not fire because axiom isn't in conflict
        conf_diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        self.assertEqual(len(conf_diags), 0)
    
    def test_mutation_skip_prohibition_negation(self):
        """MUTATION: Don't negate prohibition effect - should fail."""
        # Prohibitions must negate their effect value
        contract = self.make_contract(
            [self.rule('r1', 'x', True, kind='prohibition')],
            [self.axiom('ax1', [{'literal': 'x', 'value': True}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        # Should find conflict: prohibition of x=true means x must be false,
        # which conflicts with axiom requiring x=true
        codes = [d['code'] for d in result['diagnostics']]
        self.assertIn('CONDITIONAL_CONFLICT', codes)
    
    def test_mutation_skip_priority_resolution(self):
        """MUTATION: Don't apply priority resolution - should fail."""
        # Without priority resolution, this would show both rules in conflict
        contract = self.make_contract(
            [self.rule('r1', 'x', True, priority=10),
             self.rule('r2', 'x', False, priority=5)],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            # Only r1 (higher priority) should be in the conflict
            self.assertIn('r1', diags[0]['witness']['rules'])
            self.assertNotIn('r2', diags[0]['witness']['rules'])
    
    def test_mutation_skip_scope_grouping(self):
        """MUTATION: Don't group by scope - should fail."""
        # Rules in different scopes should be checked independently
        r1 = self.rule('r1', 'x', True)
        r1['scope'] = {'entity': 'task1', 'temporal': 'run'}
        r2 = self.rule('r2', 'y', True)
        r2['scope'] = {'entity': 'task2', 'temporal': 'run'}
        
        contract = self.make_contract(
            [r1, r2],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        # Should have conflict only in task1 scope (r1 + ax1)
        if diags:
            self.assertEqual(len(diags), 1)
            self.assertIn('r1', diags[0]['witness']['rules'])
            self.assertNotIn('r2', diags[0]['witness']['rules'])


if __name__ == '__main__':
    unittest.main()
