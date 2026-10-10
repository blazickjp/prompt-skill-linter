import json
from pathlib import Path
import tempfile
import unittest
from .run import metric_slice, validate_predictions, verify_freeze

class EvaluationTests(unittest.TestCase):
 def test_metrics_count_positive_abstention_as_miss(self):
  cases=[{'id':x} for x in 'abcd']
  p={x:{'label':label} for x,label in zip('abcd',['issue','issue','abstain','no_issue'])}
  r={x:{'label':label} for x,label in zip('abcd',['issue','no_issue','issue','abstain'])}
  m=metric_slice(cases,p,r)
  self.assertEqual(m['precision'],.5);self.assertEqual(m['recall'],.5)
  self.assertEqual(m['coverage'],.75);self.assertEqual(m['missed_issues'],1)
  self.assertEqual(m['counts']['excluded_reference_ambiguous'],1)
 def test_empty_denominators_are_null(self):
  m=metric_slice([{'id':'x'}],{'x':{'label':'abstain'}},{'x':{'label':'no_issue'}})
  self.assertIsNone(m['precision']);self.assertIsNone(m['recall']);self.assertIsNone(m['selective_accuracy'])
 def test_duplicate_missing_invalid_predictions_rejected(self):
  good={'id':'x','label':'no_issue','rationale':'A witness exists.'}
  for data in [{'predictions':[good,good]},{'predictions':[]},{'predictions':[dict(good,label='pass')]},{'predictions':[dict(good,rationale='')]}]:
   with self.assertRaises(ValueError):validate_predictions(data,{'x'})
 def test_freeze_detects_tampering(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a').write_text('x');(p/'freeze.json').write_text(json.dumps({'sha256':{'a':'wrong'}}))
   with self.assertRaises(ValueError):verify_freeze(p)
 def test_frozen_pilot_has_24_unique_ids(self):
  p=Path(__file__).parent/'pilot'
  verify_freeze(p);cases=json.loads((p/'cases.json').read_text())['cases']
  self.assertEqual(len(cases),24);self.assertEqual(len({c['id'] for c in cases}),24)
if __name__=='__main__':unittest.main()
