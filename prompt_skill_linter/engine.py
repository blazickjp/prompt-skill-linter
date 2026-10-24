"""Small, deliberately bounded checker for human-reviewed contracts.

No natural-language inference happens here. A finite context is a test, not a
universal quantifier over all possible conversations.
"""
from __future__ import annotations

import re
from collections import deque
from itertools import combinations
from pathlib import Path
from .schema import ShapeError, check, validate_shape
from .planner import explore
from .sat import checked_core

TRACE_STATE_BUDGET = 20_000


class ContractError(ValueError):
    """Invalid input, rather than an instruction conflict."""


def validate(contract, manifest, runtime, root):
    try:
        validate_shape(contract)
        string_array = {'type': 'array', 'items': {'type': 'string'}}
        tool_shape = {'type': 'object', 'required': ['arguments'], 'additionalProperties': False,
                      'properties': {'arguments': string_array, 'required': string_array, 'capabilities': string_array, 'schema': {'type': 'object'}}}
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
    for group in ('sources', 'rules', 'contexts', 'skills', 'workflows', 'vocabulary', 'axioms'):
        items = contract.get(group, [])
        ids = [x.get('id') for x in items]
        if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
            raise ContractError(f'{group} need unique nonempty string IDs')
    sources = {s['id']: s for s in contract['sources']}
    root = Path(root).resolve()
    coverage_spans = contract.get('interpretation', {}).get('unsupported_spans', [])
    if len(coverage_spans) > 256:
        raise ContractError('At most 256 untranslated source spans can be displayed.')
    for span in coverage_spans:
        if span['source_id'] not in sources:
            raise ContractError('Coverage span references an unknown source.')
        span_path = (root / sources[span['source_id']]['path']).resolve()
        if not span_path.is_relative_to(root) or span_path.stat().st_size > 1_500_000:
            raise ContractError('Invalid coverage source path or size.')
        lines = span_path.read_text(encoding='utf-8').splitlines()
        if not 1 <= span['start_line'] <= span['end_line'] <= len(lines) or span['quote'] != '\n'.join(lines[span['start_line']-1:span['end_line']]):
            raise ContractError('Coverage source quote does not match its exact line span.')
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
    action_source_lines = {}
    assertion_ids = [a['id'] for w in contract.get('workflows', []) for a in w.get('trace_assertions', [])]
    if len(assertion_ids) > 16 or len(assertion_ids) * len(contract['contexts']) > 128:
        raise ContractError('Trace analysis supports 16 assertions and 128 assertion/context pairs per bundle.')
    if len(assertion_ids) != len(set(assertion_ids)) or set(assertion_ids) & {r['id'] for r in contract['rules']}:
        raise ContractError('Trace assertion IDs must be globally unique and distinct from rule IDs.')
    ordering_rule_ids = [o['id'] for w in contract.get('workflows', []) for o in w.get('ordering_rules', [])]
    if len(ordering_rule_ids) != len(set(ordering_rule_ids)):
        raise ContractError('Ordering rule IDs must be globally unique.')
    if set(ordering_rule_ids) & ({r['id'] for r in contract['rules']} | set(assertion_ids)):
        raise ContractError('Ordering rule IDs must be distinct from rule IDs and trace assertion IDs.')
    if contract.get('field_contracts'):
        from .fields import FieldContractError, validate_field_contracts
        try:
            validate_field_contracts(contract, root)
        except FieldContractError as exc:
            raise ContractError(str(exc)) from exc
    for workflow in contract.get('workflows', []):
        if len(workflow['actions']) > 64:
            raise ContractError('A workflow may declare at most 64 actions.')
        assertions = workflow.get('trace_assertions', [])
        if len(assertions) > 8:
            raise ContractError('At most 8 trace assertions per workflow are supported.')
        if assertions:
            from .trace import validate_assertions
            try:
                validate_assertions(workflow)
            except ValueError as exc:
                raise ContractError(str(exc)) from exc
        if workflow.get('ordering_rules'):
            from .ordering import validate_ordering_rules
            try:
                validate_ordering_rules(workflow, sources, root)
            except ValueError as exc:
                raise ContractError(str(exc)) from exc
        evidence_holders = workflow['actions'] + [
            {'provenance': {'source_spans': [a['source']], 'assumptions': a['assumptions']}}
            for a in assertions
        ]
        for action in evidence_holders:
            provenance = action.get('provenance', {})
            spans = provenance.get('source_spans', [])
            if len(spans) > 32 or len(provenance.get('assumptions', [])) > 32:
                raise ContractError('Action provenance supports at most 32 spans and 32 assumptions.')
            for span in spans:
                if span['source_id'] not in sources:
                    raise ContractError('Action provenance references an unknown source.')
                path = (root / sources[span['source_id']]['path']).resolve()
                if not path.is_relative_to(root):
                    raise ContractError('Action provenance source must stay within the contract directory.')
                if path not in action_source_lines:
                    try:
                        if path.stat().st_size > 1_500_000:
                            raise ContractError('Action provenance source exceeds the analysis limit.')
                        action_source_lines[path] = path.read_text(encoding='utf-8').splitlines()
                    except (OSError, UnicodeError) as exc:
                        raise ContractError('Cannot read action provenance source.') from exc
                lines = action_source_lines[path]
                start, end = span['start_line'], span['end_line']
                if not 1 <= start <= end <= len(lines) or span['quote'] != '\n'.join(lines[start - 1:end]):
                    raise ContractError('Action provenance quote does not match its exact line span.')
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
    
    # Validate vocabulary source spans
    for vocab_entry in contract.get('vocabulary', []):
        for span in vocab_entry.get('source_spans', []):
            if span['source_id'] not in sources:
                raise ContractError(f"Vocabulary entry '{vocab_entry['id']}' references unknown source.")
            path = (root / sources[span['source_id']]['path']).resolve()
            if not path.is_relative_to(root):
                raise ContractError('Vocabulary source must stay within the contract directory.')
            if path not in action_source_lines:
                try:
                    if path.stat().st_size > 1_500_000:
                        raise ContractError('Vocabulary source exceeds the analysis limit.')
                    action_source_lines[path] = path.read_text(encoding='utf-8').splitlines()
                except (OSError, UnicodeError) as exc:
                    raise ContractError('Cannot read vocabulary source.') from exc
            lines = action_source_lines[path]
            start, end = span['start_line'], span['end_line']
            if not 1 <= start <= end <= len(lines) or span['quote'] != '\n'.join(lines[start - 1:end]):
                raise ContractError('Vocabulary quote does not match its exact line span.')
    
    # Validate axioms
    for axiom in contract.get('axioms', []):
        if not isinstance(axiom.get('clause'), list) or not axiom['clause']:
            raise ContractError(f"Axiom '{axiom['id']}' must have a non-empty clause.")
        if len(axiom['clause']) > 32:
            raise ContractError(f"Axiom '{axiom['id']}' clause may contain at most 32 literals.")
        for lit in axiom['clause']:
            if not isinstance(lit.get('literal'), str) or type(lit.get('value')) is not bool:
                raise ContractError(f"Axiom '{axiom['id']}' clause needs literal (string) and value (boolean).")
        for span in axiom.get('source_spans', []):
            if span['source_id'] not in sources:
                raise ContractError(f"Axiom '{axiom['id']}' references unknown source.")
            path = (root / sources[span['source_id']]['path']).resolve()
            if not path.is_relative_to(root):
                raise ContractError('Axiom source must stay within the contract directory.')
            if path not in action_source_lines:
                try:
                    if path.stat().st_size > 1_500_000:
                        raise ContractError('Axiom source exceeds the analysis limit.')
                    action_source_lines[path] = path.read_text(encoding='utf-8').splitlines()
                except (OSError, UnicodeError) as exc:
                    raise ContractError('Cannot read axiom source.') from exc
            lines = action_source_lines[path]
            start, end = span['start_line'], span['end_line']
            if not 1 <= start <= end <= len(lines) or span['quote'] != '\n'.join(lines[start - 1:end]):
                raise ContractError('Axiom quote does not match its exact line span.')
    
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


