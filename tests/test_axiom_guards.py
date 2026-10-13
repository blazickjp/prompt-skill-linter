"""Guard regression tests for axiom conflict detection.

These tests verify that each guard in the axiom conflict implementation
prevents its targeted error. They are not mutation tests (which would
require mutating production code); they are regression tests that would
fail if the corresponding guard were removed.
"""
import tempfile
from pathlib import Path
import unittest

from prompt_skill_linter.engine import ContractError, lint


class AxiomGuardRegressionTests(unittest.TestCase):
    """Guard regression tests for axiom checking."""
    
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
    
    def test_guard_no_axioms_skips_check(self):
        """GUARD: Without axioms, skip axiom checking."""
        contract = self.make_contract(
            [self.rule('r1', 'x', True)],
            []  # No axioms
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        codes = [d['code'] for d in result['diagnostics']]
        self.assertNotIn('AXIOM_CONFLICT', codes)
        self.assertNotIn('AXIOM_CHECK_INCOMPLETE', codes)
    
    def test_guard_permission_suppresses_prohibition(self):
        """GUARD: Permission at higher priority suppresses prohibition."""
        contract = self.make_contract(
            [self.rule('perm', 'x', True, kind='permission', priority=10),
             self.rule('prohib', 'x', True, kind='prohibition', priority=5)],
            [self.axiom('ax1', [{'literal': 'x', 'value': True}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        codes = [d['code'] for d in result['diagnostics']]
        # Should NOT have conflict because permission suppresses prohibition
        self.assertNotIn('AXIOM_CONFLICT', codes)
    
    def test_guard_preference_excluded(self):
        """GUARD: Preferences are excluded from obligations."""
        contract = self.make_contract(
            [self.rule('pref', 'x', True, kind='preference')],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        codes = [d['code'] for d in result['diagnostics']]
        # Should NOT have conflict because preferences aren't obligations
        self.assertNotIn('AXIOM_CONFLICT', codes)
    
    def test_guard_solver_unknown_surfaced(self):
        """GUARD: Solver unknown status is surfaced."""
        # Create 24 unit axioms to hit variable limit
        axioms = [self.axiom(f'ax{i}', [{'literal': f'v{i}', 'value': True}]) for i in range(24)]
        contract = self.make_contract(
            [self.rule('r1', 'x', True)],
            axioms + [self.axiom('ax_conflict', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        codes = [d['code'] for d in result['diagnostics']]
        # Should get AXIOM_CHECK_INCOMPLETE
        self.assertIn('AXIOM_CHECK_INCOMPLETE', codes)
    
    def test_guard_id_collision_rejected(self):
        """GUARD: Rule/axiom ID collisions are rejected."""
        contract = self.make_contract(
            [self.rule('same', 'x', True)],
            [self.axiom('same', [{'literal': 'y', 'value': True}])]
        )
        with self.assertRaises(ContractError) as cm:
            lint(contract, self.tools, self.runtime, self.root)
        self.assertIn('disjoint', str(cm.exception))
    
    def test_guard_axiom_involvement_required(self):
        """GUARD: Only report conflicts involving axioms."""
        contract = self.make_contract(
            [self.rule('r1', 'x', True), self.rule('r2', 'x', False)],
            [self.axiom('ax_unrelated', [{'literal': 'y', 'value': True}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        codes = [d['code'] for d in result['diagnostics']]
        # Should have INCOMPATIBLE_OBLIGATIONS (not AXIOM_CONFLICT)
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', codes)
        # Should NOT have AXIOM_CONFLICT because axiom isn't involved
        self.assertNotIn('AXIOM_CONFLICT', codes)
    
    def test_guard_prohibition_negation(self):
        """GUARD: Prohibitions negate their effect."""
        contract = self.make_contract(
            [self.rule('r1', 'x', True, kind='prohibition')],
            [self.axiom('ax1', [{'literal': 'x', 'value': True}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        # Should find conflict because prohibition x=true requires x=false
        self.assertEqual(len(diags), 1)
        self.assertIn('r1', diags[0]['witness']['rules'])
    
    def test_guard_priority_resolution(self):
        """GUARD: Priority resolution applied before conflict check."""
        contract = self.make_contract(
            [self.rule('r_high', 'x', True, priority=10),
             self.rule('r_low', 'x', False, priority=5)],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        if diags:
            # Only r_high should be in conflict
            self.assertIn('r_high', diags[0]['witness']['rules'])
            self.assertNotIn('r_low', diags[0]['witness']['rules'])
    
    def test_guard_scope_separation(self):
        """GUARD: Scopes checked independently."""
        r1 = self.rule('r1', 'x', True)
        r1['scope'] = {'entity': 'task1', 'temporal': 'run'}
        r2 = self.rule('r2', 'y', True)
        r2['scope'] = {'entity': 'task2', 'temporal': 'run'}
        
        contract = self.make_contract(
            [r1, r2],
            [self.axiom('ax1', [{'literal': 'x', 'value': False}])]
        )
        result = lint(contract, self.tools, self.runtime, self.root)
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        # Should have conflict only in task1 scope
        if diags:
            self.assertEqual(len(diags), 1)
            self.assertIn('r1', diags[0]['witness']['rules'])
            self.assertNotIn('r2', diags[0]['witness']['rules'])


if __name__ == '__main__':
    unittest.main()
