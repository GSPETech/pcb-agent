"""Generic TOML-configured command backend."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from ..process import ProcessResult, run_process
from .base import BackendError, BackendResult


class CommandBackend:
    def __init__(self, config_path: Path | str) -> None:
        path = Path(config_path).resolve(strict=True)
        try:
            config = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise BackendError(f"invalid backend TOML: {error}") from error
        table = config.get("backend", config)
        argv = table.get("argv") if isinstance(table, dict) else None
        transport = table.get("task_transport", "stdin") if isinstance(table, dict) else None
        if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) or not arg for arg in argv):
            raise BackendError("backend argv must be a non-empty string array")
        if transport not in {"stdin", "argv"}:
            raise BackendError("task_transport must be stdin or argv")
        self.argv = tuple(argv)
        self.transport = transport

    def probe(self, workspace: Path) -> ProcessResult:
        return run_process(workspace, [self.argv[0], "--help"], timeout=30)

    def execute(self, task: str, workspace: Path, timeout: float) -> BackendResult:
        if os.environ.get("PCB_AGENT_TEST_BACKEND") != "1":
            raise BackendError("generic backend BLOCKED: OS-enforced network isolation unavailable")
        probe = self.probe(workspace)
        if probe.timed_out or probe.returncode != 0:
            raise BackendError("backend capability probe failed")
        command = list(self.argv)
        input_text = task if self.transport == "stdin" else None
        if self.transport == "argv":
            command.append(task)
        result = run_process(workspace, command, timeout=timeout,
                             env={"PCB_AGENT_ACTIVE": "1"}, input_text=input_text)
        return BackendResult(result, ())
