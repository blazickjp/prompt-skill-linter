#!/usr/bin/env python3
"""Build complete evaluation: 30+ cases, labels, hand-written contracts, measurements."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# 32 diverse cases: ~10 Cursor (31%), rest from other sources
# Each has: source, text, label
# Labels created BEFORE any contracts or linter work

CASES = [
    # CURSOR (10 cases, 31%)
    {"id": "cursor_01", "src": "https://cursor.com/skills/env-setup", "text": "terminals: Named tmux sessions launched alongside start; ignored when start is absent.", "label": {"issue": True, "type": "missing_requirement"}},
    {"id": "cursor_02", "src": "https://cursor.com/skills/canvas", "text": "Embed all data inline. No fetch(), no network calls.", "label": {"issue": False}},
    {"id": "cursor_03", "src": "https://cursor.com/skills/bdk-create-agent", "text": "If the plan grows past ~10 files, cut scope.", "label": {"issue": True, "type": "vague"}},
    {"id": "cursor_04", "src": "https://cursor.com/skills/env-setup", "text": "install: package installs, compilation. Must exit. start: daemons, dev servers.", "label": {"issue": False}},
    {"id": "cursor_05", "src": "https://cursor.com/skills/canvas", "text": "If 2+ slop patterns present, redesign.", "label": {"issue": False}},
    {"id": "cursor_06", "src": "https://cursor.com/skills/env-setup", "text": "Resolution order: 1. repo .cursor/environment.json 2. Personal 3. Team. First wins.", "label": {"issue": False}},
    {"id": "cursor_07", "src": "https://cursor.com/skills/bdk-create-agent", "text": "tsx does not typecheck. Tool execute must return JSON-shaped values.", "label": {"issue": False}},
    {"id": "cursor_08", "src": "https://cursor.com/skills/canvas", "text": "Import only from cursor/canvas. No relative imports, no npm packages.", "label": {"issue": False}},
    {"id": "cursor_09", "src": "https://cursor.com/skills/env-setup", "text": "Processes never survive snapshot. Anything running belongs in start, not install.", "label": {"issue": False}},
    {"id": "cursor_10", "src": "https://cursor.com/skills/bdk-create-agent", "text": "Model turns need CURSOR_API_KEY, then CURSOR_API_KEY_FILE, then CURSOR_SERVICE_ACCOUNT_KEY, then login.", "label": {"issue": False}},
    
    # ANTHROPIC (8 cases, 25%)
    {"id": "anthropic_01", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "If tool calls depend on previous calls for parameters, do NOT call in parallel. Never use placeholders.", "label": {"issue": False}},
    {"id": "anthropic_02", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "Examples: Relevant - mirror use case. Diverse - cover edge cases, vary to avoid unintended patterns.", "label": {"issue": True, "type": "tension"}},
    {"id": "anthropic_03", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "Claude 4.6+: prefilled responses on last assistant turn unsupported. Returns 400 error. Earlier models still support.", "label": {"issue": False}},
    {"id": "anthropic_04", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "XML tags help parse complex prompts. Wrap each content type in tags like <instructions>, <context>.", "label": {"issue": False}},
    {"id": "anthropic_05", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "Providing context or motivation helps Claude understand goals better.", "label": {"issue": False}},
    {"id": "anthropic_06", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "Golden rule: Show prompt to colleague with minimal context. If confused, Claude will be too.", "label": {"issue": False}},
    {"id": "anthropic_07", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "Include 3-5 examples for best results.", "label": {"issue": False}},
    {"id": "anthropic_08", "src": "https://docs.anthropic.com/claude/prompt-engineering", "text": "Be clear and direct. Being specific about desired output enhances results.", "label": {"issue": False}},
    
    # LANGCHAIN (6 cases, 19%)
    {"id": "langchain_01", "src": "https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/agents/mrkl/prompt.py", "text": "Format: Question, Thought, Action (one of tool_names), Action Input, Observation. Repeat N times. Final Answer.", "label": {"issue": False}},
    {"id": "langchain_02", "src": "https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/agents/conversational_chat/prompt.py", "text": "Assistant is large language model trained by OpenAI, designed to assist with wide range of tasks.", "label": {"issue": False}},
    {"id": "langchain_03", "src": "https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/agents/conversational_chat/prompt.py", "text": "If using tool information, mention explicitly without tool names - I have forgotten all TOOL RESPONSES!", "label": {"issue": False}},
    {"id": "langchain_04", "src": "https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/agents/conversational_chat/prompt.py", "text": "Respond with markdown json blob with single action, and NOTHING else.", "label": {"issue": False}},
    {"id": "langchain_05", "src": "https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/agents/mrkl/prompt.py", "text": "Answer following questions as best you can. You have access to following tools.", "label": {"issue": False}},
    {"id": "langchain_06", "src": "https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/agents/conversational_chat/prompt.py", "text": "Action to take must be one of tool_names. Action input is string input to the action.", "label": {"issue": False}},
    
    # OTHER OSS (8 cases, 25%)
    {"id": "oss_01", "src": "https://github.com/tallesborges/agentic-system-prompts", "text": "Write detailed commit messages explaining changes made.", "label": {"issue": True, "type": "vague"}},
    {"id": "oss_02", "src": "https://github.com/tallesborges/agentic-system-prompts", "text": "MUST get user permission before: running commands affecting filesystem, making code changes.", "label": {"issue": False}},
    {"id": "oss_03", "src": "https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools", "text": "Never assume user intent. Always ask clarification when requirements ambiguous.", "label": {"issue": False}},
    {"id": "oss_04", "src": "https://github.com/EliFuzz/awesome-system-prompts", "text": "SEARCH section must match existing code exactly. REPLACE shows modified code.", "label": {"issue": True, "type": "undefined"}},
    {"id": "oss_05", "src": "https://github.com/tallesborges/agentic-system-prompts", "text": "Before making changes, analyze codebase to understand structure and patterns.", "label": {"issue": False}},
    {"id": "oss_06", "src": "https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools", "text": "Test changes before committing. Run relevant test suite to verify.", "label": {"issue": False}},
    {"id": "oss_07", "src": "https://github.com/EliFuzz/awesome-system-prompts", "text": "When editing files, preserve existing formatting and style conventions.", "label": {"issue": False}},
    {"id": "oss_08", "src": "https://github.com/tallesborges/agentic-system-prompts", "text": "If unsure about correct approach, propose multiple options with trade-offs.", "label": {"issue": False}},
]

def save_cases_with_labels():
    """Save cases with labels ONLY - no contracts yet."""
    Path("evaluation/final_corpus/cases").mkdir(parents=True, exist_ok=True)
    
    for case in CASES:
        case_data = {
            "id": case["id"],
            "source": {"url": case["src"], "license": "Various (see URL)", "type": "text"},
            "text": case["text"],
            "label": case["label"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(f"evaluation/final_corpus/cases/{case['id']}.json", 'w') as f:
            json.dump(case_data, f, indent=2)
    
    # Create split
    import random
    random.seed(42)
    ids = [c["id"] for c in CASES]
    random.shuffle(ids)
    dev_ids = sorted(ids[:22])
    held_out_ids = sorted(ids[22:])
    
    split = {"version": 1, "seed": 42, "dev": dev_ids, "held_out": held_out_ids}
    with open("evaluation/final_corpus/split.json", 'w') as f:
        json.dump(split, f, indent=2)
    
    print(f"Created {len(CASES)} cases with labels")
    print(f"Dev: {len(dev_ids)}, Held-out: {len(held_out_ids)}")
    
    cursor_count = sum(1 for c in CASES if c["id"].startswith("cursor"))
    print(f"Cursor: {cursor_count} ({100*cursor_count/len(CASES):.0f}%)")

if __name__ == "__main__":
    save_cases_with_labels()
