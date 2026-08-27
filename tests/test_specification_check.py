"""Tests for the SPECIFICATION constraint-coverage check (phase A)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pcb_agent.specification_check import specification_failures


ROOT = Path(__file__).resolve().parent.parent


def _fixture_payloads() -> tuple[dict, dict, str]:
    spec = json.loads((ROOT / "fixtures" / "valid-blinky" / "SPEC.json").read_text())
    acceptance = json.loads((ROOT / "fixtures" / "valid-blinky" / "ACCEPTANCE.json").read_text())
    source = (ROOT / "fixtures" / "valid-blinky" / "tests" / "blinky_test.zen").read_text(encoding="utf-8")
    return spec, acceptance, source


class SpecificationCoverageTests(unittest.TestCase):
    def test_valid_blinky_fixture_passes(self) -> None:
        spec, acceptance, source = _fixture_payloads()
        self.assertEqual(specification_failures(spec, acceptance, source), ())

    def test_invalid_value_fixture_passes_coverage(self) -> None:
        spec = json.loads((ROOT / "fixtures" / "invalid-value" / "SPEC.json").read_text())
        acceptance = json.loads((ROOT / "fixtures" / "invalid-value" / "ACCEPTANCE.json").read_text())
        source = (ROOT / "fixtures" / "invalid-value" / "tests" / "blinky_test.zen").read_text(encoding="utf-8")
        self.assertEqual(specification_failures(spec, acceptance, source), ())

    def test_missing_constraint_in_testbench(self) -> None:
        spec = json.loads((ROOT / "fixtures" / "valid-blinky" / "SPEC.json").read_text())
        acceptance = json.loads((ROOT / "fixtures" / "valid-blinky" / "ACCEPTANCE.json").read_text())
        failures = specification_failures(spec, acceptance, "no relevant string here")
        self.assertTrue(any("REQ-001" in f and "1kohm" in f for f in failures))

    def test_missing_test_function(self) -> None:
        spec, acceptance, _ = _fixture_payloads()
        failures = specification_failures(spec, acceptance, "def completely_unrelated(module, inputs): pass")
        self.assertTrue(any("BlinkyTest.component_value" in f for f in failures))

    def test_diode_build_only_for_constrained_requirement(self) -> None:
        spec, acceptance, source = _fixture_payloads()
        spec["requirements"][0]["constraints"] = {"value": "1kohm"}
        for item in acceptance["checks"]:
            item["kind"] = "diode_build"
            item.pop("test", None)
        failures = specification_failures(spec, acceptance, source)
        self.assertTrue(any("needs zener_test verification" in f for f in failures))

    def test_subject_not_in_testbench(self) -> None:
        spec, acceptance, _ = _fixture_payloads()
        spec["requirements"][0]["subject"] = "ZZ9"
        failures = specification_failures(spec, acceptance, "irrelevant body")
        self.assertTrue(any("ZZ9" in f for f in failures))


if __name__ == "__main__":
    unittest.main()