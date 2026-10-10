"""Flat-record set reasoning and provenance/shape boundary tests."""
import copy
import itertools
import unittest

from prompt_skill_linter.engine import ContractError
from prompt_skill_linter.fields import check_field_presence
from prompt_skill_linter.service import analyze, export_bundle


def bundle():
    text = 'Synthetic producer returns link.\nSynthetic consumer requires detailsUrl.\nSynthetic copy link to detailsUrl.\n'
    def provenance(line):
        return {'source_spans': [{'source_id': 's', 'start_line': line, 'end_line': line,
                                 'quote': text.splitlines()[line-1]}], 'assumptions': []}
    field = {'id': 'edge', 'scope': {'entity': 'one-check-record', 'temporal': 'manual-branch'},
             'producer': {'required_fields': ['link'], 'optional_fields': [], 'additional_fields': False,
                          'provenance': provenance(1)},
             'consumer': {'required_fields': ['detailsUrl'], 'optional_fields': [], 'provenance': provenance(2)},
             'adapters': [], 'assumptions': ['Synthetic literal-key projection; no implicit alias.']}
    return {'contract': {'version': 1, 'sources': [{'id': 's', 'path': 'source.txt'}], 'rules': [],
                         'contexts': [{'id': 'c', 'facts': {}, 'active_skills': []}], 'field_contracts': [field]},
            'sources': {'s': text}, 'tools': {'tools': {}}, 'runtime': {}}


def edge(b): return b['contract']['field_contracts'][0]


def adapter(kind='copy', source='link', target='detailsUrl'):
    text = bundle()['sources']['s'].splitlines()[2]
    return {'kind': kind, 'from': source, 'to': target,
            'provenance': {'source_spans': [{'source_id': 's', 'start_line': 3, 'end_line': 3, 'quote': text}],
                           'assumptions': ['Reviewer-declared key operation.']}}


