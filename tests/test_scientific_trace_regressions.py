import copy
import json
from pathlib import Path
import unittest

from prompt_skill_linter.service import analyze

ROOT = Path(__file__).resolve().parents[1] / 'corpus/scientific_workflows/post_audit_traces'

def load(name): return json.loads((ROOT / name).read_text())

def step(workflow, trace):
    state = set(workflow['initial']); actions = {a['id']: a for a in workflow['actions']}
    for name in trace:
        action = actions[name]
        if not set(action.get('requires', [])) <= state:
            return False, state
        state.difference_update(action.get('removes', []));state.update(action.get('adds', []))
    return True, state


class ScientificTraceRegressionTests(unittest.TestCase):
    def test_original_violations_and_corrected_safety(self):
        for case in load('manifest.json')['cases']:
            b = load(Path(case['bundle']).name)
            report = analyze(b)
            with self.subTest(case=case['id']):
                self.assertEqual(report['trace_checks'][0]['status'], case['expected_trace_status'])
                self.assertTrue(report['coverage']['incomplete'])
                self.assertEqual(report['workflow_checks'][0]['status'], 'reachable' if 'WR' in case['id'] else 'unreachable')
                if case['expected_trace_status'] == 'violated':
                    path = report['trace_checks'][0]['violation_path']
                    self.assertTrue(step(b['contract']['workflows'][0], path)[0])
                    self.assertTrue(report['trace_checks'][0]['completion_feasibility_not_disproved'])
                else:
                    self.assertTrue(report['trace_checks'][0]['search_exhaustive'])

    def test_image_budget_cannot_reset(self):
        prefix = ['compare_citations_claims_to_local_sources', 'synthesize_narrative_review']
        traces = [prefix + ['generate_first_png'] * 3,
                  prefix + ['generate_first_png', 'record_first_low_review', 'generate_second_png',
                            'record_second_low_review', 'record_first_low_review', 'generate_second_png']]
        original = load('KD-LR-04-original.json')['contract']['workflows'][0]
        corrected = load('KD-LR-04-corrected.json')['contract']['workflows'][0]
        for trace in traces:
            self.assertTrue(step(original, trace)[0])
            self.assertFalse(step(corrected, trace)[0])

    def test_redrafting_invalidates_and_reverification_recovers(self):
        initial = ['create_evidence_outline', 'draft_manuscript', 'human_reverify_changed_prose', 'run_local_consistency_audits']
        original = load('KD-WR-01-original.json')['contract']['workflows'][0]
        corrected = load('KD-WR-01-corrected.json')['contract']['workflows'][0]
        bad = initial + ['draft_manuscript', 'human_approve_ready_and_remove_banner']
        self.assertTrue(step(original, bad)[0]);self.assertFalse(step(corrected, bad)[0])
        approved = initial + ['human_approve_ready_and_remove_banner', 'draft_manuscript']
        ok, state = step(corrected, approved)
        self.assertTrue(ok)
        self.assertNotIn('submission_ready_true', state);self.assertNotIn('banner_removed', state)
        self.assertIn('submission_ready_false', state);self.assertIn('banner_retained', state)
        recovery = approved + ['human_reverify_changed_prose', 'run_local_consistency_audits', 'human_approve_ready_and_remove_banner']
        ok, state = step(corrected, recovery)
        self.assertTrue(ok);self.assertTrue(set(corrected['goal']) <= state)
        self.assertNotIn('submission_ready_false', state);self.assertNotIn('banner_retained', state)


if __name__ == '__main__': unittest.main()