def condition_status(condition, facts):
    if any(k in facts and (type(facts[k]) is not type(v) or facts[k] != v) for k, v in condition.items()):
        return 'false'
    return 'unknown' if any(k not in facts for k in condition) else 'true'


def matches(condition, facts):
    return condition_status(condition, facts) == 'true'


def activation_status(rule, context):
    if not set(rule.get('skills', [])) <= set(context.get('active_skills', [])):
        return 'inactive'
    facts = context.get('facts', {})
    when = condition_status(rule.get('when', {}), facts)
    exceptions = [condition_status(e, facts) for e in rule.get('exceptions', [])]
    if when == 'false' or 'true' in exceptions:
        return 'inactive'
    if when == 'unknown' or 'unknown' in exceptions:
        return 'unknown'
    return 'active'


def active(rule, context):
    return activation_status(rule, context) == 'active'


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


def check_vocabulary(contract):
    """Check vocabulary integrity: declaration, uniqueness, usage, types, units."""
    diagnostics = []
    vocabulary = {v['id']: v for v in contract.get('vocabulary', [])}
    
    # Only check vocabulary if it exists
    if not vocabulary:
        return diagnostics
    
    # Check for synonym conflicts:
    # 1. Synonym equals another entry's id
    # 2. Synonym equals the entry's own id
    # 3. Same synonym used by multiple entries
    synonym_to_term = {}
    all_term_ids = set(vocabulary.keys())
    
    for term in vocabulary.values():
        # Check for duplicate synonyms within the same entry
        synonyms_list = term.get('synonyms', [])
        seen_synonyms = set()
        for syn in synonyms_list:
            if syn in seen_synonyms:
                diagnostics.append(diagnostic('AMBIGUOUS_SYNONYM', 'exact', 'error', [], {},
                    {'synonym': syn, 'reason': 'duplicate_spelling_in_entry', 'term': term['id']}))
                # Skip cross-owner checks for duplicates within the same entry
                seen_synonyms.add(syn)
                continue
            seen_synonyms.add(syn)
            
            # Check if synonym equals the entry's own id
            if syn == term['id']:
                diagnostics.append(diagnostic('AMBIGUOUS_SYNONYM', 'exact', 'error', [], {},
                    {'synonym': syn, 'reason': 'synonym_equals_own_id', 'term': term['id']}))
            # Check if synonym equals another entry's id
            elif syn in all_term_ids:
                diagnostics.append(diagnostic('AMBIGUOUS_SYNONYM', 'exact', 'error', [], {},
                    {'synonym': syn, 'reason': 'synonym_equals_other_term_id', 
                     'conflicting_terms': sorted([syn, term['id']])}))
            # Check if synonym is already used by another entry
            elif syn in synonym_to_term:
                diagnostics.append(diagnostic('AMBIGUOUS_SYNONYM', 'exact', 'error', [], {},
                    {'synonym': syn, 'reason': 'synonym_used_by_multiple_terms',
                     'conflicting_terms': sorted([synonym_to_term[syn], term['id']])}))
            else:
                synonym_to_term[syn] = term['id']
    
    # Collect all vocabulary terms used anywhere (effects, clauses, conditions, context facts)
    used_terms = set()
    term_usage = {}  # term -> list of (rule_id, usage_location)
    literal_types = {}  # literal -> list of (rule_id, usage_type, details)
    
    # Track usage in effects and clauses (boolean usage)
    for rule in contract['rules']:
        if 'effect' in rule:
            lit = rule['effect']['literal']
            used_terms.add(lit)
            term_usage.setdefault(lit, []).append((rule['id'], 'effect'))
            literal_types.setdefault(lit, []).append(
                (rule['id'], 'bool_effect', {'value': rule['effect']['value']}))
        if 'clause' in rule:
            for atom in rule['clause']:
                lit = atom['literal']
                used_terms.add(lit)
                term_usage.setdefault(lit, []).append((rule['id'], 'clause'))
                literal_types.setdefault(lit, []).append(
                    (rule['id'], 'bool_clause', {'value': atom['value']}))
    
    # Track usage in when/exceptions (condition usage) and validate types
    for rule in contract['rules']:
        # Check 'when' conditions
        for fact_name, fact_value in rule.get('when', {}).items():
            used_terms.add(fact_name)
            term_usage.setdefault(fact_name, []).append((rule['id'], 'when'))
            
            if fact_name in vocabulary:
                term = vocabulary[fact_name]
                term_type = term['type']
                
                # Type validation
                if term_type == 'enum':
                    declared_values = set(term.get('values', []))
                    if declared_values and fact_value not in declared_values:
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                            {'fact': fact_name, 'declared_type': 'enum', 'value': fact_value,
                             'declared_values': sorted(declared_values),
                             'rule_id': rule['id'], 'condition_type': 'when'}))
                elif term_type == 'int':
                    if type(fact_value) not in (int, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                            {'fact': fact_name, 'declared_type': 'int', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'rule_id': rule['id'], 'condition_type': 'when'}))
                elif term_type == 'bool':
                    if type(fact_value) not in (bool, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                            {'fact': fact_name, 'declared_type': 'bool', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'rule_id': rule['id'], 'condition_type': 'when'}))
        
        # Check 'exceptions' conditions
        for exception in rule.get('exceptions', []):
            for fact_name, fact_value in exception.items():
                used_terms.add(fact_name)
                term_usage.setdefault(fact_name, []).append((rule['id'], 'exception'))
                
                if fact_name in vocabulary:
                    term = vocabulary[fact_name]
                    term_type = term['type']
                    
                    # Type validation
                    if term_type == 'enum':
                        declared_values = set(term.get('values', []))
                        if declared_values and fact_value not in declared_values:
                            diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                                {'fact': fact_name, 'declared_type': 'enum', 'value': fact_value,
                                 'declared_values': sorted(declared_values),
                                 'rule_id': rule['id'], 'condition_type': 'exception'}))
                    elif term_type == 'int':
                        if type(fact_value) not in (int, type(None)):
                            diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                                {'fact': fact_name, 'declared_type': 'int', 'value': fact_value,
                                 'value_type': type(fact_value).__name__,
                                 'rule_id': rule['id'], 'condition_type': 'exception'}))
                    elif term_type == 'bool':
                        if type(fact_value) not in (bool, type(None)):
                            diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                                {'fact': fact_name, 'declared_type': 'bool', 'value': fact_value,
                                 'value_type': type(fact_value).__name__,
                                 'rule_id': rule['id'], 'condition_type': 'exception'}))
    
    # Track usage in context facts and validate types
    for context in contract['contexts']:
        for fact_name, fact_value in context.get('facts', {}).items():
            used_terms.add(fact_name)
            term_usage.setdefault(fact_name, []).append(('context', context['id']))
            
            if fact_name in vocabulary:
                term = vocabulary[fact_name]
                term_type = term['type']
                
                # Type validation for context facts
                if term_type == 'enum':
                    declared_values = set(term.get('values', []))
                    if declared_values and fact_value not in declared_values:
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'fact': fact_name, 'declared_type': 'enum', 'value': fact_value,
                             'declared_values': sorted(declared_values),
                             'context_id': context['id'], 'location': 'context_facts'}))
                elif term_type == 'int':
                    if type(fact_value) not in (int, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'fact': fact_name, 'declared_type': 'int', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'context_id': context['id'], 'location': 'context_facts'}))
                elif term_type == 'bool':
                    if type(fact_value) not in (bool, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'fact': fact_name, 'declared_type': 'bool', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'context_id': context['id'], 'location': 'context_facts'}))
    
    # Track usage in workflow.when conditions and validate types
    for workflow in contract.get('workflows', []):
        for fact_name, fact_value in workflow.get('when', {}).items():
            used_terms.add(fact_name)
            term_usage.setdefault(fact_name, []).append(('workflow', workflow['id']))
            
            if fact_name in vocabulary:
                term = vocabulary[fact_name]
                term_type = term['type']
                
                # Type validation for workflow.when
                if term_type == 'enum':
                    declared_values = set(term.get('values', []))
                    if declared_values and fact_value not in declared_values:
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'fact': fact_name, 'declared_type': 'enum', 'value': fact_value,
                             'declared_values': sorted(declared_values),
                             'workflow_id': workflow['id'], 'condition_type': 'workflow_when'}))
                elif term_type == 'int':
                    if type(fact_value) not in (int, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'fact': fact_name, 'declared_type': 'int', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'workflow_id': workflow['id'], 'condition_type': 'workflow_when'}))
                elif term_type == 'bool':
                    if type(fact_value) not in (bool, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'fact': fact_name, 'declared_type': 'bool', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'workflow_id': workflow['id'], 'condition_type': 'workflow_when'}))
    
    # Check for controlled_action used as Boolean effect/clause
    for term_id, term in vocabulary.items():
        if term.get('role') == 'controlled_action':
            if term_id in literal_types:
                # This controlled_action is used as a boolean literal
                usages = literal_types[term_id]
                for rule_id, usage_type, _ in usages:
                    diagnostics.append(diagnostic('ACTION_STATE_CONFLATION', 'exact', 'error', [], {},
                        {'action_id': term_id, 'role': 'controlled_action',
                         'conflicting_usage': usage_type, 'rule_id': rule_id}))
    
    # Check action IDs in ordering rules match controlled_action vocabulary entries
    for workflow in contract.get('workflows', []):
        for ordering_rule in workflow.get('ordering_rules', []):
            for action_id in ordering_rule.get('actions', []):
                if action_id in vocabulary:
                    entry = vocabulary[action_id]
                    if entry.get('role') != 'controlled_action':
                        diagnostics.append(diagnostic('ACTION_VOCABULARY_ROLE_MISMATCH', 'exact', 'error', 
                            [], {}, {
                                'action_id': action_id,
                                'expected_role': 'controlled_action',
                                'actual_role': entry.get('role'),
                                'ordering_rule': ordering_rule['id']
                            }))
    
    # Check for undeclared terms (only when vocabulary exists)
    for term in sorted(used_terms):
        if term not in vocabulary:
            usage_list = [f"{rid}:{loc}" for rid, loc in term_usage[term]]
            diagnostics.append(diagnostic('UNDEFINED_TERM', 'exact', 'info', [], {},
                {'term': term, 'usage': usage_list[:5],  # Limit to first 5
                 'auto_declared': True, 'inferred_type': 'bool'}))
    
    # Check for type consistency in boolean usage (effects/clauses)
    for lit in literal_types:
        if lit in vocabulary:
            term = vocabulary[lit]
            term_type = term['type']
            
            # All boolean uses should be consistent with the declared type
            for rule_id, usage_type, details in literal_types[lit]:
                if usage_type in ('bool_effect', 'bool_clause'):
                    # This term is used as a boolean
                    if term_type != 'bool':
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'literal': lit, 'declared_type': term_type, 'used_as': 'bool',
                             'rule_id': rule_id, 'usage': usage_type}))
    
    # Check for unused vocabulary entries
    for term_id in sorted(vocabulary.keys()):
        if term_id not in used_terms:
            # Check if it's a controlled_action that might be used in ordering rules
            term = vocabulary[term_id]
            used_in_ordering = False
            for workflow in contract.get('workflows', []):
                for ordering_rule in workflow.get('ordering_rules', []):
                    if term_id in ordering_rule.get('actions', []):
                        used_in_ordering = True
                        break
                if used_in_ordering:
                    break
            
            if not used_in_ordering:
                diagnostics.append(diagnostic('UNUSED_VOCABULARY_ENTRY', 'exact', 'info', [], {},
                    {'term': term_id, 'reason': 'declared but never referenced'}))
    
    return diagnostics


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
    by_id = {r['id']: r for r in contract['rules']}
    scoped_actions = {}
    for workflow in contract.get('workflows', []):
        ad = by_id[workflow['advertisement_rule']]
        key = (ad['scope']['entity'], ad['scope']['temporal'])
        ids = {a['id'] for a in workflow['actions']}
        scoped_actions.setdefault(key, set()).update(ids)
        fallback = workflow.get('compliant_fallback')
        if fallback and fallback not in ids:
            diagnostics.append(diagnostic('BROKEN_ACTION_REFERENCE', 'exact', 'error', [ad], {},
                {'workflow': workflow['id'], 'missing_fallback_action': fallback}))
    for rule in contract['rules']:
        key = (rule['scope']['entity'], rule['scope']['temporal'])
        for field in ('forbid_action', 'allow_action'):
            if field in rule and key in scoped_actions and rule[field] not in scoped_actions[key]:
                diagnostics.append(diagnostic('BROKEN_ACTION_REFERENCE', 'exact', 'error', [rule], {},
                    {'field': field, 'missing_action': rule[field], 'scope': rule['scope']}))
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
            unresolved = [r for r in contract['rules'] if 'effect' in r and activation_status(r, context) == 'unknown' and (r['scope']['entity'], r['scope']['temporal'], r['effect']['literal']) == key]
            if unresolved:
                # Unknown applicability can change hierarchy; do not prove a conflict from a guessed effective set.
                continue
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
    trace_states_remaining = TRACE_STATE_BUDGET
    max_steps = runtime.get('max_plan_steps', 20)
    if type(max_steps) is not int or not 0 <= max_steps <= 100:
        raise ContractError('max_plan_steps must be an integer from 0 to 100')
    by_id = {r['id']: r for r in contract['rules']}
    for workflow in contract.get('workflows', []):
        for context in contract['contexts']:
            advertised = by_id[workflow['advertisement_rule']]
            if not active(advertised, context):
                continue
            condition = condition_status(workflow.get('when', {}), context.get('facts', {}))
            if condition != 'true':
                if condition == 'unknown':
                    diagnostics.append(diagnostic('UNRESOLVED_ACTIVATION', 'semantic_warning', 'warning', [advertised], context, {'workflow': workflow['id'], 'missing_facts': sorted(set(workflow.get('when', {})) - set(context.get('facts', {})))}))
                continue
            unknown_policy = [r for r in contract['rules'] if activation_status(r, context) == 'unknown' and r['scope'] == advertised['scope'] and any(k in r for k in ('forbid_action', 'allow_action'))]
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
            if unknown_policy:
                result.update({'status': 'unknown', 'reason': 'unresolved_activation', 'candidate_path': result['goal_path'], 'goal_path': None, 'fallback_path': None, 'search_exhaustive': False})
            result.update({'workflow': workflow['id'], 'context_id': context['id'], 'unavailable_actions': unavailable,
                           'resolved_restriction_ids': [r['id'] for r in restrictions],
                           'compliant_fallback_reachable': result['fallback_path'] is not None,
                           'contradictory_effective_instructions': False})
            result['action_provenance'] = {a['id']: a.get('provenance', {'source_spans': [], 'assumptions': []}) for a in workflow['actions']}
            ungrounded = [a['id'] for a in workflow['actions'] if not a.get('provenance', {}).get('source_spans')]
            result['provenance_limitations'] = ([
                'Action source evidence is absent for: ' + ', '.join(ungrounded)
            ] if ungrounded else []) + [
                'Action source quotations establish provenance only; precondition/effect equivalence to prose remains a reviewed abstraction.'
            ]
            result['trace_assertions'] = []
            if workflow.get('trace_assertions'):
                from .trace import check_trace_assertions
                if unknown_policy:
                    trace_results = [{'assertion_id': a['id'], 'kind': a['kind'], 'status': 'unknown',
                        'violation_path': None, 'search_exhaustive': False, 'visited_states': 0,
                        'bounds': {'max_steps': max_steps, 'max_states': 2000},
                        'cutoff_reasons': ['unresolved_activation']} for a in workflow['trace_assertions']]
                else:
                    trace_results = []
                    for assertion in workflow['trace_assertions']:
                        allowance = min(2000, trace_states_remaining)
                        if allowance:
                            isolated = dict(workflow, trace_assertions=[assertion])
                            trace_result = check_trace_assertions(isolated, forbidden, max_steps=max_steps, max_states=allowance)[0]
                            trace_states_remaining -= trace_result['visited_states']
                            if trace_result['status'] == 'unknown' and allowance < 2000 and 'max_states' in trace_result['cutoff_reasons']:
                                trace_result['cutoff_reasons'].append('aggregate_trace_state_budget')
                                trace_result['trigger_coverage']['cutoff_reasons'].append('aggregate_trace_state_budget')
                        else:
                            trace_result = {'assertion_id': assertion['id'], 'kind': assertion['kind'], 'status': 'unknown',
                                'violation_path': None, 'search_exhaustive': False, 'visited_states': 0,
                                'bounds': {'max_steps': max_steps, 'max_states': 0},
                                'cutoff_reasons': ['aggregate_trace_state_budget']}
                        trace_result['aggregate_budget'] = {'max_visited_states': TRACE_STATE_BUDGET,
                                                            'remaining_states': trace_states_remaining}
                        trace_results.append(trace_result)
                for assertion, trace_result in zip(workflow['trace_assertions'], trace_results):
                    trace_result.setdefault('trigger_coverage', {
                        'status': 'unknown',
                        'trigger_actions': list(assertion['actions'] if assertion['kind'] == 'action_count'
                                                else assertion['guarded_actions']),
                        'first_trigger_path': None, 'search_exhaustive': False,
                        'cutoff_reasons': list(trace_result['cutoff_reasons']),
                        'scope': 'enabled_action_events_in_reviewed_transition_model',
                    })
                    implicated = set(trace_result.get('violation_path') or [])
                    trace_result.update({'workflow': workflow['id'], 'context_id': context['id'],
                                         'source': assertion['source'], 'assumptions': assertion['assumptions'],
                                         'property_scope': 'safety_of_allowed_paths_in_reviewed_transition_model',
                                         'completion_feasibility_not_disproved': True,
                                         'minimality_not_checked': True,
                                         'implicated_actions': [a for a in workflow['actions'] if a['id'] in implicated],
                                         'resolved_action_policy': [{'id': r['id'], 'priority': r['priority'], 'kind': r['kind'],
                                             'action': r.get('allow_action', r.get('forbid_action')), 'source': r['source']}
                                             for r in applicable if 'allow_action' in r or 'forbid_action' in r],
                                         'policy_notice': 'Hierarchy determines action availability; the reviewer-declared trace property has no intrinsic priority.'})
                    result['trace_assertions'].append(trace_result)
                    if trace_result['status'] == 'safe':
                        coverage = trace_result['trigger_coverage']['status']
                        if coverage == 'reachable':
                            continue
                        code = 'TRACE_TRIGGER_UNREACHABLE' if coverage == 'unreachable' else 'TRACE_TRIGGER_COVERAGE_UNKNOWN'
                        severity = 'info'
                    else:
                        code = 'TRACE_ASSERTION_VIOLATED' if trace_result['status'] == 'violated' else 'TRACE_ANALYSIS_UNKNOWN'
                        severity = 'error' if trace_result['status'] == 'violated' else 'warning'
                    item = diagnostic(code, 'model_based', severity,
                                      [], context, trace_result, assertion['assumptions'] + [
                                          'Author-declared finite action-event assertion; no prose inference or runtime execution.',
                                          'All enabled prefixes are checked, including after the goal; assertion monitors are independent of workflow effects.',
                                          'Trigger coverage is separate from safety. An unreachable trigger may be intentional; it is not an instruction conflict.'])
                    item['source_spans'] = [assertion['source']]
                    if code == 'TRACE_TRIGGER_UNREACHABLE':
                        item['message'] = 'Safety is satisfied in this model, but no enabled assertion trigger is reachable. This may be intentional.'
                    elif code == 'TRACE_TRIGGER_COVERAGE_UNKNOWN':
                        item['message'] = 'Safety is satisfied in this model; trigger reachability remains unknown under the configured bounds.'
                    for action in trace_result['implicated_actions']:
                        for span in action.get('provenance', {}).get('source_spans', []):
                            if span not in item['source_spans']:
                                item['source_spans'].append(span)
                    item['interpreted_rules'] = [{'id': assertion['id'], 'source': assertion['source'], 'trace_assertion': assertion}]
                    item['responsible_rule_set'] = [assertion['id']]
                    item['resolved_priorities'] = {r['id']: r['priority'] for r in trace_result['resolved_action_policy']}
                    item['regression_case'].update({'assertion_id': assertion['id'], 'violation_path': trace_result.get('violation_path')})
                    item['provenance_limitations'] = ['Exact source text does not prove the assertion or transition abstraction is semantically faithful.']
                    missing_action_evidence = [a['id'] for a in trace_result['implicated_actions'] if not a.get('provenance', {}).get('source_spans')]
                    if missing_action_evidence:
                        item['provenance_limitations'].append('Witness action source evidence is absent for: ' + ', '.join(missing_action_evidence))
                    diagnostics.append(item)
            
            # Check ordering rules
            if workflow.get('ordering_rules'):
                from .ordering import check_ordering_rules
                ordering_diags, ordering_checks = check_ordering_rules(
                    workflow, result, workflow['id'], context, forbidden
                )
                diagnostics.extend(ordering_diags)
                result['ordering_rules'] = ordering_checks
            
            checks.append(result)
            if unavailable:
                diagnostics.append(diagnostic('UNAVAILABLE_WORKFLOW_ACTION', 'exact', 'error', [advertised], context,
                    {'workflow': workflow['id'], 'unavailable_actions': unavailable},
                    ['Tool IDs and argument names are checked against the supplied manifest; no tool is executed.']))
            if result['status'] == 'reachable':
                continue
            code = 'WORKFLOW_ACTIVATION_UNKNOWN' if unknown_policy else ('PLAN_BOUND_EXHAUSTED' if result['status'] == 'unknown' else ('UNSUPPORTED_WORKFLOW' if result['fallback_path'] is not None else 'MISSING_FALLBACK_PATH'))
            diagnostics.append(diagnostic(code, 'model_based', 'warning', [advertised] + restrictions, context,
                {k: v for k, v in result.items() if k != 'graph'},
                ['Closed-world deterministic finite boolean-state actions; only listed actions exist.',
                 'A fallback must be explicitly declared compliant by the reviewer.']))
            diagnostics[-1]['provenance_limitations'].extend(result['provenance_limitations'])
    return diagnostics, checks


