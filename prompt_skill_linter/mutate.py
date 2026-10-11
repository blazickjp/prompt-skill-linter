"""Contract mutation testing: test the linter by mutating contracts.

Generates small semantic mutations of reviewed contracts and measures
whether the linter detects each change (kills the mutant) or misses it
(mutant survives). High mutation scores indicate strong contract coverage
and sensitive linting rules.

Mutation is in-memory only; source files are never modified.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Mutant:
    """A single mutated contract with provenance."""
    
    id: str
    operator: str
    description: str
    contract: dict
    pointer: str
    
    def __hash__(self):
        return hash(self.id)


@dataclass(frozen=True)
class MutationResult:
    """Classification of one mutant."""
    
    mutant: Mutant
    status: str  # KILLED, SURVIVED, EQUIVALENT_SUSPECTED, INVALID, CRASHED
    original_diagnostics: frozenset
    mutant_diagnostics: frozenset | None
    error: str | None = None
    
    def hint(self) -> str:
        """One-line hint for survived mutants."""
        if self.status == 'SURVIVED':
            return f'Mutant {self.mutant.id} ({self.mutant.operator}) survived: {self.mutant.description} at {self.mutant.pointer} did not change diagnostics'
        return ''


def normalize_diagnostic(d: dict) -> tuple:
    """Normalize a diagnostic to a comparable key.
    
    Includes witness semantic content (counterexample paths, violation status)
    while excluding volatile metadata (line numbers, timestamps).
    """
    witness = d.get('witness', {})
    
    # Extract semantic witness content
    witness_content = []
    
    # For ordering violations: include counterexample
    if 'counterexample' in witness:
        witness_content.append(('counterexample', tuple(witness['counterexample'])))
    
    # For trace violations: include violating path
    if 'violating_path' in witness:
        witness_content.append(('violating_path', tuple(witness['violating_path'])))
    
    # For workflow checks: include blocked actions, status
    if 'blocked_actions' in witness:
        witness_content.append(('blocked_actions', tuple(sorted(witness['blocked_actions']))))
    
    if 'status' in witness:
        witness_content.append(('status', witness['status']))
    
    # For ordering: include violation kind
    if 'violated' in witness:
        witness_content.append(('violated', witness['violated']))
    
    # For resource checks: include bounds
    if 'lower_bound_calls' in witness:
        witness_content.append(('lower_bound_calls', witness['lower_bound_calls']))
    
    # For trigger coverage
    if 'trigger_coverage' in witness:
        cov = witness['trigger_coverage']
        witness_content.append(('trigger_status', cov.get('status')))
        if 'trigger_actions' in cov:
            witness_content.append(('trigger_actions', tuple(sorted(cov['trigger_actions']))))
    
    return (
        d['code'],
        tuple(sorted(d['responsible_rule_set'])),
        d['severity'],
        tuple(sorted(witness_content))
    )


def compare_diagnostics(original: list[dict], mutant: list[dict]) -> tuple[frozenset, frozenset]:
    """Compare diagnostic sets, returning normalized sets."""
    original_set = frozenset(normalize_diagnostic(d) for d in original)
    mutant_set = frozenset(normalize_diagnostic(d) for d in mutant)
    return original_set, mutant_set


# Mutation operators for rules

def flip_requirement_prohibition(contract: dict, rule_index: int) -> list[Mutant]:
    """Flip requirement <-> prohibition."""
    rule = contract['rules'][rule_index]
    if rule['kind'] not in ('requirement', 'prohibition'):
        return []
    
    mutated = copy.deepcopy(contract)
    new_kind = 'prohibition' if rule['kind'] == 'requirement' else 'requirement'
    mutated['rules'][rule_index]['kind'] = new_kind
    
    # Remove incompatible fields
    if new_kind == 'prohibition':
        mutated['rules'][rule_index].pop('allow_action', None)
    else:
        mutated['rules'][rule_index].pop('forbid_action', None)
    
    return [Mutant(
        id=f"rule_{rule_index}_flip_kind",
        operator='flip_kind',
        description=f"Flip rule {rule['id']} from {rule['kind']} to {new_kind}",
        contract=mutated,
        pointer=f"/rules/{rule_index}/kind"
    )]


def swap_priority(contract: dict, rule_index_a: int, rule_index_b: int) -> list[Mutant]:
    """Swap priorities of two rules."""
    if rule_index_a >= len(contract['rules']) or rule_index_b >= len(contract['rules']):
        return []
    
    rule_a = contract['rules'][rule_index_a]
    rule_b = contract['rules'][rule_index_b]
    
    if rule_a['priority'] == rule_b['priority']:
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['rules'][rule_index_a]['priority'] = rule_b['priority']
    mutated['rules'][rule_index_b]['priority'] = rule_a['priority']
    
    return [Mutant(
        id=f"rule_{rule_index_a}_{rule_index_b}_swap_priority",
        operator='swap_priority',
        description=f"Swap priorities of {rule_a['id']} and {rule_b['id']}",
        contract=mutated,
        pointer=f"/rules/{rule_index_a}/priority,/rules/{rule_index_b}/priority"
    )]


def equalize_priority(contract: dict, rule_index_a: int, rule_index_b: int) -> list[Mutant]:
    """Equalize priorities of two rules."""
    if rule_index_a >= len(contract['rules']) or rule_index_b >= len(contract['rules']):
        return []
    
    rule_a = contract['rules'][rule_index_a]
    rule_b = contract['rules'][rule_index_b]
    
    if rule_a['priority'] == rule_b['priority']:
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['rules'][rule_index_a]['priority'] = rule_b['priority']
    
    return [Mutant(
        id=f"rule_{rule_index_a}_{rule_index_b}_equalize_priority",
        operator='equalize_priority',
        description=f"Set {rule_a['id']} priority to match {rule_b['id']}",
        contract=mutated,
        pointer=f"/rules/{rule_index_a}/priority"
    )]


def drop_exception(contract: dict, rule_index: int, exception_index: int) -> list[Mutant]:
    """Remove an exception from a rule."""
    rule = contract['rules'][rule_index]
    if not rule.get('exceptions') or exception_index >= len(rule['exceptions']):
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['rules'][rule_index]['exceptions'].pop(exception_index)
    
    return [Mutant(
        id=f"rule_{rule_index}_drop_exception_{exception_index}",
        operator='drop_exception',
        description=f"Remove exception {exception_index} from rule {rule['id']}",
        contract=mutated,
        pointer=f"/rules/{rule_index}/exceptions/{exception_index}"
    )]


def add_trivial_exception(contract: dict, rule_index: int) -> list[Mutant]:
    """Add an exception that never matches."""
    rule = contract['rules'][rule_index]
    
    mutated = copy.deepcopy(contract)
    if 'exceptions' not in mutated['rules'][rule_index]:
        mutated['rules'][rule_index]['exceptions'] = []
    
    mutated['rules'][rule_index]['exceptions'].append({'__never_matches__': True})
    
    return [Mutant(
        id=f"rule_{rule_index}_add_trivial_exception",
        operator='add_trivial_exception',
        description=f"Add trivial exception to rule {rule['id']}",
        contract=mutated,
        pointer=f"/rules/{rule_index}/exceptions/-"
    )]


def negate_effect_value(contract: dict, rule_index: int) -> list[Mutant]:
    """Negate the Boolean value in an effect."""
    rule = contract['rules'][rule_index]
    if 'effect' not in rule:
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['rules'][rule_index]['effect']['value'] = not rule['effect']['value']
    
    return [Mutant(
        id=f"rule_{rule_index}_negate_effect",
        operator='negate_effect',
        description=f"Negate effect value in rule {rule['id']}",
        contract=mutated,
        pointer=f"/rules/{rule_index}/effect/value"
    )]


def delete_rule(contract: dict, rule_index: int) -> list[Mutant]:
    """Delete a rule entirely."""
    rule = contract['rules'][rule_index]
    
    mutated = copy.deepcopy(contract)
    mutated['rules'].pop(rule_index)
    
    return [Mutant(
        id=f"rule_{rule_index}_delete",
        operator='delete_rule',
        description=f"Delete rule {rule['id']}",
        contract=mutated,
        pointer=f"/rules/{rule_index}"
    )]


# Mutation operators for workflows

def drop_precondition(contract: dict, workflow_index: int, action_index: int, precond_index: int) -> list[Mutant]:
    """Remove a precondition from an action."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if action_index >= len(workflow.get('actions', [])):
        return []
    
    action = workflow['actions'][action_index]
    if not action.get('requires') or precond_index >= len(action['requires']):
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['workflows'][workflow_index]['actions'][action_index]['requires'].pop(precond_index)
    
    return [Mutant(
        id=f"workflow_{workflow_index}_action_{action_index}_drop_precond_{precond_index}",
        operator='drop_precondition',
        description=f"Remove precondition {precond_index} from action {action['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/actions/{action_index}/requires/{precond_index}"
    )]


