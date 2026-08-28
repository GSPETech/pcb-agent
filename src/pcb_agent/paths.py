"""Workspace path and executable validation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable


class PathViolation(ValueError):
    pass


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_workspace_path(
    workspace: Path | str,
    candidate: Path | str,
    *,
    must_exist: bool = False,
    allow_root: bool = False,
) -> Path:
    root = Path(workspace).resolve(strict=True)
    raw = Path(candidate)
    path = (root / raw).resolve(strict=must_exist) if not raw.is_absolute() else raw.resolve(strict=must_exist)
    if not _is_relative_to(path, root) or (path == root and not allow_root):
        raise PathViolation(f"path escapes workspace: {candidate}")
    return path


def require_regular_file(path: Path, *, reject_symlink: bool = True) -> Path:
    if reject_symlink and path.is_symlink():
        raise PathViolation(f"symlink is not allowed: {path}")
    if not path.is_file():
        raise PathViolation(f"regular file required: {path}")
    return path


def relative_evidence_path(path: Path | str, project_root: Path | str) -> str:
    """Return a POSIX path relative to the project root.

    Reports must not carry absolute host paths: they leak the operator's home
    directory and stop the report from being verifiable after the project moves.
    """
    resolved_root = Path(project_root).resolve(strict=True)
    resolved_path = Path(path).resolve(strict=True)
    if not _is_relative_to(resolved_path, resolved_root):
        raise PathViolation(f"evidence path escapes project root: {path}")
    return resolved_path.relative_to(resolved_root).as_posix()


def validate_executable(
    executable: str,
    *,
    workspace: Path | str,
    trusted_roots: Iterable[Path | str] = (),
) -> Path:
    if not executable or "\x00" in executable:
        raise PathViolation("invalid executable name")
    located = shutil.which(executable)
    if located is None:
        raise FileNotFoundError(f"executable not found: {executable}")
    # Always canonicalise. On Windows shutil.which can return an 8.3 short path
    # (for example RUNNER~1) while workspace and trusted roots resolve to long
    # paths, which would make containment checks silently pass.
    path = Path(located).resolve(strict=True)
    require_regular_file(path, reject_symlink=False)

    root = Path(workspace).resolve(strict=True)
    if _is_relative_to(path, root):
        raise PathViolation(f"workspace executable is not trusted: {path}")
    roots = tuple(Path(item).resolve(strict=True) for item in trusted_roots)
    if roots and not any(_is_relative_to(path, trusted) for trusted in roots):
        raise PathViolation(f"executable is outside trusted roots: {path}")
    if os.name == "nt" and path.suffix.lower() not in {".exe", ".com"}:
        raise PathViolation(f"unsupported Windows executable type: {path}")
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise PathViolation(f"file is not executable: {path}")
    return path
