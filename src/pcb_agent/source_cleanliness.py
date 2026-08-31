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
from typing import Optional


class SourceCleanlinessError(RuntimeError):
    pass


_GIT_TIMEOUT = 120


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _evidence_exclusion(repo_root: Path, evidence_root: Path) -> str:
    """Build the git exclude pathspec for ``evidence_root`` inside ``repo_root``.

    Both roots are canonicalized before comparison so relative paths, ``..``
    segments, or symlinked components cannot smuggle an outside root past the
    containment check. Failing to resolve either root, or an evidence root
    that is not strictly inside the repo root, raises
    ``SourceCleanlinessError`` (fail closed) instead of a bare ``ValueError``.
    """
    try:
        resolved_repo = Path(repo_root).resolve(strict=True)
        resolved_evidence = Path(evidence_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceCleanlinessError(
            f"cannot resolve source-cleanliness roots: {exc}"
        ) from exc
    try:
        relative = resolved_evidence.relative_to(resolved_repo)
    except ValueError as exc:
        raise SourceCleanlinessError(
            f"evidence root {evidence_root} is not strictly inside "
            f"repo root {repo_root}"
        ) from exc
    if relative == Path("."):
        raise SourceCleanlinessError(
            f"evidence root {evidence_root} is not strictly inside "
            f"repo root {repo_root}"
        )
    return relative.as_posix() + "/**"


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


def measure_source_cleanliness(
    repo_root: Path,
    evidence_root: Path,
    baseline_revision: Optional[str] = None,
) -> dict:
    """Return a machine-readable cleanliness record.

    Raises ``SourceCleanlinessError`` when either root cannot be resolved or
    the evidence root is not strictly inside the repo root, when any git
    command exits non-zero, or when the current revision differs from
    ``baseline_revision`` (if provided).
    """
    measured_at = datetime.now(timezone.utc).isoformat()
    pathspec = _evidence_exclusion(repo_root, evidence_root)
    exclude = f":(exclude){pathspec}"

    revision = _git_bytes(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if baseline_revision is not None and revision != baseline_revision:
        raise SourceCleanlinessError(
            f"revision drift: expected {baseline_revision}, got {revision}"
        )

    raw_status = _git_bytes(
        repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )

    filtered_status = _git_bytes(
        repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
        "--", ".", exclude,
    )
    staged = _git_bytes(repo_root, "diff", "--cached", "--binary", "--", ".", exclude)
    unstaged = _git_bytes(repo_root, "diff", "--binary", "--", ".", exclude)

    # Lossless encoding of raw binary data
    def encode_bytes(data: bytes) -> str:
        return data.hex()

    return {
        "repo_revision": revision,
        "raw_status_encoding": "hex",
        "raw_status": encode_bytes(raw_status),
        "raw_status_sha256": _sha256(raw_status),
        "filtered_source_status_encoding": "hex",
        "filtered_source_status": encode_bytes(filtered_status),
        "filtered_source_status_sha256": _sha256(filtered_status),
        "staged_diff_sha256": _sha256(staged),
        "unstaged_diff_sha256": _sha256(unstaged),
        "exclusion": pathspec,
        "source_clean": not filtered_status,
        "measured_at": measured_at,
    }