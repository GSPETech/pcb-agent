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
        kind="resistor",
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
            project, VERIFIED_VERSION
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
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("capacitor", str(ctx.exception))

    def test_unsupported_pin_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P3"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
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
            project, VERIFIED_VERSION
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
            render_connectivity_testbench(project, VERIFIED_VERSION)

    def test_unverified_pcbc_version_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P1"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, "0.99.0")
        self.assertIn("not verified", str(ctx.exception))

    def test_unknown_member_component_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["MISSING.P1"]}},
            "rules": {},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("unknown component", str(ctx.exception))

    def test_unknown_required_power_net_raises_error(self) -> None:
        contract = {
            "components": {"R1": {"kind": "resistor"}},
            "nets": {"N1": {"members": ["R1.P1"]}},
            "rules": {"required_power_nets": ["GHOST"]},
        }
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("GHOST", str(ctx.exception))

    def test_required_pullup_rejects_component_of_unverified_kind(self) -> None:
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
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("unverified kind led", str(ctx.exception))


class RequiredPullupTopologyTests(unittest.TestCase):
    """The pull-up gate must verify topology, not name existence."""

    def _contract(self) -> dict:
        return {
            "components": {
                "R1": {"kind": "resistor"},
                "R2": {"kind": "resistor"},
            },
            "nets": {
                "SDA": {
                    "members": ["R1.P1", "R2.P1"],
                    "required_pullup": {"component": "R1", "rail": "V3V3"},
                },
                "V3V3": {"members": ["R1.P2"]},
            },
            "rules": {},
        }

    def setUp(self) -> None:
        set_adapter_registry({"resistor": _resistor_adapter()})

    def tearDown(self) -> None:
        set_adapter_registry({})

    def test_renders_signal_and_rail_pin_assertions(self) -> None:
        project = DummyProjectState("src/board.zen", self._contract())
        source = render_connectivity_testbench(project, VERIFIED_VERSION)
        ref = "PcbAgentConnectivity__contract.R1.R"
        self.assertIn(f'pin_a_on_signal = ("{ref}", "1") in nets.get("SDA", [])', source)
        self.assertIn(f'pin_b_on_signal = ("{ref}", "2") in nets.get("SDA", [])', source)
        self.assertIn("check(pin_a_on_signal != pin_b_on_signal", source)
        self.assertIn(f'("{ref}", "2") in nets.get("V3V3", [])', source)
        self.assertIn(f'("{ref}", "1") in nets.get("V3V3", [])', source)

    def test_blocks_when_adapter_lacks_pullup_pin_pair(self) -> None:
        set_adapter_registry(
            {
                "resistor": ComponentAdapter(
                    kind="resistor",
                    instance_suffix="R",
                    pins={"P1": "1", "P2": "2"},
                    verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
                    evidence_sha256=TEST_EVIDENCE,
                    pullup_pin_pair=None,
                )
            }
        )
        project = DummyProjectState("src/board.zen", self._contract())
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("pullup_pin_pair", str(ctx.exception))

    def test_blocks_when_pullup_pin_pair_names_unknown_pin(self) -> None:
        set_adapter_registry(
            {
                "resistor": ComponentAdapter(
                    kind="resistor",
                    instance_suffix="R",
                    pins={"P1": "1", "P2": "2"},
                    verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
                    evidence_sha256=TEST_EVIDENCE,
                    pullup_pin_pair=("P1", "P9"),
                )
            }
        )
        project = DummyProjectState("src/board.zen", self._contract())
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("pullup pins", str(ctx.exception))

    def test_topology_ignores_pins_iteration_order(self) -> None:
        """The rendered pair must come from pullup_pin_pair, not dict order."""
        set_adapter_registry(
            {
                "resistor": ComponentAdapter(
                    kind="resistor",
                    instance_suffix="R",
                    pins={"P2": "2", "P1": "1", "P3": "3"},
                    verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
                    evidence_sha256=TEST_EVIDENCE,
                    pullup_pin_pair=("P1", "P2"),
                )
            }
        )
        project = DummyProjectState("src/board.zen", self._contract())
        source = render_connectivity_testbench(project, VERIFIED_VERSION)
        ref = "PcbAgentConnectivity__contract.R1.R"
        self.assertIn(f'pin_a_on_signal = ("{ref}", "1")', source)
        self.assertIn(f'pin_b_on_signal = ("{ref}", "2")', source)
        self.assertNotIn('"3") in nets.get("SDA"', source)

    def test_blocks_when_pullup_component_is_not_declared(self) -> None:
        contract = self._contract()
        contract["nets"]["SDA"]["required_pullup"]["component"] = "MISSING"
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("MISSING", str(ctx.exception))

    def test_blocks_when_rail_is_not_a_string(self) -> None:
        contract = self._contract()
        contract["nets"]["SDA"]["required_pullup"]["rail"] = ""
        project = DummyProjectState("src/board.zen", contract)
        with self.assertRaises(GeneratorError) as ctx:
            render_connectivity_testbench(project, VERIFIED_VERSION)
        self.assertIn("rail", str(ctx.exception))


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
            project, VERIFIED_VERSION
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
            render_specification_testbench(project, VERIFIED_VERSION)
        self.assertIn("made_up_property", str(ctx.exception))

    def test_unasserted_connectivity_properties_raise_error(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor", "value": "10kohm"}}}
        specification = {"requirements": []}
        acceptance = {"checks": []}
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project, VERIFIED_VERSION)
        self.assertIn("value", str(ctx.exception))
        self.assertIn("has no specification requirement covering it", str(ctx.exception))

    def test_mpn_constraint_is_always_blocked(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "component",
                    "subject": "R1",
                    "constraints": {"mpn": "RC0402FR-071KL"},
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
            render_specification_testbench(project, VERIFIED_VERSION)
        self.assertIn("mpn", str(ctx.exception))
        self.assertIn("unsupported", str(ctx.exception))

    def test_mpn_from_connectivity_is_always_blocked(self) -> None:
        connectivity = {
            "components": {"R1": {"kind": "resistor", "mpn": "RC0402FR-071KL"}}
        }
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
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"}
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project, VERIFIED_VERSION)
        self.assertIn("mpn", str(ctx.exception))

    def test_connectivity_requirement_rejects_value_constraint(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "connectivity",
                    "subject": "R1",
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
        with self.assertRaises(GeneratorError) as ctx:
            render_specification_testbench(project, VERIFIED_VERSION)
        self.assertIn("connectivity", str(ctx.exception))
        self.assertIn("value", str(ctx.exception))

    def test_connectivity_requirement_rejects_package_constraint(self) -> None:
        connectivity = {"components": {"R1": {"kind": "resistor"}}}
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "connectivity",
                    "subject": "R1",
                    "constraints": {"package": "0402"},
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
            render_specification_testbench(project, VERIFIED_VERSION)
        self.assertIn("package", str(ctx.exception))

    def test_connectivity_requirement_accepts_members_constraint(self) -> None:
        connectivity = {
            "components": {"R1": {"kind": "resistor", "value": "1kohm"}},
        }
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "connectivity",
                    "subject": "VCC",
                    "constraints": {"members": ["R1.P1"]},
                },
                {
                    "id": "REQ-002",
                    "type": "component",
                    "subject": "R1",
                    "constraints": {"value": "1kohm"},
                },
            ]
        }
        acceptance = {
            "checks": [
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"},
                {"id": "ACC-002", "requirement": "REQ-002", "kind": "zener_test"},
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        source = render_specification_testbench(
            project, VERIFIED_VERSION
        )
        self.assertIn('.resistance.matches("1kohm")', source)

    def test_assertion_count_matches_constraint_count(self) -> None:
        connectivity = {
            "components": {
                "R1": {"kind": "resistor"},
                "R2": {"kind": "resistor"},
            }
        }
        specification = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "type": "component",
                    "subject": "R1",
                    "constraints": {"value": "1kohm", "package": "0402"},
                },
                {
                    "id": "REQ-002",
                    "type": "component",
                    "subject": "R2",
                    "constraints": {"value": "4k7ohm"},
                },
            ]
        }
        acceptance = {
            "checks": [
                {"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test"},
                {"id": "ACC-002", "requirement": "REQ-002", "kind": "zener_test"},
            ]
        }
        project = DummyProjectState(
            "src/blinky.zen", connectivity, specification, acceptance
        )
        source = render_specification_testbench(
            project, VERIFIED_VERSION
        )
        # 3 constraints + 2 component presence assertions
        self.assertEqual(source.count("check("), 5)

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
            render_specification_testbench(project, VERIFIED_VERSION)
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
            render_specification_testbench(project, VERIFIED_VERSION)


