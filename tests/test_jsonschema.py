"""Tests for the stdlib JSON Schema subset validator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pcb_agent.jsonschema import (
    SchemaError,
    collect_used_keywords,
    load_schema,
    validate,
)


ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"


class LoadSchemaTests(unittest.TestCase):
    def test_load_specification(self) -> None:
        schema = load_schema("specification.schema.json")
        self.assertIsInstance(schema, dict)

    def test_load_connectivity(self) -> None:
        schema = load_schema("connectivity.schema.json")
        self.assertIsInstance(schema, dict)

    def test_load_verification_report(self) -> None:
        schema = load_schema("verification-report.schema.json")
        self.assertIsInstance(schema, dict)

    def test_load_rejects_path_escape(self) -> None:
        with self.assertRaises(SchemaError):
            load_schema("../pyproject.toml")

    def test_load_rejects_missing(self) -> None:
        with self.assertRaises(SchemaError):
            load_schema("nonexistent.schema.json")


class KeywordSupportTests(unittest.TestCase):
    def test_all_used_keywords_are_supported(self) -> None:
        for name in ("connectivity.schema.json", "specification.schema.json",
                     "verification-report.schema.json", "acceptance.schema.json"):
            with self.subTest(schema=name):
                schema = load_schema(name)
                used = collect_used_keywords(schema)
                self.assertTrue(used, msg=f"no used keywords found in {name}")


def _generated_report_dict() -> dict:
    from pcb_agent.models import Check, CheckStatus, Severity, VerificationReport

    checks = (
        Check(
            "CONTRACT",
            CheckStatus.PASS,
            Severity.ERROR,
            "project contracts loaded and hashed",
            "harness",
            (),
            None,
            None,
            {},
            True,
        ),
    )
    report = VerificationReport(
        "schema-test",
        checks,
        profile="schematic",
        run_id="20260101T000000.000000Z-1",
        source_dirty=False,
        hashes={"SPEC.json": "sha256:" + "0" * 64},
        artifacts=(),
    )
    return json.loads(json.dumps(report.to_dict()))


class AcceptTests(unittest.TestCase):
    def test_valid_specification(self) -> None:
        schema = load_schema("specification.schema.json")
        instance = json.loads((ROOT / "fixtures" / "valid-blinky" / "SPEC.json").read_text())
        validate(instance, schema)

    def test_valid_connectivity(self) -> None:
        schema = load_schema("connectivity.schema.json")
        instance = json.loads((ROOT / "fixtures" / "valid-blinky" / "expected-connectivity.json").read_text())
        validate(instance, schema)

    def test_valid_verification_report(self) -> None:
        schema = load_schema("verification-report.schema.json")
        instance = _generated_report_dict()
        validate(instance, schema)


class RejectTests(unittest.TestCase):
    def test_const_string_mismatch(self) -> None:
        schema = {"const": "1"}
        with self.assertRaises(SchemaError):
            validate("2", schema)

    def test_required_property_missing(self) -> None:
        schema = {"type": "object", "required": ["x"]}
        with self.assertRaises(SchemaError) as ctx:
            validate({}, schema)
        self.assertIn("x", str(ctx.exception))

    def test_bool_rejected_for_integer(self) -> None:
        schema = {"type": "integer"}
        with self.assertRaises(SchemaError):
            validate(True, schema)

    def test_unique_items(self) -> None:
        schema = {"type": "array", "uniqueItems": True}
        with self.assertRaises(SchemaError):
            validate([1, 2, 1], schema)

    def test_pattern_mismatch(self) -> None:
        schema = {"type": "string", "pattern": "^[A-Z]+$"}
        with self.assertRaises(SchemaError):
            validate("abc", schema)

    def test_unknown_keyword_rejected(self) -> None:
        schema = {"type": "object", "madeUpKeyword": True}
        with self.assertRaises(SchemaError) as ctx:
            validate({}, schema)
        self.assertIn("madeUpKeyword", str(ctx.exception))

    def test_production_ready_true_rejected(self) -> None:
        schema = load_schema("verification-report.schema.json")
        report = _generated_report_dict()
        report["production_ready"] = True
        with self.assertRaises(SchemaError):
            validate(report, schema)

    def test_additional_properties_rejected(self) -> None:
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"a": {"type": "string"}}}
        with self.assertRaises(SchemaError):
            validate({"a": "x", "b": "y"}, schema)

    def test_min_length(self) -> None:
        schema = {"type": "string", "minLength": 3}
        with self.assertRaises(SchemaError):
            validate("ab", schema)

    def test_enum_membership(self) -> None:
        schema = {"type": "string", "enum": ["PASS", "FAIL"]}
        with self.assertRaises(SchemaError):
            validate("BLOCKED", schema)

    def test_enum_strict_boolean_type(self) -> None:
        schema = {"enum": [1]}
        with self.assertRaises(SchemaError):
            validate(True, schema)
        schema2 = {"enum": [True]}
        with self.assertRaises(SchemaError):
            validate(1, schema2)

    def test_ref_sibling_keywords_apply(self) -> None:
        schema = {
            "$defs": {"base": {"type": "string"}},
            "$ref": "#/$defs/base",
            "const": "expected"
        }
        validate("expected", schema)
        with self.assertRaises(SchemaError):
            validate("other", schema)
        with self.assertRaises(SchemaError):
            validate(1, schema)

    def test_unique_items_strict_numbers(self) -> None:
        schema = {"type": "array", "uniqueItems": True}
        with self.assertRaises(SchemaError):
            validate([1, 1.0], schema)
        validate([True, 1], schema)

    def test_malformed_schemas_are_rejected(self) -> None:
        cases = [
            ({"required": "x"}, {}),
            ({"minItems": "1"}, []),
            ({"patternProperties": []}, {}),
            ({"minLength": True}, "a"),
            ({"enum": {}}, 1),
        ]
        for schema, instance in cases:
            with self.subTest(schema=schema):
                with self.assertRaises(SchemaError):
                    validate(instance, schema)

    def test_json_integer_semantics(self) -> None:
        schema = {"type": "integer"}
        validate(1, schema)
        validate(1.0, schema)
        with self.assertRaises(SchemaError):
            validate(1.5, schema)
        with self.assertRaises(SchemaError):
            validate(True, schema)
        import math
        with self.assertRaises(SchemaError):
            validate(float("inf"), schema)
        with self.assertRaises(SchemaError):
            validate(math.nan, schema)

    def test_json_number_semantics(self) -> None:
        schema = {"type": "number"}
        validate(1, schema)
        validate(1.5, schema)
        with self.assertRaises(SchemaError):
            validate(True, schema)
        import math
        with self.assertRaises(SchemaError):
            validate(float("inf"), schema)
        with self.assertRaises(SchemaError):
            validate(math.nan, schema)

    def test_absent_optional_property_schema_checked(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "optional": {"minLength": -1}
            }
        }
        with self.assertRaises(SchemaError):
            validate({}, schema)


if __name__ == "__main__":
    unittest.main()