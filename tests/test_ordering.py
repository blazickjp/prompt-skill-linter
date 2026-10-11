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
            {'id': 'fast', 'requires': ['start'], 'removes': ['start'], 'adds': ['complete']},
            {'id': 'slow', 'requires': ['start'], 'removes': ['start'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('mutual_exclusion', ['fast', 'slow'])
        ])
        
        # Two separate paths, never both (removes ensure exclusivity)
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['complete'], 'depth': 1, 'goal': True},
            {'id': 2, 'facts': ['complete'], 'depth': 1, 'goal': True}
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
            {'id': 'init', 'requires': ['start'], 'removes': ['start'], 'adds': ['initialized']},
            {'id': 'process', 'requires': ['initialized'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('exactly_once', ['init'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['initialized'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'initialized'], 'depth': 2, 'goal': True}
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
            {'id': 'init', 'requires': ['start'], 'removes': ['start'], 'adds': ['initialized']},
            {'id': 'fail', 'requires': ['initialized'], 'removes': ['initialized'], 'adds': ['failed']},
            {'id': 'retry_init', 'requires': ['failed'], 'removes': ['failed'], 'adds': ['initialized']},
            {'id': 'succeed', 'requires': ['initialized'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('exactly_once', ['init'])
        ])
        
        # Path 1: init, succeed (complete, init once) - satisfies
        # Path 2: init, fail, retry_init (incomplete, init twice) - doesn't count
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['initialized'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'initialized'], 'depth': 2, 'goal': True},
            {'id': 3, 'facts': ['failed'], 'depth': 2, 'goal': False}
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
            {'id': 'setup', 'requires': ['start'], 'removes': ['start'], 'adds': ['ready']},
            {'id': 'process', 'requires': ['ready'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['setup'])
        ])
        
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['ready'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 'ready'], 'depth': 2, 'goal': True}
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
        # Actions that remove 'start' make them mutually exclusive on first step
        actions = [
            {'id': 'a', 'requires': ['start'], 'removes': ['start'], 'adds': ['done_a']},
            {'id': 'b', 'requires': ['start'], 'removes': ['start'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('before', ['a', 'b'], rule_id='ord-1'),
            make_rule('before', ['b', 'a'], rule_id='ord-2')  # Conflicts with ord-1
        ])
        
        # Run real planner - will explore both 'a' first and 'b' first paths
        from prompt_skill_linter.planner import explore
        result = explore(workflow)
        
        diags, checks = check_ordering_rules(workflow, result, 'workflow-1', {'id': 'ctx-1'})
        
        # Should detect the conflict - both rules violated on different paths
        self.assertEqual(len(checks), 2)
        statuses = [c['status'] for c in checks]
        self.assertEqual(statuses.count('violated'), 2, 
                        'Both conflicting rules should be violated on different paths')
        
        # Must produce an ORDERING_RULES_CONFLICT diagnostic
        conflict_diags = [d for d in diags if d['code'] == 'ORDERING_RULES_CONFLICT']
        self.assertGreater(len(conflict_diags), 0, 
                          'Conflict detection must produce ORDERING_RULES_CONFLICT diagnostic')
        
        # Conflict diagnostic must mention both rule IDs
        if conflict_diags:
            rule_ids = conflict_diags[0]['responsible_rule_set']
            self.assertIn('ord-1', rule_ids, 'Conflict must mention first rule')
            self.assertIn('ord-2', rule_ids, 'Conflict must mention second rule')
    
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
            {'id': 'step1', 'requires': ['start'], 'adds': ['mid']},
            {'id': 'step2', 'requires': ['mid'], 'adds': ['complete']}
        ]
        workflow = make_workflow(actions, initial=['start'], goal=['complete'], ordering_rules=[
            make_rule('before', ['step1', 'step2'])
        ])
        
        # Put initial state (depth=0) AFTER other states in the list
        # States are intentionally out of order - ID 0 is NOT the initial state
        states = [
            {'id': 0, 'facts': ['mid'], 'depth': 1, 'goal': False},  # Decoy at ID 0
            {'id': 1, 'facts': ['complete', 'mid', 'start'], 'depth': 2, 'goal': True},
            {'id': 99, 'facts': ['start'], 'depth': 0, 'goal': False},  # True initial! depth=0, but ID=99
        ]
        edges = [
            {'from': 99, 'to': 0, 'action': 'step1'},
            {'from': 0, 'to': 1, 'action': 'step2'}
        ]
        explored = make_explored_result(states, edges)
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Should be satisfied (step1 always before step2)
        # If code uses ID 0 or states[0], it will start from wrong state and fail
        self.assertEqual(checks[0]['status'], 'satisfied',
                        'Must use depth=0 state, not hardcoded ID or states[0]')
    
    def test_depth_bound_isolated(self):
        """Depth bound alone (not state bound or planner incomplete) triggers INCOMPLETE."""
        # Linear chain to force deep exploration
        actions = [{'id': f'step{i}', 'requires': [f's{i}'], 'removes': [f's{i}'], 'adds': [f's{i+1}']} 
                   for i in range(22)]
        actions[0]['requires'] = ['start']
        actions[0]['removes'] = ['start']
        
        workflow = make_workflow(actions, initial=['start'], goal=['s22'], ordering_rules=[
            make_rule('at_most_once', ['step0'])
        ])
        
        # Chain goes to depth 21, but max_steps=20
        # Graph shows edges that WOULD be explored if not for depth bound
        states = [{'id': i, 'facts': [f's{i}' if i > 0 else 'start'], 'depth': i, 'goal': i == 22} 
                 for i in range(22)]
        edges = [{'from': i, 'to': i+1, 'action': f'step{i}'} for i in range(21)]
        
        # CRITICAL: search_exhaustive=True, under max_states, but depth 21 > max_steps 20
        explored = {'status': 'reachable', 'search_exhaustive': True, 
                   'visited_states': 22,
                   'bounds': {'max_steps': 20, 'max_states': 2000},
                   'graph': {'states': states, 'edges': edges}}
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        # Depth bound guard should trigger incomplete
        self.assertEqual(checks[0]['status'], 'incomplete',
                        'Depth bound must trigger INCOMPLETE')
        self.assertIn('max_steps', str(checks[0].get('cutoff_reasons', [])),
                     'Must cite depth bound')
    
    def test_state_bound_isolated(self):
        """State bound alone (not depth bound or planner incomplete) triggers INCOMPLETE."""
        # Many parallel branches with removes to prevent repetition
        actions = [{'id': f'branch{i}', 'requires': ['start'], 'removes': ['start'], 'adds': [f'end{i}']} 
                   for i in range(100)]
        
        workflow = make_workflow(actions, ordering_rules=[
            make_rule('at_most_once', ['branch0'])
        ])
        
        # Run real planner with low state bound, high depth bound
        from prompt_skill_linter.planner import explore
        result = explore(workflow, max_steps=100, max_states=10)
        
        diags, checks = check_ordering_rules(workflow, result, 'workflow-1', {'id': 'ctx-1'})
        
        # State bound should trigger incomplete (not satisfied, not violated)
        # The planner hit max_states, so search is not exhaustive
        self.assertEqual(checks[0]['status'], 'incomplete',
                        'State bound must trigger INCOMPLETE')
        self.assertIn('max_states', str(checks[0].get('cutoff_reasons', [])),
                     'Must cite state bound')
    
    def test_planner_nonexhaustive_incomplete(self):
        """Planner's search_exhaustive=False must propagate to INCOMPLETE."""
        # Partial graph shows valid path with no violation visible
        # But planner truncated - violation may exist in unexplored states
        actions = [
            {'id': 'step1', 'requires': ['start'], 'removes': ['start'], 'adds': ['s1']},
            {'id': 'step2', 'requires': ['s1'], 'adds': ['complete']},
        ]
        workflow = make_workflow(actions, initial=['start'], goal=['complete'], ordering_rules=[
            make_rule('before', ['step1', 'step2'])  # Satisfied in partial graph
        ])
        
        # Partial graph: both actions reachable, rule satisfied
        states = [
            {'id': 0, 'facts': ['start'], 'depth': 0, 'goal': False},
            {'id': 1, 'facts': ['s1'], 'depth': 1, 'goal': False},
            {'id': 2, 'facts': ['complete', 's1'], 'depth': 2, 'goal': True}
        ]
        edges = [
            {'from': 0, 'to': 1, 'action': 'step1'},
            {'from': 1, 'to': 2, 'action': 'step2'}
        ]
        
        # CRITICAL: search_exhaustive=False but no product bounds hit
        # Without inheriting flag, would return 'satisfied'
        # With flag, returns 'incomplete'
        explored = {'status': 'unknown', 'search_exhaustive': False,
                   'visited_states': 3,
                   'bounds': {'max_steps': 100, 'max_states': 1000},
                   'graph': {'states': states, 'edges': edges}}
        
        diags, checks = check_ordering_rules(workflow, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks[0]['status'], 'incomplete',
                        'Planner non-exhaustive must cause INCOMPLETE, not satisfied')
        self.assertIn('workflow_search_incomplete', str(checks[0].get('cutoff_reasons', [])),
                     'Must cite planner incomplete')
        
        # exactly_once case
        workflow2 = make_workflow(actions, initial=['start'], goal=['complete'], ordering_rules=[
            make_rule('exactly_once', ['step1'])
        ])
        
        diags2, checks2 = check_ordering_rules(workflow2, explored, 'workflow-1', {'id': 'ctx-1'})
        
        self.assertEqual(checks2[0]['status'], 'incomplete',
                        'Planner non-exhaustive must cause exactly_once INCOMPLETE')
        self.assertIn('workflow_search_incomplete', str(checks2[0].get('cutoff_reasons', [])),
                     'Must cite planner incomplete for exactly_once')
    
    def test_max_steps_boundary(self):
        """Max_steps semantics: paths explored up to depth max_steps-1, cut at max_steps."""
        # Build a linear chain where goal is terminal (no further actions enabled)
        actions = []
        for i in range(17):
            actions.append({'id': f'step{i}', 'requires': [f's{i}'], 'removes': [f's{i}'], 'adds': [f's{i+1}']})
        actions[0]['requires'] = ['start']
        actions[0]['removes'] = ['start']
        # Make final action also add 'goal' fact
        actions[16]['adds'] = [actions[16]['adds'][0], 'goal']
        
        # First case: goal at depth 17, well under max_steps=20, no further actions
        workflow = make_workflow(actions, initial=['start'], goal=['goal'], ordering_rules=[
            make_rule('before', ['step0', 'step16'])
        ])
        
        # Run real planner with max_steps=20
        from prompt_skill_linter.planner import explore
        result = explore(workflow, max_steps=20, max_states=2000)
        
        diags, checks = check_ordering_rules(workflow, result, 'workflow-1', {'id': 'ctx-1'})
        
        # Path of length 17 (< max_steps=20), terminal state, should be fully explored
        self.assertEqual(checks[0]['status'], 'satisfied',
                        'Path of length 17 with max_steps=20 should be satisfied')
        self.assertTrue(result['search_exhaustive'],
                       'Planner should be exhaustive when goal is terminal')
        
        # Second case: goal at depth 20 (exactly at max_steps), bound will be hit
        actions2 = []
        for i in range(20):
            actions2.append({'id': f'step{i}', 'requires': [f's{i}'], 'removes': [f's{i}'], 'adds': [f's{i+1}']})
        actions2[0]['requires'] = ['start']
        actions2[0]['removes'] = ['start']
        # Add one more action beyond to ensure bound is tested
        actions2.append({'id': 'step20', 'requires': ['s20'], 'removes': ['s20'], 'adds': ['s21']})
        
        workflow2 = make_workflow(actions2, initial=['start'], goal=['s20'], ordering_rules=[
            make_rule('before', ['step0', 'step19'])
        ])
        result2 = explore(workflow2, max_steps=20, max_states=2000)
        
        diags2, checks2 = check_ordering_rules(workflow2, result2, 'workflow-1', {'id': 'ctx-1'})
        
        # Path of length 20 hits max_steps boundary
        self.assertEqual(checks2[0]['status'], 'incomplete',
                        'Path at max_steps=20 should be incomplete')
        self.assertFalse(result2['search_exhaustive'],
                        'Planner should hit bound at max_steps=20')
    
    def test_max_steps_violation_at_boundary(self):
        """Safety violation on action number max_steps is detected with exact counterexample."""
        # Build a linear chain where the violation happens at the max_steps boundary
        actions = []
        for i in range(21):
            actions.append({'id': f'step{i}', 'requires': [f's{i}'], 'removes': [f's{i}'], 'adds': [f's{i+1}']})
        actions[0]['requires'] = ['start']
        actions[0]['removes'] = ['start']
        
        # Add a before rule that is violated at step 19 (action at depth max_steps-1)
        workflow = make_workflow(actions, initial=['start'], goal=['s21'], ordering_rules=[
            make_rule('before', ['step19', 'step9'])  # step19 comes AFTER step9, violates the rule
        ])
        
        from prompt_skill_linter.planner import explore
        result = explore(workflow, max_steps=20, max_states=2000)
        
        diags, checks = check_ordering_rules(workflow, result, 'workflow-1', {'id': 'ctx-1'})
        
        # Should detect the violation at step 19 (action number max_steps-1)
        self.assertEqual(checks[0]['status'], 'violated',
                        'Before rule violated at action max_steps-1 should be detected')
        self.assertIsNotNone(checks[0].get('counterexample'),
                           'Violation at max_steps should have a counterexample')
        # Verify the counterexample shows the violation path up to step 19
        counterexample = checks[0]['counterexample']
        self.assertGreaterEqual(len(counterexample), 10,
                        'Counterexample should include at least the violating actions')
        self.assertEqual(counterexample[-1], 'step9',
                        'Last action in counterexample should be step9 (the "before" action that came after)')

    def test_max_steps_violation_beyond_boundary_incomplete(self):
        """First violation requiring action max_steps + 1 returns incomplete."""
        # Build a linear chain that requires going beyond max_steps to reach goal
        actions = []
        for i in range(25):
            actions.append({'id': f'step{i}', 'requires': [f's{i}'], 'removes': [f's{i}'], 'adds': [f's{i+1}']})
        actions[0]['requires'] = ['start']
        actions[0]['removes'] = ['start']
        
        # Add a before rule where the violation would only manifest at depth > max_steps
        # The rule itself is satisfied by the linear structure, but we can't verify it
        # because the search is cut off before reaching the goal
        workflow = make_workflow(actions, initial=['start'], goal=['s25'], ordering_rules=[
            make_rule('before', ['step5', 'step10'])
        ])
        
        from prompt_skill_linter.planner import explore
        result = explore(workflow, max_steps=20, max_states=2000)
        
        diags, checks = check_ordering_rules(workflow, result, 'workflow-1', {'id': 'ctx-1'})
        
        # Should return incomplete since we can't explore deep enough to verify the rule
        self.assertEqual(checks[0]['status'], 'incomplete',
                        'Rule requiring exploration beyond max_steps should be incomplete')
        self.assertIn('max_steps', str(checks[0].get('cutoff_reasons', [])),
                     'Incomplete status should cite max_steps cutoff')

    def test_max_steps_exactly_once_wrong_count_at_boundary(self):
        """exactly_once goal reached at depth max_steps with wrong count is reported violated."""
        # Build a workflow where an action is executed twice by depth max_steps-1
        actions = []
        for i in range(19):
            actions.append({'id': f'step{i}', 'requires': [f's{i}'], 'removes': [f's{i}'], 'adds': [f's{i+1}']})
        actions[0]['requires'] = ['start']
        actions[0]['removes'] = ['start']
        
        # Add an action that will be executed twice (violating exactly_once)
        # Make it not require/remove any step facts so it can execute multiple times
        actions.append({'id': 'repeat_action', 'requires': ['s5'], 'adds': ['marker']})
        
        workflow = make_workflow(actions, initial=['start'], goal=['s18'], ordering_rules=[
            make_rule('exactly_once', ['repeat_action'])  # Should be executed exactly once
        ])
        
        from prompt_skill_linter.planner import explore
        result = explore(workflow, max_steps=20, max_states=2000)
        
        diags, checks = check_ordering_rules(workflow, result, 'workflow-1', {'id': 'ctx-1'})
        
        # Should detect exactly_once violation at max_steps boundary
        self.assertEqual(checks[0]['status'], 'violated',
                        'exactly_once with wrong count at max_steps should be violated')
        self.assertIsNotNone(checks[0].get('counterexample'),
                           'exactly_once violation at max_steps should have a counterexample')

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
        
        # Must produce an ORDERING_RULES_CONFLICT diagnostic
        conflict_diags = [d for d in diags if d['code'] == 'ORDERING_RULES_CONFLICT']
        self.assertGreater(len(conflict_diags), 0, 
                          'Conflict detection must produce ORDERING_RULES_CONFLICT diagnostic')
        
        # Conflict diagnostic must mention both rule IDs
        if conflict_diags:
            rule_ids = conflict_diags[0]['responsible_rule_set']
            self.assertIn('ord-1', rule_ids, 'Conflict must mention first rule')
            self.assertIn('ord-2', rule_ids, 'Conflict must mention second rule')