def check_workflows(contract, runtime):
    # Backward-compatible helper; public lint uses the supplied manifest.
    return workflow_analysis(contract, {'tools': {}}, runtime)[0]


def field_analysis(contract):
    """Field-presence checks on explicitly active, fixed-scope data edges."""
    from .fields import check_field_presence
    diagnostics, checks = [], []
    for declaration in contract.get('field_contracts', []):
        spans, assumptions = [], list(declaration['assumptions'])
        for holder in [declaration['producer'], declaration['consumer']] + declaration['adapters']:
            assumptions.extend(holder['provenance']['assumptions'])
            for span in holder['provenance']['source_spans']:
                if span not in spans:
                    spans.append(span)
        assumptions.extend([
            'One reviewer-declared data edge in its fixed entity/temporal scope; activation does not prove workflow reachability.',
            'Required producer keys are guaranteed; optional keys may be absent; a closed producer has no undeclared keys.',
            'Only literal top-level field presence is checked; values, types, nested paths, execution, and implicit aliases are outside scope.',
            'No instruction priority is inferred for this edge; policy resolution and any consumer occurrence are review assumptions.',
        ])
        for context in contract['contexts']:
            activation = activation_status(declaration, context)
            result = {'field_contract_id': declaration['id'], 'context_id': context['id'],
                      'scope': declaration['scope'], 'activation': activation,
                      'status': 'inactive' if activation == 'inactive' else 'unknown',
                      'reason': 'inactive_context' if activation == 'inactive' else 'unresolved_activation',
                      'source_spans': spans, 'assumptions': list(dict.fromkeys(assumptions)),
                      'presence_only': True, 'runtime_observations_verified': False}
            if activation == 'active':
                result.update(check_field_presence(declaration))
                result['reason'] = ('closed_record_missing_required_field' if result['status'] == 'incompatible'
                                    else 'required_field_not_guaranteed' if result['status'] == 'unknown'
                                    else 'all_required_fields_guaranteed')
            checks.append(result)
            if result['status'] in ('compatible', 'inactive'):
                continue
            incompatible = result['status'] == 'incompatible'
            code = 'REQUIRED_FIELD_NOT_PRODUCED' if incompatible else 'FIELD_PRESENCE_UNKNOWN'
            item = diagnostic(code, 'exact' if incompatible else 'model_based',
                              'error' if incompatible else 'warning', [], context, result, result['assumptions'])
            item['source_spans'] = spans
            item['interpreted_rules'] = [{'id': declaration['id'], 'field_contract': declaration,
                                         'source': declaration['consumer']['provenance']['source_spans'][0],
                                         'scope': declaration['scope']}]
            item['responsible_rule_set'] = [declaration['id']]
            item['regression_case']['field_contract_id'] = declaration['id']
            item['provenance_limitations'] = [
                'Exact source quotations do not prove that the declared schema, literal property read, adapter, or active consuming branch matches runtime behavior.'
            ]
            if incompatible:
                item['message'] = 'Required consumer keys absent from this reviewed closed producer: ' + ', '.join(result['missing_required_fields']) + '.'
                item['interpretation_status'] = 'Exact missing-field relation under the reviewed closed-record projection; not proof of runtime failure or a whole-skill conflict.'
                item['regression_case']['missing_required_fields'] = result['missing_required_fields']
            else:
                item['message'] = 'Required field presence remains unknown in this reviewed context.'
            diagnostics.append(item)
    return diagnostics, checks


