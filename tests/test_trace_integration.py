import copy
import unittest
from unittest.mock import patch

from prompt_skill_linter.engine import ContractError
from prompt_skill_linter.service import analyze


def bundle():
    span = {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'No more than two runs.'}
    return {'sources': {'s': 'No more than two runs.\n'}, 'tools': {'tools': {}}, 'runtime': {},
            'contract': {'version': 1, 'sources': [{'id': 's', 'path': 's.txt'}],
                         'rules': [{'id': 'advertise', 'source': span, 'kind': 'requirement', 'priority': 0,
                                    'scope': {'entity': 'task', 'temporal': 'one-run'}}],
                         'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
                         'workflows': [{'id': 'w', 'initial': [], 'goal': ['done'], 'advertisement_rule': 'advertise',
                                        'actions': [{'id': 'run', 'requires': [], 'adds': ['done'],
                                                     'provenance': {'source_spans': [span], 'assumptions': []}}],
                                        'trace_assertions': [{'id': 'max-two', 'kind': 'action_count', 'actions': ['run'],
                                                              'max_count': 2, 'source': span, 'assumptions': []}]}]}}


class TraceIntegrationTests(unittest.TestCase):
    def test_reachable_goal_and_unsafe_path_are_distinct(self):
        report = analyze(bundle())
        self.assertEqual(report['workflow_checks'][0]['status'], 'reachable')
        trace = report['trace_checks'][0]
        self.assertEqual(trace['status'], 'violated')
        self.assertEqual(trace['violation_path'], ['run'] * 3)
        self.assertTrue(trace['completion_feasibility_not_disproved'])
        self.assertTrue(trace['minimality_not_checked'])
        self.assertEqual(trace['implicated_actions'][0]['id'], 'run')
        diagnostic = [d for d in report['diagnostics'] if d['code'] == 'TRACE_ASSERTION_VIOLATED'][0]
        self.assertEqual(diagnostic['regression_case']['assertion_id'], 'max-two')
        self.assertEqual(diagnostic['regression_case']['violation_path'], ['run'] * 3)
        self.assertEqual(diagnostic['resolved_priorities'], {})

    def test_bounds_are_incomplete_not_safe(self):
        b = bundle(); b['runtime']['max_plan_steps'] = 2
        report = analyze(b)
        self.assertEqual(report['trace_checks'][0]['status'], 'unknown')
        self.assertIn('search_bounds', report['coverage']['incomplete_reasons'])

    def test_aggregate_budget_applies_to_later_assertions(self):
        b = bundle(); assertion = copy.deepcopy(b['contract']['workflows'][0]['trace_assertions'][0]); assertion['id'] = 'second'
        b['contract']['workflows'][0]['trace_assertions'].append(assertion)
        with patch('prompt_skill_linter.engine.TRACE_STATE_BUDGET', 1):
            report = analyze(b)
        self.assertEqual([t['status'] for t in report['trace_checks']], ['unknown', 'unknown'])
        self.assertEqual(sum(t['visited_states'] for t in report['trace_checks']), 1)
        self.assertIn('aggregate_trace_state_budget', report['trace_checks'][1]['cutoff_reasons'])

    def test_assertion_quote_and_global_ids_checked(self):
        for field, value in [('quote', 'invented'), ('source_id', 'missing')]:
            b = bundle(); b['contract']['workflows'][0]['trace_assertions'][0]['source'] = dict(b['contract']['rules'][0]['source'], **{field: value})
            with self.assertRaises(ContractError): analyze(b)
        b = bundle(); b['contract']['workflows'][0]['trace_assertions'][0]['id'] = 'advertise'
        with self.assertRaisesRegex(ContractError, 'distinct'): analyze(b)

    def test_unavailable_action_is_not_a_violation(self):
        b = bundle(); b['contract']['workflows'][0]['actions'][0]['tool_call'] = {'tool': 'missing', 'arguments': {}}
        report = analyze(b)
        self.assertEqual(report['trace_checks'][0]['status'], 'safe')
        self.assertEqual(report['workflow_checks'][0]['status'], 'unreachable')

    def test_unknown_policy_abstains(self):
        b = bundle(); r = copy.deepcopy(b['contract']['rules'][0]);r.update(id='maybe-forbid', kind='prohibition', forbid_action='run', when={'unknown': True})
        b['contract']['rules'].append(r)
        report = analyze(b)
        self.assertEqual(report['trace_checks'][0]['status'], 'unknown')
        self.assertEqual(report['trace_checks'][0]['cutoff_reasons'], ['unresolved_activation'])

    def test_duplicate_workflows_rejected(self):
        b = bundle();b['contract']['workflows'].append(copy.deepcopy(b['contract']['workflows'][0]))
        with self.assertRaisesRegex(ContractError, 'workflows need unique'): analyze(b)


if __name__ == '__main__': unittest.main()
