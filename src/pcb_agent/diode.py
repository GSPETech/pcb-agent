"""Capability-probed Diode command adapter."""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import uuid
from typing import Any, Mapping, Sequence

from .models import Check, CheckStatus, Severity
from .process import ProcessResult, run_process
from .state import ConfigurationError, ProjectState


_COMMAND_KEYS = {"build-command", "test-command", "layout-command", "layout-check-command"}


def configured_command(project: ProjectState, key: str) -> tuple[str, ...] | None:
    if key not in _COMMAND_KEYS:
        raise ConfigurationError(f"unsupported Diode command key: {key}")
    defaults = {
        "build-command": ["pcb", "build", project.source],
        "test-command": ["pcb", "test", project.test, "-f", "json"],
        "layout-command": ["pcb", "layout", project.source, "--no-open", "-f", "json"],
        "layout-check-command": ["pcb", "layout", project.source, "--check", "-f", "json"],
    }
    value = defaults[key]
    if not isinstance(value, list) or not value or any(not isinstance(arg, str) or not arg for arg in value):
        raise ConfigurationError(f"{key} must be a non-empty string array")
    if value[0] not in {"pcb", "pcbc"}:
        raise ConfigurationError(f"{key} executable must be pcb or pcbc")
    forbidden = {"--netlist", "simulate", "publish", "erc", "autoroute"}
    if any(arg.lower() in forbidden for arg in value[1:]):
        raise ConfigurationError(f"{key} requests unsupported or unsafe capability")
    return tuple(value)


def probe(
    project: ProjectState, executable: str = "pcb", command: str | None = None
) -> ProcessResult:
    argv = [executable, *([command] if command else []), "--help"]
    return run_process(project.root, argv, timeout=30)


def doctor_probes(project: ProjectState) -> tuple[ProcessResult, ...]:
    commands = (
        ("pcb", "--version"), ("pcb", "help"), ("pcb", "help", "build"),
        ("pcb", "help", "test"), ("pcb", "help", "layout"),
        ("pcb", "help", "simulate"), ("pcb", "toolchain", "show"),
    )
    return tuple(run_process(project.root, command, timeout=30) for command in commands)


def execute(project: ProjectState, key: str, *, trusted_root: Path | None = None) -> ProcessResult:
    command = configured_command(project, key)
    if command is None:
        raise ConfigurationError(f"project.toml does not define {key}")
    capability = probe(project, command[0], command[1] if len(command) > 1 else None)
    if capability.timed_out or capability.returncode != 0:
        raise FileNotFoundError(f"{command[0]} capability probe failed")
    if key != "test-command" or trusted_root is None:
        return run_process(project.root, command, timeout=300)
    snapshot = trusted_root / f"trusted-test-{uuid.uuid4().hex}"
    snapshot.mkdir(parents=True, exist_ok=False)
    closure = [path.relative_to(project.root).as_posix() for path in (project.root / "src").rglob("*") if path.is_file()]
    closure.extend((project.test, "pcb.toml", "pcb-version"))
    for relative in dict.fromkeys(closure):
        source = project.root / relative
        if source.exists():
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    snapshot_command = list(command)
    snapshot_command[snapshot_command.index(project.test)] = project.test
    result = run_process(snapshot, snapshot_command, timeout=300)
    if result.returncode == 0:
        if result.output_truncated:
            raise ValueError("pcb test JSON output was truncated")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("pcb test returned malformed JSON") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list) or not isinstance(payload.get("summary"), dict):
            raise ValueError("pcb test JSON lacks results/summary contract")
        expected = [item["test"] for item in project.acceptance["checks"]
                    if item["kind"] == "zener_test" and item["expected"] == "PASS"]
        if any(item["expected"] == "FAIL" for item in project.acceptance["checks"]):
            raise ValueError("negative fixture unexpectedly passed its locked acceptance")
        def records(value: object):
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from records(child)
            elif isinstance(value, list):
                for child in value:
                    yield from records(child)
        all_records = tuple(records(payload["results"]))
        for name in expected:
            matches = [record for record in all_records if name in {
                record.get("name"), record.get("test"),
                f"{record.get('test_bench_name')}.{record.get('check_name')}",
            }]
            if not matches or not all(str(record.get("status", "")).upper() in {"PASS", "PASSED", "OK"}
                                      for record in matches):
                raise ValueError(f"pcb test JSON lacks passing acceptance result: {name}")
        summary = payload["summary"]
        if (any(not isinstance(summary.get(key), int) for key in ("total", "passed", "failed"))
                or summary["total"] != len(payload["results"])
                or summary["passed"] + summary["failed"] != summary["total"]):
            raise ValueError("pcb test JSON summary is inconsistent")
        if any(isinstance(summary.get(key), int) and summary[key] > 0 for key in ("failed", "failures", "errors")):
            raise ValueError("pcb test JSON reports failures despite zero exit")
    return result


def result_check(check_id: str, result: ProcessResult, *, required: bool = True) -> Check:
    environment_error = any(text in result.stderr.lower() for text in (
        "a required privilege is not held by the client",
    ))
    status = (CheckStatus.BLOCKED if result.timed_out or environment_error else
              (CheckStatus.PASS if result.returncode == 0 else CheckStatus.FAIL))
    message = ("command timed out" if result.timed_out else
               "command blocked by environment" if environment_error else
               f"command exited {result.returncode}")
    return Check(
        check_id,
        status,
        Severity.ERROR,
        message,
        "tool", result.argv, result.returncode, result.duration_seconds,
        {"stdout": result.stdout, "stderr": result.stderr},
        required,
    )
