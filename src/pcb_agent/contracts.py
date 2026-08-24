"""Strict manual project-contract loader."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .paths import require_regular_file, resolve_workspace_path


REQUIRED_FILES = (
    "SPEC.json",
    "ACCEPTANCE.json",
    "expected-connectivity.json",
    "project.toml",
)


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
    if not all(isinstance(value, dict) for value in (specification, acceptance, connectivity)):
        raise ContractError("JSON contract roots must be objects")
    if not isinstance(connectivity.get("components"), dict) or not isinstance(connectivity.get("nets"), dict):
        raise ContractError("connectivity requires object fields: components and nets")
    if not connectivity["components"] or not connectivity["nets"]:
        raise ContractError("connectivity components and nets must not be empty")
    for reference, component in connectivity["components"].items():
        if not isinstance(reference, str) or not reference or not isinstance(component, dict) or not isinstance(component.get("kind"), str):
            raise ContractError("connectivity components require reference and kind")
    for net, definition in connectivity["nets"].items():
        members = definition.get("members") if isinstance(definition, dict) else None
        if not isinstance(net, str) or not net or not isinstance(members, list) or not members or any(not isinstance(item, str) or "." not in item for item in members):
            raise ContractError("connectivity nets require non-empty pin members")
    project = config.get("project")
    if not isinstance(project, dict):
        raise ContractError("project.toml requires [project]")
    name, profile = project.get("name"), project.get("profile")
    source, test = project.get("source"), project.get("test")
    toolchain, layout = config.get("toolchain"), config.get("layout")
    if not isinstance(name, str) or not name.strip():
        raise ContractError("project.name must be a non-empty string")
    if profile not in {"schematic", "layout"}:
        raise ContractError("project.profile must be schematic or layout")
    for key, value in (("project.source", source), ("project.test", test)):
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{key} must be a non-empty string")
        path = resolve_workspace_path(root, value, must_exist=True)
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
    if acceptance.get("production_ready") is not False or acceptance.get("fabrication_approved") is not False:
        raise ContractError("acceptance must keep production and fabrication false")
    if not isinstance(specification.get("requirements"), list) or not isinstance(acceptance.get("checks"), list):
        raise ContractError("specification.requirements and acceptance.checks must be arrays")
    requirements = specification["requirements"]
    checks = acceptance["checks"]
    if not requirements or not checks:
        raise ContractError("requirements and acceptance checks must not be empty")
    requirement_ids = [item.get("id") for item in requirements if isinstance(item, dict)]
    acceptance_ids = [item.get("id") for item in checks if isinstance(item, dict)]
    if (len(requirement_ids) != len(requirements) or any(not isinstance(item, str) or not item for item in requirement_ids)
            or len(set(requirement_ids)) != len(requirement_ids)):
        raise ContractError("requirement IDs must be unique non-empty strings")
    if (len(acceptance_ids) != len(checks) or any(not isinstance(item, str) or not item for item in acceptance_ids)
            or len(set(acceptance_ids)) != len(acceptance_ids)):
        raise ContractError("acceptance IDs must be unique non-empty strings")
    covered: set[str] = set()
    for item in checks:
        requirement, test_name = item.get("requirement"), item.get("test")
        if (requirement not in requirement_ids or not isinstance(test_name, str) or not test_name
                or item.get("kind") != "zener_test"):
            raise ContractError("each acceptance check needs known requirement and test")
        if item.get("expected") != "PASS":
            raise ContractError("MVP acceptance expected value must be PASS")
        covered.add(requirement)
    if covered != set(requirement_ids):
        raise ContractError("acceptance checks must cover every requirement")
    if not Path(test).as_posix().startswith("tests/") or not test.endswith(".zen"):
        raise ContractError("project.test must be a protected tests/*.zen file")
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
