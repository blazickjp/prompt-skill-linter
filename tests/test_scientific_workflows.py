import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.scientific_workflows import DEFAULT, classify, local_path, mechanical, score, verify
from prompt_skill_linter.service import examples


class ScientificWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = examples()['examples'][2]['bundle']
        self.bundle['contract']['interpretation'] = {'status': 'accepted', 'method': 'test fixture', 'accepted_candidate_ids': []}
        self.catalog = {'version': 1, 'cases': [{'id': 'one', 'family': 'demo', 'origin': 'deployment_probe', 'query': 'completion_reachability', 'bundle': 'bundle.json', 'review': {'status': 'accepted_projection', 'rationale': 'Test-only explicit finite projection.'}}]}
        self.freeze()

    def freeze(self):
        for name, data in [('bundle.json', self.bundle), ('catalog.json', self.catalog)]:
            (self.root / name).write_text(json.dumps(data))
        hashes = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest() for name in ('bundle.json', 'catalog.json')}
        (self.root / 'freeze.json').write_text(json.dumps({'sha256': hashes}))

    def test_replays_reviewed_projection(self):
        self.assertEqual(verify(self.root)['cases'], 1)
        result = mechanical(self.root)
        self.assertEqual(result['predictions'][0]['label'], 'issue')
        self.assertIsNone(result['cost'])
        self.assertIn('one', result['reports'])
        self.assertIsNotNone(result['predictions'][0]['workflows'][0]['fallback_path'])

    def test_changed_frozen_input_fails_closed(self):
        (self.root / 'bundle.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Frozen input differs'): verify(self.root)

    def test_candidate_cannot_be_silently_accepted(self):
        self.bundle['contract']['interpretation']['status'] = 'candidate'
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'unaccepted'): mechanical(self.root)

    def test_partial_translation_abstains(self):
        self.catalog['cases'][0]['review']['status'] = 'partial'
        self.freeze()
        result = mechanical(self.root)
        self.assertEqual(result['predictions'][0]['label'], 'abstain')
        self.assertEqual(result['reports'], {})

    def test_unfrozen_evidence_rejected(self):
        self.catalog['cases'][0]['evidence_files'] = ['missing.json']
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'evidence must be frozen'): verify(self.root)

    def test_duplicate_cases_rejected(self):
        self.catalog['cases'].append(copy.deepcopy(self.catalog['cases'][0]))
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'unique'): verify(self.root)

    def test_path_boundaries(self):
        for path in ('../x', '/tmp/x', 'a/../x', 'a//x', 'a\\x', 'file:x'):
            with self.subTest(path=path), self.assertRaises(ValueError): local_path(self.root, path)
        outside = self.root.parent / 'outside-test-scientific-workflow'
        (self.root / 'link').symlink_to(outside)
        with self.assertRaises(ValueError): local_path(self.root, 'link/x')

    def test_unknown_and_inactive_abstain(self):
        self.assertEqual(classify({'workflow_checks': []})[0], 'abstain')
        self.assertEqual(classify({'workflow_checks': [{'status': 'unknown'}]})[0], 'abstain')
        self.assertEqual(classify({'workflow_checks': [{'status': 'unreachable', 'search_exhaustive': False}]})[0], 'abstain')

    def test_reachable_does_not_hide_other_errors(self):
        report = {'workflow_checks': [{'status': 'reachable'}], 'summary': {'error': 1}}
        self.assertEqual(classify(report)[0], 'abstain')
        report['summary']['error'] = 0
        self.assertEqual(classify(report)[0], 'no_issue')

    def test_scoring_retains_ambiguous_references(self):
        actual = mechanical(self.root)
        native = {'arm': 'native', 'predictions': [{'id': 'one', 'label': 'no_issue', 'rationale': 'test'}]}
        refs = {'labels': [{'id': 'one', 'label': 'abstain'}]}
        result = score(self.root, actual, native, refs)
        self.assertIsNone(result['arms']['native']['all']['recall'])
        self.assertEqual(result['arms']['native']['all']['counts']['excluded_reference_ambiguous'], 1)
        self.assertIn('deployment_probe', result['arms']['native']['by_origin'])

    def test_duplicate_reference_rejected(self):
        actual = mechanical(self.root)
        native = {'arm': 'native', 'predictions': [{'id': 'one', 'label': 'no_issue', 'rationale': 'test'}]}
        refs = {'labels': [{'id': 'one', 'label': 'issue'}] * 2}
        with self.assertRaisesRegex(ValueError, 'exactly once'): score(self.root, actual, native, refs)

    def test_stale_predictions_rejected(self):
        actual = mechanical(self.root)
        actual['input_freeze_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'frozen input snapshot'):
            score(self.root, actual, {}, {})

    def test_three_arm_scoring(self):
        actual = mechanical(self.root)
        plain = {'arm': 'plain', 'predictions': [{'id': 'one', 'label': 'issue', 'rationale': 'test'}]}
        structured = {'arm': 'structured', 'predictions': [{'id': 'one', 'label': 'abstain', 'rationale': 'test'}]}
        result = score(self.root, actual, plain, {'labels': [{'id': 'one', 'label': 'issue'}]}, [structured])
        self.assertEqual(len(result['arms']), 3)
        self.assertEqual(result['arms']['structured']['all']['recall'], 0)

    def test_abstention_is_not_measured_specificity(self):
        actual = mechanical(self.root)
        native = {'arm': 'native', 'predictions': [{'id': 'one', 'label': 'abstain', 'rationale': 'test'}]}
        result = score(self.root, actual, native, {'labels': [{'id': 'one', 'label': 'no_issue'}]})
        metrics = result['arms']['native']['all']
        self.assertEqual(metrics['population_false_alarm_rate'], 0)
        self.assertIsNone(metrics['selective_false_positive_rate'])
        self.assertEqual(metrics['negative_coverage'], 0)

    def test_actual_frozen_corpus_keeps_incomplete_coverage(self):
        self.assertEqual(verify(DEFAULT)['cases'], 13)
        result = mechanical(DEFAULT)
        issues = {p['id'] for p in result['predictions'] if p['label'] == 'issue'}
        self.assertEqual(issues, {'KD-SC-02', 'KD-WR-02', 'KD-LR-02', 'KD-LR-04'})
        self.assertEqual(sum(p['label'] == 'abstain' for p in result['predictions']), 9)
        self.assertEqual(len(result['reports']), 9)
        self.assertTrue(all(r['coverage']['incomplete'] for r in result['reports'].values()))


if __name__ == '__main__': unittest.main()
