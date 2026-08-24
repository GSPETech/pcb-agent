"""Detection-only Codex adapter until invocation contract is verified."""

from __future__ import annotations

from pathlib import Path

from ..process import ProcessResult, run_process
from .base import BackendError


class CodexBackend:
    def probe(self, workspace: Path) -> ProcessResult:
        return run_process(workspace, ["codex", "exec", "--help"], timeout=30)

    def execute(self, task: str, workspace: Path, timeout: float) -> None:
        raise BackendError("Codex invocation disabled until installed exec contract is verified")
