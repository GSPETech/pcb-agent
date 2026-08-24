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
    path = Path(located)
    if path.is_symlink():
        path = path.resolve(strict=True)
    else:
        path = path.absolute()
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
