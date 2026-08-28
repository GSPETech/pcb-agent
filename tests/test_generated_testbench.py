"""Tests for deterministic generated TestBench source."""

from __future__ import annotations

import unittest
from typing import Any

from pcb_agent.generated_testbench import (
    ComponentAdapter,
    GeneratorError,
    _module_path_from_generated_test,
    adapter_for,
    build_adapter_registry,
    known_kinds,
    render_connectivity_testbench,
    render_specification_testbench,
    set_adapter_registry,
)
from pcb_agent.state import ProjectState


VERIFIED_VERSION = "0.4.34"
TEST_EVIDENCE = "sha256:" + "a" * 64


def _resistor_adapter() -> ComponentAdapter:
    return ComponentAdapter(
        instance_suffix="R",
        pins={"P1": "1", "P2": "2"},
        verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
        evidence_sha256=TEST_EVIDENCE,
        value_accessor="resistance",
        package_accessor="properties['package']",
        pullup_pin_pair=("P1", "P2"),
    )


class DummyProjectState:
    def __init__(
        self,
        source: str,
        connectivity: dict,
        specification: dict = None,
        acceptance: dict = None,
    ):
        self.source = source
        self.connectivity = connectivity
        self.specification = specification or {}
        self.acceptance = acceptance or {}


class ModulePathTests(unittest.TestCase):
    def test_resolves_relative_path_from_generated_test(self) -> None:
        self.assertEqual(
            _module_path_from_generated_test("src/blinky.zen"),
            "../src/blinky.zen",
        )
        self.assertEqual(
            _module_path_from_generated_test("boards/main.zen"),
            "../boards/main.zen",
        )

    def test_rejects_absolute_source(self) -> None:
        with self.assertRaises(GeneratorError):
            _module_path_from_generated_test("/etc/passwd")

    def test_rejects_dot_dot_within_source(self) -> None:
        with self.assertRaises(GeneratorError):
            _module_path_from_generated_test("src/../src/board.zen")

    def test_rejects_dot_only_segment(self) -> None:
        with self.assertRaises(GeneratorError):
            _module_path_from_generated_test("./source.zen")


class RegistryLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        set_adapter_registry({"resistor": _resistor_adapter()})

    def tearDown(self) -> None:
        set_adapter_registry({})

    def test_known_kinds_returns_registered(self) -> None:
        self.assertEqual(known_kinds(), frozenset({"resistor"}))

    def test_adapter_for_resistor(self) -> None:
        adapter = adapter_for("resistor", VERIFIED_VERSION)
        self.assertEqual(adapter.instance_suffix, "R")

    def test_adapter_for_unknown_pcbc_raises(self) -> None:
        with self.assertRaises(GeneratorError) as ctx:
            adapter_for("resistor", "0.99.0")
        self.assertIn("not verified", str(ctx.exception))

    def test_adapter_for_unknown_kind_raises(self) -> None:
        with self.assertRaises(GeneratorError) as ctx:
            adapter_for("capacitor", VERIFIED_VERSION)
        self.assertIn("unsupported", str(ctx.exception))


class ConnectivityGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        set_adapter_registry({"resistor": _resistor_adapter()})

    def tearDown(self) -> None:
        set_adapter_registry({})

    def test_renders_valid_blinky_connectivity(self) -> None:
        contract: dict[str, Any] = {
            "components": {
                "R1": {"kind": "resistor"},
            },
            "nets": {
                "VCC": {"members": ["R1.P1"]},
                "LED_ANODE": {"members": ["R1.P2"]},
                "GND": {"members": []},
            },
            "rules": {
                "forbid_unlisted_members": False,
                "required_power_nets": ["VCC", "GND"],
            },
        }
        project = DummyProjectState("src/blinky.zen", contract)
        source = render_connectivity_testbench(
            project, pcbc_version=VERIFIED_VERSION
        )

        self.assertIn('M = Module("../src/blinky.zen")', source)
        self.assertIn(
            'check("PcbAgentConnectivity__contract.R1.R" in components',
            source,
        )
        self.assertIn(
            'check(("PcbAgentConnectivity__contract.R1.R", "1") in observed_0',
            source,
        )
        self.assertIn('check("VCC" in nets', source)

    def test_unsupported_component_kind_raises_error(self) -> None:
        contract = {
            "components": {"C1": {"kind": "capacitor"}},
            "nets": {"N1": {"members": ["C1.P1"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("capacitor", str(ctx.exception))

    def test_unsupported_pin_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P3"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("P3", str(ctx.exception))

    def test_injection_via_net_name_does_not_reach_identifier(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {
                "PowerNet": {"members": ["R1.P1"]},
                "LedAnode": {"members": ["R1.P2"]},
            },
            "rules": {"forbid_unlisted_members": False},
        }
        project = DummyProjectState("src/blinky.zen", contract)
        source = render_connectivity_testbench(
            project, pcbc_version=VERIFIED_VERSION
        )
        self.assertNotIn("observed_PowerNet", source)
        self.assertNotIn("observed_LedAnode", source)
        self.assertIn("observed_0 =", source)
        self.assertIn("observed_1 =", source)
        self.assertIn('"PowerNet"', source)
        self.assertIn('"LedAnode"', source)

    def test_injection_via_component_ref_raises_error(self) -> None:
        contract = {
            "components": {"R1\"evil": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1\"evil.P1"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError):
            render_connectivity_testbench(project, pcbc_version=VERIFIED_VERSION)

    def test_unverified_pcbc_version_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P1"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, pcbc_version="0.99.0")
        self.assertIn("not verified", str(ctx.exception))

    def test_unknown_member_component_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["MISSING.P1"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("unknown component", str(ctx.exception))

    def test_unknown_required_power_net_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P1"]}},
            "rules": {"required_power_nets": ["GHOST"]},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("GHOST", str(ctx.exception))

    def test_required_pullup_raises_when_unsupported_kind(self) -> None:
        contract = {
            "components": {"D1": {"kind": "led"}},
            "nets": {
                "SDA": {
                    "members": ["D1.A"],
                    "required_pullup": {"component": "D1", "rail": "3V3"},
                },
            },
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("unverified kind led", str(ctx.exception))


class SpecificationGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        set_adapter_registry({"resistor": _resistor_adapter()})

    def tearDown(self) -> None:
        set_adapter_registry({})

    def test_renders_valid_blinky_specification(self) -> None:
        connectivity = {
            "components": {"R1": {"kind": "resistor"}},
        }
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "component",
                    "subject": "R1",
                    "constraints": {"value": "1kohm", "package": "0402"},
                }
            ]
        }
        acceptance = {
            "checks": [
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"}
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        source = render_specification_testbench(
            project, pcbc_version=VERIFIED_VERSION
        )

        self.assertIn('M = Module("../src/blinky.zen")', source)
        self.assertIn(
            'check("PcbAgentSpecification__contract.R1.R" in components',
            source,
        )
        self.assertIn('.resistance.matches("1kohm")', source)
        self.assertIn(
            "components[\"PcbAgentSpecification__contract.R1.R\"].properties['package'].value == \"0402\"",
            source,
        )

    def test_unsupported_constraint_raises_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "component",
                    "subject": "R1",
                    "constraints": {"made_up_property": "yes"},
                }
            ]
        }
        acceptance = {
            "checks": [
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"}
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("made_up_property", str(ctx.exception))

    def test_unasserted_connectivity_properties_raise_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor", "value": "10kohm"}}}
        specification = {"requirements": []}
        acceptance = {"checks": []}
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("value", str(ctx.exception))
        self.assertIn("has no specification requirement covering it", str(ctx.exception))

    def test_missing_zener_test_raises_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "component",
                    "subject": "R1",
                    "constraints": {"value": "1kohm"},
                }
            ]
        }
        acceptance = {
            "checks": [
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "diode_build"}
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project, pcbc_version=VERIFIED_VERSION)
        self.assertIn("zener_test", str(ctx.exception))

    def test_injection_via_subject_raises_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "component",
                    "subject": "R1\"evil",
                    "constraints": {"value": "1kohm"},
                }
            ]
        }
        acceptance = {
            "checks": [
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"}
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        with self.assertRaises(GeneratorError):
            render_specification_testbench(project, pcbc_version=VERIFIED_VERSION)


class AdapterRegistryBuildTests(unittest.TestCase):
    def test_build_rejects_empty_evidence(self) -> None:
        with self.assertRaises(ValueError):
            build_adapter_registry(
                [
                    ComponentAdapter(
                        instance_suffix="R",
                        pins={"P1": "1", "P2": "2"},
                        verified_pcbc_versions=frozenset({"0.4.34"}),
                        evidence_sha256="",
                    )
                ]
            )


if __name__ == "__main__":
    unittest.main()