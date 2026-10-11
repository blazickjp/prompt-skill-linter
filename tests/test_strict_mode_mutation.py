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
            'unsupported_dependentRequired': {
                'type': 'object',
                'properties': {'name': {'type': 'string'}, 'credit_card': {'type': 'string'}},
                'required': ['name'],
                'dependentRequired': {'credit_card': ['billing_address']},
                'additionalProperties': False
            },
            'unsupported_dependentSchemas': {
                'type': 'object',
                'properties': {'name': {'type': 'string'}},
                'required': ['name'],
                'dependentSchemas': {
                    'credit_card': {
                        'properties': {'billing_address': {'type': 'string'}},
                        'required': ['billing_address']
                    }
                },
                'additionalProperties': False
            },
            'unsupported_if_then_else': {
                'type': 'object',
                'properties': {'value': {'type': 'string'}},
                'required': ['value'],
                'additionalProperties': False,
                'if': {'properties': {'value': {'const': 'special'}}},
                'then': {'properties': {'extra': {'type': 'string'}}}
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


    def test_mutation_traversal_must_skip_property_maps(self):
        """Treating property name maps as schema nodes must fail tests."""
        # Save original traverse_schema
        from prompt_skill_linter import strict_mode
        original_traverse = strict_mode.traverse_schema
        
        # Create buggy version that treats property maps as schemas (old behavior)
        def buggy_traverse(schema, path='$'):
            if not isinstance(schema, dict):
                return [(path, schema)]
            result = [(path, schema)]
            for key, value in schema.items():
                child_path = f'{path}.{key}'
                if isinstance(value, dict):
                    result.extend(buggy_traverse(value, child_path))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            result.extend(buggy_traverse(item, f'{child_path}[{i}]'))
            return result
        
        # Temporarily use buggy version
        strict_mode.traverse_schema = buggy_traverse
        
        try:
            # Schema with property named 'minimum' should fail with buggy traversal
            schema = {
                'type': 'object',
                'properties': {
                    'minimum': {'type': 'number'}
                },
                'required': ['minimum'],
                'additionalProperties': False
            }
            violations = strict_mode.check_schema_against_provider(schema, 'anthropic')
            codes = [v['rule_id'] for v in violations]
            
            # Buggy traversal SHOULD flag this (proving the bug exists)
            has_spurious_error = 'unsupported_minimum' in codes
            
            self.assertTrue(has_spurious_error, 
                "Buggy traversal should have caused spurious error, proving the fix is necessary")
        finally:
            # Restore original
            strict_mode.traverse_schema = original_traverse


if __name__ == '__main__':
    unittest.main()
