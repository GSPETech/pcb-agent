"""Tests for deterministic generated TestBench source."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Mapping
from pathlib import Path

from pcb_agent.generated_testbench import GeneratorError, render_connectivity_testbench, render_specification_testbench
from pcb_agent.state import ProjectState


class DummyProjectState:
    def __init__(self, source: str, connectivity: dict, specification: dict = None, acceptance: dict = None):
        self.source = source
        self.connectivity = connectivity
        self.specification = specification or {}
        self.acceptance = acceptance or {}


class ConnectivityGeneratorTests(unittest.TestCase):
    def test_renders_valid_blinky_connectivity(self) -> None:
        contract = {
            "components": {
                "R1": {"kind": "resistor"},
                "D1": {"kind": "led"},
            },
            "nets": {
                "VCC": {"members": ["R1.P1"]},
                "LED_ANODE": {"members": ["R1.P2", "D1.A"]},
                "GND": {"members": ["D1.K"]},
            },
            "rules": {
                "forbid_unlisted_members": True,
                "required_power_nets": ["VCC", "GND"],
            }
        }
        project = DummyProjectState("src/blinky.zen", contract)
        # Type ignore is fine for tests that duck type
        source = render_connectivity_testbench(project)  # type: ignore

        self.assertIn('M = Module("src/blinky.zen")', source)
        self.assertIn('("PcbAgentConnectivity__contract.R1.R", "1") in observed_VCC', source)
        self.assertIn('("PcbAgentConnectivity__contract.D1.LED", "A") in observed_LED_ANODE', source)
        self.assertIn('("PcbAgentConnectivity__contract.D1.LED", "K") in observed_GND', source)
        self.assertIn('check("VCC" in nets, \'missing power net VCC\')', source)
        self.assertIn('check(set(nets.keys()) == expected_net_names, \'unlisted nets found\')', source)
        self.assertIn('check(len(observed_LED_ANODE) == 2, \'unlisted members in LED_ANODE\')', source)

    def test_unsupported_component_kind_raises_error(self) -> None:
        contract = {
            "components": {"C1": {"kind": "capacitor"}},
            "nets": {"N1": {"members": ["C1.P1"]}},
            "rules": {}
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project)  # type: ignore
        self.assertIn("capacitor", str(ctx.exception))

    def test_unsupported_pin_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P3"]}},
            "rules": {}
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project)  # type: ignore
        self.assertIn("P3", str(ctx.exception))


class SpecificationGeneratorTests(unittest.TestCase):
    def test_renders_valid_blinky_specification(self) -> None:
        connectivity = {
            "components": {"R1": {"kind": "resistor"}},
        }
        specification = {
            "requirements": [{
                "id": "REQ-001",
                "type": "component",
                "subject": "R1",
                "constraints": {"value": "1kohm", "package": "0402"},
            }]
        }
        acceptance = {
            "checks": [{"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"}]
        }
        project = DummyProjectState("src/blinky.zen", connectivity, specification, acceptance)
        source = render_specification_testbench(project)  # type: ignore

        self.assertIn('check("PcbAgentSpecification__contract.R1.R" in components', source)
        self.assertIn('components["PcbAgentSpecification__contract.R1.R"].resistance.matches("1kohm")', source)
        self.assertIn('components["PcbAgentSpecification__contract.R1.R"].properties[\'package\'].value == "0402"', source)

    def test_unsupported_constraint_raises_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [{
                "id": "REQ-001",
                "type": "component",
                "subject": "R1",
                "constraints": {"made_up_property": "yes"},
            }]
        }
        acceptance = {"checks": [{"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"}]}
        project = DummyProjectState("src/blinky.zen", connectivity, specification, acceptance)
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project)  # type: ignore
        self.assertIn("made_up_property", str(ctx.exception))

    def test_missing_zener_test_raises_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [{
                "id": "REQ-001",
                "type": "component",
                "subject": "R1",
                "constraints": {"value": "1kohm"},
            }]
        }
        acceptance = {"checks": [{"id": "ACC-001", "requirement": "REQ-001", "kind": "diode_build"}]}
        project = DummyProjectState("src/blinky.zen", connectivity, specification, acceptance)
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project)  # type: ignore
        self.assertIn("zener_test", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()