class AdapterRegistryBuildTests(unittest.TestCase):
    def test_build_keys_by_kind_not_instance_suffix(self) -> None:
        registry = build_adapter_registry([_resistor_adapter()])
        self.assertEqual(set(registry), {"resistor"})
        self.assertEqual(registry["resistor"].instance_suffix, "R")

    def test_build_registry_is_usable_by_adapter_for(self) -> None:
        registry = build_adapter_registry([_resistor_adapter()])
        set_adapter_registry(registry)
        try:
            adapter = adapter_for("resistor", VERIFIED_VERSION)
            self.assertEqual(adapter.instance_suffix, "R")
        finally:
            set_adapter_registry({})

    def test_build_rejects_duplicate_kind(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            build_adapter_registry([_resistor_adapter(), _resistor_adapter()])
        self.assertIn("duplicate", str(ctx.exception))

    def test_build_rejects_empty_kind(self) -> None:
        with self.assertRaises(ValueError):
            build_adapter_registry(
                [
                    ComponentAdapter(
                        kind="",
                        instance_suffix="R",
                        pins={"P1": "1", "P2": "2"},
                        verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
                        evidence_sha256=TEST_EVIDENCE,
                    )
                ]
            )

    def test_build_rejects_empty_evidence(self) -> None:
        with self.assertRaises(ValueError):
            build_adapter_registry(
                [
                    ComponentAdapter(
                        kind="resistor",
                        instance_suffix="R",
                        pins={"P1": "1", "P2": "2"},
                        verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
                        evidence_sha256="",
                    )
                ]
            )

    def test_build_rejects_malformed_evidence_digest(self) -> None:
        with self.assertRaises(ValueError):
            build_adapter_registry(
                [
                    ComponentAdapter(
                        kind="resistor",
                        instance_suffix="R",
                        pins={"P1": "1", "P2": "2"},
                        verified_pcbc_versions=frozenset({VERIFIED_VERSION}),
                        evidence_sha256="not-a-digest",
                    )
                ]
            )

    def test_build_rejects_empty_verified_versions(self) -> None:
        with self.assertRaises(ValueError):
            build_adapter_registry(
                [
                    ComponentAdapter(
                        kind="resistor",
                        instance_suffix="R",
                        pins={"P1": "1", "P2": "2"},
                        verified_pcbc_versions=frozenset(),
                        evidence_sha256=TEST_EVIDENCE,
                    )
                ]
            )


if __name__ == "__main__":
    unittest.main()