class FieldPresenceTests(unittest.TestCase):
    def status(self, b): return analyze(b)['field_checks'][0]['status']

    def test_closed_missing_required_key_is_exact_conditional_error(self):
        r = analyze(bundle()); check = r['field_checks'][0]; d = r['diagnostics'][0]
        self.assertEqual(check['status'], 'incompatible')
        self.assertEqual(check['missing_required_fields'], ['detailsUrl'])
        self.assertEqual(d['code'], 'REQUIRED_FIELD_NOT_PRODUCED')
        self.assertEqual(d['class'], 'exact')
        self.assertEqual(d['severity'], 'error')
        self.assertIn('reviewed closed-record projection', d['interpretation_status'])
        self.assertEqual(len(d['source_spans']), 2)
        self.assertEqual(d['resolved_priorities'], {})
        self.assertEqual(d['regression_case']['missing_required_fields'], ['detailsUrl'])
        self.assertFalse(check['runtime_observations_verified'])

    def test_open_missing_key_unknown(self):
        b = bundle(); edge(b)['producer']['additional_fields'] = True
        r = analyze(b)
        self.assertEqual(r['field_checks'][0]['status'], 'unknown')
        self.assertEqual(r['summary']['error'], 0)
        self.assertIn('field_presence', r['coverage']['incomplete_reasons'])

    def test_optional_producer_key_required_by_consumer_unknown(self):
        b = bundle(); edge(b)['producer']['optional_fields'] = ['detailsUrl']
        self.assertEqual(self.status(b), 'unknown')

    def test_missing_optional_consumer_key_is_compatible(self):
        b = bundle(); edge(b)['consumer'].update(required_fields=[], optional_fields=['detailsUrl'])
        self.assertEqual(self.status(b), 'compatible')
        self.assertEqual(analyze(b)['summary']['error'], 0)

    def test_guaranteed_key_compatible_in_both_closed_and_open_records(self):
        b = bundle(); edge(b)['consumer']['required_fields'] = ['link']
        for opened in (False, True):
            edge(b)['producer']['additional_fields'] = opened
            self.assertEqual(self.status(b), 'compatible')

    def test_copy_retains_source_and_rename_drops_it(self):
        b = bundle(); edge(b)['adapters'] = [adapter()]
        self.assertEqual(self.status(b), 'compatible')
        edge(b)['consumer']['required_fields'].append('link')
        self.assertEqual(self.status(b), 'compatible')
        edge(b)['adapters'][0]['kind'] = 'rename'
        r = analyze(b)['field_checks'][0]
        self.assertEqual(r['status'], 'incompatible')
        self.assertEqual(r['missing_required_fields'], ['link'])

    def test_optional_adapter_origin_stays_optional(self):
        b = bundle(); edge(b)['producer'].update(required_fields=[], optional_fields=['link'])
        edge(b)['adapters'] = [adapter()]
        self.assertEqual(self.status(b), 'unknown')

    def test_sequential_adapter_chain(self):
        b = bundle(); edge(b)['adapters'] = [adapter('rename', 'link', 'temporary'), adapter('copy', 'temporary', 'detailsUrl')]
        self.assertEqual(self.status(b), 'compatible')
        self.assertEqual(analyze(b)['field_checks'][0]['guaranteed_fields_after_adapters'], ['detailsUrl', 'temporary'])

    def test_open_record_removed_key_conservatively_unknown(self):
        b = bundle(); edge(b)['producer']['additional_fields'] = True
        edge(b)['adapters'] = [adapter('rename')]; edge(b)['consumer']['required_fields'] = ['link']
        self.assertEqual(self.status(b), 'unknown')

    def test_no_alias_case_folding_or_nested_path_inference(self):
        b = bundle()
        for demand in ['Link', 'item.link', 'link[0]', 'link/detailsUrl']:
            edge(b)['consumer']['required_fields'] = [demand]
            self.assertEqual(self.status(b), 'incompatible')
        edge(b)['producer']['required_fields'] = ['item.link']
        edge(b)['consumer']['required_fields'] = ['item.link']
        self.assertEqual(self.status(b), 'compatible')

    def test_missing_and_uncertain_demands_are_both_reported(self):
        b = bundle(); edge(b)['producer']['optional_fields'] = ['sometimes']
        edge(b)['consumer']['required_fields'].append('sometimes')
        r = analyze(b)['field_checks'][0]
        self.assertEqual(r['status'], 'incompatible')
        self.assertEqual(r['missing_required_fields'], ['detailsUrl'])
        self.assertEqual(r['uncertain_required_fields'], ['sometimes'])
        self.assertIn('field_presence', analyze(b)['coverage']['incomplete_reasons'])

    def test_context_activation_and_unknown_exception(self):
        b = bundle(); edge(b)['when'] = {'branch': 'manual'}
        self.assertEqual(self.status(b), 'unknown')
        b['contract']['contexts'][0]['facts'] = {'branch': 'helper'}
        self.assertEqual(self.status(b), 'inactive')
        self.assertEqual(analyze(b)['diagnostics'], [])
        b['contract']['contexts'][0]['facts']['branch'] = 'manual'
        self.assertEqual(self.status(b), 'incompatible')
        edge(b)['exceptions'] = [{'adapter_known': True}]
        self.assertEqual(self.status(b), 'unknown')
        b['contract']['contexts'][0]['facts']['adapter_known'] = True
        self.assertEqual(self.status(b), 'inactive')

    def test_bool_int_condition_mismatch_is_inactive(self):
        b = bundle(); edge(b)['when'] = {'branch': True}; b['contract']['contexts'][0]['facts'] = {'branch': 1}
        self.assertEqual(self.status(b), 'inactive')

    def test_context_results_and_skill_gate_are_independent(self):
        b = bundle(); edge(b)['skills'] = ['optional']
        b['contract']['skills'] = [{'id': 'optional'}]
        b['contract']['contexts'].append({'id': 'active', 'facts': {}, 'active_skills': ['optional']})
        r = analyze(b)
        self.assertEqual([c['status'] for c in r['field_checks']], ['inactive', 'incompatible'])
        self.assertEqual(r['diagnostics'][0]['triggering_context']['id'], 'active')

    def test_empty_declaration_is_preserved_no_english_inference(self):
        b = bundle(); b['contract'].pop('field_contracts')
        self.assertEqual(analyze(b)['field_checks'], [])
        self.assertEqual(analyze(b)['diagnostics'], [])

    def test_analysis_does_not_mutate_declaration(self):
        b = bundle(); before = copy.deepcopy(b)
        edge(b)['adapters'] = [adapter()]; before = copy.deepcopy(b)
        analyze(b); self.assertEqual(b, before)

    def test_exhaustive_small_set_oracle_864_declarations(self):
        # Independent concrete record sets over a tiny universe. Required reads
        # all pass => compatible; universally absent key => incompatible; mixed
        # optional presence => unknown. Open records use one undeclared key.
        names = ['a', 'b', 'c', 'd']
        for roles in itertools.product(('required', 'optional', 'absent'), repeat=3):
            for demands in itertools.product((False, True), repeat=4):
                for opened in (False, True):
                    d = edge(bundle())
                    req = {n for n, role in zip(names, roles) if role == 'required'}
                    opt = {n for n, role in zip(names, roles) if role == 'optional'}
                    demand = {n for n, selected in zip(names, demands) if selected}
                    d['producer'].update(required_fields=sorted(req), optional_fields=sorted(opt), additional_fields=opened)
                    d['consumer']['required_fields'] = sorted(demand)
                    variable = (set(names) - req) if opened else opt
                    records = [req | {n for n, selected in zip(sorted(variable), choices) if selected}
                               for choices in itertools.product((False, True), repeat=len(variable))]
                    expected = ('incompatible' if any(all(n not in r for r in records) for n in demand)
                                else 'compatible' if all(demand <= r for r in records) else 'unknown')
                    self.assertEqual(check_field_presence(d)['status'], expected, (roles, demand, opened))


