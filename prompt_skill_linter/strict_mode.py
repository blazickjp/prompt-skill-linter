"""Cross-provider tool-schema strict-mode checker.

Validates tool argument schemas against OpenAI Structured Outputs and Anthropic
strict tool use requirements. All checks run offline using rules grounded in
official provider documentation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_provider_rules(provider: str) -> dict:
    """Load provider-specific strict mode rules from data file."""
    rules_dir = Path(__file__).parent / 'provider_rules'
    rules_file = rules_dir / f'{provider}.json'
    if not rules_file.exists():
        raise ValueError(f'Unknown provider: {provider}')
    return json.loads(rules_file.read_text())


def traverse_schema(schema: Any, path: str = '$') -> list[tuple[str, Any]]:
    """Yield (json_pointer, node) for every node in the schema tree."""
    if not isinstance(schema, dict):
        return [(path, schema)]
    
    result = [(path, schema)]
    for key, value in schema.items():
        child_path = f'{path}.{key}' if key not in ('$ref', '$defs', 'definitions') else f'{path}/{key}'
        if isinstance(value, dict):
            result.extend(traverse_schema(value, child_path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    result.extend(traverse_schema(item, f'{child_path}[{i}]'))
    return result


def detect_recursive_refs(schema: dict) -> list[str]:
    """Detect recursive $ref cycles in a schema."""
    refs_seen = set()
    cycles = []
    
    def visit(node, path, visiting):
        if not isinstance(node, dict):
            return
        
        if '$ref' in node:
            ref = node['$ref']
            if ref in visiting:
                cycles.append(path)
                return
            if ref.startswith('#/'):
                target_path = ref[2:].split('/')
                target = schema
                try:
                    for segment in target_path:
                        target = target[segment]
                    visit(target, path, visiting | {ref})
                except (KeyError, TypeError):
                    pass
        
        for key, value in node.items():
            if key != '$ref':
                if isinstance(value, dict):
                    visit(value, f'{path}.{key}', visiting)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            visit(item, f'{path}.{key}[{i}]', visiting)
    
    visit(schema, '$', set())
    return cycles


def check_schema_against_provider(schema: dict, provider: str, tool_name: str = None) -> list[dict]:
    """Check a single schema against a provider's strict mode rules.
    
    Returns a list of violations, each with:
    - rule_id: the rule that was violated
    - path: JSON pointer to the offending node
    - description: human-readable description
    - fix: suggested fix
    """
    rules = load_provider_rules(provider)
    violations = []
    nodes = traverse_schema(schema)
    
    for rule in rules['rules']:
        rule_id = rule['id']
        
        if rule_id == 'additionalProperties_required':
            for path, node in nodes:
                if isinstance(node, dict) and node.get('type') == 'object':
                    if 'additionalProperties' not in node or node['additionalProperties'] is not False:
                        violations.append({
                            'rule_id': rule_id,
                            'provider': provider,
                            'path': path,
                            'description': rule['description'],
                            'fix': rule['fix']
                        })
        
        elif rule_id == 'all_properties_required':
            for path, node in nodes:
                if isinstance(node, dict) and node.get('type') == 'object' and 'properties' in node:
                    required = set(node.get('required', []))
                    properties = set(node['properties'].keys())
                    missing = properties - required
                    if missing:
                        violations.append({
                            'rule_id': rule_id,
                            'provider': provider,
                            'path': path,
                            'description': f"{rule['description']} (missing: {', '.join(sorted(missing))})",
                            'fix': rule['fix']
                        })
        
        elif rule_id == 'unsupported_minItems_beyond_1' and provider == 'anthropic':
            for path, node in nodes:
                if isinstance(node, dict) and 'minItems' in node:
                    if node['minItems'] not in (0, 1):
                        violations.append({
                            'rule_id': rule_id,
                            'provider': provider,
                            'path': path,
                            'description': rule['description'],
                            'fix': rule['fix'],
                            'value': node['minItems']
                        })
        
        elif rule_id == 'unsupported_recursive_schema' and provider == 'anthropic':
            cycles = detect_recursive_refs(schema)
            for cycle_path in cycles:
                violations.append({
                    'rule_id': rule_id,
                    'provider': provider,
                    'path': cycle_path,
                    'description': rule['description'],
                    'fix': rule['fix']
                })
        
        elif rule_id == 'root_anyOf_forbidden':
            if 'anyOf' in schema:
                violations.append({
                    'rule_id': rule_id,
                    'provider': provider,
                    'path': '$',
                    'description': rule['description'],
                    'fix': rule['fix']
                })
        
        elif rule_id.startswith('unsupported_'):
            keyword = rule_id.replace('unsupported_', '')
            for path, node in nodes:
                if not isinstance(node, dict):
                    continue
                
                if keyword in node:
                    violations.append({
                        'rule_id': rule_id,
                        'provider': provider,
                        'path': path,
                        'description': rule['description'],
                        'fix': rule['fix']
                    })
    
    return violations


def check_tool_schemas(manifest: dict, providers: list[str]) -> dict:
    """Check all tool schemas in a manifest against specified providers.
    
    Args:
        manifest: tools.json manifest with tool definitions
        providers: list of provider names to check (e.g., ['openai', 'anthropic'])
    
    Returns:
        dict with:
        - diagnostics: list of diagnostic dicts
        - provider_compatibility: per-tool compatibility summary
    """
    diagnostics = []
    compatibility = {}
    
    for tool_name, tool_def in manifest.get('tools', {}).items():
        # Check if tool has a schema
        if 'schema' not in tool_def:
            continue
        
        schema = tool_def['schema']
        tool_violations = {provider: [] for provider in providers}
        
        for provider in providers:
            violations = check_schema_against_provider(schema, provider, tool_name)
            tool_violations[provider] = violations
        
        # Record compatibility status
        compatibility[tool_name] = {
            provider: len(tool_violations[provider]) == 0
            for provider in providers
        }
        
        # Generate diagnostics for violations
        for provider, violations in tool_violations.items():
            for violation in violations:
                diagnostics.append({
                    'code': 'STRICT_MODE_INCOMPATIBLE',
                    'class': 'exact',
                    'severity': 'error',
                    'tool': tool_name,
                    'provider': provider,
                    'rule_id': violation['rule_id'],
                    'schema_path': violation['path'],
                    'description': violation['description'],
                    'fix': violation['fix']
                })
        
        # Check for provider divergence (passes one, fails another)
        if len(providers) > 1:
            compatible_providers = [p for p in providers if compatibility[tool_name][p]]
            incompatible_providers = [p for p in providers if not compatibility[tool_name][p]]
            
            if compatible_providers and incompatible_providers:
                diagnostics.append({
                    'code': 'PROVIDER_DIVERGENCE',
                    'class': 'model_based',
                    'severity': 'warning',
                    'tool': tool_name,
                    'compatible_with': compatible_providers,
                    'incompatible_with': incompatible_providers,
                    'description': f'Tool schema passes strict mode for {", ".join(compatible_providers)} but fails for {", ".join(incompatible_providers)}'
                })
    
    return {
        'diagnostics': diagnostics,
        'provider_compatibility': compatibility
    }
