# Contract Writing Rubric for Evaluation

When hand-writing contracts from prompt/skill text for check-only measurement:

## Extraction Rules

1. **Modal verbs to modality**:
   - "must", "required", "shall" → requirement
   - "never", "do not", "forbidden" → prohibition  
   - "may", "can" → permission
   - "should", "prefer" → preference

2. **Scope assignment**:
   - System-level constraints → entity: "system"
   - Task-specific → entity: "task"
   - Always active → temporal: "always"
   - Run-specific → temporal: "run"

3. **Priority**: Default 10 for requirements/prohibitions, 5 for permissions/preferences

4. **Source preservation**: Exact quote from original text, accurate line spans

5. **What NOT to extract**:
   - Examples or illustrations
   - Meta-commentary about the instructions
   - Contextual explanations that aren't directives

## Faithfulness

- Extract what's actually stated, not what's implied
- Don't invent constraints to make checks succeed/fail
- If ambiguous, note in assumptions
- Preserve the original phrasing in source quotes

## Tool/Runtime Stubs

- Use minimal empty tool manifests: `{"tools": {}}`
- Use standard runtime: `{"service_call_budget": 30, "request_sizes": [], "max_plan_steps": 10}`

This rubric is applied consistently to all hand-written contracts.
