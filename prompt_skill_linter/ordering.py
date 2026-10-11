"""Declarative temporal ordering constraints for workflow actions.

Checks static ordering properties against explored workflow paths:
- before: action A must occur before B on every path where B occurs
- mutual_exclusion: actions C and D can't both occur on the same path
- exactly_once: E occurs exactly once on every complete path

These are plain-data contracts that can be mutated and checked independently.
"""
from collections import deque


def validate_ordering_rules(workflow, sources, root):
    """Validate ordering rule declarations before analysis.
    
    Args:
        workflow: Workflow dict with optional ordering_rules
        sources: Contract sources dict
        root: Root path for source validation
        
    Raises:
        ValueError: On invalid ordering rule declaration
    """
    from pathlib import Path
    
    rules = workflow.get('ordering_rules', [])
    if len(rules) > 32:
        raise ValueError('At most 32 ordering rules per workflow are supported.')
    
    rule_ids = [r['id'] for r in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError('Ordering rule IDs must be unique within a workflow.')
    
    # Check for ID collisions with global contract elements (checked externally)
    
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
        
        # Check that referenced actions exist
        unknown = set(actions) - action_ids
        if unknown:
            raise ValueError(f"{rule['id']}: references unknown actions: {', '.join(sorted(unknown))}")
        
        # Validate scope
        scope = rule.get('scope')
        if not isinstance(scope, dict) or set(scope.keys()) != {'entity', 'temporal'}:
            raise ValueError(f"{rule['id']}: scope must have entity and temporal")
        
        if not all(isinstance(scope[k], str) for k in ('entity', 'temporal')):
            raise ValueError(f"{rule['id']}: scope entity and temporal must be strings")
        
        # Validate source span
        src = rule.get('source')
        if not isinstance(src, dict):
            raise ValueError(f"{rule['id']}: source must be an object")
        
        if src.get('source_id') not in sources:
            raise ValueError(f"{rule['id']}: unknown source_id")
        
        path = (Path(root) / sources[src['source_id']]['path']).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise ValueError(f"{rule['id']}: source path must stay within contract directory")
        
        # Read and verify source quote
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
        
        # Validate assumptions
        assumptions = rule.get('assumptions', [])
        if not isinstance(assumptions, list) or not all(isinstance(a, str) for a in assumptions):
            raise ValueError(f"{rule['id']}: assumptions must be an array of strings")
        
        if len(assumptions) > 32:
            raise ValueError(f"{rule['id']}: at most 32 assumptions per rule")


def check_ordering_rules(workflow, explored_result, workflow_id, context):
    """Check ordering rules against explored workflow paths.
    
    Args:
        workflow: Workflow dict with ordering_rules
        explored_result: Result from planner.explore()
        workflow_id: Workflow identifier string
        context: Context dict
        
    Returns:
        tuple: (diagnostics, checks) where diagnostics is a list of violations
               and checks is a list of check results
    """
    rules = workflow.get('ordering_rules', [])
    if not rules:
        return [], []
    
    diagnostics = []
    checks = []
    
    # Build all paths from the explored graph for checking
    # We need to explore all paths up to the bound, not just the goal path
    paths = _enumerate_paths_from_graph(explored_result)
    
    # If search was truncated, we can't prove properties hold
    search_exhaustive = explored_result.get('search_exhaustive', False)
    
    for rule in rules:
        result = _check_single_rule(rule, paths, search_exhaustive, workflow, explored_result)
        result.update({
            'ordering_rule_id': rule['id'],
            'workflow': workflow_id,
            'context_id': context['id'],
            'source': rule['source'],
            'assumptions': rule['assumptions'],
        })
        checks.append(result)
        
        # Create diagnostic for violations or warnings
        if result['status'] in ('violated', 'warning', 'incomplete'):
            code = _get_diagnostic_code(result)
            severity = 'error' if result['status'] == 'violated' else 'warning'
            
            diagnostic = {
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
                    'Ordering rule checked against bounded finite-state workflow exploration.',
                    'Counterexample paths are concrete action sequences from the reviewed model.',
                    'Truncated search reports incomplete coverage, not rule satisfaction.'
                ],
                'repairs': [],
                'regression_case': {
                    'context': context,
                    'expected_code': code,
                    'ordering_rule_id': rule['id'],
                    'counterexample': result.get('counterexample')
                },
                'provenance_limitations': [
                    'Ordering rule quote establishes provenance only; semantic fidelity to prose requirements remains a review assumption.'
                ]
            }
            
            diagnostics.append(diagnostic)
    
    return diagnostics, checks


