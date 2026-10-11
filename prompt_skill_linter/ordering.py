"""Declarative temporal ordering constraints for workflow actions.

Checks static ordering properties via product construction: BFS over
(workflow_state, monitor_state) where each rule has a finite monitor.

Monitor types:
- before: tracks whether first action has been seen (safety)
- mutual_exclusion: tracks which actions have been seen (safety)
- at_most_once: tracks count capped at 2 (safety)
- exactly_once: tracks count, checked at goal states (liveness)

Deduplication is on the full product state, which is sound even when
different action sequences reach the same workflow state. Parent pointers
enable shortest counterexample reconstruction with deterministic ordering.

This is exact within configured bounds and stays small even with cycles.
"""
from collections import deque


# Monitor classes with proper hashing for product-state deduplication

class BeforeMonitor:
    """Monitor for 'before A B' rule: tracks if A has been seen."""
    
    def __init__(self, first_action, seen_first=False):
        self.first_action = first_action
        self.seen_first = seen_first
    
    def step(self, action):
        """Return new monitor state after taking action."""
        return BeforeMonitor(
            self.first_action,
            self.seen_first or (action == self.first_action)
        )
    
    def violates(self, action, second_action):
        """Check if taking action would violate the rule."""
        return action == second_action and not self.seen_first
    
    def __hash__(self):
        return hash(self.seen_first)
    
    def __eq__(self, other):
        return isinstance(other, BeforeMonitor) and self.seen_first == other.seen_first


class MutualExclusionMonitor:
    """Monitor for mutual_exclusion: tracks which of two actions seen."""
    
    def __init__(self, action_a, action_b, seen_a=False, seen_b=False):
        self.action_a = action_a
        self.action_b = action_b
        self.seen_a = seen_a
        self.seen_b = seen_b
    
    def step(self, action):
        """Return new monitor state after taking action."""
        return MutualExclusionMonitor(
            self.action_a, self.action_b,
            self.seen_a or (action == self.action_a),
            self.seen_b or (action == self.action_b)
        )
    
    def violates(self, action):
        """Check if taking action would violate the rule."""
        if action == self.action_a and self.seen_b:
            return True
        if action == self.action_b and self.seen_a:
            return True
        return False
    
    def __hash__(self):
        return hash((self.seen_a, self.seen_b))
    
    def __eq__(self, other):
        return (isinstance(other, MutualExclusionMonitor) and
                self.seen_a == other.seen_a and self.seen_b == other.seen_b)


class CountMonitor:
    """Monitor for at_most_once/exactly_once: tracks count capped at 2."""
    
    def __init__(self, action, count=0):
        self.action = action
        self.count = count
    
    def step(self, action):
        """Return new monitor state after taking action."""
        new_count = self.count
        if action == self.action:
            new_count = min(self.count + 1, 2)  # Cap at 2 (sufficient to detect violations)
        return CountMonitor(self.action, new_count)
    
    def violates_at_most_once(self, action):
        """Check if taking action would violate at_most_once (safety)."""
        return action == self.action and self.count >= 1
    
    def violates_exactly_once_at_goal(self):
        """Check if current count violates exactly_once at a goal state."""
        return self.count != 1
    
    def __hash__(self):
        return hash(self.count)
    
    def __eq__(self, other):
        return isinstance(other, CountMonitor) and self.count == other.count


