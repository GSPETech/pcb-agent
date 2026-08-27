"""Deterministic generation of TestBench source from expected contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .state import ProjectState


class GeneratorError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentAdapter:
    instance_suffix: str
    pins: Mapping[str, str]


_ADAPTERS = {
    "resistor": ComponentAdapter(
        instance_suffix="R",
        pins={"P1": "1", "P2": "2"},
    ),
    "led": ComponentAdapter(
        instance_suffix="LED",
        pins={"A": "A", "K": "K"},
    ),
}


def _zener_string(value: str) -> str:
    return json.dumps(value)


def render_connectivity_testbench(
    project: ProjectState,
    bench_name: str = "PcbAgentConnectivity",
    case_name: str = "contract",
) -> str:
    components = project.connectivity.get("components", {})
    nets = project.connectivity.get("nets", {})
    rules = project.connectivity.get("rules", {})

    lines: list[str] = [
        f"M = Module({_zener_string(project.source)})",
        "def _check_connectivity(module, inputs):",
        "    nets = module.nets()",
    ]

    expected_members_by_net: dict[str, list[str]] = {}

    for net_name, definition in nets.items():
        members = definition.get("members", []) if isinstance(definition, dict) else []
        tuples: list[str] = []
        for member in members:
            ref, pin = member.split(".", 1)
            comp = components.get(ref, {})
            kind = comp.get("kind")
            if not isinstance(kind, str):
                raise GeneratorError(f"component {ref} is missing kind")
            adapter = _ADAPTERS.get(kind)
            if not adapter:
                raise GeneratorError(f"unsupported component kind: {kind}")
            diode_pin = adapter.pins.get(pin)
            if not diode_pin:
                raise GeneratorError(f"unsupported pin {pin} for kind {kind}")
            
            diode_ref = f"{bench_name}__{case_name}.{ref}.{adapter.instance_suffix}"
            tuples.append(f"({_zener_string(diode_ref)}, {_zener_string(diode_pin)})")
        expected_members_by_net[net_name] = tuples

    for net_name, tuples in expected_members_by_net.items():
        lines.append(f"    observed_{net_name} = nets.get({_zener_string(net_name)}, [])")
        for tup in tuples:
            lines.append(f"    check({tup} in observed_{net_name}, 'missing {tup} in {net_name}')")

    if rules.get("forbid_unlisted_members"):
        lines.append(f"    expected_net_names = set([{', '.join(_zener_string(n) for n in nets.keys())}])")
        lines.append("    check(set(nets.keys()) == expected_net_names, 'unlisted nets found')")
        for net_name, tuples in expected_members_by_net.items():
            lines.append(f"    check(len(observed_{net_name}) == {len(tuples)}, 'unlisted members in {net_name}')")

    for power_net in rules.get("required_power_nets", []):
        lines.append(f"    check({_zener_string(power_net)} in nets, 'missing power net {power_net}')")

    lines.extend([
        "",
        f"TestBench(",
        f"    name={_zener_string(bench_name)},",
        f"    module=M,",
        f"    test_cases={{{_zener_string(case_name)}: {{}}}},",
        f"    checks=[_check_connectivity],",
        f")",
        ""
    ])

    return "\n".join(lines)