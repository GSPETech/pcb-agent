"""Strict project-contract loader. Shape comes from JSON schemas; cross-document rules stay here."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .jsonschema import SchemaError, load_schema, validate
from .paths import require_regular_file, resolve_workspace_path


REQUIRED_FILES = (
    "SPEC.json",
    "ACCEPTANCE.json",
    "expected-connectivity.json",
    "project.toml",
)

_SCHEMA_BY_FILE = {
    "SPEC.json": "specification.schema.json",
    "ACCEPTANCE.json": "acceptance.schema.json",
    "expected-connectivity.json": "connectivity.schema.json",
}


class ContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectContract:
    root: Path
    name: str
    pcb_version: str
    profile: str
    source: str
    test: str
    layout_required: bool
    board: str | None
    specification: Mapping[str, Any]
    acceptance: Mapping[str, Any]
    connectivity: Mapping[str, Any]
    config: Mapping[str, Any]
    hashes: Mapping[str, str]


def _reject_unsafe_relative_path(value: str, field: str) -> PurePosixPath:
    from pathlib import PurePosixPath
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"{field} must be a canonical workspace-relative path")
    return path

def _read_required(root: Path, name: str) -> bytes:
    if (root / name).is_symlink():
        raise ContractError(f"required contract file must not be a symlink: {name}")
    path = resolve_workspace_path(root, name, must_exist=True)
    try:
        require_regular_file(path)
        data = path.read_bytes()
    except OSError as error:
        raise ContractError(f"cannot read {name}: {error}") from error
    if not data.strip():
        raise ContractError(f"required contract file is empty: {name}")
    return data


def load_project_contract(project_root: Path | str) -> ProjectContract:
    root = Path(project_root).resolve(strict=True)
    if not root.is_dir():
        raise ContractError(f"project root is not a directory: {root}")
    raw = {name: _read_required(root, name) for name in REQUIRED_FILES}
    try:
        specification = json.loads(raw["SPEC.json"])
        acceptance = json.loads(raw["ACCEPTANCE.json"])
        connectivity = json.loads(raw["expected-connectivity.json"])
        config = tomllib.loads(raw["project.toml"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise ContractError(f"invalid project contract: {error}") from error
    documents = {
        "SPEC.json": specification,
        "ACCEPTANCE.json": acceptance,
        "expected-connectivity.json": connectivity,
    }
    for filename, schema_name in _SCHEMA_BY_FILE.items():
        try:
            validate(documents[filename], load_schema(schema_name), filename)
        except SchemaError as error:
            raise ContractError(f"{filename} violates schema: {error}") from error
    project = config.get("project")
    if not isinstance(project, dict):
        raise ContractError("project.toml requires [project]")
    name, profile = project.get("name"), project.get("profile")
    import re
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ContractError("project.name must be a valid string")
    spec_name = specification.get("project", {}).get("name")
    if name != spec_name:
        raise ContractError(f"project name mismatch: project.toml={name!r}, SPEC.json={spec_name!r}")

    source, test = project.get("source"), project.get("test")
    negative_fixture = project.get("negative_fixture", False)
    if not isinstance(negative_fixture, bool):
        raise ContractError("project.negative_fixture must be boolean")
    build_negative = (negative_fixture and any(
        isinstance(item, dict) and item.get("kind") == "diode_build" and item.get("expected") == "FAIL"
        for item in acceptance.get("checks", [])
    ))
    if (not connectivity["components"] or not connectivity["nets"]) and not build_negative:
        raise ContractError("connectivity components and nets must not be empty")
    toolchain, layout = config.get("toolchain"), config.get("layout")
    if profile not in {"schematic", "layout"}:
        raise ContractError("project.profile must be schematic or layout")
    for key, value in (("project.source", source), ("project.test", test)):
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{key} must be a non-empty string")
        lexical = _reject_unsafe_relative_path(value, key)
        if key == "project.test":
            if not lexical.parts or lexical.parts[0] != "tests" or lexical.suffix != ".zen":
                raise ContractError("project.test must be a protected tests/*.zen file")
        path = resolve_workspace_path(root, value, must_exist=True)
        if key == "project.test":
            canonical_tests = resolve_workspace_path(root, "tests", must_exist=True, allow_root=False)
            if canonical_tests not in path.parents:
                raise ContractError("project.test resolved outside tests/ directory")
        require_regular_file(path)
    if not isinstance(toolchain, dict) or not isinstance(toolchain.get("pcb_version"), str):
        raise ContractError("project.toml requires [toolchain].pcb_version")
    if not isinstance(layout, dict) or not isinstance(layout.get("required"), bool):
        raise ContractError("project.toml requires [layout].required boolean")
    board = layout.get("board")
    if board is not None and (not isinstance(board, str) or not board.endswith(".kicad_pcb")):
        raise ContractError("layout.board must end in .kicad_pcb")
    if layout["required"] and profile != "layout":
        raise ContractError("layout.required requires layout profile")
    requirements = specification["requirements"]
    checks = acceptance["checks"]
    requirement_ids = [item.get("id") for item in requirements if isinstance(item, dict)]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise ContractError("requirement IDs must be unique")
    acceptance_ids = [item.get("id") for item in checks if isinstance(item, dict)]
    if len(set(acceptance_ids)) != len(acceptance_ids):
        raise ContractError("acceptance IDs must be unique")
    covered: set[str] = set()
    for item in checks:
        requirement, test_name, kind = item.get("requirement"), item.get("test"), item.get("kind")
        if requirement not in requirement_ids or kind not in {"zener_test", "diode_build"}:
            raise ContractError("each acceptance check needs known requirement and supported kind")
        if kind == "zener_test" and (not isinstance(test_name, str) or not test_name):
            raise ContractError("zener_test acceptance requires test name")
        if item.get("expected") not in {"PASS", "FAIL"}:
            raise ContractError("acceptance expected value must be PASS or FAIL")
        if item.get("expected") == "FAIL" and not negative_fixture:
            raise ContractError("expected FAIL is allowed only for an explicit negative fixture")
        covered.add(requirement)
    if covered != set(requirement_ids):
        raise ContractError("acceptance checks must cover every requirement")

    for net_name, definition in connectivity.get("nets", {}).items():
        if isinstance(definition, dict):
            for member in definition.get("members", []):
                if isinstance(member, str) and "." in member:
                    ref = member.split(".", 1)[0]
                    if ref not in connectivity.get("components", {}):
                        raise ContractError(f"connectivity net member {member} references unknown component")
            pullup = definition.get("required_pullup")
            if isinstance(pullup, dict):
                comp = pullup.get("component")
                rail = pullup.get("rail")
                if comp not in connectivity.get("components", {}):
                    raise ContractError(f"connectivity required_pullup references unknown component {comp}")
                if rail not in connectivity.get("nets", {}):
                    raise ContractError(f"connectivity required_pullup references unknown net {rail}")
    
    rules = connectivity.get("rules")
    if isinstance(rules, dict):
        for net in rules.get("required_power_nets", []):
            if net not in connectivity.get("nets", {}):
                raise ContractError(f"connectivity required_power_nets references unknown net {net}")

    hashes = {
        name: "sha256:" + hashlib.sha256(data).hexdigest() for name, data in raw.items()
    }
    return ProjectContract(
        root=root,
        name=name,
        pcb_version=toolchain["pcb_version"],
        profile=profile,
        source=source,
        test=test,
        layout_required=layout["required"],
        board=board,
        specification=specification,
        acceptance=acceptance,
        connectivity=connectivity,
        config=config,
        hashes=hashes,
    )
