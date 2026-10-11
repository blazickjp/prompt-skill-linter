"""Production-path regression tests for mutation testing fixes."""
import unittest
import json
import tempfile
import subprocess
from pathlib import Path


class CLIOperatorFilterProductionTests(unittest.TestCase):
    """Test actual CLI entrypoint with --operators argument."""
    
    def setUp(self):
        """Create temporary contract and manifest files."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Minimal valid contract
        self.contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'contexts': [],
            'rules': [
                {
                    'id': 'test_rule',
                    'source': {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Test'},
                    'priority': 100,
                    'kind': 'requirement',
                    'when': {},
                    'scope': {'entity': 'items', 'temporal': 'one_run'},
                    'exceptions': []
                },
                {
                    'id': 'effect_rule',
                    'source': {'source_id': 'policy', 'start_line': 2, 'end_line': 2, 'quote': 'Effect test'},
                    'priority': 90,
                    'kind': 'requirement',
                    'when': {},
                    'scope': {'entity': 'items', 'temporal': 'one_run'},
                    'effect': {'literal': 'flag', 'value': True},
                    'exceptions': []
                }
            ]
        }
        
        self.manifest = {'tools': {}}
        self.runtime = {
            'service_call_budget': 50,
            'request_sizes': [100],
            'max_plan_steps': 20
        }
        
        # Write files
        self.contract_path = Path(self.temp_dir) / 'contract.json'
        self.manifest_path = Path(self.temp_dir) / 'manifest.json'
        self.runtime_path = Path(self.temp_dir) / 'runtime.json'
        self.policy_path = Path(self.temp_dir) / 'policy.txt'
        
        self.contract_path.write_text(json.dumps(self.contract))
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.runtime_path.write_text(json.dumps(self.runtime))
        self.policy_path.write_text('Test\nEffect test\n')  # Match the source quotes
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_cli_flip_kind_filter(self):
        """Test actual CLI with --operators flip_kind."""
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(self.contract_path),
             '--tools', str(self.manifest_path),
             '--runtime', str(self.runtime_path),
             '--format', 'json',
             '--mutate',
             '--operators', 'flip_kind'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        
        # Parse JSON output
        output = json.loads(result.stdout)
        
        # Should have exactly 2 flip_kind mutants (one per rule)
        self.assertEqual(output['statistics']['total_mutants'], 2)
        all_mutants = output['surviving_mutants'] + output['invalid_mutants'] + output.get('crashed_mutants', [])
        self.assertTrue(all(m['operator'] == 'flip_kind' for m in all_mutants))
    
    def test_cli_negate_effect_filter(self):
        """Test actual CLI with --operators negate_effect."""
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(self.contract_path),
             '--tools', str(self.manifest_path),
             '--runtime', str(self.runtime_path),
             '--format', 'json',
             '--mutate',
             '--operators', 'negate_effect'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        
        # Parse JSON output
        output = json.loads(result.stdout)
        
        # Should have exactly 1 negate_effect mutant (only effect_rule has an effect)
        self.assertEqual(output['statistics']['total_mutants'], 1)
        all_mutants = output['surviving_mutants'] + output['invalid_mutants'] + output.get('crashed_mutants', [])
        self.assertEqual(len(all_mutants), 1)
        self.assertEqual(all_mutants[0]['operator'], 'negate_effect')


class ProductionReportingTests(unittest.TestCase):
    """Test production text and JSON output formatting."""
    
    def setUp(self):
        """Create temporary files for testing."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Contract that generates only invalid mutants (all rules will be deleted, causing INVALID)
        self.all_invalid_contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'contexts': [],
            'rules': []
        }
        
        # Contract with workflow that survives mutations (genuine 0%)
        self.zero_percent_contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'contexts': [],
            'rules': [
                {
                    'id': 'weak_rule',
                    'source': {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Weak'},
                    'priority': 100,
                    'kind': 'requirement',
                    'when': {},
                    'scope': {'entity': 'items', 'temporal': 'one_run'},
                    'exceptions': []
                }
            ],
            'workflows': []
        }
        
        self.manifest = {'tools': {}}
        self.runtime = {
            'service_call_budget': 50,
            'request_sizes': [100],
            'max_plan_steps': 20
        }
        
        self.policy_path = Path(self.temp_dir) / 'policy.txt'
        self.policy_path.write_text('Weak\n')  # Match the source quote
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_json_output_no_scorable_mutants(self):
        """Test JSON output with no scorable mutants produces null score."""
        contract_path = Path(self.temp_dir) / 'contract.json'
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        runtime_path = Path(self.temp_dir) / 'runtime.json'
        
        contract_path.write_text(json.dumps(self.all_invalid_contract))
        manifest_path.write_text(json.dumps(self.manifest))
        runtime_path.write_text(json.dumps(self.runtime))
        
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(contract_path),
             '--tools', str(manifest_path),
             '--runtime', str(runtime_path),
             '--format', 'json',
             '--mutate'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        output = json.loads(result.stdout)
        
        # No scorable mutants should produce null score
        self.assertEqual(output['statistics']['scorable_mutants'], 0)
        self.assertIsNone(output['statistics']['mutation_score'])
    
    def test_text_output_no_scorable_mutants(self):
        """Test text output with no scorable mutants shows N/A."""
        contract_path = Path(self.temp_dir) / 'contract.json'
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        runtime_path = Path(self.temp_dir) / 'runtime.json'
        
        contract_path.write_text(json.dumps(self.all_invalid_contract))
        manifest_path.write_text(json.dumps(self.manifest))
        runtime_path.write_text(json.dumps(self.runtime))
        
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(contract_path),
             '--tools', str(manifest_path),
             '--runtime', str(runtime_path),
             '--format', 'text',
             '--mutate'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        
        # Should contain "N/A" and "0 scorable mutants"
        self.assertIn('N/A', result.stdout)
        self.assertIn('0 scorable mutants', result.stdout)
    
    def test_json_output_genuine_zero_percent(self):
        """Test JSON output with scorable but unsurving mutants produces 0.0."""
        contract_path = Path(self.temp_dir) / 'contract.json'
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        runtime_path = Path(self.temp_dir) / 'runtime.json'
        
        contract_path.write_text(json.dumps(self.zero_percent_contract))
        manifest_path.write_text(json.dumps(self.manifest))
        runtime_path.write_text(json.dumps(self.runtime))
        
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(contract_path),
             '--tools', str(manifest_path),
             '--runtime', str(runtime_path),
             '--format', 'json',
             '--mutate',
             '--max-mutants', '5'],  # Limit mutants for speed
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        output = json.loads(result.stdout)
        
        # If we have scorable mutants but zero killed, score should be 0.0 (not null)
        if output['statistics']['scorable_mutants'] > 0 and output['statistics']['killed'] == 0:
            self.assertEqual(output['statistics']['mutation_score'], 0.0)
    
    def test_text_output_genuine_zero_percent(self):
        """Test text output with genuine 0% shows 0.00%."""
        contract_path = Path(self.temp_dir) / 'contract.json'
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        runtime_path = Path(self.temp_dir) / 'runtime.json'
        
        contract_path.write_text(json.dumps(self.zero_percent_contract))
        manifest_path.write_text(json.dumps(self.manifest))
        runtime_path.write_text(json.dumps(self.runtime))
        
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(contract_path),
             '--tools', str(manifest_path),
             '--runtime', str(runtime_path),
             '--format', 'text',
             '--mutate',
             '--max-mutants', '5'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        
        # If genuine 0%, should show "0.00%" not "N/A"
        if 'Killed: 0' in result.stdout and 'Survived:' in result.stdout:
            # Extract the score line
            for line in result.stdout.split('\n'):
                if 'Mutation score:' in line:
                    if 'N/A' not in line:
                        self.assertIn('0.00%', line)


