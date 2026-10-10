"""Score source-fragment extraction and synthetic downstream probes."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import tempfile
from .run import ROOT,read,write,verify_freeze,stamp,digest

DIRECTORY=ROOT/'evaluation/extraction_pilot'

def key(rule):return (rule['source_id'],rule['action'])
def canonical_exceptions(rule):return sorted(tuple(sorted(x.items())) for x in rule.get('exceptions',[]))
def score(directory=DIRECTORY):
 directory=Path(directory);verify_freeze(directory)
 cases=read(directory/'cases.json')['cases'];source={c['id']:c for c in cases}
 ref=read(directory/'reference.json');prediction=read(directory/'predictions.json')
 refs={key(r):r for r in ref['rules']};preds={key(r):r for r in prediction['rules']}
 duplicate_predictions=len(prediction['rules'])-len(preds)
 shared=refs.keys()&preds.keys();rows=[]
 for k,p in preds.items():
  r=refs.get(k);s=source.get(p['source_id'])
  rows.append({'source_id':p['source_id'],'action':p['action'],'matched':r is not None,'exact_quote':bool(s and p.get('quote')==s['text']),'exact_local_lines':p.get('start_line')==p.get('end_line')==1,'kind_agreement':p.get('kind')==r.get('kind') if r else None,'when_agreement':p.get('when',{})==r.get('when',{}) if r else None,'exception_agreement':canonical_exceptions(p)==canonical_exceptions(r) if r else None,'binding_supported_agreement':p.get('binding_supported')==r.get('binding_supported') if r else None})
 def ratio(a,b):return a/b if b else None
 metric={'atomic_action_precision':ratio(len(shared),len(preds)),'atomic_action_recall':ratio(len(shared),len(refs)),'reference_atoms':len(refs),'predicted_atoms':len(preds),'matched_atoms':len(shared),'duplicate_predictions':duplicate_predictions,'exact_quote_rate':ratio(sum(r['exact_quote'] for r in rows),len(rows)),'exact_local_line_rate':ratio(sum(r['exact_local_lines'] for r in rows),len(rows))}
 for field in ('kind_agreement','when_agreement','exception_agreement','binding_supported_agreement'):
  metric[field]=ratio(sum(r[field] is True for r in rows),len(shared))
 result={'version':1,'generated_at':stamp(),'scope':'Six hinted source fragments, supplied action vocabulary; provisional native-model references, not NLP product accuracy.','reference_sha256':digest(directory/'reference.json'),'predictions_sha256':digest(directory/'predictions.json'),'metrics':metric,'details':rows,'missing_atoms':[list(k) for k in refs.keys()-preds.keys()],'extra_atoms':[list(k) for k in preds.keys()-refs.keys()],'reference_metadata':ref.get('reviewer'),'prediction_metadata':{k:v for k,v in prediction.items() if k not in ('rules','unsupported')},'unsupported_reference':ref.get('unsupported',[]),'unsupported_predictions':prediction.get('unsupported',[])}
 result['downstream_probes']=downstream(refs,preds,source)
 review_path=directory/'manual_acceptance.json'
 if review_path.exists():
  review=read(review_path);accepted={(x['source_id'],x['action']) for x in review['accepted_actions']}
  reviewed=deepcopy(preds)
  for k,p in reviewed.items():p['binding_supported']=k in accepted
  result['manually_reviewed_downstream_probes']=downstream(refs,reviewed,source)
  result['manual_acceptance_sha256']=digest(review_path)
  result['manual_review_disclosure']='Evaluation-author acceptance of structural Boolean rules for synthetic probes only; raw predictions unchanged, runtime grounding remains false.'
 return result

def downstream(refs,preds,sources):
 """Pair each proposed rule with an explicit synthetic opposing requirement.

 This assesses preservation of condition/exception/softness in reviewed models.
 It is not evidence of an actual upstream policy conflict.
 """
 from prompt_skill_linter.engine import lint
 outputs=[]
 def check(rule,facts):
  if not rule.get('binding_supported',False):return 'abstain'
  source=sources.get(rule['source_id'])
  if not source or rule.get('quote')!=source['text'] or rule.get('start_line')!=1 or rule.get('end_line')!=1:return 'abstain'
  quote=rule['quote'];kind=rule['kind'];action=rule['action']
  probe_value=True if kind=='prohibition' else False
  probe='Synthetic probe: require '+action+'='+str(probe_value).lower()+'.'
  base={'priority':0,'skills':[],'scope':{'entity':'task','temporal':'run'}}
  original={**base,'id':'source','source':{'source_id':'s','start_line':1,'end_line':1,'quote':quote},'kind':kind,'when':rule.get('when',{}),'exceptions':rule.get('exceptions',[]),'effect':{'literal':action,'value':True}}
  opposing={**base,'id':'probe','source':{'source_id':'s','start_line':2,'end_line':2,'quote':probe},'kind':'requirement','when':{},'exceptions':[],'effect':{'literal':action,'value':probe_value}}
  contract={'version':1,'sources':[{'id':'s','path':'source.txt'}],'rules':[original,opposing],'contexts':[{'id':'probe','facts':facts,'active_skills':[]}],'assumptions':['Synthetic opposing probe; not an upstream natural defect.']}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'source.txt').write_text(quote+'\n'+probe+'\n');report=lint(contract,{'tools':{}},{},p)
  return 'issue' if any(x['code']=='INCOMPATIBLE_OBLIGATIONS' for x in report['diagnostics']) else 'no_issue'
 for k,ref in refs.items():
  for variant,facts in [('default',{'explicitly_requested':False,'using_plan':True,'serif_font':False}),('exception_or_inactive',{'explicitly_requested':True,'using_plan':False,'serif_font':True})]:
   expected=check(ref,facts);observed=check(preds[k],facts) if k in preds else 'abstain'
   outputs.append({'source_id':k[0],'action':k[1],'variant':variant,'reference_contract_prediction':expected,'extracted_contract_prediction':observed,'agreement':expected==observed,'synthetic':True})
 eligible=[x for x in outputs if x['reference_contract_prediction']!='abstain']
 return {'scope':'Matched synthetic opposing probes on manually accepted reference/extracted contracts; not real-source defect discovery. Reference-unsupported probes are reported separately.','cases':outputs,'agreement':sum(x['agreement'] for x in outputs)/len(outputs) if outputs else None,'reference_supported_probe_agreement':sum(x['agreement'] for x in eligible)/len(eligible) if eligible else None,'reference_supported_probes':len(eligible),'reference_abstentions':sum(x['reference_contract_prediction']=='abstain' for x in outputs),'extracted_abstentions':sum(x['extracted_contract_prediction']=='abstain' for x in outputs)}

if __name__=='__main__':
 result=score();write(DIRECTORY/'results.json',result)
 print(result['metrics']);print('Downstream agreement:',result['downstream_probes']['agreement'])
