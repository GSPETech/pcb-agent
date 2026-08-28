"""Deterministic generation of TestBench source from expected contracts.

Only rendering and structural helpers live here. Actual Zener execution and
classification belong to diode.execute_generated_test and cli._generated_check.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from .state import ProjectState


class GeneratorError(ValueError):
    pass


GENERATED_TEST_DIRECTORY = PurePosixPath("tests")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_NET_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PIN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_CONNECTIVITY_FIELDS: dict[str, frozenset[str]] = {
    "components": frozenset({"kind", "value", "package", "mpn"}),
    "nets": frozenset({"members", "required_pullup"}),
    "rules": frozenset({"forbid_unlisted_members", "required_power_nets"}),
}


@dataclass(frozen=True)
class ComponentAdapter:
    instance_suffix: str
    pins: Mapping[str, str]
    verified_pcbc_versions: frozenset[str]
    evidence_sha256: str
    value_accessor: str | None = None
    package_accessor: str | None = None
    mpn_accessor: str | None = None
    pullup_pin_pair: tuple[str, str] | None = None


def build_adapter_registry(entries: Iterable[ComponentAdapter]) -> dict[str, ComponentAdapter]:
    registry: dict[str, ComponentAdapter] = {}
    for adapter in entries:
        if not isinstance(adapter.evidence_sha256, str) or not adapter.evidence_sha256:
            raise ValueError("adapter evidence_sha256 must be non-empty string")
        registry[adapter.instance_suffix] = adapter
    return registry


_ADAPTERS: dict[str, ComponentAdapter] = {}


def set_adapter_registry(registry: Mapping[str, ComponentAdapter]) -> None:
    global _ADAPTERS
    _ADAPTERS = dict(registry)


def known_kinds() -> frozenset[str]:
    return frozenset(_ADAPTERS.keys())


def adapter_for(kind: str, pcbc_version: str) -> ComponentAdapter:
    adapter = _ADAPTERS.get(kind)
    if adapter is None:
        raise GeneratorError(f"unsupported component kind: {kind}")
    if pcbc_version not in adapter.verified_pcbc_versions:
        raise GeneratorError(
            f"adapter for {kind} not verified against pcbc {pcbc_version}"
        )
    return adapter


def validate_identifier(name: str, field: str) -> str:
    if not isinstance(name, str) or not _IDENTIFIER_PATTERN.match(name):
        raise GeneratorError(f"{field} must match identifier pattern")
    return name


def _zener_string(value: str) -> str:
    if not isinstance(value, str):
        raise GeneratorError("zener literal must be string")
    return json.dumps(value, ensure_ascii=True)


def _module_path_from_generated_test(source: str) -> str:
    if not isinstance(source, str) or not source:
        raise GeneratorError("source must be non-empty string")
    normalized = source.replace("\\", "/")
    if normalized.startswith("/"):
        raise GeneratorError("source path must be workspace-relative")
    raw_parts = normalized.split("/")
    if any(part in {"", "."} for part in raw_parts):
        raise GeneratorError("source path must not contain empty or dot segments")
    source_path = PurePosixPath(normalized)
    if any(part == ".." for part in source_path.parts):
        raise GeneratorError("source path must not contain traversal segments")
    relative = posixpath.relpath(
        source_path.as_posix(),
        GENERATED_TEST_DIRECTORY.as_posix(),
    )
    if relative.startswith("/"):
        raise GeneratorError("source path must resolve within workspace")
    return relative


def _check_connector_ref(ref: str, members: Iterable[str]) -> None:
    for member in members:
        if not isinstance(member, str) or "." not in member:
            raise GeneratorError(f"invalid pin member: {member!r}")
        head, _, _ = member.partition(".")
        if head != ref:
            raise GeneratorError(f"member {member!r} does not match ref {ref}")


def _supported_connectivity_fields() -> dict[str, frozenset[str]]:
    return {k: frozenset(v) for k, v in _CONNECTIVITY_FIELDS.items()}


def _validate_connectivity_shape(connectivity: Mapping[str, Any]) -> None:
    components = connectivity.get("components", {})
    nets = connectivity.get("nets", {})
    rules = connectivity.get("rules", {})

    if not isinstance(components, dict):
        raise GeneratorError("components must be object")
    if not isinstance(nets, dict):
        raise GeneratorError("nets must be object")
    if not isinstance(rules, dict):
        raise GeneratorError("rules must be object")

    supported = _supported_connectivity_fields()
    for net_name, definition in nets.items():
        if not isinstance(net_name, str) or not _NET_NAME_PATTERN.match(net_name):
            raise GeneratorError(f"net name invalid: {net_name!r}")
        if not isinstance(definition, dict):
            raise GeneratorError(f"net {net_name} must be object")
        unexpected = set(definition) - supported["nets"]
        if unexpected:
            raise GeneratorError(
                f"net {net_name} declares unsupported fields: {sorted(unexpected)}"
            )
        members = definition.get("members", [])
        if not isinstance(members, list):
            raise GeneratorError(f"net {net_name} members must be array")
        for member in members:
            if not isinstance(member, str) or "." not in member:
                raise GeneratorError(f"net {net_name} has invalid member {member!r}")
        if "required_pullup" in definition:
            pullup = definition["required_pullup"]
            if not isinstance(pullup, dict):
                raise GeneratorError(
                    f"net {net_name} required_pullup must be object"
                )
            for field in ("component", "rail"):
                if field not in pullup:
                    raise GeneratorError(
                        f"net {net_name} required_pullup missing {field}"
                    )

    for comp_ref, comp_def in components.items():
        if not isinstance(comp_ref, str) or not _IDENTIFIER_PATTERN.match(comp_ref):
            raise GeneratorError(f"component ref invalid: {comp_ref!r}")
        if not isinstance(comp_def, dict):
            raise GeneratorError(f"component {comp_ref} must be object")
        kind = comp_def.get("kind")
        if not isinstance(kind, str):
            raise GeneratorError(f"component {comp_ref} is missing kind")
        if kind not in _ADAPTERS:
            raise GeneratorError(f"component {comp_ref} uses unverified kind {kind}")
        unexpected = set(comp_def) - supported["components"]
        if unexpected:
            raise GeneratorError(
                f"component {comp_ref} declares unsupported fields: {sorted(unexpected)}"
            )

    for net_name in nets:
        for member in nets[net_name].get("members", []):
            ref = member.split(".", 1)[0]
            if ref not in components:
                raise GeneratorError(
                    f"net {net_name} member {member} references unknown component"
                )

    power_nets = rules.get("required_power_nets", [])
    if power_nets:
        if not isinstance(power_nets, list):
            raise GeneratorError("required_power_nets must be array")
        for power in power_nets:
            if power not in nets:
                raise GeneratorError(
                    f"required_power_nets references unknown net: {power}"
                )


def _check_required_pullup(
    net_name: str,
    definition: Mapping[str, Any],
    components: Mapping[str, Any],
    pcbc_version: str,
    bench_name: str,
    case_name: str,
) -> str:
    pullup = definition.get("required_pullup")
    if not isinstance(pullup, dict):
        return ""
    component = pullup.get("component")
    rail = pullup.get("rail")
    
    comp_def = components.get(component) if isinstance(component, str) else None
    if not isinstance(comp_def, dict):
        raise GeneratorError(
            f"net {net_name} required_pullup references unknown component {component}"
        )
    kind = comp_def.get("kind")
    if not isinstance(kind, str):
        raise GeneratorError(f"component {component} missing kind")
        
    adapter = adapter_for(kind, pcbc_version)
    if adapter.pullup_pin_pair is None:
        raise GeneratorError(f"adapter for {kind} lacks verified pullup_pin_pair")
        
    if not isinstance(rail, str) or not rail:
        raise GeneratorError(
            f"net {net_name} required_pullup rail must be string"
        )
        
    pin_a, pin_b = adapter.pullup_pin_pair
    diode_pin_a = adapter.pins.get(pin_a)
    diode_pin_b = adapter.pins.get(pin_b)
    if not diode_pin_a or not diode_pin_b:
        raise GeneratorError(f"adapter for {kind} missing pullup pins")
        
    diode_ref = f"{bench_name}__{case_name}.{component}.{adapter.instance_suffix}"
    
    # Assert that one pin is on the signal net (we don't know which one, but exactly one)
    # and the OTHER pin is on the rail net.
    return (
        f"    pin_a_on_signal = ({_zener_string(diode_ref)}, {_zener_string(diode_pin_a)}) in nets.get({_zener_string(net_name)}, [])\n"
        f"    pin_b_on_signal = ({_zener_string(diode_ref)}, {_zener_string(diode_pin_b)}) in nets.get({_zener_string(net_name)}, [])\n"
        f"    check(pin_a_on_signal != pin_b_on_signal, {_zener_string(f'net {net_name} must contain exactly one pullup pin from {component}')})\n"
        f"    if pin_a_on_signal:\n"
        f"        check(({_zener_string(diode_ref)}, {_zener_string(diode_pin_b)}) in nets.get({_zener_string(rail)}, []), {_zener_string(f'{component} must pull up to {rail}')})\n"
        f"    else:\n"
        f"        check(({_zener_string(diode_ref)}, {_zener_string(diode_pin_a)}) in nets.get({_zener_string(rail)}, []), {_zener_string(f'{component} must pull up to {rail}')})\n"
    )


def render_connectivity_testbench(
    project: ProjectState,
    bench_name: str = "PcbAgentConnectivity",
    case_name: str = "contract",
    pcbc_version: str = "unknown",
) -> str:
    bench_name = validate_identifier(bench_name, "bench_name")
    case_name = validate_identifier(case_name, "case_name")

    module_path = _module_path_from_generated_test(project.source)
    connectivity = project.connectivity
    _validate_connectivity_shape(connectivity)

    components = connectivity.get("components", {})
    nets = connectivity.get("nets", {})
    rules = connectivity.get("rules", {})

    lines: list[str] = [
        f"M = Module({_zener_string(module_path)})",
        "def _check_connectivity(module, inputs):",
        "    components = module.components()",
        "    nets = module.nets()",
    ]

    for comp_ref, comp_def in components.items():
        adapter = adapter_for(comp_def["kind"], pcbc_version)
        diode_ref = (
            f"{bench_name}__{case_name}.{comp_ref}.{adapter.instance_suffix}"
        )
        lines.append(
            f"    check({_zener_string(diode_ref)} in components, "
            f"{_zener_string(f'missing component {diode_ref}')})"
        )

    expected_net_names: list[str] = []
    for index, (net_name, definition) in enumerate(nets.items()):
        members = definition.get("members", [])
        expected_net_names.append(net_name)
        lines.append(f"    observed_{index} = nets.get({_zener_string(net_name)}, [])")

        for member in members:
            ref, pin = member.split(".", 1)
            adapter = adapter_for(components[ref]["kind"], pcbc_version)
            if not _PIN_NAME_PATTERN.match(pin):
                raise GeneratorError(f"invalid pin in member {member}")
            diode_pin = adapter.pins.get(pin)
            if not diode_pin:
                raise GeneratorError(f"unsupported pin {pin} for kind {components[ref]['kind']}")
            diode_ref = f"{bench_name}__{case_name}.{ref}.{adapter.instance_suffix}"
            lines.append(
                f"    check(({_zener_string(diode_ref)}, "
                f"{_zener_string(diode_pin)}) in observed_{index}, "
                f"{_zener_string(f'missing member {member} in net {net_name}')})"
            )

        if rules.get("forbid_unlisted_members"):
            lines.append(
                f"    check(len(observed_{index}) == {len(members)}, "
                f"{_zener_string(f'net {net_name} has unlisted members')})"
            )

        lines.append(_check_required_pullup(net_name, definition, components, pcbc_version, bench_name, case_name))

    if rules.get("forbid_unlisted_members"):
        names_literal = ", ".join(_zener_string(n) for n in expected_net_names)
        lines.append(f"    expected_net_names = set([{names_literal}])")
        lines.append(
            "    check(set(nets.keys()) == expected_net_names, "
            f"{_zener_string('unlisted nets found')})"
        )

    for power_net in rules.get("required_power_nets", []):
        lines.append(
            f"    check({_zener_string(power_net)} in nets, "
            f"{_zener_string(f'missing power net {power_net}')})"
        )

    lines.extend(
        [
            "",
            "TestBench(",
            f"    name={_zener_string(bench_name)},",
            "    module=M,",
            f"    test_cases={{{_zener_string(case_name)}: {{}}}},",
            "    checks=[_check_connectivity],",
            ")",
            "",
        ]
    )

    return "\n".join(lines)


def render_specification_testbench(
    project: ProjectState,
    bench_name: str = "PcbAgentSpecification",
    case_name: str = "contract",
    pcbc_version: str = "unknown",
) -> str:
    bench_name = validate_identifier(bench_name, "bench_name")
    case_name = validate_identifier(case_name, "case_name")

    module_path = _module_path_from_generated_test(project.source)
    connectivity = project.connectivity
    _validate_connectivity_shape(connectivity)

    components = connectivity.get("components", {})
    requirements = project.specification.get("requirements", [])
    checks = project.acceptance.get("checks", [])

    check_kinds: dict[str, list[str]] = {}
    for item in checks:
        if isinstance(item.get("requirement"), str) and isinstance(item.get("kind"), str):
            check_kinds.setdefault(item["requirement"], []).append(item["kind"])

    lines: list[str] = [
        f"M = Module({_zener_string(module_path)})",
        "def _check_specification(module, inputs):",
        "    components = module.components()",
    ]

    unsupported_constraint_seen = False
    components_with_assertions = set()
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        rid = requirement.get("id")
        if not isinstance(rid, str):
            continue
        rtype = requirement.get("type")
        subject = requirement.get("subject")
        constraints = dict(requirement.get("constraints", {}))

        if rtype == "connectivity":
            continue

        comp = components.get(subject) if isinstance(subject, str) else None
        if isinstance(comp, dict):
            # Transfer constraints from connectivity if present
            for field in ("value", "package", "mpn"):
                if field in comp:
                    if field not in constraints:
                        constraints[field] = comp[field]
                    elif str(constraints[field]) != str(comp[field]):
                        raise GeneratorError(
                            f"requirement {rid} constraint {field}={constraints[field]!r} "
                            f"conflicts with connectivity field={comp[field]!r}"
                        )

        if not constraints:
            continue

        kinds = check_kinds.get(rid, [])
        if "zener_test" not in kinds:
            raise GeneratorError(
                f"requirement {rid} has constraints but lacks zener_test acceptance check"
            )

        if not isinstance(subject, str) or not _IDENTIFIER_PATTERN.match(subject):
            raise GeneratorError(
                f"requirement {rid} has constraints but lacks valid subject"
            )

        comp = components.get(subject)
        if not isinstance(comp, dict):
            raise GeneratorError(
                f"subject {subject} in {rid} is not defined in expected connectivity components"
            )

        kind = comp.get("kind")
        if not isinstance(kind, str):
            raise GeneratorError(f"subject {subject} in {rid} is missing kind")

        adapter = adapter_for(kind, pcbc_version)
        diode_ref = f"{bench_name}__{case_name}.{subject}.{adapter.instance_suffix}"
        if subject not in components_with_assertions:
            lines.append(
                f"    check({_zener_string(diode_ref)} in components, "
                f"{_zener_string(f'missing component {diode_ref}')})"
            )
            components_with_assertions.add(subject)

        for key, expected_value in constraints.items():
            if key == "value":
                if adapter.value_accessor is None:
                    raise GeneratorError(f"adapter for {kind} has no verified value accessor")
                lines.append(
                    "    check(components["
                    f"{_zener_string(diode_ref)}"
                    f"].{adapter.value_accessor}.matches("
                    f"{_zener_string(str(expected_value))}"
                    f"), {_zener_string(f'wrong value for {subject}')})"
                )
            elif key == "package":
                if adapter.package_accessor is None:
                    raise GeneratorError(f"adapter for {kind} has no verified package accessor")
                lines.append(
                    "    check(components["
                    f"{_zener_string(diode_ref)}"
                    f"].{adapter.package_accessor}.value == "
                    f"{_zener_string(str(expected_value))}, "
                    f"{_zener_string(f'wrong package for {subject}')})"
                )
            elif key == "mpn":
                if adapter.mpn_accessor is None:
                    raise GeneratorError(f"adapter for {kind} has no verified mpn accessor")
            else:
                unsupported_constraint_seen = True
                raise GeneratorError(
                    f"unsupported constraint {key} in {rid}"
                )

    for comp_ref, comp_def in components.items():
        if comp_ref in components_with_assertions:
            continue
        unasserted_props = {k: v for k, v in comp_def.items() if k in ("value", "package", "mpn")}
        if unasserted_props:
            raise GeneratorError(
                f"component {comp_ref} declares properties {list(unasserted_props.keys())} "
                f"but has no specification requirement covering it"
            )

    if not lines[3:]:
        raise GeneratorError("specification produced no assertions")

    lines.extend(
        [
            "",
            "TestBench(",
            f"    name={_zener_string(bench_name)},",
            "    module=M,",
            f"    test_cases={{{_zener_string(case_name)}: {{}}}},",
            "    checks=[_check_specification],",
            ")",
            "",
        ]
    )

    return "\n".join(lines)