def _enumerate_paths_from_graph(explored_result):
    """Extract paths from the planner result up to the exploration bounds.
    
    We use the same bounded BFS approach as the planner to avoid
    enumerating exponentially many paths in workflows with cycles.
    """
    graph = explored_result.get('graph', {})
    states = {s['id']: s for s in graph.get('states', [])}
    edges = graph.get('edges', [])
    
    if not states:
        return [[]]  # Empty path for empty workflow
    
    # Build adjacency list
    adj = {}
    for edge in edges:
        adj.setdefault(edge['from'], []).append((edge['to'], edge['action']))
    
    # BFS with path limits to avoid memory explosion
    MAX_PATHS = 1000  # Limit number of unique paths to explore
    MAX_PATH_LENGTH = explored_result.get('bounds', {}).get('max_steps', 20)
    
    paths = []
    queue = deque([(0, [])])  # (state_id, path)
    seen_state_paths = set()  # Track (state_id, path_length) to deduplicate
    
    while queue and len(paths) < MAX_PATHS:
        state_id, path = queue.popleft()
        
        # Deduplicate by state and path length to limit explosion
        path_sig = (state_id, len(path))
        if path_sig in seen_state_paths:
            continue
        seen_state_paths.add(path_sig)
        
        # Record this path
        paths.append(list(path))
        
        # Explore successors if within depth limit
        if len(path) < MAX_PATH_LENGTH:
            for next_state, action in adj.get(state_id, []):
                queue.append((next_state, path + [action]))
    
    return paths if paths else [[]]


def _check_single_rule(rule, paths, search_exhaustive, workflow, explored_result):
    """Check a single ordering rule against all paths."""
    kind = rule['kind']
    actions = rule['actions']
    
    if kind == 'before':
        return _check_before(rule, actions[0], actions[1], paths, search_exhaustive, workflow, explored_result)
    elif kind == 'mutual_exclusion':
        return _check_mutual_exclusion(rule, actions[0], actions[1], paths, search_exhaustive)
    elif kind == 'exactly_once':
        return _check_exactly_once(rule, actions[0], paths, search_exhaustive, workflow)
    elif kind == 'at_most_once':
        return _check_at_most_once(rule, actions[0], paths, search_exhaustive)


def _check_before(rule, first, second, paths, search_exhaustive, workflow, explored_result):
    """Check that first occurs before second on all paths where second occurs."""
    # Find paths where second occurs
    violating_paths = []
    
    for path in paths:
        if second not in path:
            continue  # Rule doesn't apply to paths without second
        
        # Check if first occurs before second
        first_indices = [i for i, a in enumerate(path) if a == first]
        second_indices = [i for i, a in enumerate(path) if a == second]
        
        # For each occurrence of second, there must be an occurrence of first before it
        for second_idx in second_indices:
            if not any(first_idx < second_idx for first_idx in first_indices):
                violating_paths.append(path)
                break  # One violation per path is enough
    
    if violating_paths:
        return {
            'status': 'violated',
            'kind': 'before',
            'first_action': first,
            'second_action': second,
            'counterexample': violating_paths[0],  # Shortest or first found
            'reason': f'Action {second} occurs without {first} occurring first',
            'search_exhaustive': search_exhaustive
        }
    
    # Check for incomplete search before warnings
    if not search_exhaustive:
        return {
            'status': 'incomplete',
            'kind': 'before',
            'first_action': first,
            'second_action': second,
            'reason': 'Search was truncated; rule may be violated on unexplored paths',
            'search_exhaustive': False
        }
    
    # Check for warnings about unreachable actions
    all_actions = set(action for path in paths for action in path)
    
    if second not in all_actions:
        # second never occurs, rule vacuously satisfied but might be a mistake
        return {
            'status': 'warning',
            'kind': 'before',
            'first_action': first,
            'second_action': second,
            'reason': f'Action {second} is unreachable; before rule never applies',
            'search_exhaustive': search_exhaustive
        }
    
    return {
        'status': 'satisfied',
        'kind': 'before',
        'first_action': first,
        'second_action': second,
        'search_exhaustive': search_exhaustive
    }


