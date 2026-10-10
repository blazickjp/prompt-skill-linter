import copy
import unittest

from prompt_skill_linter.engine import ContractError
from prompt_skill_linter.service import analyze, examples


class ActionProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.bundle = copy.deepcopy(examples()['examples'][2]['bundle'])
        self.workflow = self.bundle['contract']['workflows'][0]
        self.action = self.workflow['actions'][0]
        self.span = copy.deepcopy(self.bundle['contract']['rules'][0]['source'])
        self.action['provenance'] = {'source_spans': [self.span], 'assumptions': ['Finite deterministic abstraction, not an executed scientific action.']}

    def test_provenance_is_preserved_without_changing_path(self):
        report = analyze(self.bundle)
        checks = report['workflow_checks']
        self.assertEqual([c['status'] for c in checks], ['unreachable', 'reachable'])
        self.assertEqual(checks[0]['action_provenance'][self.action['id']], self.action['provenance'])
        self.assertTrue(checks[0]['provenance_limitations'])
        ds = [d for d in report['diagnostics'] if d['code'] == 'UNSUPPORTED_WORKFLOW']
        self.assertIn(self.action['id'], ds[0]['witness']['action_provenance'])
        self.assertTrue(ds[0]['provenance_limitations'])

    def test_mismatched_quote_fails_closed(self):
        self.span['quote'] += ' invented'
        with self.assertRaisesRegex(ContractError, 'exact line span'): analyze(self.bundle)

    def test_unknown_source_fails_closed(self):
        self.span['source_id'] = 'invented'
        with self.assertRaisesRegex(ContractError, 'unknown source'): analyze(self.bundle)

    def test_invalid_range_fails_closed(self):
        self.span['end_line'] = 999999
        with self.assertRaisesRegex(ContractError, 'exact line span'): analyze(self.bundle)

    def test_provenance_bound(self):
        self.action['provenance']['source_spans'] = [self.span] * 33
        with self.assertRaisesRegex(ContractError, 'at most 32'): analyze(self.bundle)

    def test_legacy_actions_are_not_claimed_grounded(self):
        del self.action['provenance']
        report = analyze(self.bundle)
        self.assertIn(self.action['id'], report['workflow_checks'][0]['provenance_limitations'][0])

    def test_quote_does_not_establish_semantic_equivalence(self):
        for action in self.workflow['actions']:
            action['provenance'] = copy.deepcopy(self.action['provenance'])
        limitations = analyze(self.bundle)['workflow_checks'][0]['provenance_limitations']
        self.assertEqual(len(limitations), 1)
        self.assertIn('reviewed abstraction', limitations[0])


if __name__ == '__main__': unittest.main()
