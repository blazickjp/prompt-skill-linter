"""Dependency-free validator for the JSON Schema keywords used by this package.

This is deliberately not a general JSON Schema implementation.
"""
import json
from pathlib import Path


class ShapeError(ValueError):
    pass


def check(value, schema, path='$'):
    types = {'object': lambda v: isinstance(v, dict), 'array': lambda v: isinstance(v, list),
             'string': lambda v: isinstance(v, str), 'integer': lambda v: type(v) is int,
             'boolean': lambda v: type(v) is bool, 'null': lambda v: v is None}
    expected = schema.get('type')
    if expected:
        expected = [expected] if isinstance(expected, str) else expected
        if not any(types[t](value) for t in expected):
            raise ShapeError(f'{path}: expected {expected}')
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        raise ShapeError(f'{path}: expected {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        raise ShapeError(f'{path}: unsupported value {value!r}')
    if 'minimum' in schema and value < schema['minimum']:
        raise ShapeError(f'{path}: below minimum {schema["minimum"]}')
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                raise ShapeError(f'{path}: missing {key}')
        properties = schema.get('properties', {})
        extra = schema.get('additionalProperties', True)
        for key, item in value.items():
            if key in properties:
                check(item, properties[key], f'{path}.{key}')
            elif extra is False:
                raise ShapeError(f'{path}: unsupported field {key}')
            elif isinstance(extra, dict):
                check(item, extra, f'{path}.{key}')
    if isinstance(value, list) and 'items' in schema:
        for index, item in enumerate(value):
            check(item, schema['items'], f'{path}[{index}]')


def validate_shape(contract):
    schema = json.loads(Path(__file__).with_name('contract.schema.json').read_text())
    check(contract, schema)
