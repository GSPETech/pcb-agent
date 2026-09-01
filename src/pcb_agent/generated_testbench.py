"""Deterministic generation of TestBench source from expected contracts.

Only rendering and structural helpers live here. Actual Zener execution and
classification belong to diode.execute_generated_test and cli._generated_check.
"""

from __future__ import annotations

import contextlib
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .evidence import EvidenceError, is_sha256_digest
from .state import ProjectState


class GeneratorError(ValueError):
    pass


GENERATED_TEST_DIRECTORY = PurePosixPath("tests")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
# Hierarchical designs address components and nets through their module path,
# for example "IMU.R17" and "IMU.IMU_ADDR_SEL". A flat name is the single-segment
# case of the same pattern, so captured flat evidence is unaffected.
_HIERARCHICAL_REF_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]{0,63}(?:\.[A-Za-z][A-Za-z0-9_-]{0,63}){0,7}$"
)
_NET_NAME_PATTERN = _HIERARCHICAL_REF_PATTERN
_PIN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_CONNECTIVITY_FIELDS: dict[str, frozenset[str]] = {
    "components": frozenset({"kind", "value", "package", "mpn"}),
    "nets": frozenset({"members", "required_pullup"}),
    "rules": frozenset({"forbid_unlisted_members", "required_power_nets"}),
}
_CONNECTIVITY_REQUIREMENT_CONSTRAINTS = frozenset({"members"})


@dataclass(frozen=True)
class ComponentAdapter:
    kind: str
    instance_suffix: str
    pins: Mapping[str, str]
    verified_pcbc_versions: frozenset[str]
    evidence_sha256: str
    evidence_result_path: str = ""
    evidence_source_path: str = ""
    evidence_source_sha256: str = ""
    value_accessor: str | None = None
    package_accessor: str | None = None
    mpn_accessor: str | None = None
    pullup_pin_pair: tuple[str, str] | None = None


def build_adapter_registry(entries: Iterable[ComponentAdapter]) -> dict[str, ComponentAdapter]:
    registry: dict[str, ComponentAdapter] = {}
    for adapter in entries:
        if not isinstance(adapter.kind, str) or not _IDENTIFIER_PATTERN.match(adapter.kind):
            raise ValueError("adapter kind must be a valid identifier")
        if not isinstance(adapter.instance_suffix, str) or not adapter.instance_suffix:
            raise ValueError("adapter instance_suffix must be non-empty string")
        if not is_sha256_digest(adapter.evidence_sha256):
            raise ValueError("adapter evidence_sha256 must be sha256:<64 hex>")
        if not adapter.verified_pcbc_versions:
            raise ValueError("adapter must declare at least one verified pcbc version")
        if adapter.kind in registry:
            raise ValueError(f"duplicate adapter kind: {adapter.kind}")
        registry[adapter.kind] = adapter
    return registry


_CAPTURED_PCBC_VERSION = "0.4.40"
_CAPTURED_BLINKY_EVIDENCE = "sha256:02c6cb60bfaf371e640e34ed0ff7b707074cfad0789b38a25c014cfa66cfac11"
_CAPTURED_GENERICS_EVIDENCE = "sha256:3320a8aa668f5f28dc19b4240f9f92e22333805ead12e36cb4c5a3c3b1636267"
_CAPTURED_BLINKY_SOURCE = "sha256:4e4533b947babc249f9e1ccbb51fc7dc4b4c4022c20c58db19919adb5d770a5b"
_CAPTURED_GENERICS_SOURCE = "sha256:b268cc42821459d724affb68716b39c865be27f8dfd119d9812fee84996c76ea"
_PACKAGE_ACCESSOR = "properties['package']"

_EVIDENCE_BLINKY_RESULT = "valid-blinky/valid-blinky.json"
_EVIDENCE_BLINKY_SOURCE = "valid-blinky/valid-blinky-testbench.zen"
_EVIDENCE_GENERICS_RESULT = "spike-generics/spike-generics.json"
_EVIDENCE_GENERICS_SOURCE = "spike-generics/spike-generics-testbench.zen"


