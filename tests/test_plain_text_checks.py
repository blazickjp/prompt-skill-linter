"""Tests for plain text undefined terms and vague directives checks."""
import json
from pathlib import Path
import tempfile
import unittest

from prompt_skill_linter.engine import lint


class PlainTextChecksTests(unittest.TestCase):
    """Test plain text analysis for undefined terms and vague directives."""
    
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.contract = {
            'version': 1,
            'sources': [],
            'skills': [],
            'rules': [],
            'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}],
            'assumptions': []
        }
        self.tools = {'tools': {}}
        self.runtime = {}
    
    def add_source(self, name, content):
        """Add a source file."""
        path = self.root / name
        path.write_text(content, encoding='utf-8')
        src_id = f's{len(self.contract["sources"])}'
        self.contract['sources'].append({'id': src_id, 'path': name})
        return src_id
    
    def rule(self, rid, src_id, start_line, end_line, quote, **extra):
        """Create a rule with source reference."""
        r = {
            'id': rid,
            'source': {
                'source_id': src_id,
                'start_line': start_line,
                'end_line': end_line,
                'quote': quote
            },
            'priority': 10,
            'kind': 'requirement',
            'when': {},
            'skills': [],
            'scope': {'entity': 'task', 'temporal': 'run'},
            'exceptions': []
        }
        r.update(extra)
        self.contract['rules'].append(r)
        return r
    
    def run_lint(self):
        return lint(self.contract, self.tools, self.runtime, self.root)
    
    def codes(self):
        return [d['code'] for d in self.run_lint()['diagnostics']]
    
    # === Vague directive tests ===
    
    def test_vague_directive_concise(self):
        """Flag 'be concise' as vague."""
        src_id = self.add_source('prompt.txt', 'Be concise in your responses.\n')
        self.rule('r1', src_id, 1, 1, 'Be concise in your responses.')
        result = self.run_lint()
        vague = [d for d in result['diagnostics'] if d['code'] == 'VAGUE_DIRECTIVE']
        self.assertEqual(len(vague), 1)
        self.assertEqual(vague[0]['severity'], 'warning')
        self.assertEqual(vague[0]['witness']['term'], 'concise')
        self.assertIn('criterion', vague[0]['witness']['reason'])
    
    def test_vague_directive_appropriate(self):
        """Flag 'appropriate' as vague."""
        src_id = self.add_source('prompt.txt', 'Use appropriate formatting.\n')
        self.rule('r1', src_id, 1, 1, 'Use appropriate formatting.')
        result = self.run_lint()
        vague = [d for d in result['diagnostics'] if d['code'] == 'VAGUE_DIRECTIVE']
        self.assertEqual(len(vague), 1)
        self.assertEqual(vague[0]['witness']['term'], 'appropriate')
    
    def test_vague_directive_as_needed(self):
        """Flag 'as needed' as vague."""
        src_id = self.add_source('prompt.txt', 'Add details as needed.\n')
        self.rule('r1', src_id, 1, 1, 'Add details as needed.')
        result = self.run_lint()
        vague = [d for d in result['diagnostics'] if d['code'] == 'VAGUE_DIRECTIVE']
        self.assertEqual(len(vague), 1)
        self.assertEqual(vague[0]['witness']['term'], 'as needed')
    
    def test_vague_directive_if_relevant(self):
        """Flag 'if relevant' as vague."""
        src_id = self.add_source('prompt.txt', 'Include examples if relevant.\n')
        self.rule('r1', src_id, 1, 1, 'Include examples if relevant.')
        result = self.run_lint()
        vague = [d for d in result['diagnostics'] if d['code'] == 'VAGUE_DIRECTIVE']
        self.assertEqual(len(vague), 1)
        self.assertEqual(vague[0]['witness']['term'], 'if relevant')
    
    def test_vague_directive_detailed(self):
        """Flag 'detailed' as vague."""
        src_id = self.add_source('prompt.txt', 'Write detailed commit messages.\n')
        self.rule('r1', src_id, 1, 1, 'Write detailed commit messages.')
        result = self.run_lint()
        vague = [d for d in result['diagnostics'] if d['code'] == 'VAGUE_DIRECTIVE']
        self.assertEqual(len(vague), 1)
        self.assertEqual(vague[0]['witness']['term'], 'detailed')
    
    def test_no_vague_directive_specific(self):
        """Don't flag specific directives."""
        src_id = self.add_source('prompt.txt', 'Limit responses to 500 characters.\n')
        self.rule('r1', src_id, 1, 1, 'Limit responses to 500 characters.')
        self.assertNotIn('VAGUE_DIRECTIVE', self.codes())
    
    # === Undefined term tests ===
    
    def test_undefined_caps_term(self):
        """Flag undefined ALL_CAPS terms."""
        src_id = self.add_source('prompt.txt', 'The SEARCH section must match code.\n')
        self.rule('r1', src_id, 1, 1, 'The SEARCH section must match code.')
        result = self.run_lint()
        undefined = [d for d in result['diagnostics'] if d['code'] == 'UNDEFINED_TERM_PLAIN']
        self.assertEqual(len(undefined), 1)
        self.assertEqual(undefined[0]['witness']['term'], 'SEARCH')
        self.assertIn('defined', undefined[0]['witness']['reason'])
    
    def test_undefined_term_with_definition(self):
        """Don't flag terms that are defined."""
        src_id = self.add_source('prompt.txt', 
            'SEARCH means the code to find. Use the SEARCH section.\n')
        self.rule('r1', src_id, 1, 1, 
            'SEARCH means the code to find. Use the SEARCH section.')
        # Should not flag SEARCH since it's defined
        undefined = [d for d in self.run_lint()['diagnostics'] 
                     if d['code'] == 'UNDEFINED_TERM_PLAIN']
        self.assertEqual(len(undefined), 0)
    
    def test_common_caps_not_flagged(self):
        """Don't flag common acronyms like API, JSON, etc."""
        src_id = self.add_source('prompt.txt', 'Use the API for JSON data.\n')
        self.rule('r1', src_id, 1, 1, 'Use the API for JSON data.')
        self.assertNotIn('UNDEFINED_TERM_PLAIN', self.codes())
    
    def test_no_undefined_term_without_usage(self):
        """Don't flag capitalized terms that aren't used as known concepts."""
        src_id = self.add_source('prompt.txt', 'Consider EXAMPLE only.\n')
        self.rule('r1', src_id, 1, 1, 'Consider EXAMPLE only.')
        # "Consider EXAMPLE" doesn't match our usage patterns
        self.assertNotIn('UNDEFINED_TERM_PLAIN', self.codes())
    
    def test_no_false_positives_normal_text(self):
        """Don't flag normal text without vague directives or undefined terms."""
        src_id = self.add_source('prompt.txt', 
            'Return responses in JSON format with status code 200.\n')
        self.rule('r1', src_id, 1, 1, 
            'Return responses in JSON format with status code 200.')
        codes = self.codes()
        self.assertNotIn('VAGUE_DIRECTIVE', codes)
        self.assertNotIn('UNDEFINED_TERM_PLAIN', codes)
    
    def test_one_issue_per_rule(self):
        """Only report one issue per rule to keep noise low."""
        src_id = self.add_source('prompt.txt', 
            'Be concise and appropriate when using the SEARCH and REPLACE sections.\n')
        self.rule('r1', src_id, 1, 1, 
            'Be concise and appropriate when using the SEARCH and REPLACE sections.')
        result = self.run_lint()
        # Should get at most 2 issues (one vague, one undefined)
        issues = [d for d in result['diagnostics'] 
                  if d['code'] in ('VAGUE_DIRECTIVE', 'UNDEFINED_TERM_PLAIN')]
        self.assertLessEqual(len(issues), 2)


if __name__ == '__main__':
    unittest.main()
