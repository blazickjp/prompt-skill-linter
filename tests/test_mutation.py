"""Tests for contract mutation testing."""
import json
from pathlib import Path
import tempfile
import unittest

from prompt_skill_linter.engine import lint
from prompt_skill_linter.mutate import (
    generate_mutants,
    classify_mutant,
    compute_mutation_score,
    flip_requirement_prohibition,
    swap_priority,
    delete_rule,
    negate_effect_value,
    drop_precondition,
    drop_ordering_rule,
    swap_before_actions,
    change_exactly_once_to_at_most_once,
)


class MutationOperatorTests(unittest.TestCase):
    """Test that each operator applies correctly and doesn't modify the original."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\nRule two.\n')
        
        self.contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'r1',
                    'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                    'priority': 1,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': True}
                },
                {
                    'id': 'r2',
                    'source': {'source_id': 's', 'start_line': 2, 'end_line': 2, 'quote': 'Rule two.'},
                    'priority': 2,
                    'kind': 'prohibition',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'y', 'value': True}
                }
            ],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
    
    def test_flip_requirement_prohibition_applies(self):
        """Verify flip_requirement_prohibition creates valid mutant."""
        original_kind = self.contract['rules'][0]['kind']
        mutants = flip_requirement_prohibition(self.contract, 0)
        
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        # Original unchanged
        self.assertEqual(self.contract['rules'][0]['kind'], original_kind)
        
        # Mutant changed
        self.assertEqual(mutant.contract['rules'][0]['kind'], 'prohibition')
        self.assertNotEqual(mutant.contract['rules'][0]['kind'], original_kind)
    
    def test_swap_priority_applies(self):
        """Verify swap_priority creates valid mutant."""
        orig_p1 = self.contract['rules'][0]['priority']
        orig_p2 = self.contract['rules'][1]['priority']
        
        mutants = swap_priority(self.contract, 0, 1)
        
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        # Original unchanged
        self.assertEqual(self.contract['rules'][0]['priority'], orig_p1)
        self.assertEqual(self.contract['rules'][1]['priority'], orig_p2)
        
        # Mutant swapped
        self.assertEqual(mutant.contract['rules'][0]['priority'], orig_p2)
        self.assertEqual(mutant.contract['rules'][1]['priority'], orig_p1)
    
    def test_delete_rule_applies(self):
        """Verify delete_rule creates valid mutant."""
        orig_count = len(self.contract['rules'])
        
        mutants = delete_rule(self.contract, 0)
        
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        # Original unchanged
        self.assertEqual(len(self.contract['rules']), orig_count)
        
        # Mutant has one less rule
        self.assertEqual(len(mutant.contract['rules']), orig_count - 1)
    
    def test_negate_effect_value_applies(self):
        """Verify negate_effect_value creates valid mutant."""
        orig_value = self.contract['rules'][0]['effect']['value']
        
        mutants = negate_effect_value(self.contract, 0)
        
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        # Original unchanged
        self.assertEqual(self.contract['rules'][0]['effect']['value'], orig_value)
        
        # Mutant negated
        self.assertEqual(mutant.contract['rules'][0]['effect']['value'], not orig_value)
    
    def test_workflow_mutation_applies(self):
        """Verify workflow mutations work correctly."""
        self.contract['workflows'] = [{
            'id': 'wf1',
            'goal': ['done'],
            'actions': [
                {
                    'id': 'a1',
                    'requires': ['ready'],
                    'adds': ['done']
                }
            ],
            'advertisement_rule': 'r1'
        }]
        
        mutants = drop_precondition(self.contract, 0, 0, 0)
        
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        # Original unchanged
        self.assertEqual(len(self.contract['workflows'][0]['actions'][0]['requires']), 1)
        
        # Mutant has no preconditions
        self.assertEqual(len(mutant.contract['workflows'][0]['actions'][0]['requires']), 0)
    
    def test_ordering_rule_mutations_apply(self):
        """Verify ordering rule mutations work correctly."""
        self.contract['workflows'] = [{
            'id': 'wf1',
            'goal': ['done'],
            'actions': [
                {'id': 'a1', 'adds': ['x']},
                {'id': 'a2', 'requires': ['x'], 'adds': ['done']}
            ],
            'advertisement_rule': 'r1',
            'ordering_rules': [
                {
                    'id': 'ord1',
                    'kind': 'before',
                    'actions': ['a1', 'a2'],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                    'assumptions': []
                }
            ]
        }]
        
        # Test swap_before_actions
        mutants = swap_before_actions(self.contract, 0, 0)
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        # Original unchanged
        self.assertEqual(self.contract['workflows'][0]['ordering_rules'][0]['actions'], ['a1', 'a2'])
        
        # Mutant swapped
        self.assertEqual(mutant.contract['workflows'][0]['ordering_rules'][0]['actions'], ['a2', 'a1'])


class MutationClassificationTests(unittest.TestCase):
    """Test kill/survive classification on known cases."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\nRule two.\n')
        
        self.tools = {'tools': {}}
        self.runtime = {}
    
    def test_vacuous_rule_survives(self):
        """A rule that never fires should survive deletion."""
        contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'active',
                    'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                    'priority': 1,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': True}
                },
                {
                    'id': 'vacuous',
                    'source': {'source_id': 's', 'start_line': 2, 'end_line': 2, 'quote': 'Rule two.'},
                    'priority': 0,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': True}
                }
            ],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        
        original_report = lint(contract, self.tools, self.runtime, self.root)
        
        # Delete the vacuous rule (lower priority, same effect as another rule)
        mutants = delete_rule(contract, 1)
        self.assertEqual(len(mutants), 1)
        mutant = mutants[0]
        
        mutant_report = lint(mutant.contract, self.tools, self.runtime, self.root)
        result = classify_mutant(mutant, original_report, mutant_report, None)
        
        # Should be SURVIVED or EQUIVALENT_SUSPECTED because the lower-priority rule is shadowed
        # and doesn't affect diagnostics
        self.assertIn(result.status, ['SURVIVED', 'EQUIVALENT_SUSPECTED'])
    
    def test_conflicting_rule_killed(self):
        """Deleting a rule that causes a conflict should be killed."""
        contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'r1',
                    'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                    'priority': 1,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': True}
                },
                {
                    'id': 'r2',
                    'source': {'source_id': 's', 'start_line': 2, 'end_line': 2, 'quote': 'Rule two.'},
                    'priority': 1,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': False}
                }
            ],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        
        original_report = lint(contract, self.tools, self.runtime, self.root)
        
        # Should have INCOMPATIBLE_OBLIGATIONS
        codes = [d['code'] for d in original_report['diagnostics']]
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', codes)
        
        # Delete one conflicting rule
        mutants = delete_rule(contract, 1)
        mutant = mutants[0]
        
        mutant_report = lint(mutant.contract, self.tools, self.runtime, self.root)
        result = classify_mutant(mutant, original_report, mutant_report, None)
        
        # Should be killed because conflict disappears
        self.assertEqual(result.status, 'KILLED')
    
    def test_ordering_rule_swap_killed(self):
        """Swapping a before rule should be killed."""
        contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': [],
            'workflows': [{
                'id': 'wf1',
                'goal': ['done'],
                'actions': [
                    {'id': 'a1', 'adds': ['x']},
                    {'id': 'a2', 'requires': ['x'], 'adds': ['done']}
                ],
                'advertisement_rule': 'adv',
                'ordering_rules': [
                    {
                        'id': 'ord1',
                        'kind': 'before',
                        'actions': ['a1', 'a2'],
                        'scope': {'entity': 'task', 'temporal': 'run'},
                        'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                        'assumptions': []
                    }
                ]
            }]
        }
        
        # Add advertisement rule
        contract['rules'].append({
            'id': 'adv',
            'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
            'priority': 1,
            'kind': 'requirement',
            'when': {},
            'skills': [],
            'scope': {'entity': 'task', 'temporal': 'run'},
            'exceptions': [],
            'effect': {'literal': 'advertised', 'value': True}
        })
        
        original_report = lint(contract, self.tools, self.runtime, self.root)
        
        # Swap the before rule
        mutants = swap_before_actions(contract, 0, 0)
        mutant = mutants[0]
        
        mutant_report = lint(mutant.contract, self.tools, self.runtime, self.root)
        result = classify_mutant(mutant, original_report, mutant_report, None)
        
        # Should be killed because swapping before changes semantics
        self.assertEqual(result.status, 'KILLED')


