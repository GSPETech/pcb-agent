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
        return

    if "type" in schema:
        _check_type(instance, schema["type"], path)

    if "const" in schema:
        expected = schema["const"]
        if isinstance(instance, bool) != isinstance(expected, bool) or instance != expected:
            raise SchemaError(f"{path}: expected const {expected!r}")

    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list):
            raise SchemaError(f"{path}: enum must be array")
        if instance not in enum:
            raise SchemaError(f"{path}: value not in enum")

    if isinstance(instance, str):
        if "pattern" in schema:
            import re
            pat = schema["pattern"]
            if not isinstance(pat, str) or not re.search(pat, instance):
                raise SchemaError(f"{path}: string does not match pattern")
        if "minLength" in schema:
            minimum = schema["minLength"]
            if isinstance(minimum, int) and len(instance) < minimum:
                raise SchemaError(f"{path}: string shorter than minLength")
        if "maxLength" in schema:
            maximum = schema["maxLength"]
            if isinstance(maximum, int) and len(instance) > maximum:
                raise SchemaError(f"{path}: string longer than maxLength")

    if isinstance(instance, dict):
        if "required" in schema:
            required = schema["required"]
            if isinstance(required, list):
                for key in required:
                    if key not in instance:
                        raise SchemaError(f"{path}: missing required property {key!r}")

        if "properties" in schema:
            properties = schema["properties"]
            if isinstance(properties, dict):
                for key, sub in properties.items():
                    if key in instance:
                        _validate(instance[key], sub, root, f"{path}.{key}")

        pattern_props: dict[str, Any] = {}
        if "patternProperties" in schema:
            raw = schema["patternProperties"]
            if isinstance(raw, dict):
                pattern_props.update(raw)

        handled: set[str] = set()
        if isinstance(schema.get("properties"), dict):
            handled.update(schema["properties"].keys())

        import re as _re

        for key, value in instance.items():
            for pattern, sub in pattern_props.items():
                if _re.search(pattern, key):
                    _validate(value, sub, root, f"{path}.{key}")

        if "additionalProperties" in schema:
            extra = schema["additionalProperties"]
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
            for index, element in enumerate(instance):
                _validate(element, items_schema, root, f"{path}[{index}]")
        if "minItems" in schema:
            minimum = schema["minItems"]
            if isinstance(minimum, int) and len(instance) < minimum:
                raise SchemaError(f"{path}: array shorter than minItems")
        if "maxItems" in schema:
            maximum = schema["maxItems"]
            if isinstance(maximum, int) and len(instance) > maximum:
                raise SchemaError(f"{path}: array longer than maxItems")
        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for element in instance:
                key = json.dumps(element, sort_keys=True, default=str)
                if key in seen:
                    raise SchemaError(f"{path}: array items are not unique")
                seen.add(key)


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