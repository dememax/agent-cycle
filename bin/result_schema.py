# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Strict final-result parsing and schema validation — agent-cycle project
"""Validate final results against the JSON Schema subset used by this project."""

from __future__ import annotations

import json
from typing import cast

SUPPORTED_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "anyOf",
        "enum",
        "items",
        "properties",
        "required",
        "type",
    }
)
SUPPORTED_TYPES = frozenset({"array", "boolean", "integer", "null", "object", "string"})


class StrictJSONError(ValueError):
    """JSON is not the single finite-valued object required by the contract."""


class SchemaError(ValueError):
    """The schema uses an unsupported or malformed construct."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _finite_number(value: str) -> object:
    raise StrictJSONError(f"non-finite number {value}")


def parse_object(text: str) -> dict[str, object]:
    """Parse exactly one strict JSON object, allowing surrounding whitespace."""
    try:
        value: object = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_finite_number,
        )
    except json.JSONDecodeError as error:
        raise StrictJSONError(str(error)) from error
    if not isinstance(value, dict):
        raise StrictJSONError("top-level JSON value is not an object")
    return cast("dict[str, object]", value)


def _schema_types(schema: dict[str, object], path: str) -> tuple[str, ...]:
    if "type" not in schema:
        return ()
    value = schema["type"]
    if isinstance(value, str):
        types = (value,)
    elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        types = tuple(value)
    else:
        raise SchemaError(f"{path}.type: expected a type name or non-empty list of type names")
    unsupported = sorted(set(types) - SUPPORTED_TYPES)
    if unsupported:
        raise SchemaError(f"{path}.type: unsupported type {unsupported[0]!r}")
    return types


def _schema_list(schema: dict[str, object], keyword: str, path: str) -> list[object] | None:
    if keyword not in schema:
        return None
    value = schema[keyword]
    if not isinstance(value, list):
        raise SchemaError(f"{path}.{keyword}: expected an array")
    return value


def check_schema(schema: object, path: str = "$") -> None:
    """Reject every schema construct outside the implemented subset."""
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: expected a schema object")
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS)
    if unknown:
        raise SchemaError(f"{path}: unsupported schema keyword {unknown[0]!r}")
    _schema_types(schema, path)

    enum = _schema_list(schema, "enum", path)
    if enum is not None and not enum:
        raise SchemaError(f"{path}.enum: expected a non-empty array")

    required = _schema_list(schema, "required", path)
    if required is not None and (
        not all(isinstance(item, str) for item in required) or len(set(required)) != len(required)
    ):
        raise SchemaError(f"{path}.required: expected unique property-name strings")

    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            raise SchemaError(f"{path}.properties: expected an object")
        for name, subschema in properties.items():
            check_schema(subschema, f"{path}.properties.{name}")

    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if not isinstance(additional, bool):
            raise SchemaError(f"{path}.additionalProperties: expected a boolean")

    if "items" in schema:
        check_schema(schema["items"], f"{path}.items")

    alternatives = _schema_list(schema, "anyOf", path)
    if alternatives is not None:
        if not alternatives:
            raise SchemaError(f"{path}.anyOf: expected a non-empty array")
        for index, alternative in enumerate(alternatives):
            check_schema(alternative, f"{path}.anyOf[{index}]")


def _matches_type(value: object, type_name: str) -> bool:
    if type_name == "null":
        return value is None
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "array":
        return isinstance(value, list)
    return isinstance(value, dict)


def _value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _property_path(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def _array_path(path: str, index: int) -> str:
    return f"{path}[{index}]" if path else f"[{index}]"


def _enum_contains(values: list[object], instance: object) -> bool:
    return any(type(candidate) is type(instance) and candidate == instance for candidate in values)


def validate(instance: object, schema: dict[str, object], path: str = "") -> list[str]:
    """Return every violation of a preflighted schema, with instance paths."""
    shown_path = path or "$"
    types = _schema_types(schema, "$validated")
    if types and not any(_matches_type(instance, type_name) for type_name in types):
        expected = " or ".join(types)
        return [f"{shown_path}: expected {expected}, got {_value_type(instance)}"]

    errors: list[str] = []
    enum = schema.get("enum")
    if isinstance(enum, list) and not _enum_contains(enum, instance):
        errors.append(f"{shown_path}: {instance!r} not in enum")

    required = schema.get("required")
    if isinstance(instance, dict) and isinstance(required, list):
        for name in required:
            if name not in instance:
                errors.append(f"{_property_path(path, str(name))}: required property is missing")

    properties = schema.get("properties")
    if isinstance(instance, dict):
        if isinstance(properties, dict):
            for name, subschema in properties.items():
                if name in instance:
                    errors.extend(
                        validate(
                            instance[name],
                            cast("dict[str, object]", subschema),
                            _property_path(path, str(name)),
                        )
                    )
        if schema.get("additionalProperties") is False:
            allowed = properties.keys() if isinstance(properties, dict) else set()
            for name in instance.keys() - allowed:
                errors.append(f"{_property_path(path, str(name))}: additional property is not allowed")

    items = schema.get("items")
    if isinstance(instance, list) and isinstance(items, dict):
        for index, item in enumerate(instance):
            errors.extend(validate(item, cast("dict[str, object]", items), _array_path(path, index)))

    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        branch_errors = [
            validate(instance, cast("dict[str, object]", alternative), path) for alternative in alternatives
        ]
        if all(branch for branch in branch_errors):
            for branch in branch_errors:
                for error in branch:
                    if error not in errors:
                        errors.append(error)
    return errors


def validate_result(instance: dict[str, object], schema: dict[str, object]) -> list[str]:
    """Preflight the complete schema, then recursively validate the result."""
    check_schema(schema)
    return validate(instance, schema)
