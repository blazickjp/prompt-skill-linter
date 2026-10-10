"""Offline pilot runner and JSON adapter for externally supplied judge predictions.

No model API calls, API keys, or network operations occur in this module.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT/'evaluation/pilot'
VALID_LABELS={'issue','no_issue','abstain'}

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 data=json.dumps(value,indent=2,ensure_ascii=False)+'\n'
 with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=p.parent,delete=False) as stream:
  stream.write(data);temporary=stream.name
 os.replace(temporary,p)
def stamp(): return datetime.now(timezone.utc).isoformat()
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_freeze(directory=PILOT):
 directory=Path(directory);manifest=read(directory/'freeze.json')
 errors=[name for name,expected in manifest['sha256'].items() if not (directory/name).is_file() or digest(directory/name)!=expected]
 if errors:raise ValueError('Frozen inputs changed: '+', '.join(errors))
 return len(manifest['sha256'])

def validate_predictions(data,case_ids):
 if not isinstance(data,dict) or not isinstance(data.get('predictions'),list):raise ValueError('Expected predictions array')
 seen=set()
 for p in data['predictions']:
  if p.get('id') not in case_ids:raise ValueError('Unknown case ID: '+str(p.get('id')))
  if p['id'] in seen:raise ValueError('Duplicate case: '+p['id'])
  if p.get('label') not in VALID_LABELS:raise ValueError('Invalid label for '+p['id'])
  if not isinstance(p.get('rationale'),str) or not p['rationale'].strip():raise ValueError('Missing rationale: '+p['id'])
  seen.add(p['id'])
 if seen!=set(case_ids):raise ValueError('Missing cases: '+', '.join(sorted(set(case_ids)-seen)))
 return data

def mechanical(directory=PILOT):
 from prompt_skill_linter.engine import lint
 directory=Path(directory);verify_freeze(directory)
 cases=read(directory/'cases.json')['cases'];pred=[];started=time.perf_counter()
 for case in cases:
  t=time.perf_counter();entry={'id':case['id'],'tokens':None,'cost':None,'currency':None}
  if case['contract'] is None:
   entry.update(label='abstain',rationale='No reviewed finite contract supplied; the checker cannot translate this source case.',codes=[],supported=False)
  else:
   path=ROOT/case['contract']
   try:
    report=lint(read(path),case['tools'],case['runtime'],path.parent)
    write(directory/'reports'/f"{case['id']}.json",report)
    ds=report['diagnostics'];codes=[d['code'] for d in ds]
    bounded=any(any(token in code for token in ('BOUND','INCONCLUSIVE','UNKNOWN')) for code in codes)
    warning=any(d['class']=='semantic_warning' for d in ds)
    unreachable=any(d.get('witness',{}).get('status')=='unreachable' and d.get('witness',{}).get('search_exhaustive') for d in ds)
    label='abstain' if bounded or warning else ('issue' if report['summary']['error'] or unreachable else 'no_issue')
    entry.update(label=label,rationale=('The reviewed finite contract produced '+(', '.join(codes) if codes else 'no diagnostic')+'. This is conditional on its translation and stated search scope.'),codes=codes,supported=True,report=f'reports/{case["id"]}.json')
   except (ValueError,TypeError,KeyError,OSError) as e:
    entry.update(label='abstain',rationale='Checker input/execution failure: '+str(e),codes=['EXECUTION_ERROR'],supported=False)
  entry['latency_seconds']=time.perf_counter()-t;pred.append(entry)
 return {'run_id':'pilot_v1_adapter1','adapter_version':1,'arm':'mechanical_reviewed_contract','run_at':stamp(),'model':None,'backend_sha256':{p.name:digest(p) for p in sorted((ROOT/'prompt_skill_linter').glob('*.py'))},'input_freeze_sha256':digest(directory/'freeze.json'),'latency_seconds':time.perf_counter()-started,'cost':None,'tokens':None,'predictions':pred,'limitations':['Local latency excludes corpus preparation and manual extraction.','No cloud/API model was invoked by this runner. Unknown resource cost is null, not zero.','Reviewed contracts are partial abstractions; no finding certifies full policy compliance.']}

def prepare_evidence(directory=PILOT):
 directory=Path(directory);verify_freeze(directory)
 original=read(directory/'cases.json');packet={'version':1,'evidence_kind':'Manual finite projections, not reference labels or established English semantics.','cases':[]}
 for c in original['cases']:
  x=dict(c)
  if c['contract']:
   con=read(ROOT/c['contract']);x['structured_evidence']={'rules':con.get('rules',[]),'contexts':con.get('contexts',[]),'assumptions':con.get('assumptions',[]),'bulk_model':con.get('bulk_model'),'workflows':con.get('workflows',[])}
  else:x['structured_evidence']={'status':'No finite extraction supplied. Resolve from the same linked source context or abstain.'}
  packet['cases'].append(x)
 write(directory/'structured_packet.json',packet)
 return packet

def metric_slice(cases,predictions,references):
 totals=Counter();case_rows=[]
 for c in cases:
  pred=predictions[c['id']]['label'];ref=references[c['id']]['label']
  totals['total']+=1;totals['abstained']+=pred=='abstain'
  if ref=='abstain':
   totals['excluded_reference_ambiguous']+=1
   case_rows.append({'id':c['id'],'predicted':pred,'reference':ref,'outcome':'unscored_ambiguous'})
   continue
  totals['binary_reference']+=1;totals['reference_positive']+=ref=='issue';totals['reference_negative']+=ref=='no_issue'
  if pred=='abstain':
   outcome='abstained_positive' if ref=='issue' else 'abstained_negative';totals[outcome]+=1
  else:
   outcome='tp' if pred==ref=='issue' else 'tn' if pred==ref=='no_issue' else 'fp' if pred=='issue' else 'fn';totals[outcome]+=1
  case_rows.append({'id':c['id'],'predicted':pred,'reference':ref,'outcome':outcome})
 def div(a,b):return a/b if b else None
 total=totals['total'];covered=total-totals['abstained'];tp,tn,fp,fn=(totals[x] for x in ('tp','tn','fp','fn'))
 return {'counts':dict(totals),'precision':div(tp,tp+fp),'recall':div(tp,totals['reference_positive']),'false_positive_rate':div(fp,totals['reference_negative']),'missed_issues':fn+totals['abstained_positive'],'coverage':div(covered,total),'abstention_rate':div(totals['abstained'],total),'selective_accuracy':div(tp+tn,tp+tn+fp+fn),'cases':case_rows}

def score(directory=PILOT):
 directory=Path(directory);verify_freeze(directory)
 cases=read(directory/'cases.json')['cases'];ids={c['id'] for c in cases}
 refs=read(directory/'reference_review.json')['labels'];refmap={r['id']:r for r in refs}
 if set(refmap)!=ids or len(refs)!=len(ids):raise ValueError('References must cover every case exactly once')
 if any(r['label'] not in VALID_LABELS for r in refs):raise ValueError('Invalid reference label')
 arms={}
 for path in sorted((directory/'predictions').glob('*.json')):
  data=validate_predictions(read(path),ids);pred={p['id']:p for p in data['predictions']}
  arm=data.get('arm',path.stem)
  if arm in arms:raise ValueError('Duplicate arm: '+arm)
  arms[arm]={'all':metric_slice(cases,pred,refmap),'by_origin':{origin:metric_slice([c for c in cases if c['origin']==origin],pred,refmap) for origin in sorted({c['origin'] for c in cases})},'latency_seconds':data.get('latency_seconds'),'cost':data.get('cost'),'tokens':data.get('tokens'),'model':data.get('model'),'input_file':str(path.relative_to(directory))}
 return {'version':1,'generated_at':stamp(),'protocol_sha256':digest(directory/'protocol.json'),'reference_sha256':digest(directory/'reference_review.json'),'arms':arms,'limitations':['Selected development pilot; not held-out, representative, human-gold, or a conclusive comparison.','Reference labels derive from one independent native model reviewer. Shared model family and correlated errors may exist.','Unknown native model identity/version means the strong-judge requirement is only approximated, not verified.','Scores on manual finite contracts measure downstream checking; raw-prose extraction measured separately.','No general advantage claim is warranted; natural positive recall may be undefined.']}

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['verify','mechanical','prepare-evidence','score','validate-predictions']);parser.add_argument('--directory',type=Path,default=PILOT);parser.add_argument('--input',type=Path);parser.add_argument('--output',type=Path)
 args=parser.parse_args(argv);out=None
 if args.command=='verify':out={'verified_files':verify_freeze(args.directory)}
 elif args.command=='mechanical':out=mechanical(args.directory)
 elif args.command=='prepare-evidence':out=prepare_evidence(args.directory)
 elif args.command=='score':out=score(args.directory)
 else:
  if not args.input:parser.error('--input required')
  ids={c['id'] for c in read(args.directory/'cases.json')['cases']};out=validate_predictions(read(args.input),ids)
 if args.output:write(args.output,out)
 else:print(json.dumps(out,indent=2))
 return 0
if __name__=='__main__':raise SystemExit(main())
