"""Tests for cross-provider strict mode validation."""
import json
import unittest
from pathlib import Path

from prompt_skill_linter.strict_mode import (
    check_schema_against_provider,
    check_tool_schemas,
    detect_recursive_refs,
    load_provider_rules,
    traverse_schema
)

ROOT = Path(__file__).resolve().parents[1]


class StrictModeTests(unittest.TestCase):
    
    def test_load_provider_rules(self):
        """Provider rules load successfully with expected structure."""
        openai = load_provider_rules('openai')
        self.assertEqual(openai['provider'], 'openai')
        self.assertIn('rules', openai)
        self.assertIn('documentation_urls', openai)
        self.assertTrue(len(openai['rules']) > 0)
        
        anthropic = load_provider_rules('anthropic')
        self.assertEqual(anthropic['provider'], 'anthropic')
        self.assertIn('rules', anthropic)
        self.assertTrue(len(anthropic['rules']) > 0)
    
    def test_traverse_schema(self):
        """Schema traversal visits all nodes."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"}
            }
        }
        nodes = traverse_schema(schema)
        paths = [path for path, _ in nodes]
        self.assertIn('$', paths)
        self.assertIn('$.properties', paths)
        self.assertIn('$.properties.name', paths)
        self.assertIn('$.properties.age', paths)
    
    def test_detect_recursive_refs(self):
        """Recursive schema detection works."""
        recursive = {
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/node"}
                        }
                    }
                }
            },
            "$ref": "#/$defs/node"
        }
        cycles = detect_recursive_refs(recursive)
        self.assertTrue(len(cycles) > 0)
        
        non_recursive = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            }
        }
        cycles = detect_recursive_refs(non_recursive)
        self.assertEqual(len(cycles), 0)
    
    def test_openai_additionalProperties_required(self):
        """OpenAI requires additionalProperties: false on all objects."""
        schema_missing = {
            "type": "object",
            "properties": {"x": {"type": "string"}}
        }
        violations = check_schema_against_provider(schema_missing, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('additionalProperties_required', codes)
        
        schema_ok = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema_ok, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertNotIn('additionalProperties_required', codes)
    
    def test_openai_all_properties_required(self):
        """OpenAI requires all properties to be in required array."""
        schema_incomplete = {
            "type": "object",
            "properties": {
                "x": {"type": "string"},
                "y": {"type": "integer"}
            },
            "required": ["x"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema_incomplete, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('all_properties_required', codes)
        
        schema_complete = {
            "type": "object",
            "properties": {
                "x": {"type": "string"},
                "y": {"type": "integer"}
            },
            "required": ["x", "y"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema_complete, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertNotIn('all_properties_required', codes)
    
    def test_openai_unsupported_dependentRequired(self):
        """OpenAI rejects dependentRequired."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "credit_card": {"type": "string"}
            },
            "required": ["name"],
            "dependentRequired": {
                "credit_card": ["billing_address"]
            },
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_dependentRequired', codes)
    
    def test_openai_unsupported_dependentSchemas(self):
        """OpenAI rejects dependentSchemas."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"],
            "dependentSchemas": {
                "credit_card": {
                    "properties": {"billing_address": {"type": "string"}},
                    "required": ["billing_address"]
                }
            },
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_dependentSchemas', codes)
    
    def test_openai_supports_numeric_constraints(self):
        """OpenAI base models SUPPORT numeric constraints."""
        schema = {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "minimum": 0, "maximum": 120},
                "score": {"type": "number", "multipleOf": 0.5}
            },
            "required": ["age", "score"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema, 'openai')
        codes = [v['rule_id'] for v in violations]
        # These should NOT be violations for base models
        self.assertNotIn('unsupported_minimum', codes)
        self.assertNotIn('unsupported_maximum', codes)
        self.assertNotIn('unsupported_multipleOf', codes)
    
    def test_openai_unsupported_if_then_else(self):
        """OpenAI rejects if/then/else."""
        schema = {
            "type": "object",
            "properties": {
                "value": {"type": "string"}
            },
            "required": ["value"],
            "additionalProperties": False,
            "if": {"properties": {"value": {"const": "special"}}},
            "then": {"properties": {"extra": {"type": "string"}}}
        }
        violations = check_schema_against_provider(schema, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_if_then_else', codes)
    
    def test_openai_root_anyOf_forbidden(self):
        """OpenAI forbids anyOf at root level."""
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"}
            ]
        }
        violations = check_schema_against_provider(schema, 'openai')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('root_anyOf_forbidden', codes)
    
    def test_anthropic_unsupported_minLength(self):
        """Anthropic rejects minLength on strings."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1}
            },
            "required": ["name"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema, 'anthropic')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_minLength', codes)
    
    def test_anthropic_unsupported_numeric_constraints(self):
        """Anthropic rejects numeric constraints."""
        schema = {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "minimum": 0}
            },
            "required": ["age"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema, 'anthropic')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_minimum', codes)
    
    def test_anthropic_minItems_only_0_or_1(self):
        """Anthropic only supports minItems values of 0 or 1."""
        schema_invalid = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}, "minItems": 5}
            },
            "required": ["items"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema_invalid, 'anthropic')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_minItems_beyond_1', codes)
        
        schema_valid = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}, "minItems": 1}
            },
            "required": ["items"],
            "additionalProperties": False
        }
        violations = check_schema_against_provider(schema_valid, 'anthropic')
        codes = [v['rule_id'] for v in violations]
        self.assertNotIn('unsupported_minItems_beyond_1', codes)
    
    def test_anthropic_recursive_schemas_rejected(self):
        """Anthropic rejects recursive schemas."""
        schema = {
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/node"}
                        }
                    },
                    "additionalProperties": False
                }
            },
            "$ref": "#/$defs/node"
        }
        violations = check_schema_against_provider(schema, 'anthropic')
        codes = [v['rule_id'] for v in violations]
        self.assertIn('unsupported_recursive_schema', codes)
    
    def test_check_tool_schemas_fixture_openai_pass_anthropic_fail(self):
        """Fixture with numeric constraints passes OpenAI but fails Anthropic."""
        manifest = json.loads((ROOT / 'tests/fixtures/openai_pass_anthropic_fail.json').read_text())
        result = check_tool_schemas(manifest, ['openai', 'anthropic'])
        
        compat = result['provider_compatibility']
        self.assertTrue(compat['get_temperature']['openai'])  # minimum/maximum supported
        self.assertFalse(compat['get_temperature']['anthropic'])  # minimum/maximum unsupported
    
    def test_check_tool_schemas_fixture_anthropic_pass_openai_fail(self):
        """Fixture with if/then/else passes Anthropic but fails OpenAI."""
        manifest = json.loads((ROOT / 'tests/fixtures/anthropic_pass_openai_fail.json').read_text())
        result = check_tool_schemas(manifest, ['openai', 'anthropic'])
        
        compat = result['provider_compatibility']
        self.assertFalse(compat['conditional_update']['openai'])  # if/then/else unsupported
        self.assertTrue(compat['conditional_update']['anthropic'])  # if/then/else not mentioned in limitations
    
    def test_check_tool_schemas_fixture_both_pass(self):
        """Simple fixture passes both providers."""
        manifest = json.loads((ROOT / 'tests/fixtures/both_providers_pass.json').read_text())
        result = check_tool_schemas(manifest, ['openai', 'anthropic'])
        
        compat = result['provider_compatibility']
        self.assertTrue(compat['submit']['openai'])
        self.assertTrue(compat['submit']['anthropic'])
    
    def test_provider_divergence_diagnostic(self):
        """Provider divergence generates warning."""
        manifest = json.loads((ROOT / 'tests/fixtures/anthropic_pass_openai_fail.json').read_text())
        result = check_tool_schemas(manifest, ['openai', 'anthropic'])
        
        codes = [d['code'] for d in result['diagnostics']]
        self.assertIn('PROVIDER_DIVERGENCE', codes)
    
    def test_no_schema_skipped(self):
        """Tools without schema are skipped."""
        manifest = {
            "tools": {
                "no_schema_tool": {
                    "arguments": ["x"],
                    "required": ["x"]
                }
            }
        }
        result = check_tool_schemas(manifest, ['openai'])
        self.assertEqual(len(result['diagnostics']), 0)
    
    def test_deterministic_output(self):
        """Multiple runs produce identical output."""
        manifest = json.loads((ROOT / 'tests/fixtures/openai_pass_anthropic_fail.json').read_text())
        result1 = check_tool_schemas(manifest, ['openai', 'anthropic'])
        result2 = check_tool_schemas(manifest, ['openai', 'anthropic'])
        
        # Serialize to ensure deterministic comparison
        json1 = json.dumps(result1, sort_keys=True)
        json2 = json.dumps(result2, sort_keys=True)
        self.assertEqual(json1, json2)


if __name__ == '__main__':
    unittest.main()
