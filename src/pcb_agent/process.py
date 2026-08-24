"""Bounded, redacted subprocess execution without a shell."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from dataclasses import field

from .paths import resolve_workspace_path, validate_executable


DEFAULT_ENV_ALLOWLIST = frozenset(
    {"HOME", "LANG", "LC_ALL", "PATH", "PATHEXT", "PCB_AGENT_ACTIVE", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "USERPROFILE"}
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+"),
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b(?:ghp|github_pat|sk)-[A-Za-z0-9_-]{12,}\b"),
)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    output_truncated: bool
    input_hashes: Mapping[str, str] = field(default_factory=dict)


def redact_secrets(value: str) -> str:
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", value)
    return value


def _read_output(handle: object, limit: int) -> tuple[str, bool]:
    handle.seek(0, os.SEEK_END)  # type: ignore[attr-defined]
    size = handle.tell()  # type: ignore[attr-defined]
    handle.seek(0)  # type: ignore[attr-defined]
    data = handle.read(limit)  # type: ignore[attr-defined]
    value = data.decode("utf-8", errors="replace")
    if size <= limit:
        return redact_secrets(value), False
    return redact_secrets(value) + f"\n...[truncated {size - limit} bytes]", True


def _child_environment(
    overrides: Mapping[str, str] | None, allowlist: frozenset[str]
) -> dict[str, str]:
    normalized = {name.upper() for name in allowlist}
    result = {key: value for key, value in os.environ.items() if key.upper() in normalized}
    for key, value in (overrides or {}).items():
        if key.upper() not in normalized:
            raise ValueError(f"environment variable is not allowlisted: {key}")
        if "\x00" in key or "\x00" in value or "=" in key:
            raise ValueError(f"invalid environment variable: {key!r}")
        result[key] = value
    return result


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        taskkill = system_root / "System32" / "taskkill.exe"
        try:
            subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_process(
    workspace: Path | str,
    argv: Sequence[str],
    *,
    cwd: Path | str = ".",
    timeout: float = 300.0,
    env: Mapping[str, str] | None = None,
    env_allowlist: Iterable[str] = DEFAULT_ENV_ALLOWLIST,
    trusted_executable_roots: Iterable[Path | str] = (),
    output_limit: int = 200_000,
    input_text: str | None = None,
) -> ProcessResult:
    if not argv or any(not isinstance(arg, str) or "\x00" in arg for arg in argv):
        raise ValueError("argv must contain non-NUL strings")
    if timeout <= 0 or output_limit < 0:
        raise ValueError("timeout must be positive and output_limit non-negative")
    workdir = resolve_workspace_path(workspace, cwd, must_exist=True, allow_root=True)
    if not workdir.is_dir():
        raise ValueError(f"cwd is not a directory: {workdir}")
    executable = validate_executable(
        argv[0], workspace=workspace, trusted_roots=trusted_executable_roots
    )
    command = [str(executable), *argv[1:]]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=workdir,
            env=_child_environment(env, frozenset(env_allowlist)),
            shell=False,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        timed_out = False
        try:
            process.communicate(input=input_text.encode("utf-8") if input_text is not None else None,
                                timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_tree(process)
            process.communicate()
        stdout, stdout_cut = _read_output(stdout_file, output_limit)
        stderr, stderr_cut = _read_output(stderr_file, output_limit)
    safe_argv = tuple(redact_secrets(arg) for arg in command)
    return ProcessResult(
        argv=safe_argv,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
        output_truncated=stdout_cut or stderr_cut,
    )
