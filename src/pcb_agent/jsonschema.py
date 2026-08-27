"""Minimal JSON Schema subset validator, standard library only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_ROOT = Path(__file__).resolve().parent.parent.parent / "schemas"

_TYPES: dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}

_NUMERIC_TYPES = {"integer", "number"}

_SUPPORTED = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "properties", "required", "additionalProperties",
    "patternProperties", "items", "enum", "const", "pattern",
    "minLength", "maxLength", "minItems", "maxItems", "uniqueItems",
})


class SchemaError(ValueError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    path = (SCHEMA_ROOT / name).resolve()
    if SCHEMA_ROOT.resolve() not in path.parents:
        raise SchemaError(f"schema path escapes schemas directory: {name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SchemaError(f"cannot read schema {name}: {error}") from error
    if not isinstance(data, dict):
        raise SchemaError(f"schema root must be object: {name}")
    return data


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right

    if left is None or right is None:
        return left is None and right is None

    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return left == right

    if type(left) is not type(right):
        return False

    if isinstance(left, list):
        return (
            len(left) == len(right)
            and all(_json_equal(a, b) for a, b in zip(left, right))
        )

    if isinstance(left, dict):
        return (
            left.keys() == right.keys()
            and all(_json_equal(left[key], right[key]) for key in left)
        )

    return left == right

def validate(instance: Any, schema: dict[str, Any], path: str = "<root>") -> None:
    _validate(instance, schema, schema, path)


def _validate(instance: Any, schema: Any, root: dict[str, Any], path: str) -> None:
    if isinstance(schema, bool):
        if not schema:
            raise SchemaError(f"{path}: schema is false")
        return

    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema fragment must be object or bool")

    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise SchemaError(
            f"{path}: unsupported schema keywords: {sorted(unknown)}"
        )

    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str):
            raise SchemaError(f"{path}: $ref must be a string")
        if not ref.startswith("#/$defs/"):
            raise SchemaError(f"{path}: only local #/$defs/ refs supported")
        name = ref[len("#/$defs/"):]
        defs = root.get("$defs")
        if not isinstance(defs, dict) or name not in defs:
            raise SchemaError(f"{path}: unresolved $ref {ref}")
        _validate(instance, defs[name], root, path)

    if "type" in schema:
        _check_type(instance, schema["type"], path)

    if "const" in schema:
        expected = schema["const"]
        if not _json_equal(instance, expected):
            raise SchemaError(f"{path}: expected const {expected!r}")

    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not enum:
            raise SchemaError(f"{path}: enum must be non-empty array")
        if not any(_json_equal(instance, val) for val in enum):
            raise SchemaError(f"{path}: value not in enum")

    if isinstance(instance, str):
        if "pattern" in schema:
            import re
            pat = schema["pattern"]
            if not isinstance(pat, str):
                raise SchemaError(f"{path}: pattern must be string")
            try:
                re.compile(pat)
            except re.error as e:
                raise SchemaError(f"{path}: invalid regex {pat}: {e}")
            if not re.search(pat, instance):
                raise SchemaError(f"{path}: string does not match pattern")
        if "minLength" in schema:
            minimum = schema["minLength"]
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
                raise SchemaError(f"{path}: minLength must be non-negative integer")
            if len(instance) < minimum:
                raise SchemaError(f"{path}: string shorter than minLength")
        if "maxLength" in schema:
            maximum = schema["maxLength"]
            if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
                raise SchemaError(f"{path}: maxLength must be non-negative integer")
            if len(instance) > maximum:
                raise SchemaError(f"{path}: string longer than maxLength")

    if isinstance(instance, dict):
        if "required" in schema:
            required = schema["required"]
            if not isinstance(required, list) or not required or any(not isinstance(k, str) for k in required) or len(set(required)) != len(required):
                raise SchemaError(f"{path}: required must be unique string array")
            for key in required:
                if key not in instance:
                    raise SchemaError(f"{path}: missing required property {key!r}")

        if "properties" in schema:
            properties = schema["properties"]
            if not isinstance(properties, dict):
                raise SchemaError(f"{path}: properties must be object")
            for key, sub in properties.items():
                if key in instance:
                    _validate(instance[key], sub, root, f"{path}.{key}")

        pattern_props: dict[str, Any] = {}
        if "patternProperties" in schema:
            raw = schema["patternProperties"]
            if not isinstance(raw, dict):
                raise SchemaError(f"{path}: patternProperties must be object")
            pattern_props.update(raw)

        handled: set[str] = set()
        if isinstance(schema.get("properties"), dict):
            handled.update(schema["properties"].keys())

        import re as _re

        for key, value in instance.items():
            for pattern, sub in pattern_props.items():
                try:
                    _re.compile(pattern)
                except _re.error as e:
                    raise SchemaError(f"{path}: invalid patternProperty regex {pattern}: {e}")
                if _re.search(pattern, key):
                    _validate(value, sub, root, f"{path}.{key}")

        if "additionalProperties" in schema:
            extra = schema["additionalProperties"]
            if not isinstance(extra, (bool, dict)):
                raise SchemaError(f"{path}: additionalProperties must be bool or object")
            extras = {k for k in instance.keys() if k not in handled and
                      not any(_re.search(p, k) for p in pattern_props)}
            if extra is False:
                if extras:
                    sample = sorted(extras)[:3]
                    raise SchemaError(
                        f"{path}: additional properties not allowed: {sample}"
                    )
            elif isinstance(extra, dict):
                for k in extras:
                    _validate(instance[k], extra, root, f"{path}.{k}")

    if isinstance(instance, list):
        if "items" in schema:
            items_schema = schema["items"]
            if not isinstance(items_schema, (bool, dict)):
                raise SchemaError(f"{path}: items must be bool or object")
            for index, element in enumerate(instance):
                _validate(element, items_schema, root, f"{path}[{index}]")
        if "minItems" in schema:
            minimum = schema["minItems"]
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
                raise SchemaError(f"{path}: minItems must be non-negative integer")
            if len(instance) < minimum:
                raise SchemaError(f"{path}: array shorter than minItems")
        if "maxItems" in schema:
            maximum = schema["maxItems"]
            if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
                raise SchemaError(f"{path}: maxItems must be non-negative integer")
            if len(instance) > maximum:
                raise SchemaError(f"{path}: array longer than maxItems")
        if "uniqueItems" in schema:
            if not isinstance(schema["uniqueItems"], bool):
                raise SchemaError(f"{path}: uniqueItems must be boolean")
            if schema["uniqueItems"]:
                for i, item in enumerate(instance):
                    if any(_json_equal(item, prior) for prior in instance[:i]):
                        raise SchemaError(f"{path}: array items are not unique")


def _check_type(instance: Any, type_value: Any, path: str) -> None:
    if isinstance(type_value, list):
        for variant in type_value:
            try:
                _check_type(instance, variant, path)
                return
            except SchemaError:
                continue
        raise SchemaError(f"{path}: type mismatch (any of {type_value})")
    if type_value not in _TYPES:
        raise SchemaError(f"{path}: unknown type {type_value!r}")
    if type_value in _NUMERIC_TYPES and isinstance(instance, bool):
        raise SchemaError(f"{path}: bool not accepted as {type_value}")
    expected = _TYPES[type_value]
    if not isinstance(instance, expected):
        raise SchemaError(f"{path}: expected {type_value}, got {type(instance).__name__}")


def collect_used_keywords(schema: dict[str, Any]) -> set[str]:
    used: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if not isinstance(node, dict):
            return
        used.update(node)
        for key, value in node.items():
            if key in {"$defs"}:
                walk(value)
            elif key in {"properties", "patternProperties", "items",
                          "additionalProperties"}:
                walk(value)

    walk(schema)
    return {k for k in used if k in _SUPPORTED - {"$schema", "$id", "title", "description"}}