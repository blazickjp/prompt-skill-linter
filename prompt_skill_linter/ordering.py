"""Declarative temporal ordering constraints for workflow actions.

Checks static ordering properties via product construction: BFS over
(workflow_state, monitor_state) where each rule has a finite monitor.

Monitor types and quantification semantics:
- before(A, B): Safety property. Quantifies over all reachable runs. Violated if B occurs
  before A in any reachable run. A run is a finite sequence of enabled actions.
- mutual_exclusion(A, B): Safety property. Quantifies over all reachable runs. Violated if
  both A and B occur in any reachable run.
- at_most_once(A): Safety property. Quantifies over all reachable runs. Violated if A occurs
  more than once in any reachable run.
- exactly_once(A): Liveness property. Quantifies over all goal-reaching runs. Violated if
  A occurs 0 or >=2 times in any goal-reaching run. A goal-reaching run is a finite sequence
  of enabled actions that reaches a state containing all goal facts. The property is checked
  at every goal state, not at the end of a terminated run (runs are not terminated).

Deduplication is on the full product state (facts, monitor), which is sound even when
different action sequences reach the same workflow state. Parent pointers enable shortest
counterexample reconstruction with deterministic ordering.

Returns 'violated' with a shortest counterexample, 'satisfied' when all runs within bounds
obey the rule, or 'incomplete' when a bound cuts off exploration. A bound cuts off exploration
only when an unseen product state (facts, monitor) remains reachable but unexplored. This is
exact within configured bounds and stays small even with cycles.

Conflict detection identifies structural patterns in rule sets:
- Before-cycles (A before B, B before C, C before A) are hard conflicts when all involved
  actions are required (e.g., in exactly_once rules), since they cannot all occur in any
  order. Cycles among optional actions are weaker warnings, since a run that omits them
  satisfies all rules.
- before(A, B) + mutual_exclusion(A, B) conflicts, since before requires B after A, but
  mutual exclusion forbids both.
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


def check_ordering_rules(workflow, explored_result, workflow_id, context, forbidden=frozenset()):
    """Check ordering rules via independent product construction over (facts, monitor_state).
    
    CRITICAL: Does NOT depend on planner's display graph at all. Runs its own BFS over
    the product space (frozenset(facts), monitor_state), computing successors directly
    from workflow actions using the same semantics as the planner (requires/removes/adds).
    
    This makes the planner's display caps (graph_limit) completely irrelevant. The only
    dependencies on the planner are:
    - Initial facts (workflow initial + context facts if any)
    - Forbidden actions (unavailable tools + active prohibitions)
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
    
    # Use forbidden actions passed from engine (prohibitions + unavailable tools)
    # Ensure it's a frozenset for efficient membership checks
    forbidden = frozenset(forbidden) if not isinstance(forbidden, frozenset) else forbidden
    
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
            monitor, _before_checker, max_steps, max_states, planner_exhaustive,
            workflow_id, context
        )
    elif kind == 'mutual_exclusion':
        monitor = MutualExclusionMonitor(rule_actions[0], rule_actions[1])
        return _check_safety_property_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, _mutual_exclusion_checker, max_steps, max_states, planner_exhaustive,
            workflow_id, context
        )
    elif kind == 'at_most_once':
        monitor = CountMonitor(rule_actions[0])
        return _check_safety_property_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, _at_most_once_checker, max_steps, max_states, planner_exhaustive,
            workflow_id, context
        )
    elif kind == 'exactly_once':
        monitor = CountMonitor(rule_actions[0])
        return _check_exactly_once_independent(
            rule, initial_facts, goal_facts, actions, compute_successor,
            monitor, max_steps, max_states, planner_exhaustive,
            workflow_id, context
        )


