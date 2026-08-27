"""Tests for the contract-coverage check (CONNECTIVITY phase A)."""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from pcb_agent.connectivity import advisory_coverage_findings


ROOT = Path(__file__).resolve().parent.parent


VALID_BLINKY = json.loads(
    (ROOT / "fixtures" / "valid-blinky" / "expected-connectivity.json").read_text()
)
VALID_BLINKY_TEST = (
    ROOT / "fixtures" / "valid-blinky" / "tests" / "blinky_test.zen"
).read_text(encoding="utf-8")


class AdvisoryCoverageTests(unittest.TestCase):
    def test_valid_blinky_fixture_is_fully_covered(self) -> None:
        self.assertEqual(advisory_coverage_findings(VALID_BLINKY, VALID_BLINKY_TEST), ())

    def test_missing_net_reports_failure(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"VCC": {"members": ["R1.P1"]}, "GHOST": {"members": ["R1.P2"]}},
            "rules": {"required_power_nets": ["VCC"]},
        }
        source = textwrap.dedent(
            """
            TestBench(name="T", module=M, test_cases={"default": {}},
                      checks=[def check(module, inputs):
                check("R1" in module.components())
                check("VCC" in module.nets())
            end])
            """
        )
        failures = advisory_coverage_findings(contract, source)
        self.assertEqual(len(failures), 1)
        self.assertIn("GHOST", failures[0])

    def test_missing_component_reports_failure(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}, "R2": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P1"]}},
            "rules": {"required_power_nets": []},
        }
        source = "R1 is here. R3 is here."
        failures = advisory_coverage_findings(contract, source)
        self.assertTrue(any("R2" in f for f in failures))

    def test_required_power_nets_must_be_declared(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"VCC": {"members": ["R1.P1"]}},
            "rules": {"required_power_nets": ["VCC", "GROUND"]},
        }
        failures = advisory_coverage_findings(contract, "")
        self.assertTrue(any("GROUND" in f for f in failures))

    def test_empty_contract_plus_empty_source_returns_no_failures(self) -> None:
        contract = {
            "components": {},
            "nets": {},
            "rules": {"required_power_nets": []},
        }
        self.assertEqual(advisory_coverage_findings(contract, ""), ())

    def test_failures_are_sorted(self) -> None:
        contract = {
            "components": {"Z": {"kind": "x"}, "A": {"kind": "y"}},
            "nets": {"zeta": {"members": ["Z.1"]}, "alpha": {"members": ["A.1"]}},
            "rules": {"required_power_nets": []},
        }
        failures = advisory_coverage_findings(contract, "")
        self.assertEqual(failures, tuple(sorted(failures)))

    def test_advisory_is_satisfied_by_comments_and_substrings_showing_it_cannot_gate(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}, "LED1": {"kind": "led"}},
            "nets": {"VCC": {"members": ["R1.P1"]}, "GND": {"members": ["LED1.K"]}},
            "rules": {"required_power_nets": []},
        }
        source = textwrap.dedent(
            """
            # R1 and LED1 should connect to VCC and GND respectively
            def some_function():
                pass
            """
        )
        self.assertEqual(advisory_coverage_findings(contract, source), ())


if __name__ == "__main__":
    unittest.main()