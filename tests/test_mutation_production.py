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
        
        # Empty contract: no mutants, score should be null
        self.assertEqual(output['statistics']['scorable_mutants'], 0)
        self.assertIsNone(output['statistics']['mutation_score'])
    
    def test_json_output_all_invalid_nonempty(self):
        """Test JSON output with nonempty all-invalid mutants."""
        # Contract with advertisement rule referenced by workflow
        # Deleting the rule makes workflow reference invalid
        span = {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Advertisement'}
        contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'contexts': [],
            'rules': [
                {
                    'id': 'adv_rule',
                    'source': span,
                    'priority': 100,
                    'kind': 'requirement',
                    'scope': {'entity': 'agent', 'temporal': 'session'}
                }
            ],
            'workflows': [
                {
                    'id': 'test_wf',
                    'initial': [],
                    'goal': [],
                    'advertisement_rule': 'adv_rule',  # References the rule
                    'actions': [
                        {
                            'id': 'test_action',
                            'requires': [],
                            'adds': [],
                            'removes': [],
                            'provenance': {'source_spans': [span], 'assumptions': []}
                        }
                    ],
                    'ordering_rules': []
                }
            ]
        }
        
        contract_path = Path(self.temp_dir) / 'invalid_contract.json'
        manifest_path = Path(self.temp_dir) / 'invalid_manifest.json'
        runtime_path = Path(self.temp_dir) / 'invalid_runtime.json'
        policy_path = Path(self.temp_dir) / 'policy.txt'
        
        contract_path.write_text(json.dumps(contract))
        manifest_path.write_text(json.dumps({'tools': {}}))
        runtime_path.write_text(json.dumps(self.runtime))
        policy_path.write_text('Advertisement\n')
        
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(contract_path),
             '--tools', str(manifest_path),
             '--runtime', str(runtime_path),
             '--format', 'json',
             '--mutate',
             '--operators', 'delete_rule'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        output = json.loads(result.stdout)
        
        # Nonempty all-invalid: 1 total, 1 invalid, 0 scorable, null score
        self.assertEqual(output['statistics']['total_mutants'], 1)
        self.assertEqual(output['statistics']['invalid'], 1)
        self.assertEqual(output['statistics']['scorable_mutants'], 0)
        self.assertIsNone(output['statistics']['mutation_score'])
    
    def test_text_output_all_invalid_nonempty(self):
        """Test text output with nonempty all-invalid shows N/A."""
        # Same contract as JSON test
        span = {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Advertisement'}
        contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'contexts': [],
            'rules': [
                {
                    'id': 'adv_rule',
                    'source': span,
                    'priority': 100,
                    'kind': 'requirement',
                    'scope': {'entity': 'agent', 'temporal': 'session'}
                }
            ],
            'workflows': [
                {
                    'id': 'test_wf',
                    'initial': [],
                    'goal': [],
                    'advertisement_rule': 'adv_rule',
                    'actions': [
                        {
                            'id': 'test_action',
                            'requires': [],
                            'adds': [],
                            'removes': [],
                            'provenance': {'source_spans': [span], 'assumptions': []}
                        }
                    ],
                    'ordering_rules': []
                }
            ]
        }
        
        contract_path = Path(self.temp_dir) / 'invalid_text_contract.json'
        manifest_path = Path(self.temp_dir) / 'invalid_text_manifest.json'
        runtime_path = Path(self.temp_dir) / 'invalid_text_runtime.json'
        policy_path = Path(self.temp_dir) / 'policy.txt'
        
        contract_path.write_text(json.dumps(contract))
        manifest_path.write_text(json.dumps({'tools': {}}))
        runtime_path.write_text(json.dumps(self.runtime))
        policy_path.write_text('Advertisement\n')
        
        result = subprocess.run(
            ['python3', '-m', 'prompt_skill_linter',
             str(contract_path),
             '--tools', str(manifest_path),
             '--runtime', str(runtime_path),
             '--format', 'text',
             '--mutate',
             '--operators', 'delete_rule'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        
        # Must contain "N/A" and "0 scorable mutants"
        self.assertIn('N/A', result.stdout)
        self.assertIn('0 scorable mutants', result.stdout)
    
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
        """Test JSON output with scorable but unkilled mutants produces 0.0."""
        contract_path = Path(self.temp_dir) / 'contract.json'
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        runtime_path = Path(self.temp_dir) / 'runtime.json'
        
        # Use flip_kind on zero_percent_contract to force exactly one valid survivor
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
             '--operators', 'flip_kind'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        output = json.loads(result.stdout)
        
        # Unconditional assertions: exactly one valid survivor
        self.assertEqual(output['statistics']['total_mutants'], 1)
        self.assertEqual(output['statistics']['survived'], 1)
        self.assertEqual(output['statistics']['killed'], 0)
        self.assertEqual(output['statistics']['scorable_mutants'], 1)
        self.assertEqual(output['statistics']['mutation_score'], 0.0)  # Genuine 0%, not null
    
    def test_text_output_genuine_zero_percent(self):
        """Test text output with genuine 0% shows 0.00%."""
        contract_path = Path(self.temp_dir) / 'contract.json'
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        runtime_path = Path(self.temp_dir) / 'runtime.json'
        
        # Use flip_kind to force exactly one valid survivor
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
             '--operators', 'flip_kind'],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
        
        # Unconditional assertions: must contain 0.00%, must not contain N/A
        self.assertIn('0.00%', result.stdout)
        self.assertNotIn('N/A', result.stdout)


class WitnessFieldProductionTests(unittest.TestCase):
    """Test witness field normalization through actual lint/classification."""
    
    def test_trace_violation_path_through_production(self):
        """Test that dropping precondition changes trace violation_path and is KILLED."""
        from prompt_skill_linter.engine import lint
        from prompt_skill_linter.mutate import generate_mutants, classify_mutant
        import json
        import tempfile
        from pathlib import Path
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        policy_path = Path(temp_dir) / 'policy.txt'
        policy_path.write_text('Action a at most once\n')
        
        # Contract with action_count trace assertion: a at most once
        # setup adds 'ready', action 'a' requires 'ready'
        # Original violation path: ['setup', 'a', 'a']
        span = {'source_id': 'policy', 'start_line': 1, 'end_line': 1, 'quote': 'Action a at most once'}
        contract = {
            'version': 1,
            'sources': [{'id': 'policy', 'path': 'policy.txt'}],
            'skills': [],
            'contexts': [
                {
                    'id': 'test_ctx',
                    'facts': {},
                    'active_skills': []
                }
            ],
            'rules': [
                {
                    'id': 'advertise',
                    'source': span,
                    'priority': 100,
                    'kind': 'requirement',
                    'scope': {'entity': 'test_ctx', 'temporal': 'one_run'}
                }
            ],
            'workflows': [
                {
                    'id': 'test_wf',
                    'initial': [],
                    'goal': ['done'],
                    'advertisement_rule': 'advertise',
                    'actions': [
                        {
                            'id': 'setup',
                            'requires': [],
                            'adds': ['ready'],
                            'removes': [],
                            'provenance': {'source_spans': [span], 'assumptions': []}
                        },
                        {
                            'id': 'a',
                            'requires': ['ready'],  # Precondition makes violation [setup, a, a]
                            'adds': ['done'],
                            'removes': [],
                            'provenance': {'source_spans': [span], 'assumptions': []}
                        }
                    ],
                    'ordering_rules': [],
                    'trace_assertions': [{
                        'id': 'max-one',
                        'kind': 'action_count',
                        'actions': ['a'],
                        'max_count': 1,
                        'source': span,
                        'assumptions': []
                    }]
                }
            ]
        }
        
        manifest = {'tools': {}}
        runtime = {'max_plan_steps': 20}
        
        # Lint original contract
        original_report = lint(contract, manifest, runtime, temp_dir)
        
        # Verify original violation_path is ['setup', 'a', 'a']
        trace_diags = [d for d in original_report['diagnostics'] if d['code'] == 'TRACE_ASSERTION_VIOLATED']
        self.assertEqual(len(trace_diags), 1)
        original_diag = trace_diags[0]
        self.assertEqual(original_diag['witness']['violation_path'], ['setup', 'a', 'a'])
        
        # Generate mutant: drop a's ready precondition
        mutants = generate_mutants(contract, manifest, operator_filter={'drop_precondition'})
        
        # Find the mutant that drops a's precondition (workflow 0, action 1, precond 0)
        target_mutant = None
        for m in mutants:
            if 'workflow_0_action_1_drop_precond_0' in m.id:
                target_mutant = m
                break
        
        self.assertIsNotNone(target_mutant, "Should find mutant that drops a's ready precondition")
        
        # Lint mutant contract
        mutant_report = lint(target_mutant.contract, manifest, runtime, temp_dir)
        
        # Verify mutant violation_path is ['a', 'a'] (no setup needed)
        mutant_trace_diags = [d for d in mutant_report['diagnostics'] if d['code'] == 'TRACE_ASSERTION_VIOLATED']
        self.assertEqual(len(mutant_trace_diags), 1)
        mutant_diag = mutant_trace_diags[0]
        self.assertEqual(mutant_diag['witness']['violation_path'], ['a', 'a'])
        
        # Verify same diagnostic code/rule/status
        self.assertEqual(original_diag['code'], mutant_diag['code'])
        self.assertEqual(original_diag['severity'], mutant_diag['severity'])
        
        # Classify mutant
        result = classify_mutant(target_mutant, original_report, mutant_report)
        
        # Should be KILLED because violation_path changed
        self.assertEqual(result.status, 'KILLED',
                        f"Mutant should be KILLED due to changed violation_path, got {result.status}")
        
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()
