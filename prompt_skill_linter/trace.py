"""Finite safety checks for explicit, reviewer-authored action-trace assertions.

This is a product-state model checker, not a prose interpreter. Workflow facts
use the planner's positive-precondition, remove-then-add transition semantics.
An independent monitor records action events: workflow effects cannot reset a
count or manufacture fresh verification. All allowed finite prefixes are checked,
including prefixes after the goal has been reached; goals do not terminate runs.

``safe`` means exhaustive absence of a violation in this finite abstraction.
``violated`` includes a shortest counterexample. ``unknown`` means an exploration
bound prevented a conclusion. Source quote fidelity must be checked by the
embedding contract validator; this module validates declarations without I/O.
"""
from collections import deque


MAX_ASSERTIONS = 32
MAX_ACTIONS = 64
MAX_FACTS = 256
MAX_COUNT = 1000
MAX_STEPS = 1000
MAX_STATES = 100_000


class TraceAssertionError(ValueError):
    """Malformed or unsupported declaration, never a discovered violation."""


def _error(message):
    raise TraceAssertionError(message)


def _name(value, label):
    if not isinstance(value, str) or not value.strip():
        _error(label + ' must be a nonempty string.')


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        _error(f'{label} must be an integer from {low} to {high}.')


def _strings(value, label, maximum, nonempty=False, unique=False):
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        _error(f'{label} must be an array with '
               f'{"1" if nonempty else "0"} to {maximum} entries.')
    for item in value:
        _name(item, label + ' entry')
    if unique and len(set(value)) != len(value):
        _error(label + ' must not contain duplicates.')


def validate_assertions(workflow):
    """Validate assertion syntax and referenced action IDs, without reading files.

    No assertions is valid and preserves legacy workflow validation. With
    assertions, the finite transition inputs are checked as well. Each assertion
    requires a source span and an assumptions array. Kind-specific unknown fields
    are rejected rather than ignored. Freshness event roles must be disjoint;
    their ordering within a single event is intentionally unsupported.
    """
    if not isinstance(workflow, dict):
        _error('workflow must be an object.')
    assertions = workflow.get('trace_assertions', [])
    if not isinstance(assertions, list) or len(assertions) > MAX_ASSERTIONS:
        _error(f'trace_assertions must be an array with at most {MAX_ASSERTIONS} entries.')
    if not assertions:
        return
    actions = workflow.get('actions')
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        _error(f'workflow.actions must be an array with at most {MAX_ACTIONS} entries.')
    _strings(workflow.get('initial', []), 'workflow.initial', MAX_FACTS)
    facts = set(workflow.get('initial', []))
    action_ids = set()
    for action in actions:
        if not isinstance(action, dict):
            _error('workflow actions must be objects.')
        aid = action.get('id')
        _name(aid, 'action id')
        if aid in action_ids:
            _error('workflow action IDs must be unique.')
        action_ids.add(aid)
        for field in ('requires', 'adds', 'removes'):
            values = action.get(field, [])
            _strings(values, 'action.' + field, MAX_FACTS)
            facts.update(values)
    if len(facts) > MAX_FACTS:
        _error(f'Trace checking supports at most {MAX_FACTS} distinct workflow facts.')
    assertion_ids = set()
    common = {'id', 'kind', 'source', 'assumptions'}
    fields_by_kind = {
        'action_count': {'actions', 'max_count'},
        'freshness': {'invalidate_actions', 'refresh_actions', 'guarded_actions', 'initially_fresh'},
    }
    for assertion in assertions:
        if not isinstance(assertion, dict):
            _error('Trace assertions must be objects.')
        aid = assertion.get('id')
        _name(aid, 'trace assertion id')
        if aid in assertion_ids:
            _error('Trace assertion IDs must be unique within a workflow.')
        assertion_ids.add(aid)
        kind = assertion.get('kind')
        if not isinstance(kind, str) or kind not in fields_by_kind:
            _error('Unsupported trace assertion kind.')
        fields = common | fields_by_kind[kind]
        if set(assertion) != fields:
            _error(f'Trace assertion {aid} requires exactly these fields: ' + ', '.join(sorted(fields)))
        source = assertion['source']
        if not isinstance(source, dict) or set(source) != {'source_id', 'start_line', 'end_line', 'quote'}:
            _error('Trace assertion source requires source_id, start_line, end_line and quote.')
        _name(source['source_id'], 'trace assertion source_id')
        if (type(source['start_line']) is not int or type(source['end_line']) is not int
                or not 1 <= source['start_line'] <= source['end_line']):
            _error('Trace assertion source requires a positive ordered integer line range.')
        if not isinstance(source['quote'], str):
            _error('Trace assertion source quote must be a string.')
        _strings(assertion['assumptions'], 'trace assertion assumptions', 32)
        if kind == 'action_count':
            event_fields = ('actions',)
            _integer(assertion['max_count'], 0, MAX_COUNT, 'max_count')
        else:
            event_fields = ('invalidate_actions', 'refresh_actions', 'guarded_actions')
            if type(assertion['initially_fresh']) is not bool:
                _error('initially_fresh must be an explicit Boolean.')
        roles = set()
        for field in event_fields:
            events = assertion[field]
            _strings(events, field, MAX_ACTIONS, nonempty=field != 'invalidate_actions', unique=True)
            if not set(events) <= action_ids:
                _error(field + ' references an unknown workflow action.')
            if roles.intersection(events):
                _error('Freshness action roles must be disjoint.')
            roles.update(events)


