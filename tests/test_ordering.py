"""Tests for declarative ordering rules."""
import copy
import unittest

from prompt_skill_linter.ordering import (
    check_ordering_rules, validate_ordering_rules, _get_final_state
)


SOURCE = {'source_id': 'policy', 'start_line': 1, 'end_line': 1,
          'quote': 'Auth must complete before data access.'}

SCOPE = {'entity': 'agent', 'temporal': 'session'}


def make_rule(kind, actions, rule_id='ord-1', source=None, scope=None):
    """Helper to create an ordering rule."""
    return {
        'id': rule_id,
        'kind': kind,
        'actions': actions,
        'scope': scope or dict(SCOPE),
        'source': source or dict(SOURCE),
        'assumptions': []
    }


def make_workflow(actions, goal=None, initial=None, ordering_rules=None):
    """Helper to create a workflow dict."""
    return {
        'id': 'workflow-1',
        'initial': initial or ['start'],
        'goal': goal or ['complete'],
        'actions': actions,
        'advertisement_rule': 'adv-1',
        'ordering_rules': ordering_rules or []
    }


def make_explored_result(states, edges, exhaustive=True):
    """Helper to create an explored result from planner."""
    return {
        'status': 'reachable',
        'goal_path': ['action1', 'action2'],
        'search_exhaustive': exhaustive,
        'visited_states': len(states),
        'graph': {
            'states': states,
            'edges': edges
        }
    }


