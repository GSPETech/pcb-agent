"""Locked harness policy loaded from config/policies.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


CONFIG_ROOT = Path(__file__).resolve().parent.parent.parent / "config"


class PolicyConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Policy:
    max_iterations: int
    max_changed_files: int
    allow_files: tuple[str, ...]
    deny_files: tuple[str, ...]
    allow_symlinks: bool
    allow_path_escape: bool
    network: str
    production_ready: bool
    fabrication_approved: bool

    @classmethod
    def load(cls, path: Path | None = None) -> "Policy":
        target = path or (CONFIG_ROOT / "policies.toml")
        try:
            data = tomllib.loads(target.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise PolicyConfigError(f"cannot load policy: {error}") from error
        if not isinstance(data, dict):
            raise PolicyConfigError("policy root must be a TOML table")
        return cls._from_mapping(data)

    @classmethod
    def _from_mapping(cls, data: dict) -> "Policy":
        network = data.get("network")
        if network != "deny":
            raise PolicyConfigError("policy.network must be 'deny'")

        production_ready = data.get("production_ready")
        if production_ready is not False:
            raise PolicyConfigError("policy.production_ready must be false")

        fabrication_approved = data.get("fabrication_approved")
        if fabrication_approved is not False:
            raise PolicyConfigError("policy.fabrication_approved must be false")

        max_iterations = data.get("max_iterations")
        if not isinstance(max_iterations, int) or not 1 <= max_iterations <= 5:
            raise PolicyConfigError("policy.max_iterations must be an integer between 1 and 5")

        workspace = data.get("workspace")
        if not isinstance(workspace, dict):
            raise PolicyConfigError("policy.workspace must be a table")

        allow_symlinks = workspace.get("allow_symlinks")
        if allow_symlinks is not False:
            raise PolicyConfigError("policy.workspace.allow_symlinks must be false")

        allow_path_escape = workspace.get("allow_path_escape")
        if allow_path_escape is not False:
            raise PolicyConfigError("policy.workspace.allow_path_escape must be false")

        max_changed_files = workspace.get("max_changed_files")
        if not isinstance(max_changed_files, int) or max_changed_files < 1:
            raise PolicyConfigError("policy.workspace.max_changed_files must be a positive integer")

        files = data.get("files")
        if not isinstance(files, dict):
            raise PolicyConfigError("policy.files must be a table")

        allow_files = _normalize_patterns(files.get("allow"))
        if not allow_files:
            raise PolicyConfigError("policy.files.allow must be a non-empty list of patterns")

        deny_files = _normalize_patterns(files.get("deny"))
        if not deny_files:
            raise PolicyConfigError("policy.files.deny must be a non-empty list of patterns")

        return cls(
            max_iterations=max_iterations,
            max_changed_files=max_changed_files,
            allow_files=allow_files,
            deny_files=deny_files,
            allow_symlinks=allow_symlinks,
            allow_path_escape=allow_path_escape,
            network=network,
            production_ready=production_ready,
            fabrication_approved=fabrication_approved,
        )


def _normalize_patterns(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        return ()
    patterns: list[str] = []
    seen: set[str] = set()

    for item in value:
        if not isinstance(item, str) or not item.strip():
            return ()
        if item in seen:
            continue
        try:
            _segments(item)
        except ValueError:
            return ()
        seen.add(item)
        patterns.append(item)
    return tuple(patterns)


def _segments(value: str) -> tuple[str, ...]:
    from pathlib import PurePosixPath

    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)

    if path.is_absolute():
        raise ValueError("absolute policy path is forbidden")

    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid policy path")

    return parts


def matches(path: str, pattern: str) -> bool:
    """Segment-safe glob-style match with `**` semantics."""
    try:
        path_parts = _segments(path)
        pattern_parts = _segments(pattern)
    except ValueError:
        return False

    from fnmatch import fnmatchcase
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)

        token = pattern_parts[pattern_index]

        if token == "**":
            return (
                match(path_index, pattern_index + 1)
                or (
                    path_index < len(path_parts)
                    and match(path_index + 1, pattern_index)
                )
            )

        return (
            path_index < len(path_parts)
            and fnmatchcase(path_parts[path_index], token)
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)