def _path(nodes, index, last_action):
    result = [last_action]
    while nodes[index][2] is not None:
        _, _, parent, action, _ = nodes[index]
        result.append(action)
        index = parent
    result.reverse()
    return result


def _check_one(workflow, assertion, forbidden, max_steps, max_states):
    counting = assertion['kind'] == 'action_count'
    if counting:
        counted = frozenset(assertion['actions'])
        initial_monitor = 0
    else:
        invalidates = frozenset(assertion['invalidate_actions'])
        refreshes = frozenset(assertion['refresh_actions'])
        guarded = frozenset(assertion['guarded_actions'])
        initial_monitor = assertion['initially_fresh']
    actions = [(a['id'], frozenset(a.get('requires', [])),
                frozenset(a.get('adds', [])), frozenset(a.get('removes', [])))
               for a in workflow['actions'] if a['id'] not in forbidden]
    initial = (frozenset(workflow.get('initial', [])), initial_monitor)
    # Parent pointers avoid storing a whole path on each queue entry. Product
    # keys include the monitor: the same facts with a new count/freshness is new.
    nodes = [(initial[0], initial[1], None, None, 0)]
    seen = {initial}
    queue = deque([0])
    cutoff_reasons = set()
    trigger_actions = assertion['actions'] if counting else assertion['guarded_actions']
    triggers = frozenset(trigger_actions)
    first_trigger_path = None
    trigger_cutoffs = set()
    incomplete_layer = None

    def result(status, path=None, violation=None):
        coverage_cutoffs = cutoff_reasons | trigger_cutoffs
        coverage_status = ('reachable' if first_trigger_path is not None else
                           'unknown' if coverage_cutoffs else 'unreachable')
        return {'assertion_id': assertion['id'], 'kind': assertion['kind'],
                'status': status, 'violation_path': path, 'violation': violation,
                'search_exhaustive': status == 'safe', 'visited_states': len(seen),
                'bounds': {'max_steps': max_steps, 'max_states': max_states},
                'cutoff_reasons': sorted(cutoff_reasons),
                'trigger_coverage': {
                    'status': coverage_status, 'trigger_actions': list(trigger_actions),
                    'first_trigger_path': first_trigger_path,
                    'search_exhaustive': status == 'safe' and not coverage_cutoffs,
                    'cutoff_reasons': sorted(coverage_cutoffs),
                    'scope': 'enabled_action_events_in_reviewed_transition_model',
                }}

    while queue:
        index = queue.popleft()
        state, monitor, _, _, depth = nodes[index]
        # On a state cap, finish checking this whole layer's outgoing edges, but
        # never explore a partially admitted next layer. A later counterexample
        # could otherwise be longer than one hidden by the cap.
        if incomplete_layer is not None and depth > incomplete_layer:
            break
        for aid, requires, adds, removes in actions:
            if not requires <= state:
                continue
            if counting:
                nxt_monitor = monitor + (aid in counted)
                bad = nxt_monitor > assertion['max_count']
                evidence = {'action': aid, 'observed_count': nxt_monitor,
                            'max_count': assertion['max_count']} if bad else None
            else:
                bad = aid in guarded and not monitor
                nxt_monitor = False if aid in invalidates else True if aid in refreshes else monitor
                evidence = {'action': aid, 'fresh_before_action': False} if bad else None
            nxt = (frozenset((state - removes) | adds), nxt_monitor)
            if depth >= max_steps:
                # Even a transition to familiar workflow facts can violate the
                # assertion; test the monitor before concluding a closed graph.
                if bad or nxt not in seen:
                    cutoff_reasons.add('max_steps')
                # Safety can close over a self-loop even at depth zero. Its
                # existence does not supply an in-bound trigger witness.
                if aid in triggers and first_trigger_path is None:
                    trigger_cutoffs.add('max_steps')
                continue
            # Check events before state deduplication: an enabled no-op still
            # exercises an assertion, even when its endpoint is familiar.
            if aid in triggers and first_trigger_path is None:
                first_trigger_path = _path(nodes, index, aid)
            if bad:
                return result('violated', _path(nodes, index, aid), evidence)
            if nxt in seen:
                continue
            if len(seen) >= max_states:
                cutoff_reasons.add('max_states')
                incomplete_layer = depth
                continue
            seen.add(nxt)
            nodes.append((nxt[0], nxt[1], index, aid, depth + 1))
            queue.append(len(nodes) - 1)
    return result('unknown' if cutoff_reasons else 'safe')


