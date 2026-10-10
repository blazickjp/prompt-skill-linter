"""Independently validate selected diagnostic certificates, not English claims."""
import json
from pathlib import Path
from .run import ROOT,PILOT,read,write,verify_freeze,stamp

def verify_bulk(w,capacity=10):
 n,b=w['request_size'],w['budget']
 constraints={'coverage':lambda s,p:capacity*s>=n,'polling':lambda s,p:p>=s,'budget':lambda s,p:s+p<=b}
 # Every budget-feasible nonnegative assignment lies in this exact finite box.
 full_unsat=not any(all(f(s,p) for f in constraints.values()) for s in range(b+1) for p in range(b+1))
 removals={name:all(f(v['s'],v['p']) for other,f in constraints.items() if other!=name) and v['s']>=0 and v['p']>=0 for name,v in w['removal_witnesses'].items()}
 pairs={name:all(constraints[c](v['s'],v['p']) for c in name.split('+')) for name,v in w['pairwise_witnesses'].items()}
 expected_sub=(n+capacity-1)//capacity
 range_ok=all((2*((request+capacity-1)//capacity)>b)==(w['affected_advertised_range'][0]<=request<=w['affected_advertised_range'][1]) for request in range(1,201))
 return {'full_system_unsatisfiable':full_unsat,'removal_witnesses_valid':all(removals.values()),'pairwise_witnesses_valid':all(pairs.values()),'lower_bound_valid':w['minimum_submissions']==w['minimum_polls']==expected_sub and w['lower_bound_calls']==2*expected_sub,'affected_range_valid_for_1_to_200':range_ok,'minimal_core_valid':full_unsat and all(removals.values())}

def verify_boolean(diag):
 rules=diag['interpreted_rules'];literal=diag['witness']['literal']
 desired={r['id']:(not r['effect']['value'] if r['kind']=='prohibition' else r['effect']['value']) for r in rules}
 # Fixed witness has already activated/resolved the rules; this validates only
 # the Boolean core, not source interpretation or global activation extraction.
 unsat=not any(all(value==want for want in desired.values()) for value in (False,True))
 removals=diag['witness']['removal_witnesses']
 valid=all(all(v[literal]==want for rid,want in desired.items() if rid!=removed) for removed,v in removals.items())
 return {'full_core_unsatisfiable':unsat,'removal_witnesses_valid':valid,'minimal_core_valid':unsat and valid and set(removals)==set(desired)}

def run():
 from prompt_skill_linter.engine import lint
 verify_freeze(PILOT);cases=read(PILOT/'cases.json')['cases'];rows=[];deterministic=[]
 for case in cases:
  if not case['contract']:continue
  path=ROOT/case['contract'];contract=read(path)
  a=lint(contract,case['tools'],case['runtime'],path.parent);b=lint(contract,case['tools'],case['runtime'],path.parent)
  deterministic.append({'case_id':case['id'],'identical_reports':a==b})
  sources={s['id']:(path.parent/s['path']).read_text().splitlines() for s in contract['sources']}
  rule_ids={r['id'] for r in contract['rules']}
  for d in a['diagnostics']:
   row={'case_id':case['id'],'code':d['code'],'source_spans_exact':all('\n'.join(sources[s['source_id']][s['start_line']-1:s['end_line']])==s['quote'] for s in d['source_spans']),'regression_case_present':bool(d.get('regression_case')),'repair_targets_known':all(r['changes_requirement'] in rule_ids for r in d['repairs']),'repair_count':len(d['repairs'])}
   if d['code']=='UNREACHABLE_COMPLETION':row['certificate']=verify_bulk(d['witness'])
   elif d['code']=='INCOMPATIBLE_OBLIGATIONS':row['certificate']=verify_boolean(d)
   elif d['code']=='PLAN_BOUND_EXHAUSTED':row['cutoff_honestly_unknown']=d['witness']['status']=='unknown' and not d['witness']['search_exhaustive']
   rows.append(row)
 cores=[r for r in rows if 'certificate' in r]
 return {'generated_at':stamp(),'scope':'Reproducibility, source alignment, finite minimal-core certificates, exact synthetic range, and repair provenance. These are machine-checkable output properties, not an empirical measure of human usefulness or English correctness.','diagnostics':rows,'repeated_runs':deterministic,'summary':{'diagnostics':len(rows),'exact_source_spans':sum(r['source_spans_exact'] for r in rows),'regression_cases':sum(r['regression_case_present'] for r in rows),'cores_checked':len(cores),'minimal_cores_valid':sum(r['certificate']['minimal_core_valid'] for r in cores),'identical_repeat_reports':sum(x['identical_reports'] for x in deterministic),'repeat_cases':len(deterministic),'repairs_with_named_valid_requirement':sum(r['repair_count'] for r in rows if r['repair_targets_known'])},'limitations':['Checks apply to the declared finite models only.','The authors selected these development cases; no user study of diagnostic helpfulness has been run.','Subset-minimal is not minimum-cardinality or a unique causal explanation.','Repair proposal text is checked for named source requirement, not for business desirability or complete repair correctness.']}
if __name__=='__main__':
 out=run();write(PILOT/'certificate_results.json',out);print(json.dumps(out['summary'],indent=2))