def drop_effect(contract: dict, workflow_index: int, action_index: int, effect_kind: str, effect_index: int) -> list[Mutant]:
    """Remove an add or remove effect from an action."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if action_index >= len(workflow.get('actions', [])):
        return []
    
    action = workflow['actions'][action_index]
    if effect_kind not in ('adds', 'removes') or not action.get(effect_kind) or effect_index >= len(action[effect_kind]):
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['workflows'][workflow_index]['actions'][action_index][effect_kind].pop(effect_index)
    
    return [Mutant(
        id=f"workflow_{workflow_index}_action_{action_index}_drop_{effect_kind}_{effect_index}",
        operator='drop_effect',
        description=f"Remove {effect_kind}[{effect_index}] from action {action['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/actions/{action_index}/{effect_kind}/{effect_index}"
    )]


def delete_action(contract: dict, workflow_index: int, action_index: int) -> list[Mutant]:
    """Delete an action from a workflow."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if action_index >= len(workflow.get('actions', [])):
        return []
    
    action = workflow['actions'][action_index]
    mutated = copy.deepcopy(contract)
    mutated['workflows'][workflow_index]['actions'].pop(action_index)
    
    return [Mutant(
        id=f"workflow_{workflow_index}_action_{action_index}_delete",
        operator='delete_action',
        description=f"Delete action {action['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/actions/{action_index}"
    )]