class OrderingIntegrationTests(unittest.TestCase):
    """Integration tests using real engine.py path with planner's display graph cap."""
    
    def test_joe_display_graph_truncation_regression(self):
        """Graph cap at 200 edges must not hide violations from ordering analysis.
        
        Joe's repro: 60 no-op actions fill the edge cap before the unauthorized
        bypass path is recorded. The ordering check must build successors from
        workflow actions when display edges are truncated.
        """
        from prompt_skill_linter.planner import explore
        
        # 60 always-enabled no-ops to fill edge cap
        actions = []
        for i in range(60):
            actions.append({'id': f'noop{i}', 'requires': [], 'adds': [], 'removes': []})
        
        # Authorization flow actions
        actions.extend([
            {'id': 'auth', 'requires': ['start'], 'removes': ['start'], 'adds': ['authorized', 'ready']},
            {'id': 'access', 'requires': ['ready'], 'removes': ['ready'], 'adds': ['done']},
            {'id': 'bypass1', 'requires': ['start'], 'removes': ['start'], 'adds': ['stage']},
            {'id': 'bypass2', 'requires': ['stage'], 'removes': ['stage'], 'adds': ['ready']},
        ])
        
        workflow = {
            'id': 'wf-truncation-test',
            'initial': ['start'],
            'goal': ['done'],
            'actions': actions,
            'advertisement_rule': 'adv-1',
            'ordering_rules': [{
                'id': 'auth-before-access',
                'kind': 'before',
                'actions': ['auth', 'access'],
                'scope': {'entity': 'session', 'temporal': 'always'},
                'source': {'source_id': 'test', 'start_line': 1, 'end_line': 1, 'quote': 'auth before access'},
                'assumptions': []
            }]
        }
        
        context = {'id': 'ctx-test', 'initial_facts': ['start']}
        
        # Run through real planner with default graph_limit=200
        explored = explore(workflow, forbidden=(), max_steps=20, max_states=2000, graph_limit=200)
        
        # Verify display graph is truncated
        self.assertTrue(explored['graph']['display_truncated'],
                       'Display graph must be truncated with 60+ no-ops')
        
        # Ordering check must still detect violation via bypass path
        from prompt_skill_linter.ordering import check_ordering_rules
        diags, checks = check_ordering_rules(workflow, explored, workflow['id'], context)
        
        self.assertEqual(checks[0]['status'], 'violated',
                        'Must detect violation even when display graph truncated')
        
        # Counterexample must show the bypass path
        counterexample = checks[0].get('counterexample', [])
        self.assertEqual(counterexample, ['bypass1', 'bypass2', 'access'],
                        'Counterexample must show unauthorized bypass path')
    
    def test_joe_lint_end_to_end(self):
        """End-to-end test through lint() on a contract with ordering rules."""
        import tempfile
        from pathlib import Path
        from prompt_skill_linter.engine import lint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Write source file
            (root / 'contract.txt').write_text('auth before access')
            
            src = {'source_id': 'contract', 'start_line': 1, 'end_line': 1, 'quote': 'auth before access'}
            
            # Create minimal contract with ordering rule
            contract = {
                'version': 1,
                'sources': [{'id': 'contract', 'path': 'contract.txt'}],
                'rules': [{'id': 'adv', 'source': src, 'scope': {'entity': 'task', 'temporal': 'run'},
                          'priority': 0, 'kind': 'permission', 'when': {}, 'exceptions': [],
                          'effect': {'literal': 'allow', 'value': True}}],
                'workflows': [{
                    'id': 'auth-workflow',
                    'initial': ['start'],
                    'goal': ['done'],
                    'advertisement_rule': 'adv',
                    'actions': [
                        {'id': 'auth', 'requires': ['start'], 'removes': ['start'], 'adds': ['authorized', 'ready']},
                        {'id': 'access', 'requires': ['ready'], 'removes': ['ready'], 'adds': ['done']},
                        {'id': 'bypass', 'requires': ['start'], 'removes': ['start'], 'adds': ['ready']}
                    ],
                    'ordering_rules': [{
                        'id': 'auth-before-access',
                        'kind': 'before',
                        'actions': ['auth', 'access'],
                        'scope': {'entity': 'session', 'temporal': 'always'},
                        'source': src,
                        'assumptions': ['Bypass path must not be allowed']
                    }]
                }],
                'contexts': [{'id': 'default', 'facts': {}, 'active_skills': []}]
            }
            
            # Run lint() - should detect violation via bypass path
            result = lint(contract, {'tools': {}}, {}, root)
            
            # Check for ordering violation
            ordering_diags = [d for d in result.get('diagnostics', [])
                            if d.get('code', '').startswith('ORDERING_')]
            self.assertGreater(len(ordering_diags), 0, 'Must detect ordering violation')
            
            # Verify it's the before violation
            violations = [d for d in ordering_diags 
                         if d.get('code') == 'ORDERING_BEFORE_VIOLATED']
            self.assertEqual(len(violations), 1, 'Must have exactly one before violation')
            
            # Check counterexample includes bypass and access
            witness = violations[0].get('witness', {})
            self.assertEqual(witness.get('status'), 'violated')
            counterexample = witness.get('counterexample', [])
            self.assertIn('bypass', counterexample, 'Counterexample must include bypass')
            self.assertIn('access', counterexample, 'Counterexample must include access')
            self.assertEqual(counterexample, ['bypass', 'access'],
                           'Counterexample should be shortest: [bypass, access]')
    
    def test_lint_prohibition_blocks_ordering_violation(self):
        """Active prohibition of bypass prevents ordering violation."""
        import tempfile
        from pathlib import Path
        from prompt_skill_linter.engine import lint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'contract.txt').write_text('auth before access\nbypass forbidden')
            
            src = {'source_id': 'contract', 'start_line': 1, 'end_line': 1, 'quote': 'auth before access'}
            src2 = {'source_id': 'contract', 'start_line': 2, 'end_line': 2, 'quote': 'bypass forbidden'}
            
            # Add prohibition of bypass action with same scope
            contract = {
                'version': 1,
                'sources': [{'id': 'contract', 'path': 'contract.txt'}],
                'rules': [
                    {'id': 'adv', 'source': src, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 0, 'kind': 'permission', 'when': {}, 'exceptions': [],
                     'effect': {'literal': 'allow', 'value': True}},
                    {'id': 'no-bypass', 'source': src2, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 0, 'kind': 'prohibition', 'when': {}, 'exceptions': [],
                     'forbid_action': 'bypass'}
                ],
                'workflows': [{
                    'id': 'auth-workflow',
                    'initial': ['start'],
                    'goal': ['done'],
                    'advertisement_rule': 'adv',
                    'actions': [
                        {'id': 'auth', 'requires': ['start'], 'removes': ['start'], 'adds': ['authorized', 'ready']},
                        {'id': 'access', 'requires': ['ready'], 'removes': ['ready'], 'adds': ['done']},
                        {'id': 'bypass', 'requires': ['start'], 'removes': ['start'], 'adds': ['ready']}
                    ],
                    'ordering_rules': [{
                        'id': 'auth-before-access',
                        'kind': 'before',
                        'actions': ['auth', 'access'],
                        'scope': {'entity': 'session', 'temporal': 'always'},
                        'source': src,
                        'assumptions': []
                    }]
                }],
                'contexts': [{'id': 'default', 'facts': {}, 'active_skills': []}]
            }
            
            result = lint(contract, {'tools': {}}, {}, root)
            
            # With bypass prohibited, only auth->access path remains, so rule is satisfied
            ordering_diags = [d for d in result.get('diagnostics', [])
                            if d.get('code', '').startswith('ORDERING_')]
            # Should have NO violation (bypass was excluded)
            violations = [d for d in ordering_diags 
                         if d.get('code') == 'ORDERING_BEFORE_VIOLATED']
            self.assertEqual(len(violations), 0, 'Prohibition should prevent bypass violation')
    
    def test_lint_permission_overrides_prohibition(self):
        """Higher-priority permission overrides prohibition, allowing violation."""
        import tempfile
        from pathlib import Path
        from prompt_skill_linter.engine import lint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'contract.txt').write_text('policy')
            
            src = {'source_id': 'contract', 'start_line': 1, 'end_line': 1, 'quote': 'policy'}
            
            # Higher-priority permission overrides prohibition
            contract = {
                'version': 1,
                'sources': [{'id': 'contract', 'path': 'contract.txt'}],
                'rules': [
                    {'id': 'adv', 'source': src, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 0, 'kind': 'permission', 'when': {}, 'exceptions': [],
                     'effect': {'literal': 'allow', 'value': True}},
                    {'id': 'no-bypass', 'source': src, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 0, 'kind': 'prohibition', 'when': {}, 'exceptions': [],
                     'forbid_action': 'bypass'},
                    {'id': 'override', 'source': src, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 10, 'kind': 'permission', 'when': {}, 'exceptions': [],
                     'allow_action': 'bypass'}
                ],
                'workflows': [{
                    'id': 'auth-workflow',
                    'initial': ['start'],
                    'goal': ['done'],
                    'advertisement_rule': 'adv',
                    'actions': [
                        {'id': 'auth', 'requires': ['start'], 'removes': ['start'], 'adds': ['authorized', 'ready']},
                        {'id': 'access', 'requires': ['ready'], 'removes': ['ready'], 'adds': ['done']},
                        {'id': 'bypass', 'requires': ['start'], 'removes': ['start'], 'adds': ['ready']}
                    ],
                    'ordering_rules': [{
                        'id': 'auth-before-access',
                        'kind': 'before',
                        'actions': ['auth', 'access'],
                        'scope': {'entity': 'session', 'temporal': 'always'},
                        'source': src,
                        'assumptions': []
                    }]
                }],
                'contexts': [{'id': 'default', 'facts': {}, 'active_skills': []}]
            }
            
            result = lint(contract, {'tools': {}}, {}, root)
            
            # Higher-priority permission allows bypass, so violation should be detected
            ordering_diags = [d for d in result.get('diagnostics', [])
                            if d.get('code', '').startswith('ORDERING_')]
            violations = [d for d in ordering_diags 
                         if d.get('code') == 'ORDERING_BEFORE_VIOLATED']
            self.assertEqual(len(violations), 1, 'Override permission should allow bypass violation')
            self.assertEqual(violations[0]['witness']['counterexample'], ['bypass', 'access'])
    
    def test_lint_unavailable_tool_blocks_violation(self):
        """Unavailable tool action is excluded from ordering analysis."""
        import tempfile
        from pathlib import Path
        from prompt_skill_linter.engine import lint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'contract.txt').write_text('policy')
            
            src = {'source_id': 'contract', 'start_line': 1, 'end_line': 1, 'quote': 'policy'}
            
            # bypass action requires missing tool
            contract = {
                'version': 1,
                'sources': [{'id': 'contract', 'path': 'contract.txt'}],
                'rules': [
                    {'id': 'adv', 'source': src, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 0, 'kind': 'permission', 'when': {}, 'exceptions': [],
                     'effect': {'literal': 'allow', 'value': True}}
                ],
                'workflows': [{
                    'id': 'auth-workflow',
                    'initial': ['start'],
                    'goal': ['done'],
                    'advertisement_rule': 'adv',
                    'actions': [
                        {'id': 'auth', 'requires': ['start'], 'removes': ['start'], 'adds': ['authorized', 'ready']},
                        {'id': 'access', 'requires': ['ready'], 'removes': ['ready'], 'adds': ['done']},
                        {'id': 'bypass', 'requires': ['start'], 'removes': ['start'], 'adds': ['ready'],
                         'tool_call': {'tool': 'missing_tool', 'arguments': {}}}
                    ],
                    'ordering_rules': [{
                        'id': 'auth-before-access',
                        'kind': 'before',
                        'actions': ['auth', 'access'],
                        'scope': {'entity': 'session', 'temporal': 'always'},
                        'source': src,
                        'assumptions': []
                    }]
                }],
                'contexts': [{'id': 'default', 'facts': {}, 'active_skills': []}]
            }
            
            # Manifest doesn't include missing_tool
            result = lint(contract, {'tools': {}}, {}, root)
            
            # bypass is unavailable (missing tool), so only auth->access path, no violation
            ordering_diags = [d for d in result.get('diagnostics', [])
                            if d.get('code', '').startswith('ORDERING_')]
            violations = [d for d in ordering_diags 
                         if d.get('code') == 'ORDERING_BEFORE_VIOLATED']
            self.assertEqual(len(violations), 0, 'Unavailable tool should exclude bypass action')
    
    def test_lint_60_noop_bypass_regression(self):
        """Joe's exact 60-no-op regression through lint() (not just planner)."""
        import tempfile
        from pathlib import Path
        from prompt_skill_linter.engine import lint
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'contract.txt').write_text('auth before access')
            
            src = {'source_id': 'contract', 'start_line': 1, 'end_line': 1, 'quote': 'auth before access'}
            
            # 60 no-ops + auth flow + bypass
            actions = []
            for i in range(60):
                actions.append({'id': f'noop{i}', 'requires': [], 'adds': [], 'removes': []})
            
            actions.extend([
                {'id': 'auth', 'requires': ['start'], 'removes': ['start'], 'adds': ['authorized', 'ready']},
                {'id': 'access', 'requires': ['ready'], 'removes': ['ready'], 'adds': ['done']},
                {'id': 'bypass1', 'requires': ['start'], 'removes': ['start'], 'adds': ['stage']},
                {'id': 'bypass2', 'requires': ['stage'], 'removes': ['stage'], 'adds': ['ready']},
            ])
            
            contract = {
                'version': 1,
                'sources': [{'id': 'contract', 'path': 'contract.txt'}],
                'rules': [
                    {'id': 'adv', 'source': src, 'scope': {'entity': 'session', 'temporal': 'always'},
                     'priority': 0, 'kind': 'permission', 'when': {}, 'exceptions': [],
                     'effect': {'literal': 'allow', 'value': True}}
                ],
                'workflows': [{
                    'id': 'auth-workflow',
                    'initial': ['start'],
                    'goal': ['done'],
                    'advertisement_rule': 'adv',
                    'actions': actions,
                    'ordering_rules': [{
                        'id': 'auth-before-access',
                        'kind': 'before',
                        'actions': ['auth', 'access'],
                        'scope': {'entity': 'session', 'temporal': 'always'},
                        'source': src,
                        'assumptions': []
                    }]
                }],
                'contexts': [{'id': 'default', 'facts': {}, 'active_skills': []}]
            }
            
            result = lint(contract, {'tools': {}}, {}, root)
            
            # Must detect bypass violation through lint() despite display graph truncation
            ordering_diags = [d for d in result.get('diagnostics', [])
                            if d.get('code', '').startswith('ORDERING_')]
            violations = [d for d in ordering_diags 
                         if d.get('code') == 'ORDERING_BEFORE_VIOLATED']
            self.assertEqual(len(violations), 1, 'Must detect bypass through full lint() path')
            
            witness = violations[0].get('witness', {})
            self.assertEqual(witness['counterexample'], ['bypass1', 'bypass2', 'access'])
            # Assert IDs are populated
            self.assertEqual(witness['workflow'], 'auth-workflow')
            self.assertEqual(witness['context_id'], 'default')


if __name__ == '__main__':
    unittest.main()
