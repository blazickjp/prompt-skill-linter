"""Measure offline grammar conformance separately from natural-prose coverage."""
import json
from pathlib import Path
import time
from .run import ROOT,PILOT,read,write,digest,stamp

def grammar_cases():
 cases=[]
 kinds={'REQUIRE':'requirement','FORBID':'prohibition','PERMIT':'permission','PREFER':'preference'}
 for verb,kind in kinds.items():
  for value in (True,False):
   literal=verb.lower()+'_flag';text=f'{verb} {literal}={str(value).lower()}'
   cases.append({'id':f'{verb.lower()}_{value}','text':text,'expected':{'kind':kind,'effect':{'literal':literal,'value':value}}})
 cases += [
 {'id':'lowercase','text':'require flag=true','expected':{'kind':'requirement','effect':{'literal':'flag','value':True}}},
 {'id':'whitespace','text':'  FORBID   file.write = false  ','expected':{'kind':'prohibition','effect':{'literal':'file.write','value':False}}},
 {'id':'disjunction','text':'CLAUSE ready | !blocked','expected':{'kind':'requirement','clause':[{'literal':'ready','value':True},{'literal':'blocked','value':False}]}},
 {'id':'unknown_boolean','text':'REQUIRE ready=maybe','expected':None},
 {'id':'trailing_condition','text':'REQUIRE ready=true unless user_cancelled','expected':None},
 {'id':'empty_atom','text':'CLAUSE ready |','expected':None},
 {'id':'natural_negation','text':'Never disclose secrets.','expected':None},
 {'id':'natural_exception','text':'Always use the API unless the user requests a browser.','expected':None},
 {'id':'conditional_english','text':'If a request needs approval, ask the user before sending it.','expected':None},
 {'id':'plain_description','text':'This document describes the assistant.','expected':None}]
 return cases

def run():
 from prompt_skill_linter.extraction import extract
 from prompt_skill_linter.service import analyze
 protocol={'stage':'offline_annotation_grammar_conformance_and_raw_prose_coverage','expected_labels':'Grammar expectations authored from documented syntax, not human semantic gold. Natural binding coverage counts supported candidates, not understanding accuracy.','natural_inputs':'The same 24 frozen case policy fields; no full-policy inference is claimed.','acceptance':'End-to-end run automatically accepts only mechanically supported annotations for this test; no unsupported English is silently accepted.'}
 cases=grammar_cases();write(PILOT/'extraction_cases.json',{'protocol':protocol,'cases':cases})
 rows=[];start=time.perf_counter()
 for case in cases:
  output=extract([{'id':'test','name':'test.txt','text':case['text']}]);supported=[c for c in output['candidates'] if c['supported']]
  prediction=None
  if len(supported)==1:prediction={k:v for k,v in supported[0]['rule'].items() if k in ('kind','effect','clause')}
  rows.append({'id':case['id'],'expected':case['expected'],'observed':prediction,'correct':prediction==case['expected'],'exact_source_quote':all(c['source']['quote']==case['text'] for c in output['candidates']),'accepted_without_review':len(output['draft']['contract']['rules'])})
 natural=[]
 for case in read(PILOT/'cases.json')['cases']:
  t=time.perf_counter();result=extract([{'id':case['id'],'name':case['id']+'.txt','text':case['policy']}]);supported=[c for c in result['candidates'] if c['supported']]
  natural.append({'id':case['id'],'origin':case['origin'],'nonempty_source_lines':sum(bool(s.strip()) for s in case['policy'].splitlines()),'supported_binding_candidates':len(supported),'untranslated_lines':len(result['unsupported']),'warning_only_candidates':sum(not c['supported'] for c in result['candidates']),'task_prediction':'abstain' if not supported else 'requires_review','latency_seconds':time.perf_counter()-t})
 return {'version':1,'run_at':stamp(),'extractor_sha256':digest(ROOT/'prompt_skill_linter/extraction.py'),'cases_sha256':digest(PILOT/'extraction_cases.json'),'protocol':protocol,'grammar_results':rows,'grammar_exact_accuracy':sum(r['correct'] for r in rows)/len(rows),'grammar_cases':len(rows),'source_quote_failures':sum(not r['exact_source_quote'] for r in rows),'unexpected_unreviewed_binding_rules':sum(r['accepted_without_review'] for r in rows),'raw_prose_results':natural,'raw_prose_cases':len(natural),'raw_prose_cases_with_binding_candidate':sum(r['supported_binding_candidates']>0 for r in natural),'raw_prose_end_to_end_abstention_rate':sum(r['task_prediction']=='abstain' for r in natural)/len(natural),'natural_language_semantic_precision':None,'natural_language_semantic_recall':None,'latency_seconds':time.perf_counter()-start,'tokens':None,'cost':None,'limitations':['Grammar tests are author-derived conformance checks, not an independent NLP benchmark.','Raw prose coverage is measured; semantic extraction quality is undefined because this offline provider intentionally does not translate English into constraints.','Full raw-prose end-to-end feasibility accuracy cannot be established by the reviewed-contract pilot.','No paid/provider-model extraction was executed.']}

if __name__=='__main__':
 result=run();write(PILOT/'extraction_results.json',result)
 print(json.dumps({k:result[k] for k in ('grammar_cases','grammar_exact_accuracy','raw_prose_cases','raw_prose_cases_with_binding_candidate','raw_prose_end_to_end_abstention_rate')},indent=2))
