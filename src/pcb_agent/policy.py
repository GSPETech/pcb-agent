"""Protected-file integrity and narrowly scoped backend recovery."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
import json
import uuid

from .paths import PathViolation, resolve_workspace_path


class PolicyViolation(RuntimeError):
    pass


@dataclass(slots=True)
class WorkspaceLock:
    path: Path
    owner: str

    @classmethod
    def acquire(cls, root: Path | str) -> "WorkspaceLock":
        path = Path(root).resolve(strict=True) / ".pcb-agent.lock"
        owner = f"{os.getpid()}-{uuid.uuid4().hex}"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                pid = int(existing.get("pid"))
                os.kill(pid, 0)
            except ProcessLookupError:
                path.unlink()
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                raise PolicyViolation("workspace lock exists but ownership cannot be verified")
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise PolicyViolation("another pcb-agent run owns workspace lock") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"owner": owner, "pid": os.getpid()}, handle)
        return cls(path, owner)

    def release(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("owner") != self.owner:
                raise PolicyViolation("workspace lock ownership changed")
            self.path.unlink()
        except FileNotFoundError:
            raise PolicyViolation("workspace lock disappeared")


def _digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _read_state(path: Path) -> bytes | None:
    if path.is_symlink():
        raise PolicyViolation(f"symlink is not allowed: {path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise PolicyViolation(f"regular file required: {path}")
    return path.read_bytes()


@dataclass(frozen=True, slots=True)
class ProtectedHashes:
    root: Path
    hashes: Mapping[str, str]

    @classmethod
    def capture(cls, root: Path | str, paths: Iterable[Path | str]) -> "ProtectedHashes":
        base = Path(root).resolve(strict=True)
        hashes: dict[str, str] = {}
        for item in paths:
            if (base / item).is_symlink():
                raise PolicyViolation(f"symlink is not allowed: {item}")
            path = resolve_workspace_path(base, item, must_exist=True)
            data = _read_state(path)
            if data is None:
                raise PolicyViolation(f"protected file is missing: {item}")
            hashes[path.relative_to(base).as_posix()] = _digest(data) or ""
        return cls(base, hashes)

    def verify(self) -> None:
        for relative, expected in self.hashes.items():
            try:
                path = resolve_workspace_path(self.root, relative, must_exist=True)
                actual = _digest(_read_state(path))
            except (FileNotFoundError, PathViolation):
                actual = None
            if actual != expected:
                raise PolicyViolation(f"protected file changed: {relative}")


@dataclass(frozen=True, slots=True)
class _FileState:
    before: bytes | None
    backend_digest: str | None
    sealed: bool = False


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    root: Path
    states: Mapping[str, _FileState]

    @classmethod
    def capture_before(
        cls, root: Path | str, editable_paths: Iterable[Path | str]
    ) -> "WorkspaceSnapshot":
        base = Path(root).resolve(strict=True)
        states: dict[str, _FileState] = {}
        for item in editable_paths:
            if (base / item).is_symlink():
                raise PolicyViolation(f"symlink is not allowed: {item}")
            path = resolve_workspace_path(base, item)
            relative = path.relative_to(base).as_posix()
            states[relative] = _FileState(_read_state(path), None)
        return cls(base, states)

    def seal_backend_changes(self) -> "WorkspaceSnapshot":
        sealed: dict[str, _FileState] = {}
        for relative, state in self.states.items():
            path = resolve_workspace_path(self.root, relative)
            current = _read_state(path)
            if current != state.before:
                sealed[relative] = _FileState(state.before, _digest(current), True)
        return WorkspaceSnapshot(self.root, sealed)

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self.states))

    def restore_backend_changes(self) -> tuple[str, ...]:
        restored: list[str] = []
        for relative, state in self.states.items():
            if not state.sealed:
                raise PolicyViolation("snapshot must be sealed before restore")
            path = resolve_workspace_path(self.root, relative)
            if _digest(_read_state(path)) != state.backend_digest:
                raise PolicyViolation(
                    f"refusing to overwrite post-backend modification: {relative}"
                )
            if state.before is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.restore-{os.getpid()}")
                try:
                    temporary.write_bytes(state.before)
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            restored.append(relative)
        return tuple(restored)