def check_clauses(contract):
    diagnostics, checks = [], []
    for context in contract['contexts']:
        groups = {}
        for rule in contract['rules']:
            if 'clause' in rule and active(rule, context):
                key = (rule['scope']['entity'], rule['scope']['temporal'])
                groups.setdefault(key, []).append(rule)
        for scope, rules in groups.items():
            unresolved = [r for r in contract['rules'] if 'clause' in r and activation_status(r, context) == 'unknown' and (r['scope']['entity'], r['scope']['temporal']) == scope]
            if unresolved:
                checks.append({'context_id': context['id'], 'scope': dict(zip(('entity', 'temporal'), scope)), 'rule_ids': [r['id'] for r in rules + unresolved], 'status': 'unknown', 'reason': 'unresolved_activation'})
                continue
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


def check_conditional_conflicts(contract):
    """Check unconditional Boolean effects + axioms for satisfiability.
    
    This is a partial step toward issue #6. It checks unconditional Boolean
    effect rules combined with axioms in explicitly enumerated contexts.
    Full conditional-conflict search (input-dependent axioms, numeric conditions,
    existential witness inputs, feasible-input partitioning) is deferred.
    """
    diagnostics, checks = [], []
    
    # Only proceed if we have axioms
    if not contract.get('axioms'):
        return diagnostics, checks
    
    # Check for ID collisions between rules and axioms
    rule_ids = {r['id'] for r in contract['rules']}
    axiom_ids = {a['id'] for a in contract.get('axioms', [])}
    collisions = rule_ids & axiom_ids
    if collisions:
        raise ContractError(f'Rule and axiom IDs must be disjoint; collisions: {sorted(collisions)}')
    
    # Detect input-dependent axioms (unsupported)
    external_inputs = {v['id'] for v in contract.get('vocabulary', []) if v.get('role') == 'external_input'}
    input_dependent_axioms = []
    for axiom in contract.get('axioms', []):
        axiom_literals = {lit['literal'] for lit in axiom['clause']}
        if axiom_literals & external_inputs:
            input_dependent_axioms.append(axiom['id'])
    
    # Also detect context facts that overlap with axiom literals but lack external_input role
    context_fact_axioms = []
    all_context_facts = set()
    for context in contract['contexts']:
        all_context_facts.update(context.get('facts', {}).keys())
    
    for axiom in contract.get('axioms', []):
        axiom_literals = {lit['literal'] for lit in axiom['clause']}
        # Check if axiom references context facts that aren't declared as external_input
        undeclared_context_refs = (axiom_literals & all_context_facts) - external_inputs
        if undeclared_context_refs:
            context_fact_axioms.append(axiom['id'])
    
    # If we have input-dependent axioms or context-fact overlap, emit an incomplete diagnostic
    if input_dependent_axioms or context_fact_axioms:
        witness = {
            'input_dependent_axioms': input_dependent_axioms,
            'external_inputs_referenced': sorted(external_inputs & {lit['literal'] for ax in contract['axioms'] for lit in ax['clause']})
        }
        if context_fact_axioms:
            witness['context_fact_axioms'] = context_fact_axioms
            witness['undeclared_context_facts'] = sorted((all_context_facts & {lit['literal'] for ax in contract['axioms'] for lit in ax['clause']}) - external_inputs)
        assumptions = [
            'Axioms reference external_input variables or context facts; context facts are not substituted into axioms.',
            'The satisfiability check may miss conflicts where context facts would make axioms binding.',
            'This is an unsupported case; input-dependent axiom checking is unsupported by this checker.'
        ]
        diag = diagnostic('AXIOM_CHECK_INCOMPLETE', 'model_based', 'warning',
                        [], {}, witness, assumptions)
        diagnostics.append(diag)
        # Return with incomplete coverage
        return diagnostics, checks
    
    # Group rules by scope and context, using check_obligations semantics
    for context in contract['contexts']:
        groups = {}
        for rule in contract['rules']:
            # Use same filter as check_obligations: active, has effect, not preference
            if active(rule, context) and 'effect' in rule and rule['kind'] != 'preference':
                key = (rule['scope']['entity'], rule['scope']['temporal'])
                groups.setdefault(key, []).append(rule)
        
        for scope, rules in groups.items():
            # Skip if there are unresolved activations
            unresolved = [r for r in contract['rules'] if 'effect' in r and 
                         activation_status(r, context) == 'unknown' and 
                         (r['scope']['entity'], r['scope']['temporal']) == scope]
            if unresolved:
                continue
            
            # Apply check_obligations priority resolution logic
            # Permissions can suppress prohibitions; only requirements/prohibitions create obligations
            effective = []
            retained = []
            for rule in sorted(rules, key=lambda r: -r['priority']):
                value = rule['effect']['value'] if rule['kind'] != 'prohibition' else not rule['effect']['value']
                stronger = [r for r in retained if r['priority'] > rule['priority'] and
                           rule['effect']['literal'] == r['effect']['literal'] and (
                               (r['kind'] == 'permission' and rule['kind'] == 'prohibition' and 
                                r['effect']['value'] == rule['effect']['value'])
                               or (r['kind'] in ('requirement', 'prohibition') and
                                   (r['effect']['value'] if r['kind'] == 'requirement' else not r['effect']['value']) != value))]
                if not stronger:
                    retained.append(rule)
                    if rule['kind'] != 'permission':
                        effective.append((rule, value))
            
            if not effective:
                continue
            
            # Convert effective obligations to CNF clauses (unconditional only)
            rule_clauses = []
            for rule, value in effective:
                if not rule.get('when'):  # Only unconditional
                    rule_clauses.append({
                        'id': f'rule_{rule["id"]}',  # Tag to prevent collision
                        'clause': [{'literal': rule['effect']['literal'], 'value': value}],
                        'source': rule['source'],
                        'original_id': rule['id']
                    })
            
            # Add axioms to the clause set
            axiom_clauses = []
            for axiom in contract.get('axioms', []):
                axiom_clauses.append({
                    'id': f'axiom_{axiom["id"]}',  # Tag to prevent collision
                    'clause': axiom['clause'],
                    'source_spans': axiom.get('source_spans', []),
                    'description': axiom.get('description', ''),
                    'original_id': axiom['id']
                })
            
            if not rule_clauses or not axiom_clauses:
                continue
            
            # Check satisfiability
            all_clauses = rule_clauses + axiom_clauses
            core = checked_core(all_clauses)
            result = core['result']
            
            if result['status'] == 'unsat':
                # Extract original IDs from tagged IDs
                conflicting_rule_ids = [c['original_id'] for c in rule_clauses if c['id'] in core['rule_ids']]
                conflicting_axiom_ids = [c['original_id'] for c in axiom_clauses if c['id'] in core['rule_ids']]
                
                if conflicting_axiom_ids:  # Only report if axioms are involved
                    responsible_rules = [r for r, v in effective if r['id'] in conflicting_rule_ids]
                    responsible_axioms = [a for a in contract['axioms'] if a['id'] in conflicting_axiom_ids]
                    
                    witness = {
                        'minimal_core': conflicting_rule_ids + conflicting_axiom_ids,
                        'rules': conflicting_rule_ids,
                        'axioms': conflicting_axiom_ids,
                        'minimality_checked': core['minimality_checked'],
                        'minimality_scope': 'Deletion witnesses apply to frozen resolved formula set; not source edits followed by priority re-resolution.',
                        'removal_witnesses': {
                            c['original_id']: core['removal_witnesses'].get(c['id'], {})
                            for c in all_clauses if c['id'] in core['rule_ids']
                        }
                    }
                    
                    assumptions = [
                        'Exact relative to confirmed Boolean formalization; says nothing about whether formalization matches prose.',
                        'Axioms are author-confirmed bridge facts.',
                        'Only unconditional Boolean effects checked in explicitly enumerated contexts; input-dependent axioms, numeric conditions, exception-aware search, and feasible-input witness queries are unsupported.',
                        'Conflicts found after applying check_obligations priority resolution; permissions suppress prohibitions.',
                        'Context facts not substituted into axioms; contradictory axiom assumptions are not distinguished from policy conflicts.'
                    ]
                    
                    diag = diagnostic('AXIOM_CONFLICT', 'model_based', 'error',
                                    responsible_rules, context, witness, assumptions)
                    
                    # Add axiom source spans
                    for axiom in responsible_axioms:
                        for span in axiom.get('source_spans', []):
                            if span not in diag['source_spans']:
                                diag['source_spans'].append(span)
                    
                    # Add axiom information to interpreted rules
                    for axiom in responsible_axioms:
                        diag['interpreted_rules'].append({
                            'id': axiom['id'],
                            'axiom': True,
                            'description': axiom.get('description', ''),
                            'clause': axiom['clause']
                        })
                    
                    diagnostics.append(diag)
                    
                    checks.append({
                        'context_id': context['id'],
                        'scope': dict(zip(('entity', 'temporal'), scope)),
                        'status': 'conflict',
                        'core': conflicting_rule_ids + conflicting_axiom_ids
                    })
            elif result['status'] == 'unknown':
                # Surface solver limits
                witness = {
                    'reason': result.get('reason', 'unknown'),
                    'search_cutoff': True
                }
                assumptions = [
                    'Solver reached search limit before determining satisfiability.',
                    'At most 24 variables and configured node budget per call.'
                ]
                diag = diagnostic('AXIOM_CHECK_INCOMPLETE', 'model_based', 'warning',
                                [], context, witness, assumptions)
                diagnostics.append(diag)
                
                checks.append({
                    'context_id': context['id'],
                    'scope': dict(zip(('entity', 'temporal'), scope)),
                    'status': 'unknown',
                    'reason': result.get('reason', 'unknown')
                })
    
    return diagnostics, checks