def remove_goal_literal(contract: dict, workflow_index: int, goal_index: int) -> list[Mutant]:
    """Remove a literal from a workflow goal."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if not workflow.get('goal') or goal_index >= len(workflow['goal']):
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['workflows'][workflow_index]['goal'].pop(goal_index)
    
    return [Mutant(
        id=f"workflow_{workflow_index}_remove_goal_{goal_index}",
        operator='remove_goal_literal',
        description=f"Remove goal literal {goal_index} from workflow {workflow['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/goal/{goal_index}"
    )]


# Mutation operators for ordering rules

def swap_before_actions(contract: dict, workflow_index: int, rule_index: int) -> list[Mutant]:
    """Swap the first and second actions in a 'before' rule."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if not workflow.get('ordering_rules') or rule_index >= len(workflow['ordering_rules']):
        return []
    
    rule = workflow['ordering_rules'][rule_index]
    if rule['kind'] != 'before' or len(rule.get('actions', [])) != 2:
        return []
    
    mutated = copy.deepcopy(contract)
    actions = mutated['workflows'][workflow_index]['ordering_rules'][rule_index]['actions']
    actions[0], actions[1] = actions[1], actions[0]
    
    return [Mutant(
        id=f"workflow_{workflow_index}_ordering_{rule_index}_swap_before",
        operator='swap_before_actions',
        description=f"Swap first/second in before rule {rule['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/ordering_rules/{rule_index}/actions"
    )]


def change_exactly_once_to_at_most_once(contract: dict, workflow_index: int, rule_index: int) -> list[Mutant]:
    """Change exactly_once to at_most_once."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if not workflow.get('ordering_rules') or rule_index >= len(workflow['ordering_rules']):
        return []
    
    rule = workflow['ordering_rules'][rule_index]
    if rule['kind'] != 'exactly_once':
        return []
    
    mutated = copy.deepcopy(contract)
    mutated['workflows'][workflow_index]['ordering_rules'][rule_index]['kind'] = 'at_most_once'
    
    return [Mutant(
        id=f"workflow_{workflow_index}_ordering_{rule_index}_exactly_to_at_most",
        operator='change_exactly_to_at_most',
        description=f"Change exactly_once to at_most_once for rule {rule['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/ordering_rules/{rule_index}/kind"
    )]


def drop_ordering_rule(contract: dict, workflow_index: int, rule_index: int) -> list[Mutant]:
    """Delete an ordering rule."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if not workflow.get('ordering_rules') or rule_index >= len(workflow['ordering_rules']):
        return []
    
    rule = workflow['ordering_rules'][rule_index]
    mutated = copy.deepcopy(contract)
    mutated['workflows'][workflow_index]['ordering_rules'].pop(rule_index)
    
    return [Mutant(
        id=f"workflow_{workflow_index}_ordering_{rule_index}_drop",
        operator='drop_ordering_rule',
        description=f"Drop ordering rule {rule['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/ordering_rules/{rule_index}"
    )]


