"""Reproducibility checks for source-pinned selected development cases."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from evaluation.research_extensions import DEFAULT, reproduce, verify
from prompt_skill_linter.engine import ContractError
from prompt_skill_linter.service import analyze


class ResearchExtensionTests(unittest.TestCase):
    def test_all_16_separately_labeled_cases_reproduce(self):
        report = reproduce()
        self.assertEqual(len(report['cases']), 16)
        self.assertEqual(report['counts_by_origin'], {'natural_candidate':1,'natural_control':1,'synthetic_control':14})
        self.assertTrue(all(c['passed'] for c in report['cases']))

    def test_source_hashes_git_blobs_licenses_and_bundle_text_verified(self):
        self.assertEqual(verify()['verified_files'], 23)

    def test_natural_manual_projection_is_narrow_and_helper_is_separate(self):
        manual = json.loads((DEFAULT / 'bundles/GH-MANUAL.json').read_text())
        helper = json.loads((DEFAULT / 'bundles/GH-HELPER.json').read_text())
        md, hd = manual['contract']['field_contracts'][0], helper['contract']['field_contracts'][0]
        self.assertNotEqual(md['scope'], hd['scope'])
        self.assertEqual(md['consumer']['provenance']['source_spans'][0]['start_line'], 42)
        self.assertEqual(md['when']['branch'], 'manual')
        self.assertFalse(md['producer']['additional_fields'])
        self.assertEqual(md['adapters'], [])
        self.assertEqual(set(hd['producer']['required_fields']), {'name','detailsUrl','runId','jobId'})
        self.assertTrue(hd['producer']['additional_fields'])
        self.assertEqual(hd['consumer']['provenance']['source_spans'][0]['start_line'], 465)
        self.assertEqual(analyze(manual)['field_checks'][0]['missing_required_fields'], ['detailsUrl'])
        self.assertEqual(analyze(helper)['field_checks'][0]['status'], 'compatible')

    def test_missing_literal_property_assumption_abstains(self):
        b = json.loads((DEFAULT / 'bundles/GH-MANUAL.json').read_text())
        del b['contract']['contexts'][0]['facts']['literal_property_read']
        self.assertEqual(analyze(b)['field_checks'][0]['status'], 'unknown')

    def test_synthetic_producer_mutations_do_not_reuse_contradictory_natural_assumptions(self):
        for cid in ('SYN-OPEN', 'SYN-OPTIONAL-PRODUCER'):
            b = json.loads((DEFAULT / ('bundles/' + cid + '.json')).read_text())
            provenance = b['contract']['field_contracts'][0]['producer']['provenance']
            self.assertEqual({s['source_id'] for s in provenance['source_spans']}, {'review'})
            self.assertTrue(all('Synthetic' in a for a in provenance['assumptions']))
            self.assertNotIn('exactly the requested seven-key projection', json.dumps(provenance))

    def test_source_tamper_is_rejected_by_both_freeze_and_quote_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'corpus'
            shutil.copytree(DEFAULT, root)
            path = root / 'sources/gh-fix-ci.SKILL.md'
            path.write_text(path.read_text().replace('detailsUrl', 'link'))
            with self.assertRaisesRegex(ValueError, 'Frozen research input differs'): verify(root)
        b = json.loads((DEFAULT / 'bundles/GH-MANUAL.json').read_text())
        b['sources']['skill'] = b['sources']['skill'].replace('detailsUrl', 'link')
        with self.assertRaisesRegex(ContractError, 'quote'): analyze(b)

    def test_report_exposes_scoped_witness_without_executing_sources(self):
        # The source's shell/Python/Go text is only an inert provenance input.
        # No imports or subprocess entry points in the producer are available.
        b = json.loads((DEFAULT / 'bundles/GH-MANUAL.json').read_text())
        report = analyze(b)
        diagnostic = report['diagnostics'][0]
        self.assertIn('REQUIRED_FIELD_NOT_PRODUCED', report['report_text'])
        self.assertEqual(diagnostic['triggering_context']['facts']['branch'], 'manual')
        self.assertTrue(diagnostic['witness']['presence_only'])
        self.assertFalse(diagnostic['witness']['runtime_observations_verified'])
        self.assertIn('not proof of runtime failure', diagnostic['interpretation_status'])


if __name__ == '__main__': unittest.main()
