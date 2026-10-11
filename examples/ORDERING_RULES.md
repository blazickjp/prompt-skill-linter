# Ordering Rules Example

This example demonstrates declarative temporal ordering constraints on workflow actions.

## Example: Authorization Before Data Access

The contract in `ordering-auth-violation.contract.json` models a workflow with two paths to data access:

1. **Authorized path**: `check_auth` → `grant_auth` → `access_data` → `process_data`
2. **Unauthorized path**: `skip_auth` → `access_data` → `process_data`

The ordering rule declares:

```json
{
  "id": "auth-before-data",
  "kind": "before",
  "actions": ["grant_auth", "access_data"]
}
```

This rule requires that `grant_auth` must occur before `access_data` on every path where `access_data` occurs.

## Running the Example

```bash
python -m prompt_skill_linter ordering-auth-violation.contract.json \
  --tools ordering-tools.json --runtime ordering-runtime.json
```

## Expected Output

The checker finds a violation on the unauthorized path:

```
[model_based/error] ORDERING_BEFORE_VIOLATED
  Rules: auth-before-data
  policy:1-1: Authorization must complete before data access.
  Witness: {
    "status": "violated",
    "counterexample": ["access_data"],
    "reason": "Action access_data occurs without grant_auth occurring first"
  }
```

The counterexample `["access_data"]` shows the violating path: `access_data` is reachable directly from the initial state without `grant_auth` occurring first.

## Supported Ordering Rule Types

### before
Requires action A to occur before action B on all paths where B occurs.

### mutual_exclusion
Requires that actions A and B never both occur on the same path.

### exactly_once
Requires action A to occur exactly once on every complete path (paths reaching the goal).

### at_most_once
Requires action A to occur zero or one time on any path.

## Design Notes

- Ordering rules are checked against the bounded BFS exploration (max_steps=20, max_states=2000 by default)
- Violations include concrete counterexample paths (action sequences)
- Truncated search reports incomplete coverage as a warning rather than claiming satisfaction
- Rules on unreachable actions produce warnings
- Plain-data design enables contract mutation testing

## Limitations

- No arbitrary temporal logic or quantifier inference from prose
- No proof that the reviewed action model faithfully represents source semantics
- Source quote matching establishes provenance only, not semantic fidelity
- Rule satisfaction is conditional on the declared finite-state abstraction