def swap_mutual_exclusion_actions(contract: dict, workflow_index: int, rule_index: int) -> list[Mutant]:
    """Swap actions in a mutual_exclusion rule (should be equivalent)."""
    if 'workflows' not in contract or workflow_index >= len(contract['workflows']):
        return []
    
    workflow = contract['workflows'][workflow_index]
    if not workflow.get('ordering_rules') or rule_index >= len(workflow['ordering_rules']):
        return []
    
    rule = workflow['ordering_rules'][rule_index]
    if rule['kind'] != 'mutual_exclusion' or len(rule.get('actions', [])) != 2:
        return []
    
    mutated = copy.deepcopy(contract)
    actions = mutated['workflows'][workflow_index]['ordering_rules'][rule_index]['actions']
    actions[0], actions[1] = actions[1], actions[0]
    
    return [Mutant(
        id=f"workflow_{workflow_index}_ordering_{rule_index}_swap_mutex",
        operator='swap_mutual_exclusion',
        description=f"Swap actions in mutual_exclusion rule {rule['id']}",
        contract=mutated,
        pointer=f"/workflows/{workflow_index}/ordering_rules/{rule_index}/actions"
    )]


# Mutation operators for tool manifest

def make_required_arg_optional(manifest: dict, tool_name: str, arg_index: int) -> list[Mutant]:
    """Make a required argument optional."""
    if tool_name not in manifest.get('tools', {}):
        return []
    
    tool = manifest['tools'][tool_name]
    if not tool.get('required') or arg_index >= len(tool['required']):
        return []
    
    mutated = copy.deepcopy(manifest)
    arg_name = mutated['tools'][tool_name]['required'].pop(arg_index)
    
    return [Mutant(
        id=f"tool_{tool_name}_make_optional_{arg_index}",
        operator='make_required_optional',
        description=f"Make argument '{arg_name}' optional in tool {tool_name}",
        contract=mutated,
        pointer=f"/tools/{tool_name}/required/{arg_index}"
    )]


def remove_tool_argument(manifest: dict, tool_name: str, arg_index: int) -> list[Mutant]:
    """Remove an argument from a tool."""
    if tool_name not in manifest.get('tools', {}):
        return []
    
    tool = manifest['tools'][tool_name]
    if not tool.get('arguments') or arg_index >= len(tool['arguments']):
        return []
    
    mutated = copy.deepcopy(manifest)
    arg_name = mutated['tools'][tool_name]['arguments'][arg_index]
    mutated['tools'][tool_name]['arguments'].pop(arg_index)
    
    # Also remove from required if present
    if 'required' in mutated['tools'][tool_name] and arg_name in mutated['tools'][tool_name]['required']:
        mutated['tools'][tool_name]['required'].remove(arg_name)
    
    return [Mutant(
        id=f"tool_{tool_name}_remove_arg_{arg_index}",
        operator='remove_tool_argument',
        description=f"Remove argument {arg_index} from tool {tool_name}",
        contract=mutated,
        pointer=f"/tools/{tool_name}/arguments/{arg_index}"
    )]


# Generator: apply all applicable operators

RULE_OPERATORS = [
    flip_requirement_prohibition,
    negate_effect_value,
    add_trivial_exception,
    delete_rule,
]

RULE_PAIR_OPERATORS = [
    swap_priority,
    equalize_priority,
]


def generate_mutants(contract: dict, manifest: dict, max_mutants: int | None = None, operator_filter: set[str] | None = None) -> list[Mutant]:
    """Generate all applicable mutants for a contract and manifest.
    
    Args:
        contract: The contract to mutate
        manifest: The tool manifest (not mutated - tool schema mutations disabled)
        max_mutants: Maximum number of mutants to generate (None = unlimited)
        operator_filter: Set of operator names to include (None = all)
    
    Returns:
        List of mutants, deterministically ordered by ID
    """
    mutants = []
    
    def should_include(op_name: str) -> bool:
        return operator_filter is None or op_name in operator_filter
    
    # Rule mutations
    for i, rule in enumerate(contract.get('rules', [])):
        for op_func in RULE_OPERATORS:
            if should_include(op_func.__name__):
                mutants.extend(op_func(contract, i))
        
        # Exception mutations
        for j in range(len(rule.get('exceptions', []))):
            if should_include('drop_exception'):
                mutants.extend(drop_exception(contract, i, j))
    
    # Rule pair mutations
    rules = contract.get('rules', [])
    for i in range(len(rules)):
        for j in range(i + 1, len(rules)):
            for op_func in RULE_PAIR_OPERATORS:
                if should_include(op_func.__name__):
                    mutants.extend(op_func(contract, i, j))
    
    # Workflow mutations
    for wf_idx, workflow in enumerate(contract.get('workflows', [])):
        # Action mutations
        for act_idx, action in enumerate(workflow.get('actions', [])):
            if should_include('delete_action'):
                mutants.extend(delete_action(contract, wf_idx, act_idx))
            
            for pre_idx in range(len(action.get('requires', []))):
                if should_include('drop_precondition'):
                    mutants.extend(drop_precondition(contract, wf_idx, act_idx, pre_idx))
            
            for eff_kind in ('adds', 'removes'):
                for eff_idx in range(len(action.get(eff_kind, []))):
                    if should_include('drop_effect'):
                        mutants.extend(drop_effect(contract, wf_idx, act_idx, eff_kind, eff_idx))
        
        # Goal mutations
        for goal_idx in range(len(workflow.get('goal', []))):
            if should_include('remove_goal_literal'):
                mutants.extend(remove_goal_literal(contract, wf_idx, goal_idx))
        
        # Ordering rule mutations
        for ord_idx, ord_rule in enumerate(workflow.get('ordering_rules', [])):
            if should_include('drop_ordering_rule'):
                mutants.extend(drop_ordering_rule(contract, wf_idx, ord_idx))
            if should_include('swap_before_actions'):
                mutants.extend(swap_before_actions(contract, wf_idx, ord_idx))
            if should_include('change_exactly_to_at_most'):
                mutants.extend(change_exactly_once_to_at_most_once(contract, wf_idx, ord_idx))
            if should_include('swap_mutual_exclusion'):
                mutants.extend(swap_mutual_exclusion_actions(contract, wf_idx, ord_idx))
    
    # Tool manifest mutations are disabled - they were producing invalid schemas
    # (mutations removed the 'tools' wrapper, breaking manifest structure)
    
    # Sort by ID for determinism
    mutants.sort(key=lambda m: m.id)
    
    if max_mutants is not None:
        mutants = mutants[:max_mutants]
    
    return mutants


