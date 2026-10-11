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
    """Check ordering rules via independent product construction over (facts, monitor_state).
    
    CRITICAL: Does NOT depend on planner's display graph at all. Runs its own BFS over
    the product space (frozenset(facts), monitor_state), computing successors directly
    from workflow actions using the same semantics as the planner (requires/removes/adds).
    
    This makes the planner's display caps (graph_limit) completely irrelevant. The only
    dependencies on the planner are:
    - Initial facts (workflow initial + context facts if any)
    - Forbidden actions (unavailable tools)
    - Search bounds (max_steps, max_states)
    - search_exhaustive flag (whether planner hit its own bounds)
    
    For each rule, BFS explores the product space with deduplication on the full
    product state (facts, monitor). This is sound: different action histories reaching
    the same workflow facts may have different monitor states.
    
    Safety properties (before, mutual_exclusion, at_most_once) report violations
    immediately. Liveness properties (exactly_once) are checked at goal states.
    
    Hitting any bound produces ORDERING_CHECK_INCOMPLETE unless a violation was found.
    """
    rules = workflow.get('ordering_rules', [])
    if not rules:
        return [], []
    
    diagnostics = []
    checks = []
    
    # Get initial facts: workflow initial, same as planner
    # Note: context facts would be merged here if planner does that
    initial_facts = frozenset(workflow.get('initial', []))
    goal_facts = set(workflow.get('goal', []))
    
    # Get forbidden actions (unavailable tools)
    # For now, assume none unless passed explicitly
    # TODO: If engine.py passes forbidden actions, use them here
    forbidden = frozenset()
    
    # Get bounds from planner
    bounds = explored_result.get('bounds', {})
    max_steps = bounds.get('max_steps', 20)
    max_states = bounds.get('max_states', 2000)
    
    # Check if planner hit its bounds (this is the only remaining dependency on planner)
    planner_exhaustive = explored_result.get('search_exhaustive', False)
    
    # Get workflow actions
    actions = workflow.get('actions', [])
    
    # Build action map for quick lookup
    action_map = {a['id']: a for a in actions}
    
    # Helper to compute successor facts (same semantics as planner line 40)
    def compute_successor(facts, action):
        """Compute successor facts using planner's exact semantics."""
        requires = frozenset(action.get('requires', []))
        if not requires <= facts:
            return None  # Prerequisites not met
        if action['id'] in forbidden:
            return None  # Forbidden action
        
        removes = frozenset(action.get('removes', []))
        adds = frozenset(action.get('adds', []))
        return (facts - removes) | adds
    
    # Check each rule with independent product construction
    for rule in rules:
        result = _check_rule_with_independent_product(
            rule, initial_facts, goal_facts, actions, action_map, compute_successor,
            max_steps, max_states, planner_exhaustive, workflow, workflow_id, context
        )
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
                    'Ordering rule checked via independent product construction (facts, monitor_state).',
                    'Uses planner bounds and enabling semantics but not display graph.',
                    'Within configured bounds, this check is deterministic and exact.',
                    'Counterexamples are shortest violating prefixes.',
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


def _check_rule_with_independent_product(rule, initial_facts, goal_facts, actions, action_map,
                                         compute_successor, max_steps, max_states, planner_exhaustive,
                                         workflow, workflow_id, context):
    """Check one rule via independent product BFS over (facts, monitor)."""
    kind = rule['kind']
    rule_actions = rule['actions']
    
    # Create initial monitor
    if kind == 'before':
        monitor = BeforeMonitor(rule_actions[0])
        return _check_safety_property_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, _before_checker, max_steps, max_states, planner_exhaustive
        )
    elif kind == 'mutual_exclusion':
        monitor = MutualExclusionMonitor(rule_actions[0], rule_actions[1])
        return _check_safety_property_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, _mutual_exclusion_checker, max_steps, max_states, planner_exhaustive
        )
    elif kind == 'at_most_once':
        monitor = CountMonitor(rule_actions[0])
        return _check_safety_property_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, _at_most_once_checker, max_steps, max_states, planner_exhaustive
        )
    elif kind == 'exactly_once':
        monitor = CountMonitor(rule_actions[0])
        return _check_exactly_once_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, max_steps, max_states, planner_exhaustive
        )


