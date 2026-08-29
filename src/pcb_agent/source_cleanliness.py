"""Per-run source cleanliness measurement for evidence capture.

Measures the repository working tree with git, excluding the evidence root so
captured artifacts never dirty the source-clean verdict. Both the raw and the
evidence-excluded status are recorded; ``source_clean`` is false when any
tracked/untracked/staged change exists outside the exclusion.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class SourceCleanlinessError(RuntimeError):
    pass


_GIT_TIMEOUT = 120


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        timeout=_GIT_TIMEOUT,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise SourceCleanlinessError(
            f"git {' '.join(args)} failed (exit {proc.returncode}): {detail}"
        )
    return proc.stdout


def measure_source_cleanliness(repo_root: Path, evidence_root: Path) -> dict:
    """Return a machine-readable cleanliness record.

    Raises ``SourceCleanlinessError`` when any git command exits non-zero; the
    caller treats that as an abort, not a clean verdict.
    """
    measured_at = datetime.now(timezone.utc).isoformat()
    revision = _git_bytes(repo_root, "rev-parse", "HEAD").decode("ascii").strip()

    raw_status = _git_bytes(
        repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    pathspec = evidence_root.relative_to(repo_root).as_posix() + "/**"
    exclude = f":(exclude){pathspec}"

    filtered_status = _git_bytes(
        repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
        "--", ".", exclude,
    )
    staged = _git_bytes(repo_root, "diff", "--cached", "--binary", "--", ".", exclude)
    unstaged = _git_bytes(repo_root, "diff", "--binary", "--", ".", exclude)

    return {
        "repo_revision": revision,
        "raw_status_encoding": "utf-8",
        "raw_status": raw_status.decode("utf-8", "replace"),
        "raw_status_sha256": _sha256(raw_status),
        "filtered_source_status_encoding": "utf-8",
        "filtered_source_status": filtered_status.decode("utf-8", "replace"),
        "filtered_source_status_sha256": _sha256(filtered_status),
        "staged_diff_sha256": _sha256(staged),
        "unstaged_diff_sha256": _sha256(unstaged),
        "exclusion": pathspec,
        "source_clean": not filtered_status,
        "measured_at": measured_at,
    }