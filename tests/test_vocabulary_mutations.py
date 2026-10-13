"""Mutation tests for vocabulary checks (issue #5).

This file demonstrates that each vocabulary check is necessary by showing
that removing the check's logic causes its corresponding test to fail.
"""
import subprocess
import sys
import tempfile
from pathlib import Path


def run_specific_test(test_name):
    """Run a specific test and return True if it passes."""
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', f'tests/test_vocabulary.py::{test_name}', '-xvs'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    return result.returncode == 0


def mutate_file(file_path, old_code, new_code):
    """Temporarily mutate a file for testing."""
    content = Path(file_path).read_text()
    mutated = content.replace(old_code, new_code)
    if mutated == content:
        raise ValueError(f"Mutation failed: code not found in {file_path}")
    Path(file_path).write_text(mutated)
    return content


def restore_file(file_path, original):
    """Restore original file content."""
    Path(file_path).write_text(original)


def test_mutation_ambiguous_synonym():
    """Mutation test: removing AMBIGUOUS_SYNONYM checks should fail tests."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for synonym = own id
    check_code = '''            if syn == term['id']:
                diagnostics.append(diagnostic('AMBIGUOUS_SYNONYM', 'exact', 'error', [], {},
                    {'synonym': syn, 'reason': 'synonym_equals_own_id', 'term': term['id']}))
            # Check if synonym equals another entry's id
            elif syn in all_term_ids:'''
    
    # Mutated version that removes the check
    mutated_code = '''            # Mutation: removed synonym_equals_own_id check
            if syn in all_term_ids:'''
    
    print("\n=== Mutation Test 1: AMBIGUOUS_SYNONYM (own id) ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_ambiguous_synonym_equals_own_id'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing AMBIGUOUS_SYNONYM own-id check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_ambiguous_synonym_equals_own_id'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_undefined_term():
    """Mutation test: removing UNDEFINED_TERM check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for undefined terms
    check_code = '''    # Check for undeclared literals (only when vocabulary exists)
    for lit in sorted(used_literals):
        if lit not in vocabulary:
            diagnostics.append(diagnostic('UNDEFINED_TERM', 'exact', 'info', [], {},
                {'literal': lit, 'used_in_rules': literal_usage[lit],
                 'auto_declared': True, 'inferred_type': 'bool'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''    # Mutation: removed UNDEFINED_TERM check
    for lit in sorted(used_literals):
        pass'''
    
    print("\n=== Mutation Test 2: UNDEFINED_TERM ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_undefined_literal_when_vocabulary_exists'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing UNDEFINED_TERM check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_undefined_literal_when_vocabulary_exists'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_unused_vocabulary():
    """Mutation test: removing UNUSED_VOCABULARY_ENTRY check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for unused vocabulary
    check_code = '''            if not used_in_ordering:
                diagnostics.append(diagnostic('UNUSED_VOCABULARY_ENTRY', 'exact', 'info', [], {},
                    {'term': term_id, 'reason': 'declared but never referenced'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''            pass  # Mutation: removed UNUSED_VOCABULARY_ENTRY check'''
    
    print("\n=== Mutation Test 3: UNUSED_VOCABULARY_ENTRY ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_unused_vocabulary_entry'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing UNUSED_VOCABULARY_ENTRY check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_unused_vocabulary_entry'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_type_mismatch():
    """Mutation test: removing TYPE_MISMATCH check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for type mismatches
    check_code = '''                if usage_type in ('bool_effect', 'bool_clause'):
                    # This literal is used as a boolean
                    if term_type != 'bool':
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'literal': lit, 'declared_type': term_type, 'used_as': 'bool',
                             'rule_id': rule_id, 'usage': usage_type}))'''
    
    # Mutated version that removes the check
    mutated_code = '''                pass  # Mutation: removed TYPE_MISMATCH check'''
    
    print("\n=== Mutation Test 4: TYPE_MISMATCH ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_type_mismatch_bool_declared_as_enum'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing TYPE_MISMATCH check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_type_mismatch_bool_declared_as_enum'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_action_role():
    """Mutation test: removing ACTION_VOCABULARY_ROLE_MISMATCH check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks action roles
    check_code = '''                if action_id in vocabulary:
                    entry = vocabulary[action_id]
                    if entry.get('role') != 'controlled_action':
                        diagnostics.append(diagnostic('ACTION_VOCABULARY_ROLE_MISMATCH', 'exact', 'error', 
                            [], {}, {
                                'action_id': action_id,
                                'expected_role': 'controlled_action',
                                'actual_role': entry.get('role'),
                                'ordering_rule': ordering_rule['id']
                            }))'''
    
    # Mutated version that removes the check
    mutated_code = '''                pass  # Mutation: removed ACTION_VOCABULARY_ROLE_MISMATCH check'''
    
    print("\n=== Mutation Test 5: ACTION_VOCABULARY_ROLE_MISMATCH ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_action_role_mismatch_in_ordering_rule'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing ACTION_VOCABULARY_ROLE_MISMATCH check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_action_role_mismatch_in_ordering_rule'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


if __name__ == '__main__':
    print("Running mutation tests for vocabulary checks...")
    print("=" * 60)
    
    test_mutation_ambiguous_synonym()
    test_mutation_undefined_term()
    test_mutation_unused_vocabulary()
    test_mutation_type_mismatch()
    test_mutation_action_role()
    
    print("\n" + "=" * 60)
    print("✓ All 5 mutation tests passed!")
    print("\nThis proves that each check is necessary:")
    print("1. AMBIGUOUS_SYNONYM - catches conflicting synonym mappings")
    print("2. UNDEFINED_TERM - catches literals used without vocabulary entries")
    print("3. UNUSED_VOCABULARY_ENTRY - catches vocabulary entries never referenced")
    print("4. TYPE_MISMATCH - catches bool/enum/int type misuse")
    print("5. ACTION_VOCABULARY_ROLE_MISMATCH - catches wrong roles in ordering rules")