def captured_adapter_registry() -> dict[str, ComponentAdapter]:
    """Production adapters verified against captured Diode 0.4.40 output.

    The raw `pcb test -f json` results stored under
    `tests/evidence/diode-0.4.40/` carry only result identity and status. The
    mapping/accessor values are established by the hash-bound TestBench source
    that produced each PASS result (assertion source + module source), whose
    digests are also retained in the evidence manifest. See
    docs/spike-diode-net-naming.md. Crystal is intentionally absent: the
    adapter model cannot represent its one-to-many four-pin GND mapping.
    """
    return build_adapter_registry(
        [
            ComponentAdapter(
                kind="resistor",
                instance_suffix="R",
                pins={"P1": "1", "P2": "2"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_BLINKY_EVIDENCE,
                evidence_result_path=_EVIDENCE_BLINKY_RESULT,
                evidence_source_path=_EVIDENCE_BLINKY_SOURCE,
                evidence_source_sha256=_CAPTURED_BLINKY_SOURCE,
                value_accessor="resistance",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=("P1", "P2"),
            ),
            ComponentAdapter(
                kind="led",
                instance_suffix="LED",
                pins={"A": "A", "K": "K"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_BLINKY_EVIDENCE,
                evidence_result_path=_EVIDENCE_BLINKY_RESULT,
                evidence_source_path=_EVIDENCE_BLINKY_SOURCE,
                evidence_source_sha256=_CAPTURED_BLINKY_SOURCE,
                value_accessor=None,
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="capacitor",
                instance_suffix="C",
                pins={"P1": "1", "P2": "2"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="capacitance",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="inductor",
                instance_suffix="L",
                pins={"P1": "1", "P2": "2"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="inductance",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="ferrite_bead",
                instance_suffix="FB",
                pins={"P1": "1", "P2": "2"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="impedance",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="thermistor",
                instance_suffix="TH",
                pins={"P1": "1", "P2": "2"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="resistance",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="zener",
                instance_suffix="D",
                pins={"A": "A", "K": "K"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="zener_voltage",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="rectifier",
                instance_suffix="D",
                pins={"A": "A", "K": "K"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="reverse_voltage",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
            ComponentAdapter(
                kind="tvs",
                instance_suffix="D",
                pins={"A": "A", "K": "K"},
                verified_pcbc_versions=frozenset({_CAPTURED_PCBC_VERSION}),
                evidence_sha256=_CAPTURED_GENERICS_EVIDENCE,
                evidence_result_path=_EVIDENCE_GENERICS_RESULT,
                evidence_source_path=_EVIDENCE_GENERICS_SOURCE,
                evidence_source_sha256=_CAPTURED_GENERICS_SOURCE,
                value_accessor="reverse_standoff_voltage",
                package_accessor=_PACKAGE_ACCESSOR,
                pullup_pin_pair=None,
            ),
        ]
    )


_GENERATION = 0
_ADAPTERS: dict[str, ComponentAdapter] = captured_adapter_registry()


def evidence_root() -> Path:
    """Repository-owned evidence root for the captured Diode run.

    Resolved relative to this source file so the bundle travels with the
    repository and is never read from arbitrary home paths or the current
    working directory.
    """
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parent.parent.parent
    return root / "tests" / "evidence" / f"diode-{_CAPTURED_PCBC_VERSION}"


def validate_captured_registry(root_override: Path | None = None) -> None:
    """Fail closed if the captured registry's evidence bundle is incomplete.

    Validates every production adapter against the repository-owned manifest
    and version record. Raises `EvidenceError` on the first inconsistency.
    The evidence root is resolved relative to the package by default; a test
    may pass `root_override` to validate against a temporary bundle.
    """
    from .evidence import validate_registry_provenance

    root = root_override if root_override is not None else evidence_root()
    validate_registry_provenance(
        captured_adapter_registry(),
        root,
        root / "manifest.sha256",
    )


_PROVENANCE_CACHE: tuple[int, tuple[bool, str]] | None = None
# Test-only redirect for provenance validation. Production code never sets this;
# it only ever points at the repository-owned bundle via `evidence_root()`.
_TEST_PROVENANCE_ROOT: Path | None = None


def _run_provenance_validation() -> None:
    from .evidence import validate_registry_provenance

    root = _TEST_PROVENANCE_ROOT if _TEST_PROVENANCE_ROOT is not None else evidence_root()
    validate_registry_provenance(
        dict(_ADAPTERS),
        root,
        root / "manifest.sha256",
    )


def _bump_generation() -> None:
    global _GENERATION
    _GENERATION += 1


def ensure_registry_provenance() -> None:
    """Validate the active registry snapshot lazily before generated use.

    The verdict is cached against the registry generation. Any mutation of the
    active registry bumps the generation, so the next validation re-runs
    instead of trusting a stale verdict. On failure the registry is emptied
    (fail closed) and a `GeneratorError` is raised so generated gates report
    `BLOCKED`. Unrelated commands never call this, so `doctor` and `build`
    keep working even when the evidence bundle is invalid.
    """
    global _ADAPTERS, _PROVENANCE_CACHE
    if _PROVENANCE_CACHE is not None and _PROVENANCE_CACHE[0] == _GENERATION:
        ok, err = _PROVENANCE_CACHE[1]
        if ok:
            return
        raise GeneratorError(f"captured registry provenance invalid: {err}")
    try:
        _run_provenance_validation()
    except EvidenceError as error:
        _ADAPTERS = {}
        _bump_generation()
        _PROVENANCE_CACHE = (_GENERATION, (False, str(error)))
        raise GeneratorError(f"captured registry provenance invalid: {error}") from error
    _PROVENANCE_CACHE = (_GENERATION, (True, ""))


def reset_registry_provenance() -> None:
    """Test hook: restore the captured registry and invalidate the cache."""
    global _ADAPTERS, _PROVENANCE_CACHE
    _ADAPTERS = captured_adapter_registry()
    _PROVENANCE_CACHE = None
    _bump_generation()


def set_adapter_registry(registry: Mapping[str, ComponentAdapter]) -> None:
    global _ADAPTERS, _PROVENANCE_CACHE
    _ADAPTERS = dict(registry)
    _PROVENANCE_CACHE = None
    _bump_generation()


@contextlib.contextmanager
def temporary_test_registry(registry: Mapping[str, ComponentAdapter]):
    """Swap in a test registry and restore the previous snapshot on exit."""
    previous = dict(_ADAPTERS)
    set_adapter_registry(registry)
    try:
        yield
    finally:
        set_adapter_registry(previous)


@contextlib.contextmanager
def temporary_test_evidence_root(root: Path):
    """Test-only: redirect active-registry provenance validation to a bundle.

    This is a scoped test mechanism for renderer unit tests that use synthetic
    adapters without the captured bundle. It does not bypass validation: the
    active registry is still validated, against `root`. Production code never
    enters this context. Entering and exiting invalidate the cached verdict so
    validation re-runs against the active registry and the (restored) root.
    """
    global _TEST_PROVENANCE_ROOT, _PROVENANCE_CACHE
    previous_root = _TEST_PROVENANCE_ROOT
    _TEST_PROVENANCE_ROOT = root
    _PROVENANCE_CACHE = None
    _bump_generation()
    try:
        yield
    finally:
        _TEST_PROVENANCE_ROOT = previous_root
        _PROVENANCE_CACHE = None
        _bump_generation()


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
    return relative


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
        if not isinstance(comp_ref, str) or not _HIERARCHICAL_REF_PATTERN.match(comp_ref):
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
            # A member is "<component-ref>.<pin>" and the ref may itself be a
            # dotted module path, so the pin is the final segment.
            ref = member.rsplit(".", 1)[0]
            if ref not in components:
                raise GeneratorError(
                    f"net {net_name} member {member} references unknown component"
                )

    unexpected_rules = set(rules) - supported["rules"]
    if unexpected_rules:
        raise GeneratorError(
            f"rules declares unsupported fields: {sorted(unexpected_rules)}"
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
    pcbc_version: str,
    bench_name: str = "PcbAgentConnectivity",
    case_name: str = "contract",
) -> str:
    ensure_registry_provenance()
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
        component_ref = f"{comp_ref}.{adapter.instance_suffix}"
        lines.append(
            f"    check({_zener_string(component_ref)} in components, "
            f"{_zener_string(f'missing component {component_ref}')})"
        )

    expected_net_names: list[str] = []
    for index, (net_name, definition) in enumerate(nets.items()):
        members = definition.get("members", [])
        expected_net_names.append(net_name)
        lines.append(f"    observed_{index} = nets.get({_zener_string(net_name)}, [])")

        for member in members:
            ref, pin = member.rsplit(".", 1)
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

        # The pullup block ends in "\n", so the "\n".join below emits a blank
        # line after it. That blank line is intentional: the generated source
        # is byte-bound to the retained evidence under
        # tests/evidence/diode-0.4.40/ (Finding 10 -- do not reformat).
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
    pcbc_version: str,
    bench_name: str = "PcbAgentSpecification",
    case_name: str = "contract",
) -> str:
    ensure_registry_provenance()
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

    components_with_assertions: set[str] = set()
    expected_constraints = 0
    asserted_constraints = 0
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
            unexpected = set(constraints) - _CONNECTIVITY_REQUIREMENT_CONSTRAINTS
            if unexpected:
                raise GeneratorError(
                    f"requirement {rid} of type connectivity declares "
                    f"unsupported constraints: {sorted(unexpected)}"
                )
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

        if not isinstance(subject, str) or not _HIERARCHICAL_REF_PATTERN.match(subject):
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
        component_ref = f"{subject}.{adapter.instance_suffix}"
        # Reject mpn constraints before emitting any assertion: no captured
        # adapter provides a verified mpn accessor, so an mpn requirement can
        # never produce trustworthy evidence. Failing here (rather than after
        # value/package assertions are emitted) keeps the generator from
        # producing partial output for an unsupported constraint.
        if "mpn" in constraints:
            raise GeneratorError(
                f"component {component_ref} declares mpn, but no captured "
                f"adapter provides a verified mpn accessor"
            )
        if subject not in components_with_assertions:
            lines.append(
                f"    check({_zener_string(component_ref)} in components, "
                f"{_zener_string(f'missing component {component_ref}')})"
            )
            components_with_assertions.add(subject)

        for key, expected_value in constraints.items():
            expected_constraints += 1
            if key == "value":
                if adapter.value_accessor is None:
                    raise GeneratorError(f"adapter for {kind} has no verified value accessor")
                lines.append(
                    "    check(components["
                    f"{_zener_string(component_ref)}"
                    f"].{adapter.value_accessor}.matches("
                    f"{_zener_string(str(expected_value))}"
                    f"), {_zener_string(f'wrong value for {subject}')})"
                )
                asserted_constraints += 1
            elif key == "package":
                if adapter.package_accessor is None:
                    raise GeneratorError(f"adapter for {kind} has no verified package accessor")
                lines.append(
                    "    check(components["
                    f"{_zener_string(component_ref)}"
                    f"].{adapter.package_accessor}.value == "
                    f"{_zener_string(str(expected_value))}, "
                    f"{_zener_string(f'wrong package for {subject}')})"
                )
                asserted_constraints += 1
            elif key == "mpn":
                # Unreachable: mpn is rejected above before any assertion is
                # emitted. Kept as a defense-in-depth fallback.
                raise GeneratorError(
                    f"component {component_ref} declares mpn, but no captured "
                    f"adapter provides a verified mpn accessor"
                )
            else:
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

    if asserted_constraints != expected_constraints:
        raise GeneratorError(
            f"generated {expected_constraints} constraints but only "
            f"{asserted_constraints} assertions; refusing incomplete evidence"
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