def check_plain_text_issues(contract, root):
    """Check for undefined terms and vague directives in plain prompt/skill text.
    
    This check works on raw source text directly, without requiring vocabulary annotations
    or contract extraction. It analyzes the source files referenced in the contract.
    
    It flags:
    (a) Undefined terms: domain-specific or capitalized/quoted terms used as if defined
    (b) Vague directives: ambiguous instructions with no clear criterion
    
    Emits warnings (not errors) with source spans and reasons.
    
    Vague terms list is based on:
    - OpenAI prompt engineering guide (https://platform.openai.com/docs/guides/prompt-engineering)
    - Anthropic prompt engineering guide (https://docs.anthropic.com/claude/docs/be-clear-and-direct)
    Common vague qualifiers without measurable criteria.
    """
    diagnostics = []
    sources = {s['id']: s for s in contract['sources']}
    root = Path(root).resolve()
    
    # Read all source files once
    source_texts = {}
    for src_id, src in sources.items():
        path = (root / src['path']).resolve()
        if path.is_file() and path.is_relative_to(root):
            try:
                source_texts[src_id] = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
    
    # Track terms that are explicitly defined in the text
    defined_terms = set()
    
    # Patterns for defined terms (look for definitional context)
    # e.g., "X means...", "X is defined as...", "X refers to...", "X: a definition"
    for src_id, text in source_texts.items():
        # Find terms that appear to be defined
        # Pattern 1: "TERM means/is/refers to"
        for match in re.finditer(r'\b([A-Z][A-Za-z_]+)\s+(?:means|is|refers to|denotes|represents)\b', text):
            defined_terms.add(match.group(1).lower())
        
        # Pattern 2: "TERM: some definition" (colon-based definition)
        for match in re.finditer(r'\b([A-Z][A-Za-z_]+)\s*:\s*(?:a |an |the |[A-Z])?[a-z]', text):
            defined_terms.add(match.group(1).lower())
    
    # Vague directive patterns from cited prompt engineering guides
    # These terms lack measurable success criteria
    vague_patterns = [
        (r'\b(?:be |keep |stay |remain )?concise\b', 'concise', 'No criterion for conciseness'),
        (r'\bappropriate(?:ly)?\b', 'appropriate', 'No criterion for what is appropriate'),
        (r'\bas needed\b', 'as needed', 'No criterion for when it is needed'),
        (r'\bif relevant\b', 'if relevant', 'No criterion for relevance'),
        (r'\bif necessary\b', 'if necessary', 'No criterion for necessity'),
        (r'\bdetailed\b', 'detailed', 'No criterion for level of detail'),
        (r'\bsufficient(?:ly)?\b', 'sufficient', 'No criterion for sufficiency'),
        (r'\breasonable(?:bly)?\b', 'reasonable', 'No criterion for reasonableness'),
        (r'\bwhen possible\b', 'when possible', 'No criterion for possibility'),
    ]
    
    # Process each source file's raw text
    for src_id, full_text in source_texts.items():
        lines = full_text.splitlines()
        
        for line_num, line in enumerate(lines, 1):
            # Check for vague directives
            for pattern, term, reason in vague_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Find associated rule if any, otherwise create diagnostic without rule
                    matching_rules = [r for r in contract['rules'] 
                                     if r.get('source', {}).get('source_id') == src_id 
                                     and r['source'].get('start_line', 0) <= line_num <= r['source'].get('end_line', 0)]
                    
                    rule = matching_rules[0] if matching_rules else None
                    
                    diagnostics.append(diagnostic(
                        'VAGUE_DIRECTIVE', 'exact', 'warning', 
                        [rule] if rule else [], {},
                        {'term': term, 'reason': reason, 'line': line_num, 
                         'quote_excerpt': line[:100], 'source_id': src_id},
                        ['Deterministic pattern match on source text; directive lacks measurable criterion.',
                         'Based on common vague qualifiers from OpenAI and Anthropic prompt engineering guides.']
                    ))
                    break  # Only report one vague directive per line
            
            # Check for undefined capitalized terms
            cap_terms = set()
            
            # Find ALL_CAPS terms (2+ chars, exclude common words)
            common_caps = {'I', 'API', 'URL', 'HTTP', 'HTTPS', 'JSON', 'XML', 'SQL', 'ID', 'UUID', 'CLI', 'UI', 'UX'}
            for match in re.finditer(r'\b[A-Z][A-Z_]+\b', line):
                term = match.group(0)
                # Skip if: too short, common acronym, or part of emphatic text (multiple ALL_CAPS in a row)
                if len(term) < 2 or term in common_caps:
                    continue
                # Check if this is emphatic text (e.g., "all TOOL RESPONSES!" has multiple caps words close together)
                # Look for another ALL_CAPS word within 2 words
                words_around = line[max(0, match.start()-20):min(len(line), match.end()+20)].split()
                caps_count = sum(1 for w in words_around if w.isupper() and len(w) > 1)
                if caps_count >= 2:  # Likely emphatic text, not technical terms
                    continue
                cap_terms.add(term)
            
            # Find PascalCase terms 
            for match in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', line):
                cap_terms.add(match.group(0))
            
            # Find capitalized single words used as criteria (e.g., "Relevant", "Diverse")
            # Look for pattern: "Word - description" or "Word: description"
            for match in re.finditer(r'\b([A-Z][a-z]+)\s*[-:]\s*[a-z]', line):
                cap_terms.add(match.group(1))
            
            # Check if these terms are used in a definitional way (not defined)
            for term in cap_terms:
                if term.lower() not in defined_terms:
                    # Check if the term appears to be used as if it's a known concept
                    # Look for usage patterns like "must X", "the X", "when X", "section"
                    usage_pattern = rf'\b(?:the|must|when|if|as|use|uses|using)\s+{re.escape(term)}\b'
                    criteria_pattern = rf'\b{re.escape(term)}\s*[-:]\s*'
                    section_pattern = rf'\b{re.escape(term)}\s+section\b'
                    
                    if (re.search(usage_pattern, line, re.IGNORECASE) or 
                        re.search(criteria_pattern, line) or
                        re.search(section_pattern, line, re.IGNORECASE)):
                        
                        matching_rules = [r for r in contract['rules'] 
                                         if r.get('source', {}).get('source_id') == src_id 
                                         and r['source'].get('start_line', 0) <= line_num <= r['source'].get('end_line', 0)]
                        
                        rule = matching_rules[0] if matching_rules else None
                        
                        diagnostics.append(diagnostic(
                            'UNDEFINED_TERM_PLAIN', 'exact', 'warning', 
                            [rule] if rule else [], {},
                            {'term': term, 'reason': 'Capitalized term used as criterion but not defined in visible text',
                             'line': line_num, 'source_id': src_id},
                            ['Deterministic pattern match; term appears domain-specific but lacks definition.']
                        ))
                        break  # Only report one undefined term per line
    
    return diagnostics


