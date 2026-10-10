"""Bounded finite-state reachability and inspectable transition evidence."""
from collections import deque


def explore(workflow, forbidden=(), max_steps=20, max_states=2_000, graph_limit=200):
    initial = frozenset(workflow.get('initial', []))
    goal = set(workflow.get('goal', []))
    queue = deque([(initial, [])])
    seen = {initial: 0}
    states = [{'id': 0, 'facts': sorted(initial), 'depth': 0, 'goal': goal <= initial}]
    edges, blocked = [], []
    cutoff = False
    goal_path = [] if goal <= initial else None
    fallback_path = None
    fallback = workflow.get('compliant_fallback')
    while queue:
        state, path = queue.popleft()
        if goal <= state and goal_path is None:
            goal_path = path
        enabled = []
        for action in workflow.get('actions', []):
            reason = None
            if action['id'] in forbidden:
                reason = 'forbidden_or_unavailable'
            elif not set(action.get('requires', [])) <= state:
                reason = 'missing_prerequisites'
            if reason:
                if len(blocked) < graph_limit:
                    blocked.append({'state': seen[state], 'action': action['id'], 'reason': reason,
                                    'missing': sorted(set(action.get('requires', [])) - state)})
                continue
            enabled.append(action)
        if len(path) >= max_steps:
            if any(((state - set(a.get('removes', []))) | set(a.get('adds', []))) not in seen for a in enabled):
                cutoff = True
            if fallback and any(a['id'] == fallback for a in enabled) and fallback_path is None:
                cutoff = True
            continue
        for action in enabled:
            nxt = frozenset((state - set(action.get('removes', []))) | set(action.get('adds', [])))
            nxt_path = path + [action['id']]
            if action['id'] == fallback and fallback_path is None:
                fallback_path = nxt_path
            if nxt not in seen:
                if len(seen) >= max_states:
                    cutoff = True
                    continue
                seen[nxt] = len(seen)
                queue.append((nxt, nxt_path))
                if len(states) < graph_limit:
                    states.append({'id': seen[nxt], 'facts': sorted(nxt), 'depth': len(nxt_path), 'goal': goal <= nxt})
            if len(edges) < graph_limit:
                edges.append({'from': seen[state], 'to': seen[nxt], 'action': action['id']})
    return {'status': 'reachable' if goal_path is not None else ('unknown' if cutoff else 'unreachable'),
            'goal_path': goal_path, 'fallback_path': fallback_path,
            'search_exhaustive': not cutoff, 'visited_states': len(seen),
            'bounds': {'max_steps': max_steps, 'max_states': max_states, 'graph_display_limit': graph_limit},
            'graph': {'states': states, 'edges': edges, 'blocked_actions': blocked,
                      'display_truncated': len(seen) > len(states) or len(edges) >= graph_limit or len(blocked) >= graph_limit}}
