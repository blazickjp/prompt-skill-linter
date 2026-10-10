"""Coverage is independent of finite safety, including enabled no-op edges."""
import copy
import random
import unittest
from unittest.mock import patch

from prompt_skill_linter.service import analyze
from prompt_skill_linter.trace import check_trace_assertions
from test_trace import count_assertion, freshness_assertion
from test_trace_integration import bundle


def coverage(workflow, **kwargs):
    return check_trace_assertions(workflow, **kwargs)[0]['trigger_coverage']


def enumerate_trigger(workflow, depth, forbidden=()):
    """Independent raw-prefix oracle: no state cache or assertion monitor."""
    assertion = workflow['trace_assertions'][0]
    triggers = assertion['actions'] if assertion['kind'] == 'action_count' else assertion['guarded_actions']
    frontier = [(set(workflow.get('initial', [])), [])]
    for _ in range(depth):
        following = []
        for facts, path in frontier:
            for action in workflow['actions']:
                if action['id'] in forbidden or not set(action.get('requires', [])) <= facts:
                    continue
                events = path + [action['id']]
                if action['id'] in triggers:
                    return events
                updated = facts.difference(action.get('removes', []))
                updated.update(action.get('adds', []))
                following.append((updated, events))
        frontier = following
    return None


class TraceCoverageTests(unittest.TestCase):
    def test_safe_guard_noop_is_reachable_before_state_deduplication(self):
        assertion = freshness_assertion(True)
        assertion['invalidate_actions'] = []
        w = {'actions': [{'id': 'verify', 'requires': ['never']}, {'id': 'approve'}],
             'trace_assertions': [assertion]}
        result = check_trace_assertions(w)[0]
        self.assertEqual(result['status'], 'safe')
        self.assertEqual(result['trigger_coverage']['status'], 'reachable')
        self.assertEqual(result['trigger_coverage']['first_trigger_path'], ['approve'])
        self.assertEqual(result['visited_states'], 1)

    def test_violation_itself_is_a_trigger(self):
        w = {'actions': [{'id': 'generate'}], 'trace_assertions': [count_assertion(maximum=0)]}
        result = check_trace_assertions(w)[0]
        self.assertEqual(result['status'], 'violated')
        self.assertEqual(result['trigger_coverage']['first_trigger_path'], ['generate'])
        self.assertFalse(result['trigger_coverage']['search_exhaustive'])

    def test_safe_does_not_imply_trigger_reachable(self):
        w = {'actions': [{'id': 'generate', 'requires': ['never']}, {'id': 'noop'}],
             'trace_assertions': [count_assertion(maximum=0)]}
        result = check_trace_assertions(w)[0]
        self.assertEqual(result['status'], 'safe')
        self.assertEqual(result['trigger_coverage']['status'], 'unreachable')
        self.assertTrue(result['trigger_coverage']['search_exhaustive'])
        self.assertIsNone(result['trigger_coverage']['first_trigger_path'])

    def test_forbidden_edges_do_not_trigger(self):
        w = {'actions': [{'id': 'generate'}], 'trace_assertions': [count_assertion(maximum=0)]}
        self.assertEqual(coverage(w, forbidden=['generate'])['status'], 'unreachable')

    def test_post_goal_trigger_is_checked(self):
        w = {'initial': [], 'goal': ['done'], 'actions': [
            {'id': 'finish', 'adds': ['done']}, {'id': 'generate', 'requires': ['done']}],
            'trace_assertions': [count_assertion()]}
        self.assertEqual(coverage(w)['first_trigger_path'], ['finish', 'generate'])

    def test_effects_and_removed_prerequisite_respected(self):
        w = {'initial': ['once'], 'actions': [
            {'id': 'prepare', 'requires': ['once'], 'removes': ['once'], 'adds': ['ready']},
            {'id': 'generate', 'requires': ['once', 'ready']}],
            'trace_assertions': [count_assertion()]}
        self.assertEqual(coverage(w)['status'], 'unreachable')
        w['actions'][0]['adds'].append('once')
        self.assertEqual(coverage(w)['first_trigger_path'], ['prepare', 'generate'])

    def test_reachable_stays_reachable_after_safety_bound(self):
        w = {'actions': [{'id': 'generate'}], 'trace_assertions': [count_assertion(maximum=3)]}
        result = check_trace_assertions(w, max_steps=1)[0]
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['trigger_coverage']['status'], 'reachable')
        self.assertEqual(result['trigger_coverage']['first_trigger_path'], ['generate'])

    def test_zero_depth_safe_noop_has_unknown_coverage(self):
        assertion = freshness_assertion(True); assertion['invalidate_actions'] = []
        w = {'actions': [{'id': 'verify', 'requires': ['never']}, {'id': 'approve'}],
             'trace_assertions': [assertion]}
        result = check_trace_assertions(w, max_steps=0)[0]
        self.assertEqual(result['status'], 'safe')
        self.assertEqual(result['trigger_coverage']['status'], 'unknown')
        self.assertIsNone(result['trigger_coverage']['first_trigger_path'])
        self.assertEqual(result['trigger_coverage']['cutoff_reasons'], ['max_steps'])

    def test_no_out_of_bound_first_trigger(self):
        w = {'actions': [{'id': 'prepare', 'adds': ['ready']},
                         {'id': 'generate', 'requires': ['ready']}],
             'trace_assertions': [count_assertion()]}
        self.assertEqual(coverage(w, max_steps=1)['status'], 'unknown')
        self.assertEqual(coverage(w, max_steps=2)['first_trigger_path'], ['prepare', 'generate'])

    def test_state_cap_absence_unknown_but_admitted_edge_witness_valid(self):
        w = {'actions': [{'id': 'prepare', 'adds': ['ready']},
                         {'id': 'generate', 'requires': ['ready']}],
             'trace_assertions': [count_assertion()]}
        self.assertEqual(coverage(w, max_states=1)['status'], 'unknown')
        w['actions'][1]['requires'] = []
        self.assertEqual(coverage(w, max_states=1)['first_trigger_path'], ['generate'])

    def test_counted_set_and_shortest_action_order(self):
        w = {'actions': [{'id': 'second'}, {'id': 'first'}],
             'trace_assertions': [count_assertion(('first', 'second'))]}
        self.assertEqual(coverage(w)['trigger_actions'], ['first', 'second'])
        self.assertEqual(coverage(w)['first_trigger_path'], ['second'])

    def test_refresh_without_guard_does_not_trigger_freshness(self):
        w = {'actions': [{'id': 'verify'}, {'id': 'edit'}, {'id': 'approve', 'requires': ['never']}],
             'trace_assertions': [freshness_assertion()]}
        self.assertEqual(coverage(w)['status'], 'unreachable')

    def test_independent_random_prefix_oracle_400_models(self):
        rng = random.Random(712031)
        for case in range(400):
            actions = []
            for aid in ('verify', 'edit', 'approve'):
                action = {'id': aid}
                for key in ('requires', 'adds', 'removes'):
                    action[key] = [fact for fact in ('x', 'y') if rng.randrange(3) == 0]
                actions.append(action)
            assertion = (freshness_assertion(bool(case % 2)) if case % 3 else
                         count_assertion(('approve',), maximum=case % 4))
            w = {'actions': actions, 'initial': [f for f in ('x', 'y') if rng.randrange(2)],
                 'trace_assertions': [assertion]}
            forbidden = ['edit'] if case % 5 == 0 else []
            depth = case % 6
            expected = enumerate_trigger(w, depth, forbidden)
            got = coverage(w, max_steps=depth, forbidden=forbidden)
            self.assertEqual(got['first_trigger_path'], expected, (case, w, got))
            self.assertEqual(got['status'] == 'reachable', expected is not None, case)


