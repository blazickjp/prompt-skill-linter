"""Small, deliberately bounded checker for human-reviewed contracts.

No natural-language inference happens here. A finite context is a test, not a
universal quantifier over all possible conversations.
"""
from __future__ import annotations

from collections import deque
from itertools import combinations
from pathlib import Path
from .schema import ShapeError, check, validate_shape
from .planner import explore
from .sat import checked_core


class ContractError(ValueError):
    """Invalid input, rather than an instruction conflict."""


def validate(contract, manifest, runtime, root):
    try:
        validate_shape(contract)
        string_array = {'type': 'array', 'items': {'type': 'string'}}
        tool_shape = {'type': 'object', 'required': ['arguments'], 'additionalProperties': False,
                      'properties': {'arguments': string_array, 'required': string_array, 'capabilities': string_array}}
        check(manifest, {'type': 'object', 'required': ['tools'], 'additionalProperties': False,
                         'properties': {'tools': {'type': 'object', 'additionalProperties': tool_shape}}})
        check(runtime, {'type': 'object', 'additionalProperties': False, 'properties': {
            'service_call_budget': {'type': 'integer', 'minimum': 0},
            'request_sizes': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1}},
            'max_plan_steps': {'type': 'integer', 'minimum': 0}}})
    except ShapeError as exc:
        raise ContractError(str(exc)) from exc
    if contract.get('interpretation', {}).get('status') == 'candidate':
        raise ContractError('Extraction candidates must be explicitly reviewed and accepted before analysis.')
    if len(contract['rules']) > 256 or len(contract['contexts']) > 16 or len(contract.get('workflows', [])) > 8:
        raise ContractError('Analysis limits: 256 rules, 16 contexts and 8 workflows per bundle.')
    if contract.get('version') != 1:
        raise ContractError('contract.version must be 1')
    for key in ('sources', 'rules', 'contexts'):
        if not isinstance(contract.get(key), list):
            raise ContractError(f'contract.{key} must be an array')
    for group in ('sources', 'rules', 'contexts', 'skills'):
        items = contract.get(group, [])
        ids = [x.get('id') for x in items]
        if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
            raise ContractError(f'{group} need unique nonempty string IDs')
    sources = {s['id']: s for s in contract['sources']}
    root = Path(root).resolve()
    for rule in contract['rules']:
        src = rule.get('source', {})
        if src.get('source_id') not in sources:
            raise ContractError(f"{rule['id']}: unknown source_id")
        path = (root / sources[src['source_id']]['path']).resolve()
        if not path.is_relative_to(root):
            raise ContractError('source paths must stay within the contract directory')
        try:
            if path.stat().st_size > 1_500_000:
                raise ContractError('Source file exceeds the 1.5 MB analysis limit.')
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError) as exc:
            raise ContractError(f'cannot read source {path.name}: {exc}') from exc
        start, end = src.get('start_line'), src.get('end_line')
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ContractError(f"{rule['id']}: invalid source line range")
        if src.get('quote') != '\n'.join(lines[start - 1:end]):
            raise ContractError(f"{rule['id']}: source quote does not exactly match the declared lines")
        if rule.get('kind') not in ('requirement', 'prohibition', 'permission', 'preference'):
            raise ContractError(f"{rule['id']}: invalid kind")
        if type(rule.get('priority')) is not int:
            raise ContractError(f"{rule['id']}: priority must be an integer")
        if not isinstance(rule.get('scope'), dict) or set(rule['scope']) != {'entity', 'temporal'}:
            raise ContractError(f"{rule['id']}: scope needs entity and temporal")
        for key in ('when',):
            if not isinstance(rule.get(key, {}), dict):
                raise ContractError(f"{rule['id']}: {key} must be an equality map")
        if not all(isinstance(e, dict) for e in rule.get('exceptions', [])):
            raise ContractError(f"{rule['id']}: exceptions must be equality maps")
        if rule.get('forbid_action') and rule['kind'] != 'prohibition':
            raise ContractError('forbid_action is valid only on prohibitions')
        if rule.get('allow_action') and rule['kind'] != 'permission':
            raise ContractError('allow_action is valid only on permissions')
        if 'clause' in rule:
            if rule['kind'] != 'requirement' or any(k in rule for k in ('effect', 'forbid_action', 'allow_action', 'tool_call')):
                raise ContractError('CNF clauses must be requirements in an isolated formula fragment.')
            if len(rule['clause']) > 32:
                raise ContractError('A CNF clause may contain at most 32 literals.')
        if 'effect' in rule:
            effect = rule['effect']
            if not isinstance(effect.get('literal'), str) or type(effect.get('value')) is not bool:
                raise ContractError(f"{rule['id']}: effect needs a literal and boolean value")
    if not isinstance(manifest.get('tools', {}), dict):
        raise ContractError('manifest.tools must be an object')
    for tool in manifest['tools'].values():
        if not set(tool.get('required', [])) <= set(tool['arguments']):
            raise ContractError('required tool arguments must be declared in arguments')
    for context in contract['contexts']:
        if not isinstance(context.get('facts', {}), dict):
            raise ContractError('context facts must be an object')
    bulk = contract.get('bulk_model')
    if bulk:
        for key in ('nodes_per_submission', 'advertised_min', 'advertised_max'):
            if type(bulk.get(key)) is not int or bulk[key] < 1:
                raise ContractError(f'bulk_model.{key} must be a positive integer')
        if bulk['advertised_min'] > bulk['advertised_max']:
            raise ContractError('advertised_min exceeds advertised_max')
        if type(runtime.get('service_call_budget')) is not int or runtime['service_call_budget'] < 0:
            raise ContractError('runtime.service_call_budget must be a nonnegative integer')
        if not runtime.get('request_sizes'):
            raise ContractError('bulk analysis requires at least one explicit request_size')
        for n in runtime.get('request_sizes', []):
            if type(n) is not int or n < 1:
                raise ContractError('request sizes must be positive integers')
        expected = {'coverage', 'polling', 'budget'}
        if set(bulk.get('constraint_rules', {})) != expected:
            raise ContractError('bulk constraint_rules need coverage, polling and budget')
        if len(set(bulk['constraint_rules'].values())) != 3:
            raise ContractError('bulk constraints must reference three distinct rule IDs')
        rules = {r['id']: r for r in contract['rules']}
        if any(r not in rules for r in bulk['constraint_rules'].values()) or bulk['advertisement_rule'] not in rules:
            raise ContractError('bulk constraint or advertisement references unknown rule')
        for rid in list(bulk['constraint_rules'].values()) + [bulk['advertisement_rule']]:
            rule = rules[rid]
            if rule['kind'] != 'requirement' or rule.get('when') or rule.get('skills') or rule.get('exceptions'):
                raise ContractError('bulk constraints must be unconditional declared requirements')
            if any(key in rule for key in ('effect', 'forbid_action', 'allow_action', 'tool_call', 'clause')):
                raise ContractError('bulk rules cannot also participate in boolean/action/tool-call fragments')
            if rule['scope'] != rules[bulk['advertisement_rule']]['scope']:
                raise ContractError('bulk constraints and advertisement must share exact scope')
    for workflow in contract.get('workflows', []):
        if len(workflow['actions']) > 64:
            raise ContractError('A workflow may declare at most 64 actions.')
        action_ids = [a['id'] for a in workflow['actions']]
        if len(action_ids) != len(set(action_ids)):
            raise ContractError('workflow action IDs must be unique')
        if workflow['advertisement_rule'] not in {r['id'] for r in contract['rules']}:
            raise ContractError('workflow advertisement references unknown rule')
        if any('__fallback_done__' in a.get('adds', []) for a in workflow['actions']) or '__fallback_done__' in workflow.get('initial', []):
            raise ContractError('reserved state fact __fallback_done__')
    for context in contract['contexts']:
        grouped = {}
        for rule in contract['rules']:
            if active(rule, context):
                key = (rule['scope']['entity'], rule['scope']['temporal'])
                grouped.setdefault(key, []).append(rule)
        for rules in grouped.values():
            clauses = [r for r in rules if 'clause' in r]
            if len(clauses) > 64 or len({r['priority'] for r in clauses}) > 1:
                raise ContractError('Active CNF fragment requires at most 64 clauses at one explicit priority.')
            cnf_literals = {a['literal'] for r in clauses for a in r['clause']}
            if any(r.get('effect', {}).get('literal') in cnf_literals for r in rules):
                raise ContractError('Shared literals across CNF and Boolean-effect fragments are unsupported; use one representation.')
    pair_budget = 0
    for context in contract['contexts']:
        grouped = {}
        for rule in contract['rules']:
            if 'effect' in rule and active(rule, context):
                key = (rule['scope']['entity'], rule['scope']['temporal'], rule['effect']['literal'])
                grouped[key] = grouped.get(key, 0) + 1
        pair_budget += sum(n * (n - 1) // 2 for n in grouped.values())
    if pair_budget > 4096:
        raise ContractError('Boolean comparison budget exceeded; split this contract into smaller context groups.')
    return contract


def matches(condition, facts):
    # Missing facts are unknown/nonactivating, never silently false literals.
    return all(k in facts and type(facts[k]) is type(v) and facts[k] == v for k, v in condition.items())


def active(rule, context):
    return (set(rule.get('skills', [])) <= set(context.get('active_skills', []))
            and matches(rule.get('when', {}), context.get('facts', {}))
            and not any(matches(e, context.get('facts', {})) for e in rule.get('exceptions', [])))


def diagnostic(code, category, severity, rules, context, witness, assumptions=None, repairs=None):
    return {
        'code': code, 'class': category, 'severity': severity,
        'source_spans': [r['source'] for r in rules],
        'interpreted_rules': rules,
        'resolved_priorities': {r['id']: r['priority'] for r in rules},
        'triggering_context': context, 'witness': witness,
        'responsible_rule_set': [r['id'] for r in rules],
        'assumptions': assumptions or [], 'repairs': repairs or [],
        'regression_case': {'context': context, 'expected_code': code},
        'provenance_limitations': [] if rules else ['Source span unavailable: this diagnostic refers to an explicit contract/manifest declaration, not an extracted source rule.'],
    }


def bulk_feasible(n, capacity, budget, enabled):
    """Exact feasibility for these three monotone integer constraints.

    A canonical feasible witness, when one exists, is the smallest s allowed
    by coverage and then the smallest p allowed by polling. No search cutoff.
    """
    s = (n + capacity - 1) // capacity if 'coverage' in enabled else 0
    p = s if 'polling' in enabled else 0
    if 'budget' in enabled and s + p > budget:
        return None
    return {'s': s, 'p': p, 'total_calls': s + p}


def minimal_core(n, capacity, budget):
    core = ['coverage', 'polling', 'budget']
    if bulk_feasible(n, capacity, budget, core) is not None:
        return None
    for name in list(core):
        candidate = [x for x in core if x != name]
        if bulk_feasible(n, capacity, budget, candidate) is None:
            core = candidate
    witnesses = {name: bulk_feasible(n, capacity, budget, [x for x in core if x != name]) for name in core}
    return {'minimal_core_constraints': core, 'minimality_checked': True, 'removal_witnesses': witnesses}


def check_bulk(contract, runtime):
    model = contract.get('bulk_model')
    if not model:
        return [], []
    cap, budget = model['nodes_per_submission'], runtime['service_call_budget']
    by_id = {r['id']: r for r in contract['rules']}
    diagnostics, checks = [], []
    for n in runtime.get('request_sizes', []):
        s = (n + cap - 1) // cap
        witness = {'request_size': n, 'minimum_submissions': s, 'minimum_polls': s,
                   'lower_bound_calls': 2 * s, 'budget': budget,
                   'constraints': [f'{cap}*s >= {n}', 'p >= s', f's+p <= {budget}'],
                   'domain': 's,p are nonnegative integers'}
        core = minimal_core(n, cap, budget)
        checks.append({'request_size': n, 'status': 'infeasible' if core else 'lower_bound_pass',
                       'witness': witness, 'completion_guaranteed': False})
        if core:
            witness.update(core)
            witness['pairwise_witnesses'] = {
                '+'.join(pair): bulk_feasible(n, cap, budget, pair)
                for pair in combinations(('coverage', 'polling', 'budget'), 2)}
            lo = max(model['advertised_min'], cap * (budget // 2) + 1)
            hi = model['advertised_max']
            witness['affected_advertised_range'] = [lo, hi] if lo <= hi else None
            responsible = [by_id[model['constraint_rules'][x]] for x in core['minimal_core_constraints']]
            diag = diagnostic('UNREACHABLE_COMPLETION', 'exact', 'error', responsible,
                              {'request_size': n, 'service_call_budget': budget}, witness,
                              contract.get('assumptions', []), [
                                  {'changes_requirement': model['constraint_rules']['budget'],
                                   'proposal': f'Increase the counted-call budget to at least {2*s}; this only meets the lower bound.'},
                                  {'changes_requirement': model.get('advertisement_rule'),
                                   'proposal': f'Reduce the advertised maximum to at most {cap*(budget//2)} nodes for this budget.'},
                                  {'changes_requirement': model['constraint_rules']['polling'],
                                   'proposal': 'Redesign polling to support multiple tasks per call, then replace and revalidate the model.'}])
            diag['regression_case']['expected_lower_bound_calls'] = 2 * s
            diagnostics.append(diag)
    return diagnostics, checks


def check_references(contract, manifest):
    diagnostics = []
    skills = {s['id']: s for s in contract.get('skills', [])}
    tools = manifest.get('tools', {})
    for rule in contract['rules']:
        for skill in rule.get('skills', []):
            if skill not in skills:
                diagnostics.append(diagnostic('BROKEN_SKILL_REFERENCE', 'exact', 'error', [rule], {}, {'missing_skill': skill}))
        call = rule.get('tool_call')
        if call:
            tool = tools.get(call.get('tool'))
            if tool is None:
                diagnostics.append(diagnostic('BROKEN_TOOL_REFERENCE', 'exact', 'error', [rule], {}, {'missing_tool': call.get('tool')}))
            else:
                args = set(call.get('arguments', {}))
                invalid = sorted(args - set(tool.get('arguments', [])))
                missing = sorted(set(tool.get('required', [])) - args)
                if invalid or missing:
                    diagnostics.append(diagnostic('INVALID_TOOL_ARGUMENTS', 'exact', 'error', [rule], {}, {'invalid': invalid, 'missing_required': missing}))
    for skill in skills.values():
        for dep in skill.get('requires', []):
            if dep not in skills:
                diagnostics.append(diagnostic('MISSING_DEPENDENCY', 'exact', 'error', [], {'skill': skill['id']}, {'missing_dependency': dep}))
    for context in contract['contexts']:
        active_ids = set(context.get('active_skills', []))
        for sid in sorted(active_ids):
            if sid not in skills:
                diagnostics.append(diagnostic('BROKEN_SKILL_REFERENCE', 'exact', 'error', [], context, {'missing_skill': sid}))
            else:
                missing = sorted(set(skills[sid].get('requires', [])) - active_ids)
                if missing:
                    diagnostics.append(diagnostic('INACTIVE_DEPENDENCY', 'exact', 'error', [], context, {'skill': sid, 'missing_active_dependencies': missing}))
    return diagnostics


def check_obligations(contract):
    diagnostics = []
    for context in contract['contexts']:
        groups = {}
        for rule in contract['rules']:
            if active(rule, context) and 'effect' in rule and rule['kind'] != 'preference':
                key = (rule['scope']['entity'], rule['scope']['temporal'], rule['effect']['literal'])
                groups.setdefault(key, []).append(rule)
        for key, rules in groups.items():
            # Explicit permissions can override a lower-priority prohibition of
            # the same literal/value, but never require that action to occur.
            effective = []
            retained = []
            for rule in sorted(rules, key=lambda r: -r['priority']):
                value = rule['effect']['value'] if rule['kind'] != 'prohibition' else not rule['effect']['value']
                stronger = [r for r in retained if r['priority'] > rule['priority'] and (
                    (r['kind'] == 'permission' and rule['kind'] == 'prohibition' and r['effect']['value'] == rule['effect']['value'])
                    or (r['kind'] in ('requirement', 'prohibition') and
                        (r['effect']['value'] if r['kind'] == 'requirement' else not r['effect']['value']) != value))]
                if stronger:
                    diagnostics.append(diagnostic('SHADOWED_RULE', 'model_based', 'info', [rule] + stronger,
                        context, {'shadowed': rule['id'], 'literal': key[2]},
                        ['Literal-level override semantics; not a complete model of instruction hierarchy.']))
                else:
                    retained.append(rule)
                    if rule['kind'] != 'permission':
                        effective.append((rule, value))
            for (a, av), (b, bv) in combinations(effective, 2):
                if av != bv:
                    diagnostics.append(diagnostic('INCOMPATIBLE_OBLIGATIONS', 'model_based', 'error', [a, b], context,
                        {'literal': key[2], 'required_values': [av, bv], 'minimality_checked': True,
                         'removal_witnesses': {a['id']: {key[2]: bv}, b['id']: {key[2]: av}}},
                        ['Reviewed boolean interpretation and explicitly enumerated context.',
                         'Identical entity and temporal scope; no implicit cross-scope equivalence.']))
    return diagnostics


def reachable(workflow, forbidden, max_steps):
    initial = frozenset(workflow.get('initial', []))
    goal = set(workflow.get('goal', []))
    queue = deque([(initial, [])])
    seen = {initial}
    truncated = False
    while queue:
        state, path = queue.popleft()
        if goal <= state:
            return path, truncated
        if len(path) >= max_steps:
            truncated = True
            continue
        for action in workflow.get('actions', []):
            if action['id'] in forbidden or not set(action.get('requires', [])) <= state:
                continue
            nxt = (state - set(action.get('removes', []))) | set(action.get('adds', []))
            if nxt not in seen:
                if len(seen) >= 10000:
                    return None, True
                seen.add(nxt)
                queue.append((frozenset(nxt), path + [action['id']]))
    return None, truncated


def workflow_analysis(contract, manifest, runtime):
    diagnostics, checks = [], []
    max_steps = runtime.get('max_plan_steps', 20)
    if type(max_steps) is not int or not 0 <= max_steps <= 100:
        raise ContractError('max_plan_steps must be an integer from 0 to 100')
    by_id = {r['id']: r for r in contract['rules']}
    for workflow in contract.get('workflows', []):
        for context in contract['contexts']:
            advertised = by_id[workflow['advertisement_rule']]
            if not active(advertised, context) or not matches(workflow.get('when', {}), context.get('facts', {})):
                continue
            applicable = [r for r in contract['rules'] if active(r, context) and r['scope'] == advertised['scope']]
            restrictions = [r for r in applicable if r.get('forbid_action') and not any(
                p.get('allow_action') == r['forbid_action'] and p['priority'] > r['priority'] for p in applicable)]
            forbidden = {r['forbid_action'] for r in restrictions}
            unavailable = []
            for action in workflow['actions']:
                call = action.get('tool_call')
                if not call:
                    continue
                tool = manifest['tools'].get(call['tool'])
                args = set(call['arguments'])
                if tool is None or args - set(tool['arguments']) or set(tool.get('required', [])) - args:
                    forbidden.add(action['id'])
                    unavailable.append({'action': action['id'], 'tool': call['tool']})
            result = explore(workflow, forbidden, max_steps)
            result.update({'workflow': workflow['id'], 'context_id': context['id'], 'unavailable_actions': unavailable,
                           'resolved_restriction_ids': [r['id'] for r in restrictions],
                           'compliant_fallback_reachable': result['fallback_path'] is not None,
                           'contradictory_effective_instructions': False})
            checks.append(result)
            if unavailable:
                diagnostics.append(diagnostic('UNAVAILABLE_WORKFLOW_ACTION', 'exact', 'error', [advertised], context,
                    {'workflow': workflow['id'], 'unavailable_actions': unavailable},
                    ['Tool IDs and argument names are checked against the supplied manifest; no tool is executed.']))
            if result['status'] == 'reachable':
                continue
            code = 'PLAN_BOUND_EXHAUSTED' if result['status'] == 'unknown' else ('UNSUPPORTED_WORKFLOW' if result['fallback_path'] is not None else 'MISSING_FALLBACK_PATH')
            diagnostics.append(diagnostic(code, 'model_based', 'warning', [advertised] + restrictions, context,
                {k: v for k, v in result.items() if k != 'graph'},
                ['Closed-world deterministic finite boolean-state actions; only listed actions exist.',
                 'A fallback must be explicitly declared compliant by the reviewer.']))
    return diagnostics, checks


def check_workflows(contract, runtime):
    # Backward-compatible helper; public lint uses the supplied manifest.
    return workflow_analysis(contract, {'tools': {}}, runtime)[0]


def check_clauses(contract):
    diagnostics, checks = [], []
    for context in contract['contexts']:
        groups = {}
        for rule in contract['rules']:
            if 'clause' in rule and active(rule, context):
                key = (rule['scope']['entity'], rule['scope']['temporal'])
                groups.setdefault(key, []).append(rule)
        for scope, rules in groups.items():
            core = checked_core(rules)
            result = core['result']
            checks.append({'context_id': context['id'], 'scope': dict(zip(('entity', 'temporal'), scope)),
                           'rule_ids': [r['id'] for r in rules], **result})
            if result['status'] == 'sat':
                continue
            responsible = [r for r in rules if r['id'] in core['rule_ids']] if result['status'] == 'unsat' else rules
            diagnostics.append(diagnostic('UNSATISFIABLE_CONSTRAINT_SET' if result['status'] == 'unsat' else 'SOLVER_BOUND_EXHAUSTED',
                'model_based', 'error' if result['status'] == 'unsat' else 'warning', responsible, context, core,
                ['Explicit finite propositional CNF at one reviewed priority; no arbitrary-English proof.',
                 'At most 24 variables and 20,000 search nodes per solver call.']))
    return diagnostics, checks


def lint(contract, manifest, runtime, root):
    validate(contract, manifest, runtime, root)
    diagnostics = check_references(contract, manifest)
    interpretation = contract.get('interpretation', {})
    if interpretation.get('untranslated_line_count', 0) or interpretation.get('excluded_candidate_ids'):
        warning = diagnostic('INCOMPLETE_SOURCE_COVERAGE', 'semantic_warning', 'warning', [], {},
            {'untranslated_line_count': interpretation.get('untranslated_line_count', 0), 'excluded_candidate_ids': interpretation.get('excluded_candidate_ids', []), 'accepted_rule_count': len(contract['rules'])},
            ['Omitted or untranslated source instructions were not proven compatible.'])
        warning['source_spans'] = interpretation.get('unsupported_spans', [])
        diagnostics.append(warning)
    diagnostics += check_obligations(contract)
    workflow_diags, workflow_checks = workflow_analysis(contract, manifest, runtime)
    diagnostics += workflow_diags
    clause_diags, constraint_checks = check_clauses(contract)
    diagnostics += clause_diags
    bulk_diags, checks = check_bulk(contract, runtime)
    diagnostics += bulk_diags
    for rule in contract['rules']:
        for warning in rule.get('semantic_warnings', []):
            diagnostics.append(diagnostic('SEMANTIC_REVIEW_NEEDED', 'semantic_warning', 'warning', [rule], {}, {'review_note': warning}, ['Author-supplied annotation; no automatic English interpretation.']))
    for d in diagnostics:
        d['assumptions'] = list(dict.fromkeys(contract.get('assumptions', []) + d['assumptions']))
        if d['class'] == 'model_based':
            d['interpretation_status'] = 'Conditional on this declared abstraction; not proof that the source prose conflicts.'
    incomplete_reasons = []
    if interpretation.get('untranslated_line_count', 0) or interpretation.get('excluded_candidate_ids'):
        incomplete_reasons.append('source_coverage')
    if any(d['code'] in ('PLAN_BOUND_EXHAUSTED', 'SOLVER_BOUND_EXHAUSTED') for d in diagnostics):
        incomplete_reasons.append('search_bounds')
    if any(d['code'] == 'SEMANTIC_REVIEW_NEEDED' for d in diagnostics):
        incomplete_reasons.append('semantic_review')
    return {'version': 1, 'contract': contract, 'diagnostics': diagnostics, 'resource_checks': checks, 'workflow_checks': workflow_checks, 'constraint_checks': constraint_checks,
            'coverage': {'translation': 'declared_only', 'incomplete': bool(incomplete_reasons), 'incomplete_reasons': incomplete_reasons, 'interpretation': interpretation, 'context_count': len(contract['contexts']),
                         'plan_bound': runtime.get('max_plan_steps', 20),
                         'universal_prompt_correctness_certified': False},
            'summary': {level: sum(d['severity'] == level for d in diagnostics) for level in ('error', 'warning', 'info')}}
