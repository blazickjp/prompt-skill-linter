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
    check_code = '''    # Check for undeclared terms (only when vocabulary exists)
    for term in sorted(used_terms):
        if term not in vocabulary:
            usage_list = [f"{rid}:{loc}" for rid, loc in term_usage[term]]
            diagnostics.append(diagnostic('UNDEFINED_TERM', 'exact', 'info', [], {},
                {'term': term, 'usage': usage_list[:5],  # Limit to first 5
                 'auto_declared': True, 'inferred_type': 'bool'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''    # Mutation: removed UNDEFINED_TERM check
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
    
    # The code that checks for type mismatches in boolean usage
    check_code = '''            # All boolean uses should be consistent with the declared type
            for rule_id, usage_type, details in literal_types[lit]:
                if usage_type in ('bool_effect', 'bool_clause'):
                    # This term is used as a boolean
                    if term_type != 'bool':
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [], {},
                            {'literal': lit, 'declared_type': term_type, 'used_as': 'bool',
                             'rule_id': rule_id, 'usage': usage_type}))'''
    
    # Mutated version that removes the check
    mutated_code = '''            # Mutation: removed TYPE_MISMATCH check
            pass'''
    
    print("\n=== Mutation Test 4: TYPE_MISMATCH (bool) ===")
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


def test_mutation_enum_value():
    """Mutation test: removing enum TYPE_MISMATCH check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks enum values
    check_code = '''                # Type validation
                if term_type == 'enum':
                    declared_values = set(term.get('values', []))
                    if declared_values and fact_value not in declared_values:
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                            {'fact': fact_name, 'declared_type': 'enum', 'value': fact_value,
                             'declared_values': sorted(declared_values),
                             'rule_id': rule['id'], 'condition_type': 'when'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''                # Mutation: removed enum TYPE_MISMATCH check
                pass'''
    
    print("\n=== Mutation Test 6: TYPE_MISMATCH (enum) ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_enum_value_invalid_in_when_condition'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing enum TYPE_MISMATCH check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_enum_value_invalid_in_when_condition'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_int_value():
    """Mutation test: removing int TYPE_MISMATCH check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks int values
    check_code = '''                elif term_type == 'int':
                    if type(fact_value) not in (int, type(None)):
                        diagnostics.append(diagnostic('TYPE_MISMATCH', 'exact', 'error', [rule], {},
                            {'fact': fact_name, 'declared_type': 'int', 'value': fact_value,
                             'value_type': type(fact_value).__name__,
                             'rule_id': rule['id'], 'condition_type': 'when'}))'''
    
    # Mutated version that removes the check
    mutated_code = '''                # Mutation: removed int TYPE_MISMATCH check
                pass'''
    
    print("\n=== Mutation Test 7: TYPE_MISMATCH (int) ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_int_value_non_numeric_in_when'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing int TYPE_MISMATCH check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_int_value_non_numeric_in_when'), \
            "Test should fail after removing the check"
        print("✓ Test fails with check removed - mutation test passed!")
    finally:
        restore_file(engine_path, original)
        print("✓ Restored original file")


def test_mutation_action_state_conflation():
    """Mutation test: removing ACTION_STATE_CONFLATION check should fail its test."""
    engine_path = Path(__file__).parent.parent / 'prompt_skill_linter' / 'engine.py'
    
    # The code that checks for action/state conflation
    check_code = '''    # Check for controlled_action used as Boolean effect/clause
    for term_id, term in vocabulary.items():
        if term.get('role') == 'controlled_action':
            if term_id in literal_types:
                # This controlled_action is used as a boolean literal
                usages = literal_types[term_id]
                for rule_id, usage_type, _ in usages:
                    diagnostics.append(diagnostic('ACTION_STATE_CONFLATION', 'exact', 'error', [], {},
                        {'action_id': term_id, 'role': 'controlled_action',
                         'conflicting_usage': usage_type, 'rule_id': rule_id}))'''
    
    # Mutated version that removes the check
    mutated_code = '''    # Mutation: removed ACTION_STATE_CONFLATION check
    pass'''
    
    print("\n=== Mutation Test 8: ACTION_STATE_CONFLATION ===")
    print("Testing that the test passes with the check present...")
    assert run_specific_test('VocabularyTests::test_controlled_action_used_as_boolean_error'), \
        "Test should pass before mutation"
    print("✓ Test passes with check present")
    
    print("\nMutating: removing ACTION_STATE_CONFLATION check logic...")
    original = mutate_file(engine_path, check_code, mutated_code)
    
    try:
        print("Testing that the test fails with the check removed...")
        assert not run_specific_test('VocabularyTests::test_controlled_action_used_as_boolean_error'), \
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
    test_mutation_enum_value()
    test_mutation_int_value()
    test_mutation_action_state_conflation()
    
    print("\n" + "=" * 60)
    print("✓ All 8 mutation tests passed!")
    print("\nThis proves that each check is necessary:")
    print("1. AMBIGUOUS_SYNONYM - catches conflicting synonym mappings")
    print("2. UNDEFINED_TERM - catches terms used without vocabulary entries")
    print("3. UNUSED_VOCABULARY_ENTRY - catches vocabulary entries never referenced")
    print("4. TYPE_MISMATCH - catches bool/enum/int type misuse in effects/clauses")
    print("5. ACTION_VOCABULARY_ROLE_MISMATCH - catches wrong roles in ordering rules")
    print("6. TYPE_MISMATCH (enum) - catches enum values not in declared values list")
    print("7. TYPE_MISMATCH (int) - catches non-numeric values for int facts")
    print("8. ACTION_STATE_CONFLATION - catches controlled_action used as boolean")