def _check_mutual_exclusion(rule, action_a, action_b, paths, search_exhaustive):
    """Check that action_a and action_b never both occur on the same path."""
    violating_paths = []
    
    for path in paths:
        if action_a in path and action_b in path:
            violating_paths.append(path)
    
    if violating_paths:
        return {
            'status': 'violated',
            'kind': 'mutual_exclusion',
            'excluded_actions': [action_a, action_b],
            'counterexample': violating_paths[0],
            'reason': f'Actions {action_a} and {action_b} both occur on the same path',
            'search_exhaustive': search_exhaustive
        }
    
    # Check for incomplete search before warnings
    if not search_exhaustive:
        return {
            'status': 'incomplete',
            'kind': 'mutual_exclusion',
            'excluded_actions': [action_a, action_b],
            'reason': 'Search was truncated; rule may be violated on unexplored paths',
            'search_exhaustive': False
        }
    
    # Check for warnings
    all_actions = set(action for path in paths for action in path)
    unreachable = [a for a in [action_a, action_b] if a not in all_actions]
    
    if len(unreachable) == 2:
        return {
            'status': 'warning',
            'kind': 'mutual_exclusion',
            'excluded_actions': [action_a, action_b],
            'reason': f'Both actions are unreachable; mutual_exclusion never applies',
            'search_exhaustive': search_exhaustive
        }
    elif unreachable:
        return {
            'status': 'warning',
            'kind': 'mutual_exclusion',
            'excluded_actions': [action_a, action_b],
            'reason': f'Action {unreachable[0]} is unreachable',
            'search_exhaustive': search_exhaustive
        }
    
    return {
        'status': 'satisfied',
        'kind': 'mutual_exclusion',
        'excluded_actions': [action_a, action_b],
        'search_exhaustive': search_exhaustive
    }


