"""Independent bounded truth-completion oracle for uncertain rule activation.

The oracle enumerates Boolean fact completions and resolves each finite policy
independently. This checks soundness, not natural-language extraction accuracy.
"""
import copy
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from prompt_skill_linter.engine import lint

src = {'source_id': 's', 'start_line': 1, 'end_line': 1, 'quote': 'rule'}

def group(r):return (r['scope']['entity'],r['scope']['temporal'],r['effect']['literal'])
def oracle(rules,facts):
 active=[r for r in rules if all(facts[k]==v for k,v in r['when'].items()) and not any(all(facts[k]==v for k,v in e.items()) for e in r['exceptions']) and r['kind']!='preference']
 groups={}
 for r in active:groups.setdefault(group(r),[]).append(r)
 bad=set()
 for k,rs in groups.items():
  kept=[];binding=[]
  for r in sorted(rs,key=lambda x:-x['priority']):
   value=r['effect']['value'] != (r['kind']=='prohibition')
   shadow=False
   for h in kept:
    if h['priority']<=r['priority']:continue
    hv=h['effect']['value'] != (h['kind']=='prohibition')
    if h['kind']=='permission':shadow|=r['kind']=='prohibition' and h['effect']['value']==r['effect']['value']
    else:shadow|=hv!=value
   if not shadow:
    kept.append(r)
    if r['kind']!='permission':binding.append(value)
  if True in binding and False in binding:bad.add(k)
 return bad

class AdversarialSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'source.txt').write_text('rule\n')

    def test_hard_collision_survives_every_missing_fact_completion(self):
        rng = random.Random(301)
        root = self.root
        count=errors=0
        for case in range(600):
         rules=[]
         for i in range(rng.randrange(2,9)):
          cond=lambda:{k:rng.choice([True,False]) for k in ['a','b'] if rng.random()<.35}
          rules.append({'id':str(i),'source':src,'scope':{'entity':'task','temporal':'run'},'priority':rng.randrange(3),'kind':rng.choice(['requirement','prohibition','permission','preference']),'when':cond(),'exceptions':[cond()] if rng.random()<.3 else [],'effect':{'literal':rng.choice(['x','y']),'value':rng.choice([True,False])}})
         facts={k:rng.choice([True,False]) for k in ['a','b'] if rng.random()<.5};missing=[k for k in ['a','b'] if k not in facts]
         completion_bad=[oracle(rules,{**facts,**dict(zip(missing,vals))}) for vals in itertools.product([False,True],repeat=len(missing))]
         c={'version':1,'sources':[{'id':'s','path':'source.txt'}],'rules':rules,'contexts':[{'id':'c','facts':facts,'active_skills':[]}]}
         report=lint(c,{'tools':{}},{},root)
         for d in report['diagnostics']:
          if d['code']=='INCOMPATIBLE_OBLIGATIONS':
           k=group(d['interpreted_rules'][0]);assert all(k in bad for bad in completion_bad),json.dumps({'case':case,'facts':facts,'rules':rules,'bad':[list(x) for x in completion_bad]})
           errors+=1
         count+=1
        self.assertEqual(count, 600)
        self.assertGreater(errors, 0, 'The oracle must exercise actual hard findings')

    def test_unknown_group_preserves_independent_exact_and_boolean_findings(self):
        def rule(rid, literal, value, **extra):
            return {'id': rid, 'source': src, 'scope': {'entity': 'task', 'temporal': 'run'},
                    'priority': 0, 'kind': 'requirement', 'when': {}, 'exceptions': [],
                    'effect': {'literal': literal, 'value': value}, **extra}
        rules = [rule('x_true', 'x', True), rule('x_false', 'x', False),
                 rule('uncertain_y', 'y', True, when={'missing': True},
                      tool_call={'tool': 'missing_tool', 'arguments': {}})]
        contract = {'version': 1, 'sources': [{'id': 's', 'path': 'source.txt'}], 'rules': rules,
                    'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}]}
        report = lint(contract, {'tools': {}}, {}, self.root)
        codes = {d['code'] for d in report['diagnostics']}
        self.assertTrue({'UNRESOLVED_ACTIVATION', 'BROKEN_TOOL_REFERENCE',
                         'INCOMPATIBLE_OBLIGATIONS'} <= codes)
        self.assertTrue(report['coverage']['incomplete'])


if __name__ == '__main__':
    unittest.main()
