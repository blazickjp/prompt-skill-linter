"""Bounded propositional CNF decision procedure with audited deletion cores.

The solver is mechanical, not a natural-language contradiction oracle.
"""
from itertools import product


def solve(clauses, max_nodes=20_000):
    variables = sorted({a['literal'] for clause in clauses for a in clause})
    if len(variables) > 24:
        return {'status': 'unknown', 'reason': 'variable_limit', 'max_variables': 24, 'nodes': 0}
    nodes = 0
    cutoff = False

    def visit(assignment):
        nonlocal nodes, cutoff
        nodes += 1
        if nodes > max_nodes:
            cutoff = True
            return None
        pending = []
        for clause in clauses:
            if any(a['literal'] in assignment and assignment[a['literal']] == a['value'] for a in clause):
                continue
            remaining = [a for a in clause if a['literal'] not in assignment]
            if not remaining:
                return None
            pending.append(remaining)
        if not pending:
            return {v: assignment.get(v, False) for v in variables}
        unit = next((c[0] for c in pending if len(c) == 1), None)
        if unit:
            return visit(dict(assignment, **{unit['literal']: unit['value']}))
        var = min(pending, key=len)[0]['literal']
        for val in (False, True):
            found = visit(dict(assignment, **{var: val}))
            if found is not None or cutoff:
                return found
        return None

    assignment = visit({})
    return {'status': 'sat' if assignment is not None else ('unknown' if cutoff else 'unsat'),
            'assignment': assignment, 'nodes': nodes, 'max_nodes': max_nodes,
            'variables': variables, 'reason': 'search_limit' if cutoff else None}


def checked_core(rules, max_nodes=20_000):
    total_budget = 100_000
    used = 0

    def bounded(items):
        nonlocal used
        remaining = min(max_nodes, total_budget - used)
        if remaining <= 0:
            return {'status': 'unknown', 'reason': 'core_total_search_limit', 'nodes': 0}
        result = solve([r['clause'] for r in items], remaining)
        used += result.get('nodes', 0)
        return result

    original = bounded(rules)
    if original['status'] != 'unsat':
        return {'result': original, 'minimality_checked': False, 'rule_ids': []}
    core = list(rules)
    for rule in list(core):
        subset = [r for r in core if r['id'] != rule['id']]
        result = bounded(subset)
        if result['status'] == 'unsat':
            core = subset
    removals = {r['id']: bounded([x for x in core if x['id'] != r['id']]) for r in core}
    return {'result': original, 'rule_ids': [r['id'] for r in core],
            'minimality_checked': all(r['status'] == 'sat' for r in removals.values()), 'removal_witnesses': removals,
            'core_search_nodes': used, 'core_total_node_budget': total_budget}


def truth_table(clauses, limit=64):
    variables = sorted({a['literal'] for c in clauses for a in c})
    if len(variables) > 12:
        return {'variables': variables, 'rows': [], 'truncated': True, 'reason': 'truth_table_variable_limit'}
    rows = []
    for values in product((False, True), repeat=len(variables)):
        if len(rows) >= limit:
            break
        assignment = dict(zip(variables, values))
        satisfied = [any(assignment[a['literal']] == a['value'] for a in c) for c in clauses]
        rows.append({'assignment': assignment, 'clauses_satisfied': satisfied, 'all_satisfied': all(satisfied)})
    return {'variables': variables, 'rows': rows, 'truncated': 2**len(variables) > len(rows)}
