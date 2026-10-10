"""Independent finite-prefix checks for the reviewed trace assertion fragment."""
import copy
from itertools import product
import unittest

from prompt_skill_linter.trace import (
    MAX_ASSERTIONS, MAX_COUNT, MAX_STATES, MAX_STEPS,
    TraceAssertionError, check_trace_assertions, validate_assertions,
)


SOURCE = {'source_id': 'review', 'start_line': 1, 'end_line': 1,
          'quote': 'Reviewer-authored trace requirement.'}


def count_assertion(actions=('generate',), maximum=2, aid='budget'):
    return {'id': aid, 'kind': 'action_count', 'actions': list(actions),
            'max_count': maximum, 'source': dict(SOURCE), 'assumptions': []}


def freshness_assertion(initially_fresh=False):
    return {'id': 'fresh-review', 'kind': 'freshness',
            'invalidate_actions': ['edit'], 'refresh_actions': ['verify'],
            'guarded_actions': ['approve'], 'initially_fresh': initially_fresh,
            'source': dict(SOURCE), 'assumptions': []}


def counter_reset_workflow():
    return {'initial': ['budget'], 'goal': ['complete'], 'actions': [
        {'id': 'generate', 'requires': ['budget'], 'removes': ['budget'], 'adds': ['complete']},
        {'id': 'reset', 'adds': ['budget']},
    ], 'trace_assertions': [count_assertion()]}


def stale_review_workflow():
    return {'initial': ['draft'], 'goal': ['approved'], 'actions': [
        {'id': 'verify', 'requires': ['draft'], 'adds': ['verified']},
        {'id': 'edit', 'requires': ['verified'], 'adds': ['edited']},
        {'id': 'approve', 'requires': ['edited', 'verified'], 'adds': ['approved']},
    ], 'trace_assertions': [freshness_assertion()]}


def raw_trace_violates(assertion, trace):
    """Oracle reconstructs history each time; it has no product-state cache."""
    if assertion['kind'] == 'action_count':
        return sum(event in assertion['actions'] for event in trace) > assertion['max_count']
    for index, action in enumerate(trace):
        if action not in assertion['guarded_actions']:
            continue
        previous = trace[:index]
        edits = [i for i, event in enumerate(previous) if event in assertion['invalidate_actions']]
        last_edit = max(edits, default=-1)
        new_verifications = any(event in assertion['refresh_actions']
                                for event in previous[last_edit + 1:])
        initial_still_valid = assertion['initially_fresh'] and last_edit == -1
        if not (initial_still_valid or new_verifications):
            return True
    return False


def enumerate_prefixes(workflow, assertion, depth, forbidden=()):
    """Brute-force every allowed action string up to depth, without deduping."""
    frontier = [(set(workflow.get('initial', [])), [])]
    for _ in range(depth):
        following = []
        for facts, trace in frontier:
            for action in workflow['actions']:
                if action['id'] in forbidden:
                    continue
                if not all(fact in facts for fact in action.get('requires', [])):
                    continue
                next_facts = {fact for fact in facts if fact not in action.get('removes', [])}
                next_facts.update(action.get('adds', []))
                next_trace = trace + [action['id']]
                if raw_trace_violates(assertion, next_trace):
                    return next_trace
                following.append((next_facts, next_trace))
        frontier = following
    return None