class OrderingRuleTests(unittest.TestCase):
    
    # ==================== BEFORE tests ====================
    
    def test_before_satisfied(self):
        """Auth before data access is satisfied."""
        actions = [
            {'id': 'auth', 'requires': ['start'], 'adds': ['authenticated']},
            {'id': 'access_data', 'requires': ['authenticated'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['auth', 'access_data'])
        ])
        
        # Simulate explored result
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['authenticated', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['authenticated', 'complete', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'auth'},
            {'from': 1, 'to': 2, 'action': 'access_data'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['status'], 'satisfied')
        self.assertEqual(len(diags), 0)
    
    def test_before_violated(self):
        """Data access before auth violates the rule."""
        actions = [
            {'id': 'auth', 'requires': ['start'], 'adds': ['authenticated']},
            {'id': 'access_data', 'requires': ['start'], 'adds': ['data_accessed']},
            {'id': 'finish', 'requires': ['data_accessed'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['auth', 'access_data'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['data_accessed', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'data_accessed', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'access_data'},
            {'from': 1, 'to': 2, 'action': 'finish'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertIn('access_data', checks[0]['counterexample'])
        self.assertNotIn('auth', checks[0]['counterexample'])
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]['code'], 'ORDERING_BEFORE_VIOLATED')
        self.assertEqual(diags[0]['severity'], 'error')
    
    def test_before_second_unreachable_warning(self):
        """Second action unreachable makes rule vacuously true but warns."""
        actions = [
            {'id': 'auth', 'requires': ['start'], 'adds': ['complete']},
            {'id': 'unreachable', 'requires': ['never'], 'adds': ['data']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['auth', 'unreachable'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'auth'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'warning')
        self.assertIn('unreachable', checks[0]['reason'])
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]['code'], 'ORDERING_RULE_UNREACHABLE_ACTIONS')
    
    def test_before_with_multiple_occurrences(self):
        """First can occur multiple times; any before second suffices."""
        actions = [
            {'id': 'auth', 'requires': ['start'], 'adds': ['auth1']},
            {'id': 're_auth', 'requires': ['auth1'], 'adds': ['auth2']},
            {'id': 'access_data', 'requires': ['auth1'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['auth', 'access_data'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['auth1', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['auth1', 'auth2', 'start'], 'depth': 2, 'goal': False},
            {'id': 3, 'facts': ['auth1', 'complete', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'auth'},
            {'from': 1, 'to': 2, 'action': 're_auth'},
            {'from': 1, 'to': 3, 'action': 'access_data'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'satisfied')
        self.assertEqual(len(diags), 0)
    
    # ==================== MUTUAL_EXCLUSION tests ====================
    
    def test_mutual_exclusion_satisfied(self):
        """Fast path and slow path are mutually exclusive."""
        actions = [
            {'id': 'fast', 'requires': ['start'], 'adds': ['complete']},
            {'id': 'slow', 'requires': ['start'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('mutual_exclusion', ['fast', 'slow'])
        ])
        
        # Two separate paths, never both
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True},
            {'id': 2, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'fast'},
            {'from': 0, 'to': 2, 'action': 'slow'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'satisfied')
        self.assertEqual(len(diags), 0)
    
    def test_mutual_exclusion_violated(self):
        """Both actions on same path violates mutual exclusion."""
        actions = [
            {'id': 'write', 'requires': ['start'], 'adds': ['written']},
            {'id': 'read', 'requires': ['written'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('mutual_exclusion', ['write', 'read'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['start', 'written'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'start', 'written'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'write'},
            {'from': 1, 'to': 2, 'action': 'read'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertEqual(checks[0]['counterexample'], ['write', 'read'])
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]['code'], 'ORDERING_MUTUAL_EXCLUSION_VIOLATED')
    
    def test_mutual_exclusion_both_unreachable_warning(self):
        """Both actions unreachable warns."""
        actions = [
            {'id': 'reachable', 'requires': ['start'], 'adds': ['complete']},
            {'id': 'unreachable1', 'requires': ['never'], 'adds': []},
            {'id': 'unreachable2', 'requires': ['never'], 'adds': []}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('mutual_exclusion', ['unreachable1', 'unreachable2'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'reachable'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'warning')
        self.assertIn('Both actions are unreachable', checks[0]['reason'])
    
    # ==================== EXACTLY_ONCE tests ====================
    
    def test_exactly_once_satisfied(self):
        """Action occurs exactly once on goal path."""
        actions = [
            {'id': 'init', 'requires': ['start'], 'adds': ['initialized']},
            {'id': 'process', 'requires': ['initialized'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('exactly_once', ['init'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['initialized', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'initialized', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'init'},
            {'from': 1, 'to': 2, 'action': 'process'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'satisfied')
        self.assertEqual(len(diags), 0)
    
    def test_exactly_once_violated_zero_times(self):
        """Action never occurring violates exactly_once."""
        actions = [
            {'id': 'skip_init', 'requires': ['start'], 'adds': ['complete']},
            {'id': 'init', 'requires': ['never'], 'adds': ['initialized']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('exactly_once', ['init'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'skip_init'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertEqual(checks[0]['observed_count'], 0)
        self.assertEqual(checks[0]['expected_count'], 1)
        self.assertEqual(diags[0]['code'], 'ORDERING_EXACTLY_ONCE_VIOLATED')
    
    def test_exactly_once_violated_twice(self):
        """Action occurring twice violates exactly_once."""
        actions = [
            {'id': 'retry', 'requires': ['start'], 'adds': ['attempted'], 'removes': []},
            {'id': 'finish', 'requires': ['attempted'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('exactly_once', ['retry'])
        ])
        
        # Path has retry action twice then finish
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['attempted', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['attempted', 'start'], 'depth': 2, 'goal': False},
            {'id': 3, 'facts': ['attempted', 'complete', 'start'], 'depth': 3, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'retry'},
            {'from': 1, 'to': 2, 'action': 'retry'},  # Same action twice
            {'from': 2, 'to': 3, 'action': 'finish'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertEqual(checks[0]['observed_count'], 2)
        self.assertEqual(diags[0]['code'], 'ORDERING_EXACTLY_ONCE_VIOLATED')
    
    def test_exactly_once_only_checks_complete_paths(self):
        """exactly_once only applies to paths reaching the goal."""
        actions = [
            {'id': 'init', 'requires': ['start'], 'adds': ['initialized']},
            {'id': 'fail', 'requires': ['initialized'], 'adds': ['failed']},
            {'id': 'retry_init', 'requires': ['failed'], 'adds': ['initialized']},
            {'id': 'succeed', 'requires': ['initialized'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('exactly_once', ['init'])
        ])
        
        # Path 1: init, succeed (complete, init once) - satisfies
        # Path 2: init, fail, retry_init (incomplete, init twice) - doesn't count
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['initialized', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'initialized', 'start'], 'depth': 2, 'goal': True},
            {'id': 3, 'facts': ['failed', 'start'], 'depth': 2, 'goal': False}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'init'},
            {'from': 1, 'to': 2, 'action': 'succeed'},
            {'from': 1, 'to': 3, 'action': 'fail'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should be satisfied because the complete path has init exactly once
        self.assertEqual(checks[0]['status'], 'satisfied')
    
    # ==================== AT_MOST_ONCE tests ====================
    
    def test_at_most_once_satisfied_zero(self):
        """Action never occurring satisfies at_most_once."""
        actions = [
            {'id': 'process', 'requires': ['start'], 'adds': ['complete']},
            {'id': 'optional', 'requires': ['never'], 'adds': []}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['optional'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'process'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should warn about unreachable but still be satisfied
        self.assertEqual(checks[0]['status'], 'warning')
        self.assertEqual(len(diags), 1)
    
    def test_at_most_once_satisfied_once(self):
        """Action occurring once satisfies at_most_once."""
        actions = [
            {'id': 'setup', 'requires': ['start'], 'adds': ['ready']},
            {'id': 'process', 'requires': ['ready'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['setup'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['ready', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'ready', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'setup'},
            {'from': 1, 'to': 2, 'action': 'process'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'satisfied')
        self.assertEqual(len(diags), 0)
    
    def test_at_most_once_violated(self):
        """Action occurring twice violates at_most_once."""
        actions = [
            {'id': 'increment', 'requires': ['start'], 'adds': ['once']},
            {'id': 'increment_again', 'requires': ['once'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['increment'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['once', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'once', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'increment'},
            {'from': 1, 'to': 2, 'action': 'increment'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertEqual(checks[0]['observed_count'], 2)
        self.assertEqual(diags[0]['code'], 'ORDERING_AT_MOST_ONCE_VIOLATED')
    
    # ==================== Edge cases ====================
    
    def test_truncated_search_incomplete(self):
        """Non-exhaustive search marks checks as incomplete."""
        actions = [
            {'id': 'a1', 'requires': ['start'], 'adds': ['s1']},
            {'id': 'a2', 'requires': ['s1'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['a1', 'a2'])
        ])
        
        states = [{'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False}]
        edges = []
        explored = make_explored_result(states, edges, exhaustive=False)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'incomplete')
        self.assertIn('truncated', checks[0]['reason'].lower())
        self.assertEqual(diags[0]['code'], 'ORDERING_CHECK_INCOMPLETE')
        self.assertEqual(diags[0]['severity'], 'warning')
    
    def test_empty_workflow(self):
        """Empty workflow with ordering rules."""
        workflow = make_workflow([], ordering_rules=[
            make_rule('before', ['never1', 'never2'])
        ])
        
        # This should fail validation because actions don't exist
        # But if it somehow got through, check should handle gracefully
    
    def test_loop_in_workflow(self):
        """Workflow with cycles handles ordering rules correctly."""
        actions = [
            {'id': 'loop', 'requires': ['start'], 'adds': ['looped']},
            {'id': 'exit', 'requires': ['looped'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['loop'])
        ])
        
        # Loop action can repeat
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['looped', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['looped', 'start'], 'depth': 2, 'goal': False},
            {'id': 3, 'facts': ['complete', 'looped', 'start'], 'depth': 3, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'loop'},
            {'from': 1, 'to': 2, 'action': 'loop'},
            {'from': 2, 'to': 3, 'action': 'exit'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertEqual(checks[0]['observed_count'], 2)
    
    def test_small_cycle_fully_explored_not_incomplete(self):
        """Small cyclic workflow fully explored under max_steps reports satisfied, not incomplete."""
        actions = [
            {'id': 'a', 'requires': ['start'], 'adds': ['s1']},
            {'id': 'b', 'requires': ['s1'], 'adds': ['s2']},
            {'id': 'reset', 'requires': ['s2'], 'adds': ['start'], 'removes': ['s1', 's2']},
            {'id': 'finish', 'requires': ['s2'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, initial=['start'], goal=['complete'], ordering_rules=[
            make_rule('before', ['a', 'finish'])
        ])
        
        # Fully explored cyclic graph (well under max_steps=20)
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['s1', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['s1', 's2', 'start'], 'depth': 2, 'goal': False},
            {'id': 3, 'facts': ['complete', 's1', 's2', 'start'], 'depth': 3, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'a'},
            {'from': 1, 'to': 2, 'action': 'b'},
            {'from': 2, 'to': 0, 'action': 'reset'},  # Cycle back to start
            {'from': 2, 'to': 3, 'action': 'finish'}
        ]
        explored = make_explored_result(states, edges, exhaustive=True)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should be satisfied, not incomplete (cycle is fully explored, 'a' always before 'finish')
        self.assertEqual(checks[0]['status'], 'satisfied',
                        'Fully explored cycle should report satisfied, not incomplete')
        self.assertTrue(checks[0].get('search_exhaustive', False),
                       'Search should be marked exhaustive')
    
    def test_conflicting_rules_both_checked(self):
        """Conflicting ordering rules are both checked independently."""
        actions = [
            {'id': 'a', 'requires': ['start'], 'adds': ['done_a']},
            {'id': 'b', 'requires': ['start'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['a', 'b'], rule_id='ord-1'),
            make_rule('before', ['b', 'a'], rule_id='ord-2')
        ])
        
        # A path with a then b will violate ord-2
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['done_a', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'done_a', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'a'},
            {'from': 1, 'to': 2, 'action': 'b'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(len(checks), 2)
        self.assertEqual(checks[0]['status'], 'satisfied')  # a before b
        self.assertEqual(checks[1]['status'], 'violated')   # b before a violated
        self.assertEqual(len(diags), 1)  # Only the violated one
    
    def test_deterministic_output(self):
        """Check results are deterministic."""
        actions = [
            {'id': 'a', 'requires': ['start'], 'adds': ['s1']},
            {'id': 'b', 'requires': ['s1'], 'adds': ['s2']},
            {'id': 'c', 'requires': ['s2'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['a', 'c']),
            make_rule('mutual_exclusion', ['a', 'c']),
            make_rule('exactly_once', ['b'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['s1', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['s1', 's2', 'start'], 'depth': 2, 'goal': False},
            {'id': 3, 'facts': ['complete', 's1', 's2', 'start'], 'depth': 3, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'a'},
            {'from': 1, 'to': 2, 'action': 'b'},
            {'from': 2, 'to': 3, 'action': 'c'}
        ]
        explored = make_explored_result(states, edges)
        
        # Run multiple times
        results = []
        for _ in range(3):
            diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
            results.append((
                tuple(c['status'] for c in checks),
                tuple(d['code'] for d in diags)
            ))
        
        # All runs should be identical
        self.assertEqual(len(set(results)), 1)
    
    def test_multiple_paths_all_checked(self):
        """All paths are checked, not just the goal path."""
        actions = [
            {'id': 'auth', 'requires': ['start'], 'adds': ['authenticated']},
            {'id': 'skip_auth', 'requires': ['start'], 'adds': ['noauth']},
            {'id': 'data', 'requires': ['noauth'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['auth', 'data'])
        ])
        
        # Two paths: one with auth (doesn't reach data), one without (violates)
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['authenticated', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['noauth', 'start'], 'depth': 1, 'goal': False},
            {'id': 3, 'facts': ['complete', 'noauth', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'auth'},
            {'from': 0, 'to': 2, 'action': 'skip_auth'},
            {'from': 2, 'to': 3, 'action': 'data'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should find violation on the skip_auth path
        self.assertEqual(checks[0]['status'], 'violated')
        self.assertEqual(checks[0]['counterexample'], ['skip_auth', 'data'])
    
    # ==================== Helper function tests ====================
    
    def test_get_final_state_simple(self):
        """Test final state computation."""
        workflow = {
            'initial': ['start'],
            'actions': [
                {'id': 'a', 'requires': ['start'], 'adds': ['mid'], 'removes': []},
                {'id': 'b', 'requires': ['mid'], 'adds': ['end'], 'removes': ['mid']}
            ]
        }
        
        final = _get_final_state(['a', 'b'], workflow)
        
        self.assertEqual(final, {'start', 'end'})
        self.assertNotIn('mid', final)
    
    def test_diamond_history_bug_regression(self):
        """Regression test for unsound deduplication in path enumeration.
        
        Two different action sequences reach the same state at the same depth.
        The dedup on (state_id, path_length) drops one, missing violations.
        
        Workflow: s0 -grant_auth-> s1, s0 -skip-> s1, s1 -access_data-> s2
        Rule: grant_auth before access_data
        
        Path [grant_auth, access_data] satisfies the rule.
        Path [skip, access_data] VIOLATES the rule (access_data without grant_auth first).
        
        With buggy dedup on (state_id, length), BFS sees [grant_auth] at (s1, 1),
        then drops [skip] as duplicate, never exploring the violating [skip, access_data].
        """
        actions = [
            {'id': 'grant_auth', 'requires': ['start'], 'adds': ['authed']},
            {'id': 'skip', 'requires': ['start'], 'adds': ['authed']},  # Same result state
            {'id': 'access_data', 'requires': ['authed'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, initial=['start'], goal=['complete'], ordering_rules=[
            make_rule('before', ['grant_auth', 'access_data'])
        ])
        
        # Simulate the explored graph
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['authed', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['authed', 'complete', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'grant_auth'},
            {'from': 0, 'to': 1, 'action': 'skip'},  # Different action, same destination
            {'from': 1, 'to': 2, 'action': 'access_data'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # This should detect the violation on path [skip, access_data]
        # but the buggy implementation at 485c91b will incorrectly return satisfied
        self.assertEqual(checks[0]['status'], 'violated', 
                        'Diamond bug: dedup on (state, length) drops [skip] path, missing violation')
        self.assertIn('skip', checks[0].get('counterexample', []),
                     'Counterexample should show the violating path through skip')
    
    def test_path_cap_must_report_incomplete(self):
        """MAX_PATHS truncation must mark check as incomplete, not satisfied.
        
        When path enumeration hits the cap, we've only checked a subset of paths,
        so we cannot claim the rule is satisfied.
        """
        # This test will be updated after the product construction fix
        # For now, it documents the requirement
        pass
    
    def test_depth_bound_exactly_once_incomplete(self):
        """Paths cut at max_steps before goal cannot prove exactly_once."""
        actions = [
            {'id': 'step', 'requires': ['start'], 'adds': ['s1'],'removes': []},
            {'id': 'repeat', 'requires': ['s1'], 'adds': ['s2'], 'removes': []},
            # Goal requires many steps, will hit depth bound
        ]
        workflow = make_workflow(actions, goal=['very_far'], ordering_rules=[
            make_rule('exactly_once', ['step'])
        ])
        
        # Simulate truncated exploration (non-exhaustive, no goal reached)
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['s1', 'start'], 'depth': 1, 'goal': False}
        ]
        edges = [{'from': 0, 'to': 1, 'action': 'step'}]
        explored = make_explored_result(states, edges, exhaustive=False)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should be incomplete, not satisfied, since we didn't explore complete paths
        self.assertIn(checks[0]['status'], ['incomplete', 'warning'],
                     'Truncated search cannot prove exactly_once')
    
    def test_non_zero_initial_state(self):
        """Initial state ID should not be hardcoded to 0."""
        actions = [
            {'id': 'a', 'requires': ['start'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['a'])
        ])
        
        # Initial state is 5, not 0
        states = [
            {'id': 5, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 6, 'facts': ['complete', 'start'], 'depth': 1, 'goal': True}
        ]
        edges = [{'from': 5, 'to': 6, 'action': 'a'}]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should work correctly even with non-zero initial state
        self.assertEqual(checks[0]['status'], 'satisfied')
    
    def test_conflicting_before_rules_detected(self):
        """A before B and B before A should be detected as conflicting."""
        actions = [
            {'id': 'a', 'requires': ['start'], 'adds': ['done_a']},
            {'id': 'b', 'requires': ['done_a'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['a', 'b'], rule_id='ord-1'),
            make_rule('before', ['b', 'a'], rule_id='ord-2')  # Conflicts with ord-1
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['done_a', 'start'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'done_a', 'start'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'a'},
            {'from': 1, 'to': 2, 'action': 'b'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should detect the conflict (either as a warning or in the diagnostics)
        # At minimum, one rule should violate
        statuses = [c['status'] for c in checks]
        self.assertIn('violated', statuses, 'Conflicting rules should cause at least one violation')


if __name__ == '__main__':
    unittest.main()
