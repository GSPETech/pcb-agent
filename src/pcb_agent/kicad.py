"""Read-only KiCad PCB DRC adapter."""

from __future__ import annotations

from pathlib import Path
import json
import hashlib

from .models import Check, CheckStatus, Severity
from .process import ProcessResult, run_process
from .state import ConfigurationError, ProjectState, RunState


def _board(project: ProjectState) -> Path:
    value = project.board
    if not isinstance(value, str) or not value.endswith(".kicad_pcb"):
        raise ConfigurationError("project.toml requires board path ending in .kicad_pcb")
    path = (project.root / value).resolve(strict=True)
    if project.root not in path.parents or not path.is_file() or path.is_symlink():
        raise ConfigurationError("board must be a regular project file")
    return path


def probe(project: ProjectState) -> ProcessResult:
    return run_process(project.root, ["kicad-cli", "pcb", "drc", "--help"], timeout=30)


def drc(project: ProjectState, run: RunState) -> ProcessResult:
    capability = probe(project)
    if capability.timed_out or capability.returncode != 0:
        raise FileNotFoundError("kicad-cli pcb drc capability probe failed")
    output = run.raw_directory / "kicad-drc.json"
    result = run_process(
        project.root,
        [
            "kicad-cli", "pcb", "drc", "--format", "json", "--output", str(output),
            "--severity-all", "--exit-code-violations", str(_board(project)),
        ],
        timeout=300,
    )
    if result.returncode in {0, 5}:
        if not output.is_file() or output.is_symlink():
            raise ValueError("KiCad DRC did not produce regular JSON evidence")
        try:
            json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("KiCad DRC evidence is malformed") from error
    return result


def result_check(result: ProcessResult, artifact: Path | None = None) -> Check:
    if result.timed_out:
        status, message = CheckStatus.BLOCKED, "KiCad DRC timed out"
    elif result.returncode == 0:
        status, message = CheckStatus.PASS, "KiCad DRC completed without violations"
    elif result.returncode == 5:
        status, message = CheckStatus.FAIL, "KiCad DRC found violations"
    elif result.returncode in {2, 3}:
        status, message = CheckStatus.BLOCKED, f"KiCad rejected command/input ({result.returncode})"
    else:
        status, message = CheckStatus.BLOCKED, f"KiCad DRC could not complete ({result.returncode})"
    evidence = {}
    if artifact is not None and artifact.is_file():
        evidence = {"path": str(artifact), "sha256": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()}
    return Check("KICAD_DRC", status, Severity.ERROR, message, "tool", result.argv,
                 result.returncode, result.duration_seconds, evidence, True)
