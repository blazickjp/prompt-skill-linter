"""Tests for unconditional Boolean effect + axiom checking (partial toward issue #6)."""
import json
from pathlib import Path
import tempfile
import unittest

from prompt_skill_linter.engine import ContractError, lint


class AxiomConflictTests(unittest.TestCase):
    """Test unconditional Boolean effect + axiom satisfiability checking."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\nRule two.\nRule three.\n')
        self.contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': [],
            'axioms': []
        }
        self.tools = {'tools': {}}
        self.runtime = {}
    
    def rule(self, rid, literal='x', value=True, priority=0, **extra):
        """Create a rule with an effect."""
        r = {
            'id': rid,
            'source': {
                'source_id': 's',
                'start_line': 1,
                'end_line': 1,
                'quote': 'Rule one.'
            },
            'priority': priority,
            'kind': 'requirement',
            'when': {},
            'skills': [],
            'scope': {'entity': 'task', 'temporal': 'run'},
            'exceptions': [],
            'effect': {'literal': literal, 'value': value}
        }
        r.update(extra)
        self.contract['rules'].append(r)
        return r
    
    def axiom(self, aid, clause):
        """Create an axiom with a CNF clause."""
        a = {
            'id': aid,
            'clause': clause,
            'description': f'Axiom {aid}',
            'source_spans': []
        }
        self.contract['axioms'].append(a)
        return a
    
    def run_lint(self):
        return lint(self.contract, self.tools, self.runtime, self.root)
    
    def codes(self):
        return [d['code'] for d in self.run_lint()['diagnostics']]
    
    def test_no_axioms_no_axiom_conflicts(self):
        """No axiom conflicts without axioms."""
        self.rule('r1', 'x', True)
        self.rule('r2', 'x', False)
        # This is a regular INCOMPATIBLE_OBLIGATIONS, not an axiom conflict
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', self.codes())
        self.assertNotIn('AXIOM_CONFLICT', self.codes())
    
    def test_no_conflict_with_compatible_axiom(self):
        """Compatible axioms don't trigger conflicts."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'y', 'value': True}])
        self.assertNotIn('AXIOM_CONFLICT', self.codes())
    
    def test_simple_conflict_with_axiom(self):
        """Basic conflict: rule requires x, axiom requires not-x."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        self.assertEqual(len(diags), 1)
        self.assertIn('ax1', diags[0]['witness']['axioms'])
        self.assertIn('r1', diags[0]['witness']['rules'])
    
    def test_permission_suppresses_prohibition_no_false_conflict(self):
        """Regression: permission x=true at priority 10, prohibition x=true at priority 5 → no conflict."""
        self.rule('perm', 'x', True, priority=10, kind='permission')
        self.rule('prohib', 'x', True, priority=5, kind='prohibition')
        self.axiom('ax1', [{'literal': 'x', 'value': True}])
        # Permission should suppress prohibition; axiom x=true is compatible with permission
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        self.assertEqual(len(diags), 0, "Permission should suppress prohibition, no conflict with axiom")
    
    def test_lone_preference_no_conflict(self):
        """Regression: preference x=true plus axiom x=true → no conflict (preference not an obligation)."""
        self.rule('pref', 'x', True, kind='preference')
        self.axiom('ax1', [{'literal': 'x', 'value': True}])
        # Preferences are filtered out by check_obligations semantics
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        self.assertEqual(len(diags), 0, "Preference is not an obligation, should not conflict")
    
    def test_id_collision_rejected(self):
        """Rule and axiom ID collision is rejected."""
        self.rule('same_id', 'x', True)
        self.axiom('same_id', [{'literal': 'y', 'value': True}])
        with self.assertRaises(ContractError) as cm:
            self.run_lint()
        self.assertIn('disjoint', str(cm.exception))
    
    def test_prohibition_negates_effect(self):
        """Prohibitions correctly negate their effect."""
        self.rule('r1', 'x', True, kind='prohibition')
        self.axiom('ax1', [{'literal': 'x', 'value': True}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        self.assertEqual(len(diags), 1)
        self.assertIn('r1', diags[0]['witness']['rules'])
    
    def test_solver_limit_surfaces_unknown(self):
        """Solver limit returns unknown diagnostic."""
        # 24 fresh variables to hit the limit
        for i in range(24):
            self.axiom(f'ax{i}', [{'literal': f'v{i}', 'value': True}])
        self.rule('r1', 'x', True)
        self.axiom('ax_conflict', [{'literal': 'x', 'value': False}])
        result = self.run_lint()
        codes = [d['code'] for d in result['diagnostics']]
        # Should get AXIOM_CHECK_INCOMPLETE due to variable limit
        self.assertIn('AXIOM_CHECK_INCOMPLETE', codes)
    
    def test_minimality_checked_field(self):
        """Minimality_checked field present."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        if diags:
            self.assertIn('minimality_checked', diags[0]['witness'])
    
    def test_axiom_in_interpreted_rules(self):
        """Axioms appear in interpreted_rules field."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'AXIOM_CONFLICT']
        if diags:
            axiom_rules = [r for r in diags[0]['interpreted_rules'] if r.get('axiom')]
            self.assertGreater(len(axiom_rules), 0)
            self.assertEqual(axiom_rules[0]['id'], 'ax1')


if __name__ == '__main__':
    unittest.main()
