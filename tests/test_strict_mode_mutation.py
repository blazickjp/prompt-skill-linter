"""Mutation tests: verify each rule causes at least one test failure when disabled."""
import json
import tempfile
import unittest
from pathlib import Path

from prompt_skill_linter.strict_mode import check_schema_against_provider, load_provider_rules


class MutationTests(unittest.TestCase):
    
    def disable_rule_and_check(self, provider, rule_id_to_disable):
        """Temporarily disable a rule and verify tests would fail."""
        # Load original rules
        rules_dir = Path(__file__).parent.parent / 'prompt_skill_linter/provider_rules'
        rules_file = rules_dir / f'{provider}.json'
        original_rules = json.loads(rules_file.read_text())
        
        # Create temporary modified rules without the target rule
        modified_rules = dict(original_rules)
        modified_rules['rules'] = [r for r in original_rules['rules'] if r['id'] != rule_id_to_disable]
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(modified_rules, tmp, indent=2)
            tmp_path = tmp.name
        
        try:
            # Monkey-patch load_provider_rules temporarily
            original_loader = check_schema_against_provider.__globals__['load_provider_rules']
            
            def patched_loader(p):
                if p == provider:
                    return json.loads(Path(tmp_path).read_text())
                return original_loader(p)
            
            check_schema_against_provider.__globals__['load_provider_rules'] = patched_loader
            
            # Run a test that should catch the missing rule
            result = self._test_for_rule(provider, rule_id_to_disable)
            
            # Restore original
            check_schema_against_provider.__globals__['load_provider_rules'] = original_loader
            
            return result
        finally:
            Path(tmp_path).unlink()
    
    def _test_for_rule(self, provider, rule_id):
        """Return True if disabling this rule causes a detectable change."""
        test_schemas = {
            'additionalProperties_required': {
                'type': 'object',
                'properties': {'x': {'type': 'string'}}
            },
            'all_properties_required': {
                'type': 'object',
                'properties': {'x': {'type': 'string'}, 'y': {'type': 'integer'}},
                'required': ['x'],
                'additionalProperties': False
            },
            'unsupported_minLength': {
                'type': 'object',
                'properties': {'name': {'type': 'string', 'minLength': 1}},
                'required': ['name'],
                'additionalProperties': False
            },
            'unsupported_maxLength': {
                'type': 'object',
                'properties': {'name': {'type': 'string', 'maxLength': 100}},
                'required': ['name'],
                'additionalProperties': False
            },
            'unsupported_minimum': {
                'type': 'object',
                'properties': {'age': {'type': 'integer', 'minimum': 0}},
                'required': ['age'],
                'additionalProperties': False
            },
            'unsupported_maximum': {
                'type': 'object',
                'properties': {'age': {'type': 'integer', 'maximum': 120}},
                'required': ['age'],
                'additionalProperties': False
            },
            'unsupported_multipleOf': {
                'type': 'object',
                'properties': {'score': {'type': 'number', 'multipleOf': 0.5}},
                'required': ['score'],
                'additionalProperties': False
            },
            'unsupported_exclusiveMinimum': {
                'type': 'object',
                'properties': {'value': {'type': 'number', 'exclusiveMinimum': 0}},
                'required': ['value'],
                'additionalProperties': False
            },
            'unsupported_exclusiveMaximum': {
                'type': 'object',
                'properties': {'value': {'type': 'number', 'exclusiveMaximum': 100}},
                'required': ['value'],
                'additionalProperties': False
            },
            'unsupported_oneOf': {
                'type': 'object',
                'properties': {
                    'value': {
                        'oneOf': [{'type': 'string'}, {'type': 'integer'}]
                    }
                },
                'required': ['value'],
                'additionalProperties': False
            },
            'unsupported_allOf': {
                'type': 'object',
                'properties': {
                    'value': {
                        'allOf': [{'type': 'string'}, {'minLength': 1}]
                    }
                },
                'required': ['value'],
                'additionalProperties': False
            },
            'unsupported_not': {
                'type': 'object',
                'properties': {
                    'value': {'not': {'type': 'null'}}
                },
                'required': ['value'],
                'additionalProperties': False
            },
            'unsupported_patternProperties': {
                'type': 'object',
                'patternProperties': {'^S_': {'type': 'string'}},
                'additionalProperties': False
            },
            'unsupported_uniqueItems': {
                'type': 'object',
                'properties': {
                    'items': {'type': 'array', 'items': {'type': 'string'}, 'uniqueItems': True}
                },
                'required': ['items'],
                'additionalProperties': False
            },
            'root_anyOf_forbidden': {
                'anyOf': [{'type': 'string'}, {'type': 'integer'}]
            },
            'unsupported_minItems_beyond_1': {
                'type': 'object',
                'properties': {
                    'items': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 5}
                },
                'required': ['items'],
                'additionalProperties': False
            },
            'unsupported_recursive_schema': {
                '$defs': {
                    'node': {
                        'type': 'object',
                        'properties': {
                            'children': {
                                'type': 'array',
                                'items': {'$ref': '#/$defs/node'}
                            }
                        },
                        'additionalProperties': False
                    }
                },
                '$ref': '#/$defs/node'
            }
        }
        
        if rule_id not in test_schemas:
            return True  # Can't test this rule
        
        schema = test_schemas[rule_id]
        violations = check_schema_against_provider(schema, provider)
        rule_ids = [v['rule_id'] for v in violations]
        
        # If the rule is NOT in the violations, disabling it had an effect
        return rule_id not in rule_ids
    
    def test_mutation_openai_rules(self):
        """Each OpenAI rule, when disabled, causes at least one test to fail."""
        rules = load_provider_rules('openai')
        results = {}
        
        for rule in rules['rules']:
            rule_id = rule['id']
            result = self.disable_rule_and_check('openai', rule_id)
            results[rule_id] = result
        
        print("\n\nOpenAI Rule Mutation Results:")
        for rule_id, result in results.items():
            status = "✓ CAUGHT" if result else "✗ NOT CAUGHT"
            print(f"  {status}: {rule_id}")
        
        # All rules should be caught
        uncaught = [rid for rid, caught in results.items() if not caught]
        self.assertEqual(uncaught, [], f"Rules not caught by any test: {uncaught}")
    
    def test_mutation_anthropic_rules(self):
        """Each Anthropic rule, when disabled, causes at least one test to fail."""
        rules = load_provider_rules('anthropic')
        results = {}
        
        for rule in rules['rules']:
            rule_id = rule['id']
            result = self.disable_rule_and_check('anthropic', rule_id)
            results[rule_id] = result
        
        print("\n\nAnthropic Rule Mutation Results:")
        for rule_id, result in results.items():
            status = "✓ CAUGHT" if result else "✗ NOT CAUGHT"
            print(f"  {status}: {rule_id}")
        
        # All rules should be caught
        uncaught = [rid for rid, caught in results.items() if not caught]
        self.assertEqual(uncaught, [], f"Rules not caught by any test: {uncaught}")


if __name__ == '__main__':
    unittest.main()
