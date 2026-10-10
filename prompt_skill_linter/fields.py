"""Reviewed flat-record field-presence compatibility, without executing producers.

A declaration describes one data edge in one fixed entity/temporal scope. Fields
are literal top-level keys, not JSON paths, value types, or inferred English
references. Required producer keys are guaranteed by the declaration; optional
keys may be present. A closed record admits no other keys. Adapters are explicit
sequential key copies/renames, never executable code or inferred aliases.
"""
from pathlib import Path


MAX_CONTRACTS = 32
MAX_FIELDS = 128
MAX_ADAPTERS = 32
MAX_FIELD_NAME = 256
MAX_SPANS = 32
MAX_ASSUMPTIONS = 32


class FieldContractError(ValueError):
    """An invalid or unsupported declaration, not a compatibility finding."""


def _names(values, label, maximum=MAX_FIELDS):
    if not isinstance(values, list) or len(values) > maximum:
        raise FieldContractError(f'{label} must be an array with at most {maximum} entries.')
    if any(not isinstance(v, str) or not v.strip() or len(v) > MAX_FIELD_NAME for v in values):
        raise FieldContractError(f'{label} entries must be nonempty strings of at most {MAX_FIELD_NAME} characters.')
    if len(values) != len(set(values)):
        raise FieldContractError(f'{label} must not contain duplicates.')


def _adapted_fields(declaration):
    required = set(declaration['producer']['required_fields'])
    optional = set(declaration['producer']['optional_fields'])
    for adapter in declaration['adapters']:
        source, target = adapter['from'], adapter['to']
        # Restrict the language to known sources and targets absent from the
        # declared key sets. Hidden collisions in open records are not analyzed.
        # Optional origins stay optional, even through several adapters.
        if source not in required | optional:
            raise FieldContractError('Adapter source must be a declared key available at this step.')
        if target in required | optional:
            raise FieldContractError('Adapter target must be absent from declared keys; declared-key overwrites and identity adapters are unsupported.')
        destination = required if source in required else optional
        destination.add(target)
        if adapter['kind'] == 'rename':
            destination.remove(source)
    return required, optional


def validate_field_contracts(contract, root):
    """Validate bounded semantics and exact source spans after shape validation."""
    declarations = contract.get('field_contracts', [])
    if len(declarations) > MAX_CONTRACTS or len(declarations) * len(contract['contexts']) > 256:
        raise FieldContractError('Field analysis supports 32 contracts and 256 contract/context pairs per bundle.')
    ids = [declaration['id'] for declaration in declarations]
    if any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise FieldContractError('Field contract IDs must be unique nonempty strings.')
    used_ids = {rule['id'] for rule in contract['rules']}
    used_ids.update(assertion['id'] for workflow in contract.get('workflows', [])
                    for assertion in workflow.get('trace_assertions', []))
    if set(ids) & used_ids:
        raise FieldContractError('Field contract IDs must be distinct from rule and trace assertion IDs.')
    sources = {source['id']: source for source in contract['sources']}
    skills = {skill['id'] for skill in contract.get('skills', [])}
    root = Path(root).resolve()
    source_lines = {}
    for declaration in declarations:
        _names(declaration.get('skills', []), 'field contract skills', 32)
        if not set(declaration.get('skills', [])) <= skills:
            raise FieldContractError('Field contract references an unknown skill.')
        if len(declaration.get('exceptions', [])) > 32 or any(
                len(condition) > 32 for condition in
                [declaration.get('when', {})] + declaration.get('exceptions', [])):
            raise FieldContractError('Field activation supports at most 32 exceptions and 32 facts per condition.')
        for value in declaration['scope'].values():
            if not value.strip() or len(value) > MAX_FIELD_NAME:
                raise FieldContractError('Field contract scope requires nonempty bounded entity and temporal names.')
        _names(declaration['assumptions'], 'field contract assumptions', MAX_ASSUMPTIONS)
        for side in ('producer', 'consumer'):
            record = declaration[side]
            _names(record['required_fields'], side + '.required_fields')
            _names(record['optional_fields'], side + '.optional_fields')
            if set(record['required_fields']) & set(record['optional_fields']):
                raise FieldContractError('Required and optional field sets must be disjoint.')
            if len(record['required_fields']) + len(record['optional_fields']) > MAX_FIELDS:
                raise FieldContractError(f'{side} supports at most {MAX_FIELDS} distinct fields.')
        adapters = declaration['adapters']
        if len(adapters) > MAX_ADAPTERS:
            raise FieldContractError(f'At most {MAX_ADAPTERS} field adapters are supported.')
        for adapter in adapters:
            _names([adapter['from'], adapter['to']], 'adapter fields', 2)
        _adapted_fields(declaration)
        for holder in [declaration['producer'], declaration['consumer']] + adapters:
            provenance = holder['provenance']
            spans = provenance['source_spans']
            if not 1 <= len(spans) <= MAX_SPANS:
                raise FieldContractError(f'Field provenance requires 1 to {MAX_SPANS} source spans.')
            _names(provenance['assumptions'], 'field provenance assumptions', MAX_ASSUMPTIONS)
            for span in spans:
                if span['source_id'] not in sources:
                    raise FieldContractError('Field provenance references an unknown source.')
                path = (root / sources[span['source_id']]['path']).resolve()
                if not path.is_relative_to(root):
                    raise FieldContractError('Field provenance source must stay within the contract directory.')
                if path not in source_lines:
                    try:
                        if path.stat().st_size > 1_500_000:
                            raise FieldContractError('Field provenance source exceeds the analysis limit.')
                        source_lines[path] = path.read_text(encoding='utf-8').splitlines()
                    except (OSError, UnicodeError) as exc:
                        raise FieldContractError('Cannot read field provenance source.') from exc
                lines = source_lines[path]
                start, end = span['start_line'], span['end_line']
                if not 1 <= start <= end <= len(lines) or span['quote'] != '\n'.join(lines[start - 1:end]):
                    raise FieldContractError('Field provenance quote does not match its exact line span.')


def check_field_presence(declaration):
    """Exact key-set reasoning conditional on a validated, active declaration.

    Optional consumer reads make no presence demand. A guaranteed producer key
    satisfies a required read even for an open record. A required consumer key
    that is optional at the producer, or undeclared in an open producer, is
    unknown. Only absence from a closed record establishes incompatibility.
    """
    required, optional = _adapted_fields(declaration)
    demand = set(declaration['consumer']['required_fields'])
    possible = required | optional
    # Retain explicit removals as evidence, but conservatively keep all missing
    # demands unknown for open producers. Exact absence is closed-record only.
    removed = set()
    for adapter in declaration['adapters']:
        removed.discard(adapter['to'])
        if adapter['kind'] == 'rename':
            removed.add(adapter['from'])
    absent = demand - possible if not declaration['producer']['additional_fields'] else set()
    uncertain = demand - required - absent
    return {
        'status': 'incompatible' if absent else 'unknown' if uncertain else 'compatible',
        'missing_required_fields': sorted(absent),
        'uncertain_required_fields': sorted(uncertain),
        'guaranteed_fields_after_adapters': sorted(required),
        'optional_fields_after_adapters': sorted(optional),
        'explicitly_removed_fields': sorted(removed),
        'additional_fields': declaration['producer']['additional_fields'],
        'optional_consumer_fields': list(declaration['consumer']['optional_fields']),
        'presence_only': True,
    }