def lint(contract, manifest, runtime, root, strict_providers=None):
    validate(contract, manifest, runtime, root)
    diagnostics = check_references(contract, manifest)
    diagnostics += check_vocabulary(contract)
    
    # Only run plain text checks when there are no extracted rules AND no field contracts
    # (i.e., when analyzing raw source text without contract extraction)
    # This ensures it doesn't interfere with other analysis modes
    if not contract.get('rules') and not contract.get('field_contracts'):
        diagnostics += check_plain_text_issues(contract, root)
    
    # Check tool schemas for provider strict mode compatibility
    if strict_providers:
        from .strict_mode import check_tool_schemas
        strict_result = check_tool_schemas(manifest, strict_providers)
        for diag in strict_result['diagnostics']:
            # Convert strict mode diagnostics to engine diagnostic format
            if diag['code'] == 'STRICT_MODE_INCOMPATIBLE':
                witness = {
                    'rule_id': diag['rule_id'],
                    'schema_path': diag['schema_path'],
                    'description': diag['description']
                }
                if 'enforcement' in diag:
                    witness['enforcement'] = diag['enforcement']
                diagnostics.append({
                    'code': diag['code'],
                    'class': diag['class'],
                    'severity': diag['severity'],
                    'source_spans': [],
                    'interpreted_rules': [],
                    'resolved_priorities': {},
                    'triggering_context': {'tool': diag['tool'], 'provider': diag['provider']},
                    'witness': witness,
                    'responsible_rule_set': [],
                    'assumptions': ['Offline check against official provider documentation; no API calls made.'],
                    'repairs': [{'changes_requirement': 'tool_schema', 'proposal': diag['fix']}],
                    'regression_case': {'tool': diag['tool'], 'provider': diag['provider'], 'expected_code': diag['code']},
                    'provenance_limitations': ['Tool schema reference points to manifest declaration, not source prose.']
                })
            elif diag['code'] == 'PROVIDER_DIVERGENCE':
                diagnostics.append({
                    'code': diag['code'],
                    'class': diag['class'],
                    'severity': diag['severity'],
                    'source_spans': [],
                    'interpreted_rules': [],
                    'resolved_priorities': {},
                    'triggering_context': {'tool': diag['tool']},
                    'witness': {
                        'compatible_with': diag['compatible_with'],
                        'incompatible_with': diag['incompatible_with'],
                        'description': diag['description']
                    },
                    'responsible_rule_set': [],
                    'assumptions': ['Provider divergence indicates portability risk; schema valid for some providers but not others.'],
                    'repairs': [],
                    'regression_case': {'tool': diag['tool'], 'expected_code': diag['code']},
                    'provenance_limitations': ['Tool schema reference points to manifest declaration, not source prose.']
                })
    for context in contract['contexts']:
        for rule in contract['rules']:
            if activation_status(rule, context) == 'unknown':
                conditions = [rule.get('when', {})] + rule.get('exceptions', [])
                missing = sorted({k for condition in conditions for k in condition if k not in context.get('facts', {})})
                diagnostics.append(diagnostic('UNRESOLVED_ACTIVATION', 'semantic_warning', 'warning', [rule], context, {'missing_facts': missing, 'binding_interpretation_skipped': True}, ['Missing conditions/exception facts can change applicability; no closed-world assumption is made.']))
    interpretation = contract.get('interpretation', {})
    if interpretation.get('untranslated_line_count', 0) or interpretation.get('excluded_candidate_ids'):
        warning = diagnostic('INCOMPLETE_SOURCE_COVERAGE', 'semantic_warning', 'warning', [], {},
            {'untranslated_line_count': interpretation.get('untranslated_line_count', 0), 'excluded_candidate_ids': interpretation.get('excluded_candidate_ids', []), 'accepted_rule_count': len(contract['rules'])},
            ['Omitted or untranslated source instructions were not proven compatible.'])
        warning['source_spans'] = interpretation.get('unsupported_spans', [])
        diagnostics.append(warning)
    diagnostics += check_obligations(contract)
    diagnostics += check_conditional_conflicts(contract)[0]
    workflow_diags, workflow_checks = workflow_analysis(contract, manifest, runtime)
    diagnostics += workflow_diags
    field_diags, field_checks = field_analysis(contract)
    diagnostics += field_diags
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
    if any(d['code'] in ('PLAN_BOUND_EXHAUSTED', 'SOLVER_BOUND_EXHAUSTED', 'TRACE_ANALYSIS_UNKNOWN', 'TRACE_TRIGGER_COVERAGE_UNKNOWN', 'ORDERING_CHECK_INCOMPLETE', 'AXIOM_CHECK_INCOMPLETE') for d in diagnostics):
        incomplete_reasons.append('search_bounds')
    if any(d['class'] == 'semantic_warning' and d['code'] != 'INCOMPLETE_SOURCE_COVERAGE' for d in diagnostics):
        incomplete_reasons.append('semantic_review')
    if any(check['status'] == 'unknown' or check.get('uncertain_required_fields') for check in field_checks):
        incomplete_reasons.append('field_presence')
    return {'version': 1, 'contract': contract, 'diagnostics': diagnostics, 'resource_checks': checks, 'workflow_checks': workflow_checks,
            'trace_checks': [t for w in workflow_checks for t in w.get('trace_assertions', [])], 'constraint_checks': constraint_checks,
            'field_checks': field_checks,
            'coverage': {'translation': 'declared_only', 'runtime_grounding': 'declared_snapshot_only', 'runtime_observations_verified': False, 'interpretation_review_recorded': interpretation.get('status') == 'accepted', 'incomplete': bool(incomplete_reasons), 'incomplete_reasons': incomplete_reasons, 'interpretation': interpretation, 'context_count': len(contract['contexts']),
                         'plan_bound': runtime.get('max_plan_steps', 20),
                         'universal_prompt_correctness_certified': False},
            'summary': {level: sum(d['severity'] == level for d in diagnostics) for level in ('error', 'warning', 'info')}}
