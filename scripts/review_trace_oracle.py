"""Independent seeded bounded trace enumeration: 1,000 monitor comparisons."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import random
from collections import deque
from prompt_skill_linter.trace import check_trace_assertions
r=random.Random(726191)
source={'source_id':'s','start_line':1,'end_line':1,'quote':'Declared trace policy.'}
def oracle(w,p,forbidden,bound):
    queue=deque([(set(w['initial']),0 if p['kind']=='action_count' else p['initially_fresh'],[])])
    while queue:
        facts,monitor,path=queue.popleft()
        if len(path)==bound: continue
        for a in w['actions']:
            name=a['id']
            if name in forbidden or not set(a['requires']).issubset(facts): continue
            if p['kind']=='action_count':
                nxt=monitor+int(name in p['actions']); bad=nxt>p['max_count']
            else:
                bad=name in p['guarded_actions'] and not monitor
                nxt=monitor
                if name in p['invalidate_actions']: nxt=False
                if name in p['refresh_actions']: nxt=True
            if bad:return path+[name]
            changed=set(facts)
            for v in a['removes']:changed.discard(v)
            changed.update(a['adds'])
            queue.append((changed,nxt,path+[name]))
    return None
n=0
for i in range(500):
    names=['a','b','c']; facts=['x','y','z']
    subset=lambda xs:[x for x in xs if r.random()<.35]
    w={'id':'w','initial':subset(facts),'actions':[{'id':name,'requires':subset(facts),'adds':subset(facts),'removes':subset(facts)} for name in names]}
    common={'id':'p','source':source,'assumptions':[]}
    props=[dict(common,kind='action_count',actions=['a','b'],max_count=r.randrange(4)),dict(common,kind='freshness',invalidate_actions=['a'],refresh_actions=['b'],guarded_actions=['c'],initially_fresh=bool(r.randrange(2)))]
    for p in props:
        w['trace_assertions']=[p]; forbidden=subset(names); bound=r.randrange(6)
        expected=oracle(w,p,forbidden,bound)
        result=check_trace_assertions(w,forbidden,max_steps=bound,max_states=2000)[0]
        assert (expected is not None)==(result['status']=='violated'),(w,p,expected,result)
        if expected is not None:assert len(expected)==len(result['violation_path']),(expected,result)
        n+=1
print(f'{n} independent seeded finite-trace enumerations agree; shortest violation lengths agree.')