def check_trace_assertions(workflow, forbidden=(), max_steps=20, max_states=2000):
    """Return one independent result per assertion, in declaration order.

    ``action_count`` sums events in ``actions`` over the entire run, allowing
    at most ``max_count`` (including zero). ``freshness`` starts at explicit
    ``initially_fresh``, resets on ``invalidate_actions``, becomes fresh on
    ``refresh_actions``, and requires freshness before ``guarded_actions``.
    Guard events do not consume freshness. Events are action IDs, not facts.

    ``forbidden`` must contain the caller's resolved prohibited *and* unavailable
    action IDs. Unknown IDs are harmless, as in the planner. No actions are run.
    Hard bounds reject accidental unbounded searches; each assertion has its own
    state budget. Declaration order breaks ties among shortest witnesses.

    ``trigger_coverage`` is independent of safety: counted actions trigger an
    action-count assertion, and guarded actions trigger a freshness assertion.
    Reachable includes a shortest in-bound event prefix. Unreachable requires
    exhaustive absence; truncated absence is unknown. Unreachable is neutral
    coverage, not a violation (for example a deliberate zero-event policy).
    """
    validate_assertions(workflow)
    _integer(max_steps, 0, MAX_STEPS, 'max_steps')
    _integer(max_states, 1, MAX_STATES, 'max_states')
    if not isinstance(forbidden, (tuple, list, set, frozenset)):
        _error('forbidden must be a list, tuple or set of action IDs.')
    for aid in forbidden:
        _name(aid, 'forbidden action ID')
    forbidden = frozenset(forbidden)
    return [_check_one(workflow, assertion, forbidden, max_steps, max_states)
            for assertion in workflow.get('trace_assertions', [])]
