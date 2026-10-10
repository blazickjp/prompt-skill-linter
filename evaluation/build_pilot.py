"""Build the frozen development pilot (never call during an evaluated run)."""
import copy, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/pilot'

def write(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')

cases=[]
def add(case_id,origin,policy,context,contract=None,tools=None,runtime=None,**extra):
 d={'id':case_id,'origin':origin,'policy':policy,'context':context,'tools':tools or {'tools':{}},'runtime':runtime or {'max_plan_steps':20},**extra}
 if contract is not None:
  folder=OUT/'fixtures'/case_id; folder.mkdir(exist_ok=True)
  if isinstance(contract,str):
   original=ROOT/contract; c=json.loads(original.read_text())
   for source in c['sources']:
    (folder/source['path']).write_text((original.parent/source['path']).read_text())
  else:
   c=contract
   (folder/'policy.txt').write_text(policy+'\n')
  write(folder/'contract.json',c);d['contract']=str((folder/'contract.json').relative_to(ROOT))
 else:d['contract']=None
 cases.append(d)

def rules_contract(lines, rules, facts=None, skills=None, workflows=None):
 c={'version':1,'sources':[{'id':'policy','path':'policy.txt'}], 'skills':skills or [], 'rules':[], 'contexts':[{'id':'task','facts':facts or {},'active_skills':[]}], 'assumptions':['Explicitly synthetic finite model; no inferred natural-language completeness.']}
 for i,r in enumerate(rules):
  rr={'id':f'r{i+1}','source':{'source_id':'policy','start_line':i+1,'end_line':i+1,'quote':lines[i]},'priority':0,'kind':'requirement','scope':{'entity':'task','temporal':'turn'},'when':{},'exceptions':[],**r}; c['rules'].append(rr)
 if workflows:c['workflows']=workflows
 return c

external=json.loads((ROOT/'corpus/external/manifest.json').read_text());src={x['id']:x for x in external['sources']}
originals=[('openhands_config_bug','Configuration-file bug fix. Both bug-fix and configuration-change conditions hold.'),('mini_call_count','Response recovering from token-limit truncation; the recovery branch is active.'),('pdf_subscript','Create a ReportLab PDF paragraph containing subscript typography.'),('openhands_import_exception','A top-level import would create a circular dependency; a delayed import avoids it.'),('openhands_pr_consent','Fix code in the original repository, no explicit PR request. Built-in security policy enabled and not replaced. Is there no compliant action path, rather than merely an authorization tension?')]
for i,(name,context) in enumerate(originals,1):
 rec=next(c for c in external['cases'] if c['id']==name)
 policy='\n'.join(s.get('quote') or s['paraphrase'] for s in rec['source_spans'])
 add(f'c{i:03}','natural',policy,context,('corpus/external/'+rec['contract']) if rec['contract'] else None,source_urls=[s['url'] for s in rec['source_spans']],source_context_required=True,source_case_id=name)
add('c006','natural','ASCII is the default. Non-ASCII is allowed with clear justification in a file that already uses it.','The existing source file already contains Unicode; keeping the localized label has a clear justification.',source_urls=['https://github.com/openai/codex/blob/806d9732c974bc8a51b8317c1bd8985544fe627c/codex-rs/core/gpt-5.2-codex_prompt.md#L9'],source_context_required=True,source_case_id='codex_ascii_exception')
add('c007','natural','A worktree may already contain user edits; preserve them. Unexpected changes noticed during work require stopping and asking the user.','At task start, the user explicitly identifies pre-existing changes. No new unexpected change is observed.',source_urls=['https://github.com/openai/codex/blob/806d9732c974bc8a51b8317c1bd8985544fe627c/codex-rs/core/gpt-5.2-codex_prompt.md#L12-L18'],source_context_required=True,source_case_id='codex_dirty_known')
add('c008','natural','Prefer noninteractive commands unless a persistent process is specifically required; some commands require interaction.','The user explicitly requires a persistent development watcher.',source_urls=['https://github.com/google-gemini/gemini-cli/blob/9b6e0265d16bbd29ca51e33c9e0c01dc4cec5e83/packages/core/src/prompts/snippets.ts#L849-L853'],source_context_required=True,source_case_id='gemini_interactive_exception')
# Deliberate mutations of public instruction themes, never natural findings.
mutations=[
 ('c009','mini_call_count',['Every response must include at least one bash call.','Every response must include zero bash calls.'],[{'effect':{'literal':'has_bash','value':True}},{'kind':'prohibition','effect':{'literal':'has_bash','value':True}}],{},'Same response; no exceptions or priority differences.'),
 ('c010','pdf_subscript',['For subscripts, use Unicode subscript characters.','Never use Unicode subscript characters.'],[{'effect':{'literal':'unicode','value':True}},{'kind':'prohibition','effect':{'literal':'unicode','value':True}}],{},'A subscript is required in this PDF; both rules have the same scope.'),
 ('c011','openhands_import_exception',['Place this import at top level unless that causes a circular dependency.','For a circular dependency, do not place this import at top level.'],[{'effect':{'literal':'top','value':True},'exceptions':[{'circular':True}]},{'when':{'circular':True},'kind':'prohibition','effect':{'literal':'top','value':True}}],{'circular':True},'A circular dependency occurs if the import is at top level.'),
 ('c012','openhands_import_exception',['Place every import at top level, without exceptions.','Do not place this import at top level, without exceptions.'],[{'effect':{'literal':'top','value':True}},{'kind':'prohibition','effect':{'literal':'top','value':True}}],{},'Both rules have equal priority and refer to this import.'),
 ('c013','openhands_config_bug',['For functional bug fixes, write new tests.','For documentation-only updates, do not write new tests.'],[{'when':{'functional_bug':True},'effect':{'literal':'tests','value':True}},{'when':{'docs_only':True},'kind':'prohibition','effect':{'literal':'tests','value':True}}],{'functional_bug':False,'docs_only':True},'This update is documentation-only; it is not a functional bug fix.'),
 ('c014','codex_ascii_exception',['Use only ASCII in this file, without exceptions.','Include a non-ASCII character in this file.'],[{'kind':'prohibition','effect':{'literal':'non_ascii','value':True}},{'effect':{'literal':'non_ascii','value':True}}],{},'Both apply to the same file in the same edit.'),
 ('c015','mini_call_count',['Prefer including a bash call in each response.','Do not include a bash call in this response.'],[{'kind':'preference','effect':{'literal':'has_bash','value':True}},{'kind':'prohibition','effect':{'literal':'has_bash','value':True}}],{},'The first rule is explicitly a preference, not a hard duty.'),
 ('c016','openhands_pr_consent',['You may open a pull request.','Do not open a pull request.'],[{'kind':'permission','effect':{'literal':'open_pr','value':True}},{'kind':'prohibition','effect':{'literal':'open_pr','value':True}}],{},'No other rule requires a pull request. Target is existence of a compliant action path; declining is allowed.')]
for cid,parent,lines,rules,facts,context in mutations:
 add(cid,'synthetic_mutation','\n'.join(lines),context,rules_contract(lines,rules,facts),parent_case_id=parent,mutation_disclosure='Authored mutation, not an observed upstream defect.')
# Original handoff arithmetic, with exact near-boundary controls.
for cid,n,budget in [('c017',150,30),('c018',151,30),('c019',184,30),('c020',184,38)]:
 c=json.loads((ROOT/'examples/bulk.contract.json').read_text()); lines=(ROOT/'examples/bulk.skill.txt').read_text().splitlines(); lines[3]=f'The run permits at most {budget} counted service calls.'
 c['sources']=[{'id':'bulk','path':'policy.txt'}];c['rules'][3]['source']['quote']=lines[3]
 add(cid,'synthetic_handoff','\n'.join(lines),f'Update all {n} nodes within this run; no prior tasks or alternative operations.',c,json.loads((ROOT/'examples/tools.json').read_text()),{'service_call_budget':budget,'request_sizes':[n],'max_plan_steps':20},family='bulk_capacity')
for cid,call,tools in [('c021',{'tool':'submit','arguments':{'nodes':[1]}},{'tools':{'poll':{'arguments':['task_id'],'required':['task_id']}}}),('c022',{'tool':'submit','arguments':{'node_ids':[1]}},{'tools':{'submit':{'arguments':['nodes'],'required':['nodes']}}})]:
 lines=['Invoke '+call['tool']+' with arguments '+json.dumps(call['arguments'])+'.']
 add(cid,'synthetic_interface','\n'.join(lines),'The declared manifest is complete; no aliasing or alternative operation exists.',rules_contract(lines,[{'tool_call':call}]),tools)
lines=['The workflow advertises reaching done.']
for cid,actions,bound in [('c023',[{'id':'finish','requires':['ready'],'adds':['done']}],5),('c024',[{'id':'prepare','requires':[],'adds':['ready']},{'id':'finish','requires':['ready'],'adds':['done']}],1)]:
 workflow={'id':'flow','initial':[],'goal':['done'],'actions':actions,'advertisement_rule':'r1'}
 add(cid,'synthetic_workflow','\n'.join(lines),'Initial state is empty. Actions: '+json.dumps(actions)+f'. Search depth limit is {bound}; a limit is not a semantic prohibition on longer plans.',rules_contract(lines,[{}],workflows=[workflow]),runtime={'max_plan_steps':bound})
write(OUT/'cases.json',{'version':1,'cases':cases})
protocol={'version':1,'frozen_before_predictions':True,'frozen_at_utc':'2026-10-10T14:40:33Z','target':'Task-level existence of a compliant completion in the supplied scope, or exact advertised tool-interface inconsistency. Authorization tension with a safe no-op is not automatically no-completion.','labels':['issue','no_issue','abstain'],'abstain_conditions':['unresolved semantic ambiguity','missing context','unsupported translation','bounded search without exhaustive closure'], 'primary_strata':['natural','synthetic_mutation','synthetic_handoff','synthetic_interface','synthetic_workflow'],'arms':['native_judge','native_judge_structured','mechanical_reviewed_contract'],'reference':'Independent blind native model review plus explicit mathematical checks; not human gold. Cases with unresolved reference disagreement excluded from binary scoring and retained for abstention reporting.','metrics':{'precision':'TP/(TP+FP), null if denominator zero','recall':'TP/(TP+FN+abstained_reference_positive), null if no reference positives','coverage':'non-abstained predictions / all cases','selective_accuracy':'correct non-abstained / scored non-abstained','false_positive_rate':'FP / reference-negative cases','abstention_rate':'abstained / all cases','missed_issues':'false-negative plus abstained reference-positive cases'},'cost':'Record actual known tokens/dollars; unknown stays null, not zero. No explicit paid API calls.','latency':'Batch wall clock includes orchestration/tool reads; not comparable to isolated local checker latency.','disclosure':['24 selected development cases; not representative or held-out production benchmark.','Native judge model identity/version may be unknown; cannot certify frontier strength or cross-model independence.','Natural inputs are source-linked excerpts/paraphrases with full-source verification required by native arms. Mechanical arm runs reviewed finite projections for supported cases and abstains otherwise.','Extraction is separately evaluated; this is not an end-to-end superiority test.','No judge tuning after predictions; amendments require a new run ID and report changes.']}
write(OUT/'protocol.json',protocol)
files=['cases.json','protocol.json']+[str(p.relative_to(OUT)) for p in sorted((OUT/'fixtures').rglob('*')) if p.is_file()]
write(OUT/'freeze.json',{'sha256':{f:hashlib.sha256((OUT/f).read_bytes()).hexdigest() for f in files}})
print('Built',len(cases),'cases with frozen manifest; predictions not collected.')
if __name__=='__main__':pass
