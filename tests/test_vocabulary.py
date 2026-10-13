"""Tests for vocabulary/glossary feature (issue #5)."""
import json
from pathlib import Path
import tempfile
import unittest

from prompt_skill_linter.engine import ContractError, lint


class VocabularyTests(unittest.TestCase):
    """Test vocabulary integrity checks."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompt.txt').write_text('The system must be secure.\n')
        self.contract = {
            'version': 1,
            'sources': [{'id': 's', 'path': 'prompt.txt'}],
            'skills': [],
            'rules': [],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        self.tools = {'tools': {}}
        self.runtime = {}
    
    def rule(self, rid, literal='x', value=True, priority=0, **extra):
        """Create a rule with an effect."""
        r = {
            'id': rid,
            'source': {
                'source_id': 's',
                'start_line': 1,
                'end_line': 1,
                'quote': 'The system must be secure.'
            },
            'priority': priority,
            'kind': 'requirement',
            'when': {},
            'skills': [],
            'scope': {'entity': 'task', 'temporal': 'run'},
            'exceptions': [],
            'effect': {'literal': literal, 'value': value}
        }
        r.update(extra)
        self.contract['rules'].append(r)
        return r
    
    def vocab(self, term_id, term_type='bool', **extra):
        """Add a vocabulary entry."""
        if 'vocabulary' not in self.contract:
            self.contract['vocabulary'] = []
        entry = {'id': term_id, 'type': term_type}
        entry.update(extra)
        self.contract['vocabulary'].append(entry)
        return entry
    
    def run_lint(self):
        return lint(self.contract, self.tools, self.runtime, self.root)
    
    def codes(self):
        return [d['code'] for d in self.run_lint()['diagnostics']]
    
    # === Core functionality tests ===
    
    def test_no_vocabulary_no_diagnostics(self):
        """Without vocabulary section, no vocabulary diagnostics."""
        self.rule('r1', literal='secure')
        self.assertNotIn('UNDEFINED_TERM', self.codes())
        self.assertNotIn('UNUSED_VOCABULARY_ENTRY', self.codes())
    
    def test_declared_literal_has_no_warning(self):
        """Declared literals should not trigger UNDEFINED_TERM."""
        self.vocab('secure', 'bool')
        self.rule('r1', literal='secure')
        self.assertNotIn('UNDEFINED_TERM', self.codes())
    
    def test_undefined_literal_when_vocabulary_exists(self):
        """Undeclared literals trigger UNDEFINED_TERM only when vocabulary exists."""
        self.vocab('other_term', 'bool')
        self.rule('r1', literal='authenticated')
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'UNDEFINED_TERM']
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]['severity'], 'info')
        self.assertEqual(diags[0]['witness']['term'], 'authenticated')
        self.assertTrue(diags[0]['witness']['auto_declared'])
    
    def test_unused_vocabulary_entry(self):
        """Vocabulary entries never used should trigger info diagnostic."""
        self.vocab('obsolete_term', 'bool')
        result = self.run_lint()
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 1)
        self.assertEqual(unused[0]['witness']['term'], 'obsolete_term')
        self.assertEqual(unused[0]['severity'], 'info')
    
    # === Synonym checks (issue #5 + dots comment) ===
    
    def test_ambiguous_synonym_same_synonym_two_terms(self):
        """Same synonym mapping to multiple terms should be an error."""
        self.vocab('personal_data', 'bool', synonyms=['PII'])
        self.vocab('protected_info', 'bool', synonyms=['PII'])
        result = self.run_lint()
        ambig = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM'
                 and d['witness'].get('reason') == 'synonym_used_by_multiple_terms']
        self.assertEqual(len(ambig), 1)
        self.assertEqual(ambig[0]['severity'], 'error')
        self.assertEqual(ambig[0]['witness']['synonym'], 'PII')
        self.assertIn('personal_data', ambig[0]['witness']['conflicting_terms'])
        self.assertIn('protected_info', ambig[0]['witness']['conflicting_terms'])
    
    def test_ambiguous_synonym_duplicate_in_one_entry(self):
        """Duplicate synonym within one entry should be an error."""
        self.vocab('data', 'bool', synonyms=['PII', 'PII'])
        result = self.run_lint()
        ambig = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM'
                 and d['witness'].get('reason') == 'duplicate_spelling_in_entry']
        self.assertEqual(len(ambig), 1)
        self.assertEqual(ambig[0]['severity'], 'error')
        self.assertEqual(ambig[0]['witness']['synonym'], 'PII')
        
        # Assert no false cross-owner diagnostics
        cross_owner = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM'
                      and d['witness'].get('reason') == 'synonym_used_by_multiple_terms']
        self.assertEqual(len(cross_owner), 0, 
            "Duplicate within one entry should not emit cross-owner conflict")
    
    def test_ambiguous_synonym_equals_other_term_id(self):
        """Synonym that equals another entry's id should be an error."""
        self.vocab('term_a', 'bool', synonyms=['term_b'])
        self.vocab('term_b', 'bool')
        result = self.run_lint()
        ambig = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM']
        self.assertEqual(len(ambig), 1)
        self.assertEqual(ambig[0]['severity'], 'error')
        self.assertEqual(ambig[0]['witness']['reason'], 'synonym_equals_other_term_id')
    
    def test_ambiguous_synonym_equals_own_id(self):
        """Synonym that equals the entry's own id should be an error."""
        self.vocab('recursive', 'bool', synonyms=['recursive'])
        result = self.run_lint()
        ambig = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM']
        self.assertEqual(len(ambig), 1)
        self.assertEqual(ambig[0]['severity'], 'error')
        self.assertEqual(ambig[0]['witness']['reason'], 'synonym_equals_own_id')
    
    # === Type checks (dots comment requirement) ===
    
    def test_type_mismatch_bool_declared_as_enum(self):
        """Using a bool literal declared as enum should error."""
        self.vocab('status', 'enum', values=['pending', 'approved'])
        self.rule('r1', literal='status', value=True)
        result = self.run_lint()
        type_errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH']
        self.assertEqual(len(type_errors), 1)
        self.assertEqual(type_errors[0]['severity'], 'error')
        self.assertEqual(type_errors[0]['witness']['declared_type'], 'enum')
        self.assertEqual(type_errors[0]['witness']['used_as'], 'bool')
    
    def test_type_mismatch_bool_declared_as_int(self):
        """Using a bool literal declared as int should error."""
        self.vocab('timeout', 'int', unit='seconds')
        self.rule('r1', literal='timeout', value=True)
        result = self.run_lint()
        type_errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH']
        self.assertEqual(len(type_errors), 1)
        self.assertEqual(type_errors[0]['witness']['declared_type'], 'int')
    
    def test_type_no_error_for_correct_bool_usage(self):
        """Correct bool usage should not trigger TYPE_MISMATCH."""
        self.vocab('authenticated', 'bool')
        self.rule('r1', literal='authenticated', value=True)
        self.assertNotIn('TYPE_MISMATCH', self.codes())
    
    # === Enum value checks ===
    
    def test_enum_value_invalid_in_when_condition(self):
        """Using invalid enum value in when condition should error."""
        self.vocab('status', 'enum', values=['pending', 'approved', 'rejected'])
        self.rule('r1', when={'status': 'invalid_value'})
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['severity'], 'error')
        self.assertEqual(errors[0]['witness']['declared_type'], 'enum')
        self.assertEqual(errors[0]['witness']['value'], 'invalid_value')
        self.assertIn('pending', errors[0]['witness']['declared_values'])
    
    def test_enum_value_valid_in_when_condition(self):
        """Using valid enum value in when condition should not error."""
        self.vocab('status', 'enum', values=['pending', 'approved', 'rejected'])
        self.rule('r1', when={'status': 'pending'})
        self.assertNotIn('TYPE_MISMATCH', self.codes())
    
    def test_enum_value_invalid_in_exception(self):
        """Using invalid enum value in exception should error."""
        self.vocab('priority', 'enum', values=['low', 'medium', 'high'])
        self.rule('r1', exceptions=[{'priority': 'critical'}])
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH' 
                  and d['witness'].get('declared_type') == 'enum']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['condition_type'], 'exception')
    
    def test_enum_without_values_no_error(self):
        """Enum without declared values should not error (values optional)."""
        self.vocab('status', 'enum')
        self.rule('r1', when={'status': 'any_value'})
        result = self.run_lint()
        # No TYPE_MISMATCH for missing values list
        type_errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH']
        self.assertEqual(len(type_errors), 0)
    
    def test_enum_used_in_when_not_reported_unused(self):
        """Enum used in when condition should not be reported as unused."""
        self.vocab('status', 'enum', values=['pending', 'approved'])
        self.contract['contexts'][0]['facts'] = {'status': 'pending'}
        self.rule('r1', when={'status': 'pending'})
        result = self.run_lint()
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 0)
    
    # === Int unit checks ===
    
    def test_int_value_non_numeric_in_when(self):
        """Using non-numeric value for int fact in when should error."""
        self.vocab('timeout', 'int', unit='seconds')
        self.rule('r1', when={'timeout': 'thirty'})  # String instead of int
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('declared_type') == 'int']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['severity'], 'error')
        self.assertEqual(errors[0]['witness']['value'], 'thirty')
        self.assertEqual(errors[0]['witness']['value_type'], 'str')
    
    def test_int_value_numeric_valid(self):
        """Using numeric value for int fact should not error."""
        self.vocab('timeout', 'int', unit='seconds')
        self.rule('r1', when={'timeout': 30})
        self.assertNotIn('TYPE_MISMATCH', self.codes())
    
    def test_int_value_null_allowed(self):
        """Null value for int fact should be allowed (missing fact)."""
        self.vocab('count', 'int')
        self.rule('r1', when={'count': None})
        result = self.run_lint()
        type_errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH']
        self.assertEqual(len(type_errors), 0)
    
    def test_int_value_bool_in_exception(self):
        """Using bool value for int fact in exception should error."""
        self.vocab('retries', 'int')
        self.rule('r1', exceptions=[{'retries': True}])  # Bool instead of int
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('declared_type') == 'int']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['condition_type'], 'exception')
    
    def test_term_used_in_context_facts_not_unused(self):
        """Term used in context facts should not be reported unused."""
        self.vocab('api_version', 'int')
        self.contract['contexts'][0]['facts'] = {'api_version': 2}
        result = self.run_lint()
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 0)
    
    def test_context_facts_type_check_int_invalid(self):
        """Context fact with wrong type for int should error."""
        self.vocab('api_version', 'int')
        self.contract['contexts'][0]['facts'] = {'api_version': 'two'}  # String instead of int
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('location') == 'context_facts']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['declared_type'], 'int')
        self.assertEqual(errors[0]['witness']['value'], 'two')
    
    def test_context_facts_type_check_enum_invalid(self):
        """Context fact with invalid enum value should error."""
        self.vocab('status', 'enum', values=['pending', 'approved', 'rejected'])
        self.contract['contexts'][0]['facts'] = {'status': 'bogus'}
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('location') == 'context_facts']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['value'], 'bogus')
    
    def test_context_facts_type_check_bool_invalid(self):
        """Context fact with wrong type for bool should error."""
        self.vocab('is_active', 'bool')
        self.contract['contexts'][0]['facts'] = {'is_active': 'yes'}  # String instead of bool
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('location') == 'context_facts']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['declared_type'], 'bool')
    
    def test_bool_when_condition_invalid(self):
        """Bool term with non-bool value in when should error."""
        self.vocab('flag', 'bool')
        self.rule('r1', when={'flag': 'yes'})  # String instead of bool
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('declared_type') == 'bool'
                  and d['witness'].get('condition_type') == 'when']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['value'], 'yes')
    
    def test_bool_exception_condition_invalid(self):
        """Bool term with non-bool value in exception should error."""
        self.vocab('enabled', 'bool')
        self.rule('r1', exceptions=[{'enabled': 1}])  # Int instead of bool
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('declared_type') == 'bool'
                  and d['witness'].get('condition_type') == 'exception']
        self.assertEqual(len(errors), 1)
    
    def test_workflow_when_type_check_enum(self):
        """Workflow.when with invalid enum value should error."""
        self.vocab('mode', 'enum', values=['test', 'prod'])
        self.rule('ad', literal='x')
        self.contract['workflows'] = [{
            'id': 'wf1',
            'advertisement_rule': 'ad',
            'when': {'mode': 'invalid'},  # Invalid enum value
            'goal': ['done'],
            'actions': []
        }]
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'TYPE_MISMATCH'
                  and d['witness'].get('condition_type') == 'workflow_when']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['witness']['value'], 'invalid')
    
    def test_workflow_when_tracks_usage(self):
        """Term used in workflow.when should not be unused."""
        self.vocab('environment', 'enum', values=['dev', 'prod'])
        self.rule('ad', literal='x')
        self.contract['workflows'] = [{
            'id': 'wf1',
            'advertisement_rule': 'ad',
            'when': {'environment': 'prod'},
            'goal': ['done'],
            'actions': []
        }]
        result = self.run_lint()
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 0)
    
    # === Role checks (dots comment requirement) ===
    
    def test_controlled_action_role_in_ordering_rule(self):
        """Action IDs in ordering rules should have controlled_action role."""
        self.vocab('send_email', 'bool', role='controlled_action')
        self.vocab('log_event', 'bool', role='controlled_action')
        self.rule('ad', literal='x')
        self.contract['workflows'] = [{
            'id': 'wf',
            'advertisement_rule': 'ad',
            'goal': ['done'],
            'actions': [
                {'id': 'send_email', 'adds': ['sent']},
                {'id': 'log_event', 'adds': ['done']}
            ],
            'ordering_rules': [{
                'id': 'ord1',
                'kind': 'before',
                'actions': ['send_email', 'log_event'],
                'scope': {'entity': 'task', 'temporal': 'run'},
                'source': {'source_id': 's', 'start_line': 1, 'end_line': 1, 
                          'quote': 'The system must be secure.'},
                'assumptions': []
            }]
        }]
        # send_email and log_event should not trigger errors
        self.assertNotIn('ACTION_VOCABULARY_ROLE_MISMATCH', self.codes())
    
    def test_action_role_mismatch_in_ordering_rule(self):
        """Action IDs with wrong role in ordering rules should error."""
        self.vocab('send_email', 'bool', role='derived_fact')  # Wrong role
        self.rule('ad', literal='x')
        self.contract['workflows'] = [{
            'id': 'wf',
            'advertisement_rule': 'ad',
            'goal': ['done'],
            'actions': [{'id': 'send_email', 'adds': ['done']}],
            'ordering_rules': [{
                'id': 'ord1',
                'kind': 'at_most_once',
                'actions': ['send_email'],
                'scope': {'entity': 'task', 'temporal': 'run'},
                'source': {'source_id': 's', 'start_line': 1, 'end_line': 1,
                          'quote': 'The system must be secure.'},
                'assumptions': []
            }]
        }]
        result = self.run_lint()
        role_errors = [d for d in result['diagnostics'] if d['code'] == 'ACTION_VOCABULARY_ROLE_MISMATCH']
        self.assertEqual(len(role_errors), 1)
        self.assertEqual(role_errors[0]['severity'], 'error')
        self.assertEqual(role_errors[0]['witness']['expected_role'], 'controlled_action')
        self.assertEqual(role_errors[0]['witness']['actual_role'], 'derived_fact')
    
    def test_action_not_in_vocabulary_no_role_error(self):
        """Actions not in vocabulary don't trigger role errors."""
        self.vocab('other_term', 'bool')  # Vocabulary exists but action isn't in it
        self.rule('ad', literal='x')
        self.contract['workflows'] = [{
            'id': 'wf',
            'advertisement_rule': 'ad',
            'goal': ['done'],
            'actions': [{'id': 'undefined_action', 'adds': ['done']}],
            'ordering_rules': [{
                'id': 'ord1',
                'kind': 'at_most_once',
                'actions': ['undefined_action'],
                'scope': {'entity': 'task', 'temporal': 'run'},
                'source': {'source_id': 's', 'start_line': 1, 'end_line': 1,
                          'quote': 'The system must be secure.'},
                'assumptions': []
            }]
        }]
        # Should not trigger ACTION_VOCABULARY_ROLE_MISMATCH
        self.assertNotIn('ACTION_VOCABULARY_ROLE_MISMATCH', self.codes())
    
    def test_controlled_action_used_as_boolean_error(self):
        """controlled_action ID used as boolean effect/clause should error."""
        self.vocab('send_email', 'bool', role='controlled_action')
        # Using it as a boolean effect - this is conflation
        self.rule('r1', literal='send_email', value=True)
        result = self.run_lint()
        errors = [d for d in result['diagnostics'] if d['code'] == 'ACTION_STATE_CONFLATION']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['severity'], 'error')
        self.assertEqual(errors[0]['witness']['action_id'], 'send_email')
        self.assertEqual(errors[0]['witness']['conflicting_usage'], 'bool_effect')
    
    # === Tests for dots requirements ===
    
    def test_overlapping_categories_not_error(self):
        """Overlapping categories (similar terms) should NOT error (dots req)."""
        self.vocab('personal_data', 'bool')
        self.vocab('sensitive_data', 'bool')
        self.vocab('private_info', 'bool')
        # These are similar/overlapping but distinct terms - should not error
        self.assertNotIn('AMBIGUOUS_SYNONYM', self.codes())
    
    def test_distinct_similar_names_not_error(self):
        """Distinct terms with similar names should NOT error (dots req)."""
        self.vocab('user_authenticated', 'bool')
        self.vocab('user_authorized', 'bool')
        self.vocab('user_verified', 'bool')
        # Similar names but distinct meanings - should not error
        self.assertNotIn('AMBIGUOUS_SYNONYM', self.codes())
    
    def test_auto_declared_preserves_unknown_behavior(self):
        """Auto-declared legacy literals should preserve unknown activation (dots req)."""
        # Without vocabulary, missing facts cause UNRESOLVED_ACTIVATION
        self.rule('r1', when={'missing_fact': True})
        result = self.run_lint()
        self.assertIn('UNRESOLVED_ACTIVATION', self.codes())
        
        # Now add vocabulary but don't declare the literal used in the rule
        self.contract['vocabulary'] = [{'id': 'other_term', 'type': 'bool'}]
        self.rule('r2', literal='x')  # Uses 'x' which is not in vocab
        result2 = self.run_lint()
        # Should still get UNRESOLVED_ACTIVATION for missing facts
        self.assertIn('UNRESOLVED_ACTIVATION', [d['code'] for d in result2['diagnostics']])
        # And UNDEFINED_TERM for the auto-declared literal
        self.assertIn('UNDEFINED_TERM', [d['code'] for d in result2['diagnostics']])
    
    # === Additional field tests ===
    
    def test_vocabulary_with_all_fields(self):
        """Vocabulary entry with all fields."""
        self.vocab('timeout', 'int',
                   role='external_input',
                   unit='seconds',
                   values=['5', '10', '30'],
                   definition='Maximum wait time',
                   synonyms=['wait_duration'],
                   boundary_notes='Must be positive',
                   source_spans=[{
                       'source_id': 's',
                       'start_line': 1,
                       'end_line': 1,
                       'quote': 'The system must be secure.'
                   }])
        result = self.run_lint()
        # Should have UNUSED_VOCABULARY_ENTRY since we don't use 'timeout'
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 1)
    
    def test_vocabulary_source_span_must_match_quote(self):
        """Vocabulary source spans must exactly match their quotes."""
        self.contract['vocabulary'] = [{
            'id': 'secure',
            'type': 'bool',
            'source_spans': [{
                'source_id': 's',
                'start_line': 1,
                'end_line': 1,
                'quote': 'Wrong quote here.'
            }]
        }]
        with self.assertRaises(ContractError) as ctx:
            self.run_lint()
        self.assertIn('quote does not match', str(ctx.exception))
    
    def test_vocabulary_ids_must_be_unique(self):
        """Vocabulary entry IDs must be unique."""
        self.contract['vocabulary'] = [
            {'id': 'secure', 'type': 'bool'},
            {'id': 'secure', 'type': 'bool'}
        ]
        with self.assertRaises(ContractError) as ctx:
            self.run_lint()
        self.assertIn('unique', str(ctx.exception))
    
    def test_clause_literals_checked_for_vocabulary(self):
        """Literals in CNF clauses should be checked against vocabulary."""
        self.vocab('term1', 'bool')
        self.contract['rules'] = [{
            'id': 'cnf_rule',
            'source': {
                'source_id': 's',
                'start_line': 1,
                'end_line': 1,
                'quote': 'The system must be secure.'
            },
            'priority': 100,
            'kind': 'requirement',
            'when': {},
            'skills': [],
            'scope': {'entity': 'task', 'temporal': 'run'},
            'exceptions': [],
            'clause': [
                {'literal': 'authenticated', 'value': True},
                {'literal': 'authorized', 'value': True}
            ]
        }]
        result = self.run_lint()
        undefined = [d for d in result['diagnostics'] if d['code'] == 'UNDEFINED_TERM']
        # Should have UNDEFINED_TERM for 'authenticated' and 'authorized'
        self.assertEqual(len(undefined), 2)
        terms = {d['witness']['term'] for d in undefined}
        self.assertEqual(terms, {'authenticated', 'authorized'})


if __name__ == '__main__':
    unittest.main()