def _check_safety_property_independent(rule, initial_facts, goal_facts, actions, compute_successor,
                                       initial_monitor, violation_checker, max_steps, max_states,
                                       planner_exhaustive, workflow_id, context):
    """Check safety property via independent product BFS over (facts, monitor).
    
    Quantifies over all reachable runs within bounds. A run is a finite sequence of enabled
    actions starting from initial facts. Safety properties (before, mutual_exclusion,
    at_most_once) are checked at every action step. A violation is an enabled action that
    breaks the rule.
    
    Returns 'violated' with a shortest counterexample, 'satisfied' when all reachable runs
    within bounds obey the rule, or 'incomplete' when a bound cuts off exploration before a
    conclusion can be reached. A bound cuts off exploration only when an unseen product state
    (facts, monitor) remains reachable but unexplored.
    """
    # Product BFS: (facts, monitor, path, depth)
    queue = deque([(initial_facts, initial_monitor, [], 0)])
    seen = {(initial_facts, initial_monitor)}
    visited_product_states = 1
    hit_depth_bound = False
    hit_state_bound = False
    all_actions_seen = set()
    
    while queue:
        facts, monitor, path, depth = queue.popleft()
        
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
                    'workflow': workflow_id,
                    'context_id': context['id'],
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
            
            # Step monitor and compute successor product state
            new_monitor = monitor.step(action_id)
            new_path = path + [action_id]
            prod_state = (next_facts, new_monitor)
            
            # Check depth bound: at the bound, only mark cutoff if successor is unseen
            # This matches trace.py's safer boundary behavior (lines 211-220)
            if depth >= max_steps:
                if prod_state not in seen:
                    hit_depth_bound = True
                continue
            
            # Dedupe on full product state
            if prod_state in seen:
                continue
            
            # Check state bound
            if visited_product_states >= max_states:
                hit_state_bound = True
                continue
            
            seen.add(prod_state)
            visited_product_states += 1
            queue.append((next_facts, new_monitor, new_path, depth + 1))
    
    # No violation found - check completeness
    if hit_depth_bound or hit_state_bound or not planner_exhaustive:
        return {
            'ordering_rule_id': rule['id'],
            'workflow': workflow_id,
            'context_id': context['id'],
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
            'workflow': workflow_id,
            'context_id': context['id'],
            'status': 'warning',
            'kind': rule['kind'],
            'reason': reason,
            'search_exhaustive': True,
            'source': rule['source'],
            'assumptions': rule['assumptions']
        }
    
    return {
        'ordering_rule_id': rule['id'],
        'workflow': workflow_id,
        'context_id': context['id'],
        'status': 'satisfied',
        'kind': rule['kind'],
        'search_exhaustive': True,
        'source': rule['source'],
        'assumptions': rule['assumptions']
    }