class TraceCoverageIntegrationTests(unittest.TestCase):
    def test_zero_max_with_forbidden_counted_action_is_info_only(self):
        b = bundle(); w = b['contract']['workflows'][0]
        w['goal'] = []; w['trace_assertions'][0]['max_count'] = 0
        rule = copy.deepcopy(b['contract']['rules'][0])
        rule.update(id='disabled', kind='prohibition', forbid_action='run')
        b['contract']['rules'].append(rule)
        r = analyze(b)
        self.assertEqual(r['summary']['error'], 0)
        self.assertEqual(r['trace_checks'][0]['status'], 'safe')
        info = next(d for d in r['diagnostics'] if d['code'] == 'TRACE_TRIGGER_UNREACHABLE')
        self.assertEqual(info['severity'], 'info')
        self.assertEqual(info['source_spans'], [w['trace_assertions'][0]['source']])
        self.assertFalse(r['coverage']['incomplete'])

    def test_optional_workflow_context_is_inactive_not_defective(self):
        b = bundle(); b['contract']['workflows'][0]['when'] = {'online': True}
        b['contract']['contexts'][0]['facts'] = {'online': False}
        r = analyze(b)
        self.assertEqual(r['trace_checks'], [])
        self.assertEqual(r['summary']['error'], 0)
        self.assertEqual(r['summary']['warning'], 0)

    def test_unavailable_tool_action_is_not_trigger_coverage(self):
        b = bundle(); b['contract']['workflows'][0]['actions'][0]['tool_call'] = {'tool': 'absent', 'arguments': {}}
        self.assertEqual(analyze(b)['trace_checks'][0]['trigger_coverage']['status'], 'unreachable')

    def test_unresolved_policy_is_not_unreachable(self):
        b = bundle(); rule = copy.deepcopy(b['contract']['rules'][0])
        rule.update(id='maybe-disabled', kind='prohibition', forbid_action='run', when={'unknown': True})
        b['contract']['rules'].append(rule)
        t = analyze(b)['trace_checks'][0]
        self.assertEqual(t['trigger_coverage']['status'], 'unknown')
        self.assertEqual(t['trigger_coverage']['cutoff_reasons'], ['unresolved_activation'])

    def test_exhausted_aggregate_budget_keeps_coverage_unknown(self):
        b = bundle(); second = copy.deepcopy(b['contract']['workflows'][0]['trace_assertions'][0])
        second['id'] = 'second'; b['contract']['workflows'][0]['trace_assertions'].append(second)
        with patch('prompt_skill_linter.engine.TRACE_STATE_BUDGET', 1):
            t = analyze(b)['trace_checks']
        self.assertEqual(t[0]['trigger_coverage']['status'], 'reachable')
        self.assertEqual(t[1]['trigger_coverage']['status'], 'unknown')
        self.assertIn('aggregate_trace_state_budget', t[1]['trigger_coverage']['cutoff_reasons'])


if __name__ == '__main__': unittest.main()