def _check_exactly_once(rule, action, paths, search_exhaustive, workflow):
    """Check that action occurs exactly once on every complete path (paths reaching goal)."""
    goal = set(workflow.get('goal', []))
    violating_paths = []
    reason_counts = {}
    
    for path in paths:
        # Determine if this is a complete path (reaches goal)
        # We need to check the final state after following this path
        final_state = _get_final_state(path, workflow)
        is_complete = goal <= final_state
        
        if not is_complete:
            continue  # Rule only applies to complete paths
        
        count = path.count(action)
        if count != 1:
            violating_paths.append(path)
            reason_counts[count] = reason_counts.get(count, 0) + 1
            if len(violating_paths) == 1:  # Save first counterexample
                first_violation_count = count
    
    if violating_paths:
        # Report the most common violation count
        first_violation_count = violating_paths[0].count(action)
        return {
            'status': 'violated',
            'kind': 'exactly_once',
            'action': action,
            'counterexample': violating_paths[0],
            'observed_count': first_violation_count,
            'expected_count': 1,
            'reason': f'Action {action} occurs {first_violation_count} times on a complete path (expected exactly 1)',
            'search_exhaustive': search_exhaustive
        }
    
    # Check if any complete paths exist (needed to distinguish from warnings)
    complete_paths = [p for p in paths if goal <= _get_final_state(p, workflow)]
    
    # Check for incomplete search before warnings (but only if complete paths exist)
    if not search_exhaustive and complete_paths:
        return {
            'status': 'incomplete',
            'kind': 'exactly_once',
            'action': action,
            'reason': 'Search was truncated; rule may be violated on unexplored complete paths',
            'search_exhaustive': False
        }
    
    # Check warnings
    all_actions = set(action for path in paths for action in path)
    
    if action not in all_actions:
        return {
            'status': 'warning',
            'kind': 'exactly_once',
            'action': action,
            'reason': f'Action {action} is unreachable; exactly_once cannot be satisfied',
            'search_exhaustive': search_exhaustive
        }
    
    if not complete_paths:
        return {
            'status': 'warning',
            'kind': 'exactly_once',
            'action': action,
            'reason': 'No complete paths found; exactly_once rule cannot apply',
            'search_exhaustive': search_exhaustive
        }
    
    return {
        'status': 'satisfied',
        'kind': 'exactly_once',
        'action': action,
        'search_exhaustive': search_exhaustive
    }


def _check_at_most_once(rule, action, paths, search_exhaustive):
    """Check that action occurs at most once on every path."""
    violating_paths = []
    
    for path in paths:
        count = path.count(action)
        if count > 1:
            violating_paths.append(path)
    
    if violating_paths:
        first_violation_count = violating_paths[0].count(action)
        return {
            'status': 'violated',
            'kind': 'at_most_once',
            'action': action,
            'counterexample': violating_paths[0],
            'observed_count': first_violation_count,
            'max_count': 1,
            'reason': f'Action {action} occurs {first_violation_count} times (expected at most 1)',
            'search_exhaustive': search_exhaustive
        }
    
    # Check for incomplete search before warnings
    if not search_exhaustive:
        return {
            'status': 'incomplete',
            'kind': 'at_most_once',
            'action': action,
            'reason': 'Search was truncated; rule may be violated on unexplored paths',
            'search_exhaustive': False
        }
    
    # Check warnings
    all_actions = set(action for path in paths for action in path)
    
    if action not in all_actions:
        return {
            'status': 'warning',
            'kind': 'at_most_once',
            'action': action,
            'reason': f'Action {action} is unreachable',
            'search_exhaustive': search_exhaustive
        }
    
    return {
        'status': 'satisfied',
        'kind': 'at_most_once',
        'action': action,
        'search_exhaustive': search_exhaustive
    }


def _get_final_state(path, workflow):
    """Compute the final state after following a path."""
    state = set(workflow.get('initial', []))
    action_map = {a['id']: a for a in workflow['actions']}
    
    for action_id in path:
        action = action_map.get(action_id)
        if action:
            state = (state - set(action.get('removes', []))) | set(action.get('adds', []))
    
    return state


def _get_diagnostic_code(result):
    """Get the appropriate diagnostic code for a check result."""
    if result['status'] == 'violated':
        kind = result['kind']
        if kind == 'before':
            return 'ORDERING_BEFORE_VIOLATED'
        elif kind == 'mutual_exclusion':
            return 'ORDERING_MUTUAL_EXCLUSION_VIOLATED'
        elif kind == 'exactly_once':
            return 'ORDERING_EXACTLY_ONCE_VIOLATED'
        elif kind == 'at_most_once':
            return 'ORDERING_AT_MOST_ONCE_VIOLATED'
    elif result['status'] == 'warning':
        return 'ORDERING_RULE_UNREACHABLE_ACTIONS'
    elif result['status'] == 'incomplete':
        return 'ORDERING_CHECK_INCOMPLETE'
    
    return 'ORDERING_RULE_UNKNOWN_STATUS'