class MutationDeterminismTests(unittest.TestCase):
    """Test that mutation generation is deterministic."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\n')
        
        self.contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'r1',
                    'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                    'priority': 1,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': True}
                }
            ],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        
        self.manifest = {'tools': {}}
    
    def test_mutant_ids_stable(self):
        """Verify mutant IDs are deterministic."""
        mutants1 = generate_mutants(self.contract, self.manifest)
        mutants2 = generate_mutants(self.contract, self.manifest)
        
        ids1 = [m.id for m in mutants1]
        ids2 = [m.id for m in mutants2]
        
        self.assertEqual(ids1, ids2)
    
    def test_mutant_ordering_stable(self):
        """Verify mutants are returned in stable order."""
        mutants1 = generate_mutants(self.contract, self.manifest)
        mutants2 = generate_mutants(self.contract, self.manifest)
        
        self.assertEqual(
            [(m.id, m.operator) for m in mutants1],
            [(m.id, m.operator) for m in mutants2]
        )


class MutationCrashHandlingTests(unittest.TestCase):
    """Test that crashes are reported separately."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\n')
    
    def test_crash_reported_separately(self):
        """Verify crashed mutants are classified correctly."""
        contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        
        from prompt_skill_linter.mutate import Mutant
        
        # Create a mutant with invalid contract
        bad_contract = contract.copy()
        bad_contract['version'] = 99  # Invalid version
        
        mutant = Mutant(
            id='bad',
            operator='test',
            description='Bad mutant',
            contract=bad_contract,
            pointer='/version'
        )
        
        original_report = lint(contract, {'tools': {}}, {}, self.root)
        
        result = classify_mutant(mutant, original_report, None, 'contract.version must be 1')
        
        self.assertEqual(result.status, 'CRASHED')
        self.assertIsNotNone(result.error)


class GuardMutationTests(unittest.TestCase):
    """Test that disabling guards causes test failures."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\n')
        
        self.contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [
                {
                    'id': 'r1',
                    'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
                    'priority': 1,
                    'kind': 'requirement',
                    'when': {},
                    'skills': [],
                    'scope': {'entity': 'task', 'temporal': 'run'},
                    'exceptions': [],
                    'effect': {'literal': 'x', 'value': True}
                }
            ],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
    
    def test_original_not_modified_guard(self):
        """Verify mutations don't modify the original."""
        import copy
        original_copy = copy.deepcopy(self.contract)
        
        mutants = flip_requirement_prohibition(self.contract, 0)
        
        # This should pass because we use deepcopy
        self.assertEqual(self.contract, original_copy)


if __name__ == '__main__':
    unittest.main()