def _check_safety_property_independent(rule, initial_facts, goal_facts, actions, compute_successor,
                                       initial_monitor, violation_checker, max_steps, max_states,
                                       planner_exhaustive):
    """Check safety property via independent product BFS over (facts, monitor)."""
    # Product BFS: (facts, monitor, path, depth)
    queue = deque([(initial_facts, initial_monitor, [], 0)])
    seen = {(initial_facts, initial_monitor)}
    visited_product_states = 1
    hit_depth_bound = False
    hit_state_bound = False
    all_actions_seen = set()
    
    while queue:
        facts, monitor, path, depth = queue.popleft()
        
        # Check depth bound BEFORE expanding (same as planner)
        if depth >= max_steps:
            hit_depth_bound = True
            continue
        
        # Try each action
        for action in actions:
            action_id = action['id']
            
            # FIRST check if action is enabled
            next_facts = compute_successor(facts, action)
            if next_facts is None:
                continue  # Action not enabled, skip it entirely
            
            all_actions_seen.add(action_id)
            
            # NOW check for violation (only for enabled actions)
            if violation_checker(monitor, action_id, rule):
                counterexample = path + [action_id]
                result = {
                    'ordering_rule_id': rule['id'],
                    'workflow': '',
                    'context_id': '',
                    'status': 'violated',
                    'kind': rule['kind'],
                    'counterexample': counterexample,
                    'reason': 'Shortest violating prefix found',
                    'search_exhaustive': planner_exhaustive,
                    'source': rule['source'],
                    'assumptions': rule['assumptions']
                }
                if rule['kind'] == 'at_most_once':
                    result['observed_count'] = counterexample.count(rule['actions'][0])
                return result
            
            # Step monitor
            new_monitor = monitor.step(action_id)
            new_path = path + [action_id]
            new_depth = depth + 1
            
            # Dedupe on full product state
            prod_state = (next_facts, new_monitor)
            if prod_state in seen:
                continue
            
            # Check state bound
            if visited_product_states >= max_states:
                hit_state_bound = True
                continue
            
            seen.add(prod_state)
            visited_product_states += 1
            queue.append((next_facts, new_monitor, new_path, new_depth))
    
    # No violation found - check completeness
    if hit_depth_bound or hit_state_bound or not planner_exhaustive:
        return {
            'ordering_rule_id': rule['id'],
            'workflow': '',
            'context_id': '',
            'status': 'incomplete',
            'kind': rule['kind'],
            'reason': 'Search truncated by bounds; cannot prove satisfaction',
            'search_exhaustive': False,
            'cutoff_reasons': [
                r for r, hit in [
                    ('max_steps', hit_depth_bound),
                    ('max_states', hit_state_bound),
                    ('workflow_search_incomplete', not planner_exhaustive)
                ] if hit
            ],
            'source': rule['source'],
            'assumptions': rule['assumptions']
        }
    
    # Check for unreachable actions (warning)
    rule_actions_set = set(rule['actions'])
    unreachable = rule_actions_set - all_actions_seen
    if unreachable:
        if rule['kind'] == 'before' and rule['actions'][1] in unreachable:
            if rule['actions'][0] in unreachable:
                reason = 'Both actions are unreachable; rule never applies'
            else:
                reason = f"Second action '{rule['actions'][1]}' is unreachable; rule vacuously satisfied"
        elif rule['kind'] == 'mutual_exclusion' and len(unreachable) == 2:
            reason = 'Both actions are unreachable; rule never applies'
        elif unreachable == rule_actions_set:
            reason = f'Actions {rule_actions_set} are unreachable; rule never applies'
        else:
            reason = f'Some actions are unreachable: {unreachable}'
        
        return {
            'ordering_rule_id': rule['id'],
            'workflow': '',
            'context_id': '',
            'status': 'warning',
            'kind': rule['kind'],
            'reason': reason,
            'search_exhaustive': True,
            'source': rule['source'],
            'assumptions': rule['assumptions']
        }
    
    return {
        'ordering_rule_id': rule['id'],
        'workflow': '',
        'context_id': '',
        'status': 'satisfied',
        'kind': rule['kind'],
        'search_exhaustive': True,
        'source': rule['source'],
        'assumptions': rule['assumptions']
    }


