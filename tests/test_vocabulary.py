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
    
    def test_empty_vocabulary_is_valid(self):
        """Empty vocabulary should not cause errors."""
        self.rule('r1', literal='secure')
        result = self.run_lint()
        # Should get UNDEFINED_TERM info diagnostic for auto-declared literal
        self.assertIn('UNDEFINED_TERM', self.codes())
        self.assertEqual(result['diagnostics'][0]['severity'], 'info')
    
    def test_declared_literal_has_no_warning(self):
        """Declared literals should not trigger UNDEFINED_TERM."""
        self.vocab('secure', 'bool')
        self.rule('r1', literal='secure')
        self.assertNotIn('UNDEFINED_TERM', self.codes())
    
    def test_undefined_literal_triggers_info_diagnostic(self):
        """Undeclared literals should trigger info-level UNDEFINED_TERM."""
        self.rule('r1', literal='authenticated')
        result = self.run_lint()
        diags = [d for d in result['diagnostics'] if d['code'] == 'UNDEFINED_TERM']
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]['severity'], 'info')
        self.assertEqual(diags[0]['witness']['literal'], 'authenticated')
        self.assertTrue(diags[0]['witness']['auto_declared'])
        self.assertEqual(diags[0]['witness']['inferred_type'], 'bool')
    
    def test_multiple_undefined_literals(self):
        """Each undefined literal should get its own diagnostic."""
        self.rule('r1', literal='secure')
        self.rule('r2', literal='authenticated')
        self.rule('r3', literal='authorized')
        result = self.run_lint()
        undefined = [d for d in result['diagnostics'] if d['code'] == 'UNDEFINED_TERM']
        self.assertEqual(len(undefined), 3)
        literals = {d['witness']['literal'] for d in undefined}
        self.assertEqual(literals, {'secure', 'authenticated', 'authorized'})
    
    def test_unused_vocabulary_entry(self):
        """Vocabulary entries never used should trigger info diagnostic."""
        self.vocab('obsolete_term', 'bool')
        result = self.run_lint()
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 1)
        self.assertEqual(unused[0]['witness']['term'], 'obsolete_term')
        self.assertEqual(unused[0]['severity'], 'info')
    
    def test_ambiguous_synonym_error(self):
        """Same synonym mapping to multiple terms should be an error."""
        self.vocab('personal_data', 'bool', synonyms=['PII'])
        self.vocab('protected_info', 'bool', synonyms=['PII'])
        result = self.run_lint()
        ambig = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM']
        self.assertEqual(len(ambig), 1)
        self.assertEqual(ambig[0]['severity'], 'error')
        self.assertEqual(ambig[0]['witness']['synonym'], 'PII')
        self.assertIn('personal_data', ambig[0]['witness']['conflicting_terms'])
        self.assertIn('protected_info', ambig[0]['witness']['conflicting_terms'])
    
    def test_synonym_uniqueness_across_terms(self):
        """Synonyms must be unique across all vocabulary entries."""
        self.vocab('term_a', 'bool', synonyms=['alias1', 'alias2'])
        self.vocab('term_b', 'bool', synonyms=['alias3', 'alias2'])
        result = self.run_lint()
        ambig = [d for d in result['diagnostics'] if d['code'] == 'AMBIGUOUS_SYNONYM']
        self.assertEqual(len(ambig), 1)
        self.assertEqual(ambig[0]['witness']['synonym'], 'alias2')
    
    def test_vocabulary_with_definition(self):
        """Vocabulary entries can have definitions."""
        self.vocab('secure', 'bool', definition='Free from unauthorized access or modification')
        self.rule('r1', literal='secure')
        self.assertNotIn('UNDEFINED_TERM', self.codes())
    
    def test_vocabulary_with_unit(self):
        """Vocabulary entries can have units."""
        self.vocab('timeout', 'int', unit='seconds')
        # Note: literals in rules are used in effect clauses as bool, 
        # so we don't test int literals in this version
        self.assertNotIn('AMBIGUOUS_SYNONYM', self.codes())
    
    def test_vocabulary_with_enum_values(self):
        """Vocabulary entries can have enum values."""
        self.vocab('status', 'enum', values=['pending', 'approved', 'rejected'])
        self.assertNotIn('AMBIGUOUS_SYNONYM', self.codes())
    
    def test_vocabulary_with_boundary_notes(self):
        """Vocabulary entries can have boundary notes."""
        self.vocab('sensitive', 'bool', 
                   boundary_notes='Includes PII, financial data, and health records')
        self.assertNotIn('AMBIGUOUS_SYNONYM', self.codes())
    
    def test_vocabulary_with_source_spans(self):
        """Vocabulary entries can reference source spans."""
        self.vocab('secure', 'bool', source_spans=[{
            'source_id': 's',
            'start_line': 1,
            'end_line': 1,
            'quote': 'The system must be secure.'
        }])
        self.rule('r1', literal='secure')
        self.assertNotIn('UNDEFINED_TERM', self.codes())
    
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
    
    def test_vocabulary_source_span_unknown_source(self):
        """Vocabulary source spans must reference known sources."""
        self.contract['vocabulary'] = [{
            'id': 'secure',
            'type': 'bool',
            'source_spans': [{
                'source_id': 'unknown',
                'start_line': 1,
                'end_line': 1,
                'quote': 'Text.'
            }]
        }]
        with self.assertRaises(ContractError) as ctx:
            self.run_lint()
        self.assertIn('unknown source', str(ctx.exception))
    
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
        self.assertEqual(len(undefined), 2)
        literals = {d['witness']['literal'] for d in undefined}
        self.assertEqual(literals, {'authenticated', 'authorized'})
    
    def test_declared_clause_literals_pass(self):
        """Declared literals in CNF clauses should not trigger warnings."""
        self.vocab('authenticated', 'bool')
        self.vocab('authorized', 'bool')
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
        self.assertNotIn('UNDEFINED_TERM', self.codes())
    
    def test_multiple_rules_using_same_undefined_literal(self):
        """Multiple rules using same undefined literal should list all rules."""
        self.rule('r1', literal='secure')
        self.rule('r2', literal='secure')
        self.rule('r3', literal='secure')
        result = self.run_lint()
        undefined = [d for d in result['diagnostics'] if d['code'] == 'UNDEFINED_TERM']
        self.assertEqual(len(undefined), 1)
        self.assertEqual(len(undefined[0]['witness']['used_in_rules']), 3)
    
    def test_vocabulary_with_all_fields(self):
        """Vocabulary entry with all optional fields."""
        self.vocab('timeout', 'int',
                   unit='seconds',
                   values=['5', '10', '30'],
                   definition='Maximum wait time before giving up',
                   synonyms=['wait_duration', 'max_wait'],
                   boundary_notes='Must be positive; zero means no timeout',
                   source_spans=[{
                       'source_id': 's',
                       'start_line': 1,
                       'end_line': 1,
                       'quote': 'The system must be secure.'
                   }])
        # Just verify it validates correctly
        result = self.run_lint()
        # Should have UNUSED_VOCABULARY_ENTRY since we don't use 'timeout'
        unused = [d for d in result['diagnostics'] if d['code'] == 'UNUSED_VOCABULARY_ENTRY']
        self.assertEqual(len(unused), 1)


if __name__ == '__main__':
    unittest.main()