def _check_exactly_once_independent(rule, initial_facts, goal_facts, actions, compute_successor,
                                    initial_monitor, max_steps, max_states, planner_exhaustive,
                                    workflow_id, context):
    """Check exactly_once via independent product BFS, evaluating at goal states.
    
    Quantifies over all goal-reaching runs within bounds. A goal-reaching run is a finite
    sequence of enabled actions that reaches a state containing all goal facts. The
    exactly_once property is evaluated at every goal state: the monitored action must have
    occurred exactly once along the path to that goal state.
    
    Returns 'violated' with a shortest counterexample (a goal-reaching path where the action
    occurred 0 or >=2 times), 'satisfied' when all goal-reaching runs within bounds have
    exactly one occurrence, or 'incomplete' when a bound cuts off exploration. A bound cuts
    off exploration only when an unseen product state remains reachable but unexplored.
    """
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
        
        # Try each action
        for action in actions:
            action_id = action['id']
            
            # Check if action is enabled
            next_facts = compute_successor(facts, action)
            if next_facts is None:
                continue
            
            all_actions_seen.add(action_id)
            
            # Step monitor and compute successor product state
            new_monitor = monitor.step(action_id)
            new_path = path + [action_id]
            prod_state = (next_facts, new_monitor)
            
            # Check depth bound: at the bound, only mark cutoff if successor is unseen
            # This matches trace.py's safer boundary behavior
            if depth >= max_steps:
                if prod_state not in seen:
                    hit_depth_bound = True
                continue
            
            # Dedupe on full product state
            if prod_state in seen:
                continue
            
            # Check state bound
            if visited_product_states >= max_states:
                hit_state_bound = True
                continue
            
            seen.add(prod_state)
            visited_product_states += 1
            queue.append((next_facts, new_monitor, new_path, depth + 1))
    
    # Check liveness property at goal states
    for facts, monitor, path in goal_states:
        if monitor.count != 1:
            return {
                'ordering_rule_id': rule['id'],
                'workflow': workflow_id,
                'context_id': context['id'],
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
            'workflow': workflow_id,
            'context_id': context['id'],
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
            'workflow': workflow_id,
            'context_id': context['id'],
            'status': 'warning',
            'kind': rule['kind'],
            'reason': f"Action '{rule_action}' is unreachable; rule never applies",
            'search_exhaustive': True,
            'source': rule['source'],
            'assumptions': rule['assumptions']
        }
    
    return {
        'ordering_rule_id': rule['id'],
        'workflow': workflow_id,
        'context_id': context['id'],
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
    """Detect conflicts in ordering rules: before-cycles and before + mutual-exclusion.
    
    A cycle among 'before' rules (e.g., A before B, B before C, C before A) is a hard conflict
    only when the involved actions are required. If actions are optional (not required by
    exactly_once or on every goal path), then a run that performs none of them satisfies all
    rules, so the cycle is not a hard conflict. Such cases are reported as weaker warnings.
    
    A 'before(A, B)' combined with 'mutual_exclusion(A, B)' is a conflict when B is required,
    since the before rule requires B to occur (with A before it), but mutual exclusion forbids
    B when A occurs.
    
    This analysis is structural and does not prove unrealizability; it identifies patterns that
    are likely to be mistakes in rule declarations.
    """
    conflicts = []
    
    # Build the before-graph: edges represent "must occur before" constraints
    before_rules_with_checks = [(r, c) for r, c in zip(rules, checks) if r['kind'] == 'before']
    before_edges = {}  # Maps (first_action, second_action) -> (rule, check)
    for rule, check in before_rules_with_checks:
        first, second = rule['actions']
        before_edges[(first, second)] = (rule, check)
    
    # Find required actions (actions in exactly_once rules)
    required_actions = {r['actions'][0] for r in rules if r['kind'] == 'exactly_once'}
    
    # Find strongly connected components (SCCs) in the before-graph using Tarjan's algorithm
    # An SCC represents a cycle where all nodes can reach each other
    sccs = _find_sccs_in_before_graph(before_edges)
    
    # Check each SCC with more than one node (a cycle)
    for scc in sccs:
        if len(scc) <= 1:
            continue
        
        # Check if all actions in the cycle are required
        scc_required = scc <= required_actions
        
        # Collect the rules involved in this cycle
        cycle_rules = []
        cycle_edges = []
        for i, action in enumerate(sorted(scc)):
            for next_action in sorted(scc):
                if action != next_action and (action, next_action) in before_edges:
                    rule, check = before_edges[(action, next_action)]
                    if rule not in cycle_rules:
                        cycle_rules.append(rule)
                    cycle_edges.append((action, next_action))
        
        if scc_required:
            # Hard conflict: all actions are required
            action_list = ', '.join(sorted(scc))
            conflicts.append({
                'rules': cycle_rules,
                'reason': f'Before-cycle among required actions: {action_list}. These actions cannot all occur in any order.',
                'conflict_type': 'before_cycle_required',
                'cycle_actions': sorted(scc)
            })
        else:
            # Weaker warning: cycle among optional actions
            action_list = ', '.join(sorted(scc))
            optional_actions = sorted(scc - required_actions)
            conflicts.append({
                'rules': cycle_rules,
                'reason': f'Before-cycle detected: {action_list}. These actions can never all occur, but a run that omits {", ".join(optional_actions)} satisfies all rules.',
                'conflict_type': 'before_cycle_optional',
                'cycle_actions': sorted(scc),
                'optional_actions': optional_actions
            })
    
    # Check for before + mutual_exclusion conflicts
    mutex_rules = [(r, c) for r, c in zip(rules, checks) if r['kind'] == 'mutual_exclusion']
    
    for before_rule, before_check in before_rules_with_checks:
        first, second = before_rule['actions']
        
        for mutex_rule, mutex_check in mutex_rules:
            mutex_a, mutex_b = mutex_rule['actions']
            
            # Check if before(A, B) conflicts with mutual_exclusion(A, B) or (B, A)
            if (first == mutex_a and second == mutex_b) or (first == mutex_b and second == mutex_a):
                # This is a conflict: before requires second to occur (with first before it),
                # but mutual exclusion forbids them both occurring
                conflicts.append({
                    'rules': [before_rule, mutex_rule],
                    'reason': f'before({first}, {second}) conflicts with mutual_exclusion({mutex_a}, {mutex_b}): '
                             f'before requires {second} to occur after {first}, but mutual exclusion forbids both.',
                    'conflict_type': 'before_mutex',
                    'actions': sorted([first, second])
                })
    
    return conflicts


def _find_sccs_in_before_graph(before_edges):
    """Find strongly connected components in the before-graph using Tarjan's algorithm.
    
    Returns a list of SCCs, where each SCC is a set of action IDs that form a cycle.
    """
    # Build adjacency list
    graph = {}
    nodes = set()
    for (first, second) in before_edges:
        nodes.add(first)
        nodes.add(second)
        if first not in graph:
            graph[first] = []
        graph[first].append(second)
    
    # Tarjan's algorithm
    index_counter = [0]
    stack = []
    lowlink = {}
    index = {}
    on_stack = {}
    sccs = []
    
    def strongconnect(node):
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True
        
        if node in graph:
            for successor in graph[node]:
                if successor not in index:
                    strongconnect(successor)
                    lowlink[node] = min(lowlink[node], lowlink[successor])
                elif on_stack.get(successor, False):
                    lowlink[node] = min(lowlink[node], index[successor])
        
        if lowlink[node] == index[node]:
            scc = set()
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.add(w)
                if w == node:
                    break
            sccs.append(scc)
    
    for node in nodes:
        if node not in index:
            strongconnect(node)
    
    return sccs


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
