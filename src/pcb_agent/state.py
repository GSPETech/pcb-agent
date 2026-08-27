"""Run directories, project metadata, and immutable evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import VerificationReport
from .contracts import ContractError, load_project_contract
from .report import render_markdown


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectState:
    root: Path
    name: str
    config: Mapping[str, Any]
    hashes: Mapping[str, str]
    profile: str
    source: str
    test: str
    board: str | None
    acceptance: Mapping[str, Any]


def source_is_dirty(root: Path) -> bool:
    try:
        result = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=root,
                                shell=False, capture_output=True, text=True, timeout=10, check=False)
        return result.returncode == 0 and bool(result.stdout.strip())
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


@dataclass(frozen=True, slots=True)
class RunState:
    run_id: str
    directory: Path
    raw_directory: Path





def load_project(project: Path | str) -> ProjectState:
    try:
        contract = load_project_contract(project)
    except (ContractError, OSError, ValueError) as error:
        raise ConfigurationError(str(error)) from error
    return ProjectState(contract.root, contract.name, contract.config, contract.hashes,
                        contract.profile, contract.source, contract.test, contract.board,
                        contract.acceptance)


def new_run(project: ProjectState, reports_root: Path | str | None = None) -> RunState:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"{stamp}-{os.getpid()}"
    base = Path(reports_root) if reports_root else project.root / "reports"
    directory = base.resolve() / run_id
    raw = directory / "raw"
    raw.mkdir(parents=True, exist_ok=False)
    return RunState(run_id, directory, raw)


def _atomic_write(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_run_report(
    run: RunState, report: VerificationReport, project: ProjectState | None = None
) -> Path:
    data = report.to_dict()
    if project is not None:
        data["hashes"] = dict(project.hashes)
    json_path = run.directory / "verify-report.json"
    _atomic_write(json_path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    _atomic_write(run.directory / "verify-report.md", render_markdown(report))
    return json_path


def latest_report(project: ProjectState) -> Path:
    root = project.root / "reports"
    candidates = sorted(root.glob("*/verify-report.json"), reverse=True) if root.is_dir() else []
    if not candidates:
        raise FileNotFoundError("no verification report found")
    return candidates[0]