def classify_mutant(mutant: Mutant, original_report: dict, mutant_report: dict | None, error: str | None) -> MutationResult:
    """Classify a mutant as KILLED, SURVIVED, EQUIVALENT_SUSPECTED, INVALID, or CRASHED."""
    if error is not None:
        # Distinguish schema-invalid mutants from real linter bugs
        invalid_patterns = [
            'bulk constraints must be unconditional',
            'references unknown rule',
            'references unknown action',
            'must be unconditional declared requirements',
            'missing version',
        ]
        
        is_invalid = any(pattern in error for pattern in invalid_patterns)
        status = 'INVALID' if is_invalid else 'CRASHED'
        
        return MutationResult(
            mutant=mutant,
            status=status,
            original_diagnostics=frozenset(),
            mutant_diagnostics=None,
            error=error
        )
    
    orig_diags, mut_diags = compare_diagnostics(
        original_report['diagnostics'],
        mutant_report['diagnostics']
    )
    
    if orig_diags == mut_diags:
        # Only mark as EQUIVALENT_SUSPECTED if we have evidence of equivalence
        # For now, only swap_mutual_exclusion is truly equivalent (symmetric)
        # All other surviving mutants are genuine blind spots
        if mutant.operator == 'swap_mutual_exclusion':
            status = 'EQUIVALENT_SUSPECTED'
        else:
            status = 'SURVIVED'
    else:
        status = 'KILLED'
    
    return MutationResult(
        mutant=mutant,
        status=status,
        original_diagnostics=orig_diags,
        mutant_diagnostics=mut_diags
    )


def compute_mutation_score(results: list[MutationResult]) -> dict:
    """Compute mutation testing metrics."""
    total = len(results)
    killed = sum(1 for r in results if r.status == 'KILLED')
    survived = sum(1 for r in results if r.status == 'SURVIVED')
    equivalent = sum(1 for r in results if r.status == 'EQUIVALENT_SUSPECTED')
    invalid = sum(1 for r in results if r.status == 'INVALID')
    crashed = sum(1 for r in results if r.status == 'CRASHED')
    
    # Mutation score = killed / (total - equivalent - invalid)
    # We exclude equivalent mutants (likely symmetric) and invalid mutants (schema violations)
    effective_total = total - equivalent - invalid
    score = killed / effective_total if effective_total > 0 else 0.0
    
    # Operator statistics
    operator_stats = {}
    for result in results:
        op = result.mutant.operator
        if op not in operator_stats:
            operator_stats[op] = {'total': 0, 'killed': 0, 'survived': 0, 'equivalent': 0, 'invalid': 0, 'crashed': 0}
        operator_stats[op]['total'] += 1
        operator_stats[op][result.status.lower()] += 1
    
    return {
        'total_mutants': total,
        'killed': killed,
        'survived': survived,
        'equivalent_suspected': equivalent,
        'invalid': invalid,
        'crashed': crashed,
        'mutation_score': score,
        'operator_stats': operator_stats
    }