class FieldValidationTests(unittest.TestCase):
    def test_strict_schema_rejects_unknown_and_wrong_typed_fields(self):
        edits = [lambda d: d.update(priority=4), lambda d: d['producer'].update(additional_fields='false'),
                 lambda d: d['consumer'].update(required_fields='link'), lambda d: d.update(adapters=[{'kind':'arbitrary_code'}]),
                 lambda d: d['producer'].update(value_type='url'), lambda d: d['scope'].update(entity=3)]
        for edit in edits:
            b = bundle(); edit(edge(b))
            with self.assertRaises(ContractError): analyze(b)

    def test_duplicate_and_overlapping_keys_rejected(self):
        for changes in [{'required_fields':['link','link']}, {'optional_fields':['link']}, {'required_fields':['']}]:
            b = bundle(); edge(b)['producer'].update(changes)
            with self.assertRaises(ContractError): analyze(b)

    def test_unsupported_adapter_source_overwrite_identity_rejected(self):
        for item in [adapter(source='missing'), adapter(target='link'), adapter(source='missing', target='link')]:
            b = bundle(); edge(b)['adapters'] = [item]
            with self.assertRaises(ContractError): analyze(b)
        b = bundle(); edge(b)['adapters'] = [adapter('rename'), adapter()]
        with self.assertRaises(ContractError): analyze(b)

    def test_exact_quote_line_source_and_adapter_provenance_required(self):
        for location, key, value in [('producer','quote','invented'), ('consumer','start_line',0),
                                     ('producer','source_id','missing'), ('consumer','end_line',999)]:
            b = bundle(); edge(b)[location]['provenance']['source_spans'][0][key] = value
            with self.assertRaises(ContractError): analyze(b)
        b = bundle(); edge(b)['adapters'] = [adapter()]
        edge(b)['adapters'][0]['provenance']['source_spans'] = []
        with self.assertRaises(ContractError): analyze(b)

    def test_source_traversal_rejected(self):
        b = bundle(); b['contract']['sources'][0]['path'] = '../outside.txt'
        with self.assertRaises(ContractError): analyze(b)

    def test_unreviewed_extraction_candidate_rejected(self):
        b = bundle(); b['contract']['interpretation'] = {'status':'candidate','method':'test','accepted_candidate_ids':[]}
        with self.assertRaises(ContractError): analyze(b)

    def test_limits_and_scope_validated(self):
        edits = [lambda d: d['producer'].update(required_fields=[str(i) for i in range(129)]),
                 lambda d: d['producer'].update(required_fields=['x'*257]),
                 lambda d: d.update(assumptions=['x']*33),
                 lambda d: d['scope'].update(temporal=''),
                 lambda d: d.update(id=' '),
                 lambda d: d.update(adapters=[adapter()]*33)]
        for edit in edits:
            b = bundle(); edit(edge(b))
            with self.assertRaises(ContractError): analyze(b)

    def test_contract_count_context_pair_and_unique_id_limits(self):
        for n, contexts in [(33,1), (32,9)]:
            b = bundle(); b['contract']['field_contracts'] = [dict(copy.deepcopy(edge(b)),id=f'e{i}') for i in range(n)]
            b['contract']['contexts'] = [{'id':f'c{i}','facts':{},'active_skills':[]} for i in range(contexts)]
            with self.assertRaises(ContractError): analyze(b)
        b = bundle(); b['contract']['field_contracts'].append(copy.deepcopy(edge(b)))
        with self.assertRaises(ContractError): analyze(b)

    def test_global_assertion_rule_id_collisions_rejected(self):
        b = bundle(); b['contract']['rules'] = [{'id':'edge','kind':'requirement','priority':0,
            'scope':edge(b)['scope'], 'source':edge(b)['consumer']['provenance']['source_spans'][0]}]
        with self.assertRaises(ContractError): analyze(b)

    def test_unknown_skill_cannot_silently_disable_edge(self):
        b = bundle(); edge(b)['skills'] = ['typo-skill']
        with self.assertRaisesRegex(ContractError, 'unknown skill'): analyze(b)

    def test_activation_shape_limits(self):
        b = bundle(); edge(b)['when'] = {str(i): True for i in range(33)}
        with self.assertRaises(ContractError): analyze(b)
        b = bundle(); edge(b)['exceptions'] = [{}] * 33
        with self.assertRaises(ContractError): analyze(b)


if __name__ == '__main__': unittest.main()
