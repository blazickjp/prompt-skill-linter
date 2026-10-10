import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prompt_skill_linter.engine import ContractError, bulk_feasible, lint, minimal_core

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('Rule one.\nRule two.\nRule three.\nRule four.\n')
        self.contract = {'version': 1, 'sources': [{'id': 's', 'path': 'prompt.txt'}], 'skills': [],
                         'rules': [], 'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}], 'assumptions': []}
        self.tools = {'tools': {}}
        self.runtime = {}

    def rule(self, rid, kind='requirement', value=True, priority=0, **extra):
        r = {'id': rid, 'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'Rule one.'},
             'priority': priority, 'kind': kind, 'when': {}, 'skills': [],
             'scope': {'entity': 'task', 'temporal': 'run'}, 'exceptions': [], 'effect': {'literal': 'x', 'value': value}}
        r.update(extra)
        self.contract['rules'].append(r)
        return r

    def run_lint(self):
        return lint(self.contract, self.tools, self.runtime, self.root)

    def codes(self):
        return [d['code'] for d in self.run_lint()['diagnostics']]

    def bulk(self, budget=30, ns=None):
        c = json.loads((ROOT / 'examples/bulk.contract.json').read_text())
        return lint(c, json.loads((ROOT / 'examples/tools.json').read_text()),
                    {'service_call_budget': budget, 'request_sizes': ns or [150, 151, 184]}, ROOT / 'examples')

    def test_bulk_151_184_and_150_control(self):
        r = self.bulk()
        self.assertEqual([d['witness']['lower_bound_calls'] for d in r['diagnostics']], [32, 38])
        self.assertEqual(r['diagnostics'][0]['witness']['affected_advertised_range'], [151, 200])
        self.assertEqual(r['resource_checks'][0]['status'], 'lower_bound_pass')
        self.assertFalse(r['resource_checks'][0]['completion_guaranteed'])

    def test_increased_budget_controls(self):
        for budget, n in [(32, 151), (38, 184), (40, 200)]:
            self.assertEqual(self.bulk(budget, [n])['diagnostics'], [])

    def test_pairwise_sat_triple_unsat_and_minimality(self):
        core = minimal_core(151, 10, 30)
        self.assertTrue(core['minimality_checked'])
        self.assertEqual(len(core['minimal_core_constraints']), 3)
        self.assertTrue(all(v is not None for v in core['removal_witnesses'].values()))
        self.assertIsNone(bulk_feasible(151, 10, 30, ['coverage', 'polling', 'budget']))

    def test_nonminimal_three_constraint_claim_avoided(self):
        core = minimal_core(400, 10, 30)
        self.assertEqual(core['minimal_core_constraints'], ['coverage', 'budget'])

    def test_integer_arithmetic_never_float(self):
        n = 10**18 + 1
        w = bulk_feasible(n, 10, 10**20, ['coverage', 'polling', 'budget'])
        self.assertGreaterEqual(10 * w['s'], n)

    def test_arithmetic_exhaustive_small_crosscheck(self):
        for n in range(1, 20):
            for budget in range(10):
                for enabled in [[], ['coverage'], ['polling'], ['budget'], ['coverage', 'polling'], ['coverage', 'budget'], ['polling', 'budget'], ['coverage', 'polling', 'budget']]:
                    brute = any(('coverage' not in enabled or 3*s >= n) and ('polling' not in enabled or p >= s) and ('budget' not in enabled or s+p <= budget) for s in range(21) for p in range(21))
                    self.assertEqual(bulk_feasible(n, 3, budget, enabled) is not None, brute)

    def test_conflict(self):
        self.rule('a'); self.rule('b', value=False)
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', self.codes())

    def test_prohibition_forbids_named_value(self):
        self.rule('a'); self.rule('b', kind='prohibition')
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', self.codes())

    def test_permission_is_not_obligation(self):
        self.rule('a', kind='permission'); self.rule('b', kind='prohibition')
        self.assertNotIn('INCOMPATIBLE_OBLIGATIONS', self.codes())

    def test_preference_is_not_obligation(self):
        self.rule('a', kind='preference'); self.rule('b', value=False)
        self.assertNotIn('INCOMPATIBLE_OBLIGATIONS', self.codes())

    def test_hierarchy(self):
        self.rule('a'); self.rule('b', value=False, priority=1)
        self.assertEqual(self.codes(), ['SHADOWED_RULE'])

    def test_overridden_prohibition_cannot_shadow(self):
        self.rule('yes', priority=1); self.rule('no', priority=1, value=False)
        self.rule('ban', priority=2, kind='prohibition'); self.rule('permit', priority=3, kind='permission')
        self.assertIn('INCOMPATIBLE_OBLIGATIONS', self.codes())

    def test_exception(self):
        self.rule('a'); self.rule('b', value=False, exceptions=[{}])
        self.assertEqual(self.codes(), [])

    def test_coactivation(self):
        self.contract['skills'] = [{'id': 'one'}, {'id': 'two'}]
        self.contract['contexts'][0]['active_skills'] = ['one']
        self.rule('a', skills=['one']); self.rule('b', value=False, skills=['two'])
        self.assertEqual(self.codes(), [])

    def test_scopes_do_not_alias(self):
        self.rule('a'); self.rule('b', value=False, scope={'entity': 'other', 'temporal': 'run'})
        self.assertEqual(self.codes(), [])

    def test_missing_fact_does_not_activate(self):
        self.rule('a'); self.rule('b', value=False, when={'flag': False})
        self.assertEqual(self.codes(), [])

    def test_boolean_and_integer_facts_not_equal(self):
        self.contract['contexts'][0]['facts'] = {'flag': 1}
        self.rule('a'); self.rule('b', value=False, when={'flag': True})
        self.assertEqual(self.codes(), [])

    def test_broken_reference(self):
        self.rule('a', tool_call={'tool': 'missing', 'arguments': {}})
        self.assertIn('BROKEN_TOOL_REFERENCE', self.codes())

    def test_invalid_and_missing_arguments(self):
        self.tools = {'tools': {'submit': {'arguments': ['nodes'], 'required': ['nodes']}}}
        self.rule('a', tool_call={'tool': 'submit', 'arguments': {'node': 1}})
        self.assertIn('INVALID_TOOL_ARGUMENTS', self.codes())

    def test_dependency(self):
        self.contract['skills'] = [{'id': 'one', 'requires': ['missing']}]
        self.assertIn('MISSING_DEPENDENCY', self.codes())

    def test_semantic_warning_is_not_error(self):
        self.rule('a', semantic_warnings=['Meaning of promptly is unspecified.'])
        r = self.run_lint()
        self.assertEqual(r['diagnostics'][0]['class'], 'semantic_warning')
        self.assertEqual(r['summary']['error'], 0)

    def workflow(self, fallback=True):
        self.rule('advertise')
        self.rule('ban', kind='prohibition', forbid_action='update')
        self.contract['workflows'] = [{'id': 'update', 'advertisement_rule': 'advertise', 'goal': ['done'],
            'actions': [{'id': 'update', 'adds': ['done']}, {'id': 'refuse'}]}]
        if fallback:
            self.contract['workflows'][0]['compliant_fallback'] = 'refuse'

    def test_refusal_is_compliant_but_workflow_unsupported(self):
        self.workflow()
        self.assertIn('UNSUPPORTED_WORKFLOW', self.codes())

    def test_missing_fallback(self):
        self.workflow(False)
        self.assertIn('MISSING_FALLBACK_PATH', self.codes())

    def test_workflow_scope(self):
        self.workflow()
        self.contract['rules'][1]['scope']['entity'] = 'other'
        self.assertNotIn('UNSUPPORTED_WORKFLOW', self.codes())

    def test_workflow_advertisement_activation(self):
        self.workflow()
        self.contract['rules'][0]['when'] = {'enabled': True}
        self.assertNotIn('UNSUPPORTED_WORKFLOW', self.codes())

    def test_workflow_permission(self):
        self.workflow()
        self.rule('permit', kind='permission', allow_action='update', priority=1)
        self.assertNotIn('UNSUPPORTED_WORKFLOW', self.codes())

    def test_workflow_bound(self):
        self.rule('advertise')
        self.contract['workflows'] = [{'id': 'w', 'advertisement_rule': 'advertise', 'goal': ['done'], 'actions': [{'id': 'a', 'adds': ['ready']}, {'id': 'b', 'requires': ['ready'], 'adds': ['done']}]}]
        self.runtime = {'max_plan_steps': 1}
        self.assertIn('PLAN_BOUND_EXHAUSTED', self.codes())

    def test_wrong_source_quote_rejected(self):
        self.rule('a')['source']['quote'] = 'Made up'
        with self.assertRaises(ContractError): self.run_lint()

    def test_unsupported_field_rejected(self):
        self.rule('a')['unless'] = 'sometimes'
        with self.assertRaises(ContractError): self.run_lint()

    def test_invalid_action_kind_rejected(self):
        self.rule('a', kind='permission', forbid_action='update')
        with self.assertRaises(ContractError): self.run_lint()

    def test_conditional_bulk_rejected(self):
        c = json.loads((ROOT / 'examples/bulk.contract.json').read_text())
        c['rules'][1]['when'] = {'enabled': True}
        with self.assertRaises(ContractError): lint(c, self.tools, {'service_call_budget': 30}, ROOT/'examples')

    def test_cli_exit_and_generated_contract(self):
        out = self.root/'out.json'; contract_out = self.root/'contract.json'
        p = subprocess.run([sys.executable, '-m', 'prompt_skill_linter', 'examples/bulk.contract.json', '--tools', 'examples/tools.json', '--runtime', 'examples/runtime.json', '--format', 'json', '--output', str(out), '--contract-out', str(contract_out)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertEqual(json.loads(out.read_text())['summary']['error'], 2)
        self.assertTrue(contract_out.exists())

    def test_cli_malformed_no_traceback(self):
        bad = self.root/'bad.json'; bad.write_text('{"version": 1}')
        p = subprocess.run([sys.executable, '-m', 'prompt_skill_linter', str(bad), '--tools', 'examples/tools.json', '--runtime', 'examples/runtime.json'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn('Traceback', p.stderr)

    def test_bulk_cross_fragment_effect_rejected(self):
        c = json.loads((ROOT / 'examples/bulk.contract.json').read_text())
        c['rules'][1]['effect'] = {'literal': 'submit', 'value': True}
        with self.assertRaises(ContractError):
            lint(c, self.tools, {'service_call_budget': 30, 'request_sizes': [151]}, ROOT/'examples')

    def test_bulk_mixed_scope_rejected(self):
        c = json.loads((ROOT / 'examples/bulk.contract.json').read_text())
        c['rules'][1]['scope']['entity'] = 'other'
        with self.assertRaises(ContractError):
            lint(c, self.tools, {'service_call_budget': 30, 'request_sizes': [151]}, ROOT/'examples')

    def test_bulk_empty_request_rejected(self):
        c = json.loads((ROOT / 'examples/bulk.contract.json').read_text())
        with self.assertRaises(ContractError):
            lint(c, self.tools, {'service_call_budget': 30, 'request_sizes': []}, ROOT/'examples')

    def test_assumptions_preserved(self):
        self.rule('a'); self.rule('b', value=False)
        self.contract['assumptions'] = ['Unreviewed extraction may be wrong.']
        self.assertIn('Unreviewed extraction may be wrong.', self.run_lint()['diagnostics'][0]['assumptions'])

    def test_path_escape_rejected(self):
        self.rule('a')
        self.contract['sources'][0]['path'] = '../outside.txt'
        with self.assertRaises(ContractError): self.run_lint()

    def test_cli_baseline_regression(self):
        old = self.root/'old.json'; new = self.root/'new.json'
        old.write_text(json.dumps(self.bulk(40, [150, 151, 184])))
        p = subprocess.run([sys.executable, '-m', 'prompt_skill_linter', 'examples/bulk.contract.json', '--tools', 'examples/tools.json', '--runtime', 'examples/runtime.json', '--baseline', str(old), '--format', 'json', '--output', str(new)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertEqual(len(json.loads(new.read_text())['regressions']['introduced']), 2)


if __name__ == '__main__': unittest.main()