class TraceTests(unittest.TestCase):
    def check(self, workflow, **kwargs):
        return check_trace_assertions(workflow, **kwargs)[0]

    def test_boolean_budget_reset_cannot_reset_counter(self):
        result = self.check(counter_reset_workflow())
        self.assertEqual(result['status'], 'violated')
        self.assertEqual(result['violation_path'], ['generate', 'reset', 'generate', 'reset', 'generate'])
        self.assertEqual(result['violation']['observed_count'], 3)
        self.assertEqual(result['violation']['max_count'], 2)
        self.assertFalse(result['search_exhaustive'])

    def test_counts_action_set_cumulatively(self):
        workflow = {'actions': [{'id': 'first', 'adds': ['next']},
                                {'id': 'second', 'requires': ['next']}],
                    'trace_assertions': [count_assertion(('first', 'second'), 1)]}
        result = self.check(workflow)
        self.assertEqual(result['violation_path'], ['first', 'first'])
        workflow['actions'][0]['requires'] = ['once']
        workflow['actions'][0]['removes'] = ['once']
        workflow['initial'] = ['once']
        self.assertEqual(self.check(workflow)['violation_path'], ['first', 'second'])

    def test_pure_noop_loop_still_counts_events(self):
        result = self.check({'actions': [{'id': 'generate'}],
                             'trace_assertions': [count_assertion(maximum=4)]})
        self.assertEqual(result['violation_path'], ['generate'] * 5)
        self.assertEqual(result['visited_states'], 5)

    def test_stale_fact_cannot_manufacture_fresh_review(self):
        result = self.check(stale_review_workflow())
        self.assertEqual(result['status'], 'violated')
        self.assertEqual(result['violation_path'], ['verify', 'edit', 'approve'])
        self.assertFalse(result['violation']['fresh_before_action'])

    def test_freshness_monitor_not_merged_when_facts_identical(self):
        workflow = {'actions': [{'id': 'verify'}, {'id': 'edit'}, {'id': 'approve'}],
                    'trace_assertions': [freshness_assertion(initially_fresh=True)]}
        self.assertEqual(self.check(workflow)['violation_path'], ['edit', 'approve'])

    def test_initially_fresh_is_explicit_and_guard_does_not_consume_it(self):
        workflow = {'actions': [{'id': 'verify'}, {'id': 'edit', 'requires': ['never']},
                                {'id': 'approve'}],
                    'trace_assertions': [freshness_assertion(initially_fresh=True)]}
        self.assertEqual(self.check(workflow)['status'], 'safe')
        workflow['trace_assertions'][0]['initially_fresh'] = False
        self.assertEqual(self.check(workflow)['violation_path'], ['approve'])

    def test_safe_budget_control_is_exhaustive(self):
        workflow = {'initial': ['one', 'two'], 'actions': [
            {'id': 'g1', 'requires': ['one'], 'removes': ['one']},
            {'id': 'g2', 'requires': ['two'], 'removes': ['two']},
            {'id': 'noop'},
        ], 'trace_assertions': [count_assertion(('g1', 'g2'))]}
        result = self.check(workflow, max_steps=2)
        self.assertEqual(result['status'], 'safe')
        self.assertTrue(result['search_exhaustive'])
        self.assertEqual(result['visited_states'], 4)
        self.assertIsNone(result['violation_path'])

    def test_safe_freshness_control_requires_new_event(self):
        workflow = stale_review_workflow()
        workflow['actions'][1]['removes'] = ['verified']
        result = self.check(workflow)
        self.assertEqual(result['status'], 'safe')
        self.assertTrue(result['search_exhaustive'])

    def test_empty_invalidating_set_is_supported(self):
        workflow = stale_review_workflow()
        workflow['trace_assertions'][0]['invalidate_actions'] = []
        self.assertEqual(self.check(workflow)['status'], 'safe')

    def test_forbidden_and_unavailable_actions_have_same_semantics(self):
        workflow = counter_reset_workflow()
        for forbidden in (['generate'], {'reset'}, ('generate',), frozenset({'reset'})):
            with self.subTest(forbidden=forbidden):
                self.assertEqual(self.check(workflow, forbidden=forbidden)['status'], 'safe')
        self.assertEqual(self.check(workflow, forbidden=['unknown'])['status'], 'violated')
        workflow = stale_review_workflow()
        self.assertEqual(self.check(workflow, forbidden=['verify'])['status'], 'safe')
        self.assertEqual(self.check(workflow, forbidden=['edit'])['status'], 'safe')

    def test_zero_budget_including_disabled_action(self):
        workflow = {'actions': [{'id': 'generate'}], 'trace_assertions': [count_assertion(maximum=0)]}
        self.assertEqual(self.check(workflow)['violation_path'], ['generate'])
        workflow['actions'][0]['requires'] = ['absent']
        self.assertEqual(self.check(workflow)['status'], 'safe')

    def test_zero_depth_is_unknown_if_next_event_can_violate(self):
        workflow = {'actions': [{'id': 'generate'}], 'trace_assertions': [count_assertion(maximum=0)]}
        result = self.check(workflow, max_steps=0)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['cutoff_reasons'], ['max_steps'])
        self.assertIsNone(result['violation_path'])
        workflow['actions'][0]['requires'] = ['absent']
        self.assertEqual(self.check(workflow, max_steps=0)['status'], 'safe')

    def test_zero_depth_can_prove_closed_safe_loop(self):
        workflow = {'actions': [{'id': 'verify', 'requires': ['absent']}, {'id': 'approve'}],
                    'trace_assertions': [freshness_assertion(initially_fresh=True)]}
        workflow['trace_assertions'][0]['invalidate_actions'] = []
        self.assertEqual(self.check(workflow, max_steps=0)['status'], 'safe')

    def test_depth_limit_does_not_report_out_of_bound_witness(self):
        workflow = counter_reset_workflow()
        for depth in range(5):
            result = self.check(workflow, max_steps=depth)
            self.assertEqual(result['status'], 'unknown')
            self.assertFalse(result['search_exhaustive'])
        self.assertEqual(self.check(workflow, max_steps=5)['status'], 'violated')

    def test_state_cap_is_unknown_and_never_exceeded(self):
        for cap in range(1, 5):
            result = self.check(counter_reset_workflow(), max_states=cap)
            self.assertEqual(result['status'], 'unknown')
            self.assertLessEqual(result['visited_states'], cap)
            self.assertEqual(result['cutoff_reasons'], ['max_states'])

    def test_state_cutoff_does_not_hide_same_layer_violation(self):
        workflow = {'actions': [{'id': 'grow', 'adds': ['x']}, {'id': 'generate'}],
                    'trace_assertions': [count_assertion(maximum=0)]}
        result = self.check(workflow, max_states=1)
        self.assertEqual(result['violation_path'], ['generate'])
        self.assertEqual(result['status'], 'violated')
        self.assertEqual(result['visited_states'], 1)

    def test_state_cutoff_never_labels_longer_partial_path_shortest(self):
        workflow = {'initial': ['start'], 'actions': [
            {'id': 'long1', 'requires': ['start'], 'adds': ['l1'], 'removes': ['start']},
            {'id': 'short', 'requires': ['start'], 'adds': ['short'], 'removes': ['start']},
            {'id': 'long2', 'requires': ['l1'], 'adds': ['l2']},
            {'id': 'generate', 'requires': ['l2']},
            {'id': 'shortcut', 'requires': ['short']},
        ], 'trace_assertions': [count_assertion(('generate', 'shortcut'), 0)]}
        self.assertEqual(self.check(workflow)['violation_path'], ['short', 'shortcut'])
        result = self.check(workflow, max_states=2)
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['violation_path'])

    def test_add_wins_when_fact_also_removed_as_in_planner(self):
        workflow = {'actions': [{'id': 'prepare', 'adds': ['x'], 'removes': ['x']},
                                {'id': 'generate', 'requires': ['x']}],
                    'trace_assertions': [count_assertion(maximum=0)]}
        self.assertEqual(self.check(workflow)['violation_path'], ['prepare', 'generate'])

    def test_shortest_witness_uses_action_order_tie_break(self):
        workflow = {'actions': [{'id': 'setup', 'adds': ['x']}, {'id': 'second'}, {'id': 'first'},
                                {'id': 'later', 'requires': ['x']}],
                    'trace_assertions': [count_assertion(('first', 'second', 'later'), 0)]}
        self.assertEqual(self.check(workflow)['violation_path'], ['second'])

    def test_independent_assertions_keep_separate_monitors_and_budgets(self):
        workflow = counter_reset_workflow()
        workflow['trace_assertions'].append(count_assertion(maximum=0, aid='none'))
        results = check_trace_assertions(workflow, max_steps=1)
        self.assertEqual([r['assertion_id'] for r in results], ['budget', 'none'])
        self.assertEqual([r['status'] for r in results], ['unknown', 'violated'])

    def test_absent_assertions_preserve_legacy_input_and_do_no_inference(self):
        self.assertEqual(check_trace_assertions({'description': 'Never generate more than two images.'}), [])
        self.assertEqual(check_trace_assertions({'trace_assertions': []}), [])

    def test_no_io_or_source_tools_and_no_input_mutation(self):
        workflow = counter_reset_workflow()
        workflow['actions'][0]['tool_call'] = {'tool': 'not-an-executed-tool', 'arguments': {}}
        before = copy.deepcopy(workflow)
        self.assertEqual(self.check(workflow)['status'], 'violated')
        self.assertEqual(workflow, before)

    def test_invalid_bounds_and_forbidden(self):
        workflow = counter_reset_workflow()
        for field, values in [('max_steps', [-1, True, 1.5, '2', MAX_STEPS + 1]),
                              ('max_states', [0, -1, True, 1.5, MAX_STATES + 1]),
                              ('forbidden', ['generate', {'x': 'generate'}, [None], [0]])]:
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(TraceAssertionError):
                    check_trace_assertions(workflow, **{field: value})

    def test_invalid_assertion_declarations(self):
        mutations = [
            lambda w: w.update(trace_assertions={}),
            lambda w: w.update(trace_assertions=[None]),
            lambda w: w.update(trace_assertions=w['trace_assertions'] * (MAX_ASSERTIONS + 1)),
            lambda w: w['trace_assertions'].append(copy.deepcopy(w['trace_assertions'][0])),
            lambda w: w['trace_assertions'][0].update(id=''),
            lambda w: w['trace_assertions'][0].update(kind='prose'),
            lambda w: w['trace_assertions'][0].update(kind=[]),
            lambda w: w['trace_assertions'][0].pop('source'),
            lambda w: w['trace_assertions'][0].pop('assumptions'),
            lambda w: w['trace_assertions'][0].update(extra=True),
            lambda w: w['trace_assertions'][0].update(max_count=True),
            lambda w: w['trace_assertions'][0].update(max_count=-1),
            lambda w: w['trace_assertions'][0].update(max_count=MAX_COUNT + 1),
            lambda w: w['trace_assertions'][0].update(actions=[]),
            lambda w: w['trace_assertions'][0].update(actions=['missing']),
            lambda w: w['trace_assertions'][0].update(actions=['generate', 'generate']),
            lambda w: w['trace_assertions'][0].update(actions='generate'),
            lambda w: w['trace_assertions'][0].update(assumptions='reviewed'),
            lambda w: w['trace_assertions'][0].update(assumptions=['x'] * 33),
            lambda w: w['trace_assertions'][0].update(source={}),
            lambda w: w['trace_assertions'][0]['source'].update(source_id=''),
            lambda w: w['trace_assertions'][0]['source'].update(start_line=True),
            lambda w: w['trace_assertions'][0]['source'].update(start_line=0),
            lambda w: w['trace_assertions'][0]['source'].update(start_line=2),
            lambda w: w['trace_assertions'][0]['source'].update(quote=None),
            lambda w: w['trace_assertions'][0]['source'].update(unchecked='bad'),
        ]
        for index, mutate in enumerate(mutations):
            workflow = counter_reset_workflow()
            mutate(workflow)
            with self.subTest(mutation=index), self.assertRaises(TraceAssertionError):
                validate_assertions(workflow)

    def test_invalid_freshness_declarations(self):
        for field, value in [('initially_fresh', 1), ('refresh_actions', []), ('guarded_actions', []),
                             ('invalidate_actions', ['verify']), ('guarded_actions', ['verify']),
                             ('refresh_actions', ['verify', 'verify']), ('invalidate_actions', ['missing']),
                             ('actions', ['verify']), ('max_count', 2)]:
            workflow = stale_review_workflow()
            workflow['trace_assertions'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(TraceAssertionError):
                validate_assertions(workflow)
        workflow = stale_review_workflow()
        workflow['trace_assertions'][0].pop('initially_fresh')
        with self.assertRaises(TraceAssertionError):
            validate_assertions(workflow)

    def test_invalid_finite_model_inputs(self):
        for mutate in [lambda w: w.update(actions=None), lambda w: w.update(actions=[None]),
                       lambda w: w.update(actions=[{'id': ''}]),
                       lambda w: w.update(actions=w['actions'] * 33),
                       lambda w: w['actions'].append({'id': 'generate'}),
                       lambda w: w['actions'][0].update(requires='budget'),
                       lambda w: w['actions'][0].update(adds=[False]),
                       lambda w: w.update(initial=[str(i) for i in range(256)]),
                       lambda w: w.update(initial=[str(i) for i in range(257)])]:
            workflow = counter_reset_workflow()
            mutate(workflow)
            with self.assertRaises(TraceAssertionError):
                validate_assertions(workflow)
        with self.assertRaises(TraceAssertionError):
            validate_assertions(None)

    def test_small_exhaustive_comparison_to_raw_trace_enumeration(self):
        # One Boolean fact has two valuations. A count budget <=2 needs <=3
        # safe monitor states, and freshness needs two. Thus a shortest bad
        # prefix, if any, has length <=6. The oracle enumerates action strings
        # without importing monitor updates or visited-state logic from trace.py.
        variants = [(required, effect) for required in (False, True) for effect in ('keep', 'add', 'remove')]
        checked = 0
        for action_variants in product(variants, repeat=3):
            actions = []
            for aid, (required, effect) in zip(('edit', 'verify', 'approve'), action_variants):
                action = {'id': aid, 'requires': ['x'] if required else []}
                if effect != 'keep':
                    action['adds' if effect == 'add' else 'removes'] = ['x']
                actions.append(action)
            assertions = [count_assertion(('edit', 'approve'), n) for n in range(3)]
            assertions += [freshness_assertion(fresh) for fresh in (False, True)]
            for assertion, initial, forbidden in product(assertions, ([], ['x']), ((), ('verify',))):
                workflow = {'initial': initial, 'actions': actions, 'trace_assertions': [assertion]}
                expected = enumerate_prefixes(workflow, assertion, 6, forbidden)
                result = self.check(workflow, forbidden=forbidden, max_steps=6, max_states=12)
                self.assertEqual(result['status'], 'violated' if expected is not None else 'safe',
                                 (workflow, forbidden, expected, result))
                self.assertEqual(result['violation_path'], expected)
                checked += 1
        self.assertEqual(checked, 4320)

    def test_cutoff_results_never_overstate_exhaustion_or_witness_minimality(self):
        for workflow in (counter_reset_workflow(), stale_review_workflow()):
            oracle = enumerate_prefixes(workflow, workflow['trace_assertions'][0], 8)
            self.assertIsNotNone(oracle)
            for depth, states in product(range(8), range(1, 9)):
                result = self.check(workflow, max_steps=depth, max_states=states)
                self.assertLessEqual(result['visited_states'], states)
                self.assertNotEqual(result['status'], 'safe')
                self.assertFalse(result['search_exhaustive'])
                if result['status'] == 'violated':
                    self.assertEqual(result['violation_path'], oracle)
                    self.assertLessEqual(len(result['violation_path']), depth)
                else:
                    self.assertIsNone(result['violation_path'])
                    self.assertTrue(result['cutoff_reasons'])


if __name__ == '__main__':
    unittest.main()