def validate_ordering_rules(workflow, sources, root):
    """Validate ordering rule declarations before analysis."""
    from pathlib import Path
    
    rules = workflow.get('ordering_rules', [])
    if len(rules) > 32:
        raise ValueError('At most 32 ordering rules per workflow are supported.')
    
    rule_ids = [r['id'] for r in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError('Ordering rule IDs must be unique within a workflow.')
    
    action_ids = {a['id'] for a in workflow['actions']}
    action_source_lines = {}
    
    for rule in rules:
        if not isinstance(rule.get('id'), str) or not rule['id']:
            raise ValueError('Ordering rule id must be a nonempty string.')
        
        kind = rule.get('kind')
        if kind not in ('before', 'mutual_exclusion', 'exactly_once', 'at_most_once'):
            raise ValueError(f"{rule['id']}: kind must be before, mutual_exclusion, exactly_once, or at_most_once")
        
        actions = rule.get('actions', [])
        if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            raise ValueError(f"{rule['id']}: actions must be an array of strings")
        
        if kind == 'before':
            if len(actions) != 2:
                raise ValueError(f"{rule['id']}: before requires exactly 2 actions [first, second]")
        elif kind == 'mutual_exclusion':
            if len(actions) != 2:
                raise ValueError(f"{rule['id']}: mutual_exclusion requires exactly 2 actions")
        elif kind in ('exactly_once', 'at_most_once'):
            if len(actions) != 1:
                raise ValueError(f"{rule['id']}: {kind} requires exactly 1 action")
        
        if len(set(actions)) != len(actions):
            raise ValueError(f"{rule['id']}: actions must be unique")
        
        unknown = set(actions) - action_ids
        if unknown:
            raise ValueError(f"{rule['id']}: references unknown actions: {', '.join(sorted(unknown))}")
        
        scope = rule.get('scope')
        if not isinstance(scope, dict) or set(scope.keys()) != {'entity', 'temporal'}:
            raise ValueError(f"{rule['id']}: scope must have entity and temporal")
        
        if not all(isinstance(scope[k], str) for k in ('entity', 'temporal')):
            raise ValueError(f"{rule['id']}: scope entity and temporal must be strings")
        
        src = rule.get('source')
        if not isinstance(src, dict):
            raise ValueError(f"{rule['id']}: source must be an object")
        
        if src.get('source_id') not in sources:
            raise ValueError(f"{rule['id']}: unknown source_id")
        
        path = (Path(root) / sources[src['source_id']]['path']).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise ValueError(f"{rule['id']}: source path must stay within contract directory")
        
        if path not in action_source_lines:
            try:
                if path.stat().st_size > 1_500_000:
                    raise ValueError(f"{rule['id']}: source file exceeds 1.5 MB limit")
                action_source_lines[path] = path.read_text(encoding='utf-8').splitlines()
            except (OSError, UnicodeError) as exc:
                raise ValueError(f"{rule['id']}: cannot read source: {exc}") from exc
        
        lines = action_source_lines[path]
        start, end = src.get('start_line'), src.get('end_line')
        if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= len(lines):
            raise ValueError(f"{rule['id']}: invalid source line range")
        
        if src.get('quote') != '\n'.join(lines[start - 1:end]):
            raise ValueError(f"{rule['id']}: source quote does not match exact lines")
        
        assumptions = rule.get('assumptions', [])
        if not isinstance(assumptions, list) or not all(isinstance(a, str) for a in assumptions):
            raise ValueError(f"{rule['id']}: assumptions must be an array of strings")
        
        if len(assumptions) > 32:
            raise ValueError(f"{rule['id']}: at most 32 assumptions per rule")


def check_ordering_rules(workflow, explored_result, workflow_id, context):
    """Check ordering rules via product construction over (workflow_state, monitor_state).
    
    For each rule, BFS explores the product space with deduplication on the full
    product state. This is sound: different action histories reaching the same
    workflow state may have different monitor states.
    
    Safety properties (before, mutual_exclusion, at_most_once) report violations
    immediately. Liveness properties (exactly_once) are checked at goal states.
    
    Any bound that truncates exploration produces ORDERING_CHECK_INCOMPLETE unless
    a violation was already found.
    """
    rules = workflow.get('ordering_rules', [])
    if not rules:
        return [], []
    
    diagnostics = []
    checks = []
    
    # Build workflow graph
    graph = explored_result.get('graph', {})
    states_list = graph.get('states', [])
    edges = graph.get('edges', [])
    
    if not states_list:
        # Empty workflow - all rules trivially satisfied but warn
        for rule in rules:
            checks.append({
                'ordering_rule_id': rule['id'],
                'workflow': workflow_id,
                'context_id': context['id'],
                'status': 'warning',
                'kind': rule['kind'],
                'reason': 'Empty workflow',
                'search_exhaustive': True,
                'source': rule['source'],
                'assumptions': rule['assumptions']
            })
        return diagnostics, checks
    
    # Find initial state (not hardcoded to 0!)
    initial_state_id = None
    for state in states_list:
        if state.get('depth', 0) == 0:
            initial_state_id = state['id']
            break
    if initial_state_id is None:
        initial_state_id = states_list[0]['id']  # Fallback to first state
    
    # Build state info map
    states = {s['id']: s for s in states_list}
    goal = set(workflow.get('goal', []))
    
    # Build adjacency list with deterministic edge ordering (stable counterexamples)
    adj = {}
    for edge in sorted(edges, key=lambda e: (e['from'], e['action'], e['to'])):
        adj.setdefault(edge['from'], []).append((edge['to'], edge['action']))
    
    # Check each rule with product construction
    for rule in rules:
        result = _check_rule_with_product(
            rule, adj, states, initial_state_id, goal, workflow, explored_result
        )
        result.update({
            'ordering_rule_id': rule['id'],
            'workflow': workflow_id,
            'context_id': context['id'],
            'source': rule['source'],
            'assumptions': rule['assumptions']
        })
        checks.append(result)
        
        # Create diagnostics for violations, warnings, or incomplete
        if result['status'] in ('violated', 'warning', 'incomplete'):
            code = _get_diagnostic_code(result)
            severity = 'error' if result['status'] == 'violated' else 'warning'
            
            diagnostics.append({
                'code': code,
                'class': 'model_based',
                'severity': severity,
                'source_spans': [rule['source']],
                'interpreted_rules': [{
                    'id': rule['id'],
                    'ordering_rule': rule,
                    'source': rule['source'],
                    'scope': rule['scope']
                }],
                'resolved_priorities': {},
                'responsible_rule_set': [rule['id']],
                'triggering_context': context,
                'witness': result,
                'assumptions': rule['assumptions'] + [
                    'Ordering rule checked via product construction (workflow_state, monitor_state).',
                    'Within configured bounds, this check is deterministic and exact.',
                    'Counterexamples are shortest violating prefixes from the reviewed model.',
                    'Truncated search reports incomplete, never satisfied.'
                ],
                'repairs': [],
                'regression_case': {
                    'context': context,
                    'expected_code': code,
                    'ordering_rule_id': rule['id'],
                    'counterexample': result.get('counterexample')
                },
                'provenance_limitations': [
                    'Source quote establishes provenance; semantic fidelity remains a review assumption.'
                ]
            })
    
    # Simple conflict detection: pairwise before cycles
    # Only warn when BOTH rules cannot be satisfied (both violated or both incomplete)
    conflicts = _detect_conflicts(rules, checks)
    for conflict in conflicts:
        diagnostics.append({
            'code': 'ORDERING_RULES_CONFLICT',
            'class': 'model_based',
            'severity': 'warning',
            'source_spans': [r['source'] for r in conflict['rules']],
            'interpreted_rules': [{'id': r['id'], 'ordering_rule': r, 'source': r['source']} 
                                 for r in conflict['rules']],
            'resolved_priorities': {},
            'responsible_rule_set': [r['id'] for r in conflict['rules']],
            'triggering_context': context,
            'witness': conflict,
            'assumptions': ['Conflicting ordering rules detected via pairwise analysis.'],
            'repairs': [],
            'regression_case': {'context': context, 'expected_code': 'ORDERING_RULES_CONFLICT'},
            'provenance_limitations': []
        })
    
    return diagnostics, checks


def _check_rule_with_product(rule, adj, states, initial_state_id, goal, workflow, explored_result):
    """Check one rule via product construction BFS."""
    kind = rule['kind']
    actions = rule['actions']
    
    # Create initial monitor
    if kind == 'before':
        monitor = BeforeMonitor(actions[0])
        return _check_safety_property(rule, monitor, adj, states, initial_state_id, 
                                      explored_result, _before_checker)
    elif kind == 'mutual_exclusion':
        monitor = MutualExclusionMonitor(actions[0], actions[1])
        return _check_safety_property(rule, monitor, adj, states, initial_state_id,
                                      explored_result, _mutual_exclusion_checker)
    elif kind == 'at_most_once':
        monitor = CountMonitor(actions[0])
        return _check_safety_property(rule, monitor, adj, states, initial_state_id,
                                      explored_result, _at_most_once_checker)
    elif kind == 'exactly_once':
        monitor = CountMonitor(actions[0])
        return _check_exactly_once(rule, monitor, adj, states, initial_state_id, goal,
                                   workflow, explored_result)


def _check_safety_property(rule, initial_monitor, adj, states, initial_state_id, 
                           explored_result, violation_checker):
    """Check a safety property: report shortest violating prefix immediately."""
    max_steps = explored_result.get('bounds', {}).get('max_steps', 20)
    max_states = explored_result.get('bounds', {}).get('max_states', 2000)
    
    # Product BFS: (wf_state_id, monitor, path, depth)
    queue = deque([(initial_state_id, initial_monitor, [], 0)])
    seen = {(initial_state_id, initial_monitor)}
    visited_product_states = 1
    hit_depth_bound = False
    hit_state_bound = False
    all_actions_seen = set()  # Track all actions encountered
    
    while queue:
        wf_state, monitor, path, depth = queue.popleft()
        
        # Explore successors
        for next_wf, action in adj.get(wf_state, []):
            all_actions_seen.add(action)
            
            # Check for violation BEFORE stepping monitor
            if violation_checker(monitor, action, rule):
                counterexample = path + [action]
                result = {
                    'status': 'violated',
                    'kind': rule['kind'],
                    'counterexample': counterexample,
                    'reason': f"Shortest violating prefix found",
                    'search_exhaustive': explored_result.get('search_exhaustive', False)
                }
                # Add observed_count for at_most_once violations
                if rule['kind'] == 'at_most_once':
                    result['observed_count'] = counterexample.count(rule['actions'][0])
                return result
            
            # Step monitor
            new_monitor = monitor.step(action)
            new_path = path + [action]
            new_depth = depth + 1
            
            # Dedupe on FULL product state (using monitor object directly, not hash)
            prod_state = (next_wf, new_monitor)
            if prod_state in seen:
                continue  # Already explored this product state
            
            # Check bounds only for NEW product states
            if new_depth >= max_steps:
                hit_depth_bound = True
                continue
            
            if visited_product_states >= max_states:
                hit_state_bound = True
                continue
            
            seen.add(prod_state)
            visited_product_states += 1
            queue.append((next_wf, new_monitor, new_path, new_depth))
    
    # No violation found - check completeness
    if hit_depth_bound or hit_state_bound or not explored_result.get('search_exhaustive', False):
        return {
            'status': 'incomplete',
            'kind': rule['kind'],
            'reason': 'Search truncated by bounds; cannot prove satisfaction',
            'search_exhaustive': False,
            'cutoff_reasons': [
                r for r, hit in [
                    ('max_steps', hit_depth_bound),
                    ('max_states', hit_state_bound),
                    ('workflow_search_incomplete', not explored_result.get('search_exhaustive', False))
                ] if hit
            ]
        }
    
    # Check for unreachable actions (warning)
    rule_actions = set(rule['actions'])
    unreachable = rule_actions - all_actions_seen
    if unreachable:
        # Different messages for different rule kinds
        if rule['kind'] == 'before' and rule['actions'][1] in unreachable:
            if rule['actions'][0] in unreachable:
                reason = f"Both actions are unreachable; rule never applies"
            else:
                reason = f"Second action '{rule['actions'][1]}' is unreachable; rule vacuously satisfied"
        elif rule['kind'] == 'mutual_exclusion' and len(unreachable) == 2:
            reason = "Both actions are unreachable; rule never applies"
        elif unreachable == rule_actions:
            reason = f"Actions {rule_actions} are unreachable; rule never applies"
        else:
            reason = f"Some actions are unreachable: {unreachable}"
        
        return {
            'status': 'warning',
            'kind': rule['kind'],
            'reason': reason,
            'search_exhaustive': True
        }
    
    return {
        'status': 'satisfied',
        'kind': rule['kind'],
        'search_exhaustive': True
    }


def _before_checker(monitor, action, rule):
    """Check if action violates before rule with current monitor."""
    return monitor.violates(action, rule['actions'][1])


def _mutual_exclusion_checker(monitor, action, rule):
    """Check if action violates mutual_exclusion with current monitor."""
    return monitor.violates(action)


def _at_most_once_checker(monitor, action, rule):
    """Check if action violates at_most_once with current monitor."""
    return monitor.violates_at_most_once(action)


def _check_exactly_once(rule, initial_monitor, adj, states, initial_state_id, goal,
                       workflow, explored_result):
    """Check exactly_once: must occur exactly once on every complete path.
    
    This is a liveness property checked at goal states. Paths cut at max_steps
    before reaching a goal make the result incomplete.
    """
    max_steps = explored_result.get('bounds', {}).get('max_steps', 20)
    max_states = explored_result.get('bounds', {}).get('max_states', 2000)
    
    queue = deque([(initial_state_id, initial_monitor, [], 0)])
    seen = {(initial_state_id, initial_monitor)}
    visited_product_states = 1
    hit_depth_bound = False
    hit_state_bound = False
    found_violation = False
    violation_path = None
    found_complete_path = False
    incomplete_paths = False
    all_actions_seen = set()
    
    while queue:
        wf_state, monitor, path, depth = queue.popleft()
        
        # Get current workflow state facts
        state_facts = set(states[wf_state].get('facts', []))
        is_goal = goal <= state_facts
        
        if is_goal:
            found_complete_path = True
            # Check count at goal
            if monitor.violates_exactly_once_at_goal():
                found_violation = True
                violation_path = path
                break  # Found violation, stop search
        
        # Explore successors
        has_successors = False
        for next_wf, action in adj.get(wf_state, []):
            has_successors = True
            all_actions_seen.add(action)
            new_monitor = monitor.step(action)
            new_path = path + [action]
            new_depth = depth + 1
            
            prod_state = (next_wf, new_monitor)
            if prod_state in seen:
                continue  # Already explored
            
            # Check bounds only for NEW product states
            if new_depth >= max_steps:
                hit_depth_bound = True
                # This path was cut before reaching terminal state
                if not is_goal:
                    incomplete_paths = True
                continue
            
            if visited_product_states >= max_states:
                hit_state_bound = True
                incomplete_paths = True
                continue
            
            seen.add(prod_state)
            visited_product_states += 1
            queue.append((next_wf, new_monitor, new_path, new_depth))
    
    if found_violation:
        count = violation_path.count(rule['actions'][0])
        return {
            'status': 'violated',
            'kind': 'exactly_once',
            'counterexample': violation_path,
            'reason': f"Action occurs {count} times (expected exactly 1)",
            'observed_count': count,
            'expected_count': 1,
            'search_exhaustive': explored_result.get('search_exhaustive', False)
        }
    
    # Check if search was complete
    if incomplete_paths or hit_depth_bound or hit_state_bound or not explored_result.get('search_exhaustive', False):
        return {
            'status': 'incomplete',
            'kind': 'exactly_once',
            'reason': 'Paths cut before goal; cannot prove exactly_once',
            'search_exhaustive': False,
            'cutoff_reasons': [
                r for r, hit in [
                    ('max_steps_before_goal', incomplete_paths or hit_depth_bound),
                    ('max_states', hit_state_bound),
                    ('workflow_search_incomplete', not explored_result.get('search_exhaustive', False))
                ] if hit
            ]
        }
    
    if not found_complete_path:
        return {
            'status': 'warning',
            'kind': 'exactly_once',
            'reason': 'No complete paths found; exactly_once cannot apply',
            'search_exhaustive': True
        }
    
    # Check unreachable
    if rule['actions'][0] not in all_actions_seen:
        return {
            'status': 'warning',
            'kind': 'exactly_once',
            'reason': f"Action {rule['actions'][0]} is unreachable",
            'search_exhaustive': True
        }
    
    return {
        'status': 'satisfied',
        'kind': 'exactly_once',
        'search_exhaustive': True
    }


def _detect_conflicts(rules, checks):
    """Detect pairwise conflicts in before rules.
    
    Simple heuristic: A before B and B before A is a cycle.
    Flag when both rules exist (logical conflict), especially when at least one is violated.
    """
    conflicts = []
    before_rules = [(r, c) for r, c in zip(rules, checks) if r['kind'] == 'before']
    
    for i, (rule1, check1) in enumerate(before_rules):
        for rule2, check2 in before_rules[i+1:]:
            # Check for cycle: A before B and B before A
            a1, b1 = rule1['actions']
            a2, b2 = rule2['actions']
            
            if (a1 == b2 and b1 == a2):  # Direct cycle
                # This is a logical conflict - the rules are mutually incompatible
                # At least one must be violated (or both incomplete)
                if check1['status'] in ('violated', 'incomplete') or check2['status'] in ('violated', 'incomplete'):
                    conflicts.append({
                        'rules': [rule1, rule2],
                        'reason': f'Cycle detected: {a1} before {b1} and {b1} before {a1} are mutually incompatible',
                        'both_checked': True
                    })
    
    return conflicts


def _get_diagnostic_code(result):
    """Map result status and kind to diagnostic code."""
    if result['status'] == 'violated':
        return {
            'before': 'ORDERING_BEFORE_VIOLATED',
            'mutual_exclusion': 'ORDERING_MUTUAL_EXCLUSION_VIOLATED',
            'exactly_once': 'ORDERING_EXACTLY_ONCE_VIOLATED',
            'at_most_once': 'ORDERING_AT_MOST_ONCE_VIOLATED'
        }.get(result['kind'], 'ORDERING_RULE_VIOLATION')
    elif result['status'] == 'incomplete':
        return 'ORDERING_CHECK_INCOMPLETE'
    elif result['status'] == 'warning':
        return 'ORDERING_RULE_UNREACHABLE_ACTIONS'
    return 'ORDERING_RULE_UNKNOWN'


# Helper for backwards compatibility with tests
def _get_final_state(path, workflow):
    """Compute final state after following a path (for test compatibility)."""
    state = set(workflow.get('initial', []))
    action_map = {a['id']: a for a in workflow['actions']}
    
    for action_id in path:
        action = action_map.get(action_id)
        if action:
            state = (state - set(action.get('removes', []))) | set(action.get('adds', []))
    
    return state
