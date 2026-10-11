#!/usr/bin/env python3
"""Mutation testing for ordering rules.

Disables each ordering rule check type in turn and verifies that at least
one test fails, proving the check is necessary.
"""
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

def run_tests():
    """Run ordering tests and return (passed, failed) counts."""
    result = subprocess.run(
        ['python3', '-m', 'unittest', 'tests.test_ordering', '-v'],
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    
    # Parse test results
    if 'FAILED' in output:
        # Extract failure count
        for line in output.split('\n'):
            if line.startswith('FAILED'):
                return False, output
    elif 'OK' in output:
        for line in output.split('\n'):
            if line.startswith('Ran'):
                return True, output
    
    return False, output

def mutate_ordering_check(kind):
    """Disable a specific ordering rule check by making it always return satisfied."""
    ordering_file = Path('prompt_skill_linter/ordering.py')
    content = ordering_file.read_text()
    
    # Find the check function and replace it to always return satisfied
    check_func = f'_check_{kind}'
    
    # Create a backup
    backup = ordering_file.with_suffix('.py.bak')
    shutil.copy(ordering_file, backup)
    
    # Inject early return at start of function
    lines = content.split('\n')
    new_lines = []
    in_target_func = False
    injected = False
    
    for line in lines:
        new_lines.append(line)
        if f'def {check_func}(' in line:
            in_target_func = True
        elif in_target_func and not injected and line.strip().startswith('"""'):
            # After docstring, inject early return
            pass
        elif in_target_func and not injected and not line.strip().startswith('"""') and not line.strip().startswith('#'):
            # Found first line of code after def, inject before it
            indent = len(line) - len(line.lstrip())
            new_lines.insert(-1, ' ' * indent + '# MUTATED: Always return satisfied')
            new_lines.insert(-1, ' ' * indent + 'return {')
            new_lines.insert(-1, ' ' * indent + '    "status": "satisfied",')
            new_lines.insert(-1, ' ' * indent + f'    "kind": "{kind.replace("_", "-")}",')
            new_lines.insert(-1, ' ' * indent + '    "search_exhaustive": search_exhaustive')
            new_lines.insert(-1, ' ' * indent + '}')
            injected = True
            in_target_func = False
    
    ordering_file.write_text('\n'.join(new_lines))
    return backup

def restore_from_backup(backup):
    """Restore original file from backup."""
    original = backup.with_suffix('.py')
    shutil.copy(backup, original)
    backup.unlink()

def main():
    print("Mutation Testing for Ordering Rules")
    print("=" * 60)
    print()
    
    # First, verify all tests pass with original code
    print("Baseline: Running tests with all checks enabled...")
    passed, output = run_tests()
    if not passed:
        print("BASELINE FAILED: Tests don't pass with original code!")
        print(output)
        return 1
    
    baseline_count = None
    for line in output.split('\n'):
        if line.startswith('Ran'):
            baseline_count = line.split()[1]
    
    print(f"✓ Baseline passed: {baseline_count} tests\n")
    
    # Test each mutation
    mutations = {
        'before': 'before rule check',
        'mutual_exclusion': 'mutual_exclusion rule check',
        'exactly_once': 'exactly_once rule check',
        'at_most_once': 'at_most_once rule check'
    }
    
    all_mutations_caught = True
    
    for kind, description in mutations.items():
        print(f"Testing mutation: Disabling {description}...")
        
        # Reinstall package to ensure changes take effect
        subprocess.run(
            ['python3', '-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '.'],
            capture_output=True
        )
        
        backup = mutate_ordering_check(kind)
        
        try:
            # Reinstall with mutation
            result = subprocess.run(
                ['python3', '-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '.'],
                capture_output=True
            )
            
            # Run tests
            passed, output = run_tests()
            
            if passed:
                print(f"  ✗ MUTATION NOT CAUGHT: Tests still pass!")
                print(f"    This suggests the {description} may not be tested.")
                all_mutations_caught = False
            else:
                # Count failures
                failed_tests = []
                for line in output.split('\n'):
                    if line.startswith('FAIL:') or line.startswith('ERROR:'):
                        test_name = line.split()[1] if len(line.split()) > 1 else 'unknown'
                        failed_tests.append(test_name)
                
                print(f"  ✓ Mutation caught: {len(failed_tests)} test(s) failed")
                for test in failed_tests[:3]:  # Show first 3
                    print(f"    - {test}")
                if len(failed_tests) > 3:
                    print(f"    ... and {len(failed_tests) - 3} more")
        
        finally:
            # Restore original
            restore_from_backup(backup)
            # Reinstall clean version
            subprocess.run(
                ['python3', '-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '.'],
                capture_output=True
            )
        
        print()
    
    if all_mutations_caught:
        print("=" * 60)
        print("SUCCESS: All mutations were caught by tests!")
        print("Each ordering rule check is necessary.")
        return 0
    else:
        print("=" * 60)
        print("WARNING: Some mutations were not caught.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