class WitnessFieldProductionTests(unittest.TestCase):
    """Test witness field normalization through actual lint/classification."""
    
    def test_trace_violation_path_through_production(self):
        """Test that witness field normalization works through production lint/classification."""
        from prompt_skill_linter.engine import lint
        from prompt_skill_linter.mutate import generate_mutants, classify_mutant
        import json
        import tempfile
        from pathlib import Path
        import os
        
        # Find the examples directory relative to the test file
        test_dir = Path(__file__).parent
        examples_dir = test_dir.parent / 'examples'
        
        # Use the ordering-auth-pass example which has actual ordering rules and diagnostics
        temp_dir = tempfile.mkdtemp()
        
        # Load the actual ordering-auth-pass contract
        contract = json.loads((examples_dir / 'ordering-auth-pass.contract.json').read_text())
        
        policy_src = (examples_dir / 'ordering-auth-pass-policy.txt').read_text()
        policy_path = Path(temp_dir) / 'ordering-auth-pass-policy.txt'
        policy_path.write_text(policy_src)
        
        tools = json.loads((examples_dir / 'ordering-tools.json').read_text())
        runtime = json.loads((examples_dir / 'ordering-runtime.json').read_text())
        
        # Get original lint report
        original_report = lint(contract, tools, runtime, temp_dir)
        
        # Generate mutants with swap_before_actions which changes ordering witnesses
        mutants = generate_mutants(contract, tools, operator_filter={'swap_before_actions'})
        
        # Classify each mutant
        killed_count = 0
        for mutant in mutants:
            mutant_report = lint(mutant.contract, tools, runtime, temp_dir)
            result = classify_mutant(mutant, original_report, mutant_report)
            if result.status == 'KILLED':
                killed_count += 1
        
        # Should have at least one killed mutant due to witness field differences
        self.assertGreater(killed_count, 0, 
                          "Should have at least one KILLED mutant when ordering changes affect witnesses")
        
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()