def _check_exactly_once_independent(rule, initial_facts, goal_facts, actions, compute_successor,
                                    initial_monitor, max_steps, max_states, planner_exhaustive):
    """Check exactly_once via independent product BFS, evaluating at goal states."""
    queue = deque([(initial_facts, initial_monitor, [], 0)])
    seen = {(initial_facts, initial_monitor)}
    visited_product_states = 1
    hit_depth_bound = False
    hit_state_bound = False
    goal_states = []
    all_actions_seen = set()
    
    while queue:
        facts, monitor, path, depth = queue.popleft()
        
        # Check if at goal
        at_goal = goal_facts <= facts
        if at_goal:
            goal_states.append((facts, monitor, path))
        
        # Check depth bound BEFORE expanding (same as planner)
        if depth >= max_steps:
            hit_depth_bound = True
            continue
        
        # Try each action
        for action in actions:
            action_id = action['id']
            
            # Check if action is enabled
            next_facts = compute_successor(facts, action)
            if next_facts is None:
                continue
            
            all_actions_seen.add(action_id)
            
            # Step monitor
            new_monitor = monitor.step(action_id)
            new_path = path + [action_id]
            new_depth = depth + 1
            
            # Dedupe on full product state
            prod_state = (next_facts, new_monitor)
            if prod_state in seen:
                continue
            
            # Check state bound
            if visited_product_states >= max_states:
                hit_state_bound = True
                continue
            
            seen.add(prod_state)
            visited_product_states += 1
            queue.append((next_facts, new_monitor, new_path, new_depth))
    
    # Check liveness property at goal states
    for facts, monitor, path in goal_states:
        if monitor.count != 1:
            return {
                'ordering_rule_id': rule['id'],
                'workflow': '',
                'context_id': '',
                'status': 'violated',
                'kind': rule['kind'],
                'counterexample': path,
                'observed_count': monitor.count,
                'expected_count': 1,
                'reason': f"Goal reached but action executed {monitor.count} times",
                'search_exhaustive': planner_exhaustive,
                'source': rule['source'],
                'assumptions': rule['assumptions']
            }
    
    # Check completeness
    if hit_depth_bound or hit_state_bound or not planner_exhaustive:
        return {
            'ordering_rule_id': rule['id'],
            'workflow': '',
            'context_id': '',
            'status': 'incomplete',
            'kind': rule['kind'],
            'reason': 'Search truncated; cannot prove satisfaction',
            'search_exhaustive': False,
            'cutoff_reasons': [
                r for r, hit in [
                    ('max_steps', hit_depth_bound),
                    ('max_states', hit_state_bound),
                    ('workflow_search_incomplete', not planner_exhaustive)
                ] if hit
            ],
            'source': rule['source'],
            'assumptions': rule['assumptions']
        }
    
    # Check unreachable actions
    rule_action = rule['actions'][0]
    if rule_action not in all_actions_seen:
        return {
            'ordering_rule_id': rule['id'],
            'workflow': '',
            'context_id': '',
            'status': 'warning',
            'kind': rule['kind'],
            'reason': f"Action '{rule_action}' is unreachable; rule never applies",
            'search_exhaustive': True,
            'source': rule['source'],
            'assumptions': rule['assumptions']
        }
    
    return {
        'ordering_rule_id': rule['id'],
        'workflow': '',
        'context_id': '',
        'status': 'satisfied',
        'kind': rule['kind'],
        'search_exhaustive': True,
        'source': rule['source'],
        'assumptions': rule['assumptions']
    }


def _before_checker(monitor, action_id, rule):
    """Check if a before rule is violated."""
    return action_id == rule['actions'][1] and not monitor.seen_first


def _mutual_exclusion_checker(monitor, action_id, rule):
    """Check if a mutual exclusion rule is violated."""
    return ((action_id == rule['actions'][0] and monitor.seen_b) or
            (action_id == rule['actions'][1] and monitor.seen_a))


def _at_most_once_checker(monitor, action_id, rule):
    """Check if an at_most_once rule is violated."""
    return action_id == rule['actions'][0] and monitor.count >= 1

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
