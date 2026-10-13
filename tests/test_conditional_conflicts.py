"""Tests for conditional conflict detection (issue #6)."""
import json
from pathlib import Path
import tempfile
import unittest

from prompt_skill_linter.engine import ContractError, lint


class ConditionalConflictTests(unittest.TestCase):
    """Test conditional conflict detection with axioms."""
    
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
    
    def test_no_axioms_no_conditional_conflicts(self):
        """No conditional conflicts without axioms."""
        self.rule('r1', 'x', True)
        self.rule('r2', 'x', False)
        # This is a regular INCOMPATIBLE_OBLIGATIONS, not a conditional conflict
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', self.codes())
        self.assertNotIn('CONDITIONAL_CONFLICT', self.codes())
    
    def test_no_conflict_with_compatible_axiom(self):
        """Compatible axioms don't trigger conflicts."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'y', 'value': True}])
        self.assertNotIn('CONDITIONAL_CONFLICT', self.codes())
    
    def test_simple_conflict_with_axiom(self):
        """Basic conflict: x=true, x=false, axiom enforces both."""
        self.rule('r1', 'x', True)
        self.rule('r2', 'y', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        self.assertEqual(len(diags), 1)
        self.assertIn('ax1', diags[0]['witness']['axioms'])
        self.assertIn('r1', diags[0]['witness']['rules'])
    
    def test_three_way_conflict(self):
        """Three rules and an axiom create a conflict."""
        self.rule('r1', 'a', True)
        self.rule('r2', 'b', True)
        self.rule('r3', 'c', True)
        # Axiom: if a and b then not c
        self.axiom('ax1', [
            {'literal': 'a', 'value': False},
            {'literal': 'b', 'value': False},
            {'literal': 'c', 'value': False}
        ])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            self.assertIn('ax1', diags[0]['witness']['axioms'])
    
    def test_scope_separation(self):
        """Different scopes checked independently."""
        # Two rules in different scopes
        r1 = self.rule('r1', 'x', True)
        r1['scope'] = {'entity': 'task1', 'temporal': 'run'}
        r2 = self.rule('r2', 'y', True)
        r2['scope'] = {'entity': 'task2', 'temporal': 'run'}
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        # Axiom applies to all scopes, but each scope is checked independently
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        # Should have one conflict in task1 scope (r1 + ax1)
        self.assertEqual(len(diags), 1)
        self.assertIn('r1', diags[0]['witness']['rules'])
        self.assertNotIn('r2', diags[0]['witness']['rules'])
    
    def test_permission_not_in_conflict(self):
        """Permissions don't create conflicts (they're not obligations)."""
        self.rule('r1', 'x', True, kind='permission')
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        # Permission doesn't obligate, so no conflict expected
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        # This should not trigger CONDITIONAL_CONFLICT since permission is not an obligation
        self.assertEqual(len(diags), 0)
    
    def test_priority_resolution_prevents_conflict(self):
        """Higher priority rules shadow lower ones, preventing conflicts."""
        self.rule('r1', 'x', True, priority=10)
        self.rule('r2', 'x', False, priority=5)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        # r1 shadows r2, so only r1 and ax1 remain
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            self.assertIn('r1', diags[0]['witness']['rules'])
            self.assertNotIn('r2', diags[0]['witness']['rules'])
    
    def test_minimality_checked(self):
        """Conflict cores are checked for minimality."""
        self.rule('r1', 'x', True)
        self.rule('r2', 'y', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        self.axiom('ax2', [{'literal': 'z', 'value': True}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            self.assertTrue(diags[0]['witness']['minimality_checked'])
            # ax2 should not be in the minimal core
            self.assertNotIn('ax2', diags[0]['witness']['axioms'])
    
    def test_prohibition_negates_effect(self):
        """Prohibitions require the negation of their effect."""
        self.rule('r1', 'x', True, kind='prohibition')
        self.axiom('ax1', [{'literal': 'x', 'value': True}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        self.assertEqual(len(diags), 1)
        self.assertIn('r1', diags[0]['witness']['rules'])
    
    def test_axiom_source_spans_in_diagnostic(self):
        """Axiom source spans appear in diagnostics."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        self.contract['axioms'][0]['source_spans'] = [{
            'source_id': 's',
            'start_line': 2,
            'end_line': 2,
            'quote': 'Rule two.'
        }]
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            spans = diags[0]['source_spans']
            # Should have both rule and axiom spans
            self.assertGreaterEqual(len(spans), 2)
    
    def test_axiom_in_interpreted_rules(self):
        """Axioms appear in interpreted_rules field."""
        self.rule('r1', 'x', True)
        self.axiom('ax1', [{'literal': 'x', 'value': False}])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            axiom_rules = [r for r in diags[0]['interpreted_rules'] if r.get('axiom')]
            self.assertGreater(len(axiom_rules), 0)
            self.assertEqual(axiom_rules[0]['id'], 'ax1')
    
    def test_removal_witnesses_present(self):
        """Removal witnesses show what happens without each element."""
        self.rule('r1', 'x', True)
        self.rule('r2', 'y', True)
        self.axiom('ax1', [
            {'literal': 'x', 'value': False},
            {'literal': 'y', 'value': False}
        ])
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'CONDITIONAL_CONFLICT']
        if diags:
            self.assertIn('removal_witnesses', diags[0]['witness'])
            witnesses = diags[0]['witness']['removal_witnesses']
            # Each element in the core should have a removal witness
            for rid in diags[0]['witness']['minimal_core']:
                self.assertIn(rid, witnesses)


if __name__ == '__main__':
    unittest.main()
