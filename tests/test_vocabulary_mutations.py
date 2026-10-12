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
    """Mutation test: removing AMBIGUOUS_SYNONYM check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for ambiguous synonyms
    check_code = '''    for term in vocabulary.values():
        for syn in term.get('synonyms', []):
            if syn in synonym_to_term:
                diagnostics.append(diagnostic('AMBIGUOUS_SYNONYM', 'exact', 'error', [], {},
                    {'synonym': syn, 'conflicting_terms': sorted([synonym_to_term[syn], term['id']])}))
            else:
                synonym_to_term[syn] = term['id']'''
    
    # Mutated version that removes the check
    mutated_code = '''    for term in vocabulary.values():
        for syn in term.get('synonyms', []):
            synonym_to_term[syn] = term['id']  # Mutation: removed AMBIGUOUS_SYNONYM check'''
    
    print("\n=== Mutation Test 1: AMBIGUOUS_SYNONYM ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_ambiguous_synonym_error'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing AMBIGUOUS_SYNONYM check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_ambiguous_synonym_error'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_undefined_term():
    """Mutation test: removing UNDEFINED_TERM check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for undefined terms
    check_code = '''    for lit in sorted(used_literals):
        if lit not in vocabulary:
            diagnostics.append(diagnostic('UNDEFINED_TERM', 'exact', 'info', [], {},
                {'literal': lit, 'used_in_rules': literal_usage[lit],
                 'auto_declared': True, 'inferred_type': 'bool'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''    for lit in sorted(used_literals):
        pass  # Mutation: removed UNDEFINED_TERM check'''
    
    print("\n=== Mutation Test 2: UNDEFINED_TERM ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_undefined_literal_triggers_info_diagnostic'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing UNDEFINED_TERM check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_undefined_literal_triggers_info_diagnostic'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_unused_vocabulary():
    """Mutation test: removing UNUSED_VOCABULARY_ENTRY check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for unused vocabulary
    check_code = '''    for term_id in sorted(vocabulary.keys()):
        if term_id not in used_literals:
            diagnostics.append(diagnostic('UNUSED_VOCABULARY_ENTRY', 'exact', 'info', [], {},
                {'term': term_id, 'reason': 'declared but never referenced'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''    for term_id in sorted(vocabulary.keys()):
        pass  # Mutation: removed UNUSED_VOCABULARY_ENTRY check'''
    
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


if __name__ == '__main__':
    print("Running mutation tests for vocabulary checks...")
    print("=" * 60)
    
    test_mutation_ambiguous_synonym()
    test_mutation_undefined_term()
    test_mutation_unused_vocabulary()
    
    print("\n" + "=" * 60)
    print("✓ All 3 mutation tests passed!")
    print("\nThis proves that each check is necessary:")
    print("1. AMBIGUOUS_SYNONYM - catches conflicting synonym mappings")
    print("2. UNDEFINED_TERM - catches literals used without vocabulary entries")
    print("3. UNUSED_VOCABULARY_ENTRY - catches vocabulary entries never referenced")
