"""Repository-owned evidence provenance for the Diode net-naming spike.

The adapter registry must never silently trust a captured evidence digest.
A `ComponentAdapter`'s `evidence_sha256` is only meaningful if the referenced
file exists, its manifest entry exists, the on-disk bytes match the digest,
and the version record matches the adapter's verified pcbc versions.

All evidence must be repository-owned: paths are resolved inside an evidence
root that is itself inside the repository, never from arbitrary home paths.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Mapping

from .paths import resolve_workspace_path


class EvidenceError(ValueError):
    pass


_MANIFEST_ENTRY = re.compile(r"^[0-9a-f]{64}\s+(\S+)$")
_PCBC_VERSION_LINE = re.compile(r"\Apcbc (\d+\.\d+\.\d+)\n\Z")


def load_evidence_manifest(manifest_path: Path) -> dict[str, str]:
    """Parse a `sha256sum`-style manifest into {relative_path: sha256_hex}.

    Blank lines and `#` comment lines are ignored. A duplicate path is an
    error because the bundle must list every file exactly once.
    """
    if manifest_path.is_symlink():
        raise EvidenceError("evidence manifest is a symlink")
    if not manifest_path.is_file():
        raise EvidenceError(f"evidence manifest missing: {manifest_path}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _MANIFEST_ENTRY.match(stripped)
        if match is None:
            raise EvidenceError(
                f"{manifest_path.name}:{line_number}: malformed manifest entry"
            )
        relative = match.group(1)
        while relative.startswith("./"):
            relative = relative[2:]
        if relative in entries:
            raise EvidenceError(
                f"{manifest_path.name}:{line_number}: duplicate entry {relative}"
            )
        entries[relative] = match.group(0).split()[0]
    return entries


def _ensure_within(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise EvidenceError(f"evidence path must be relative: {relative!r}")
    try:
        return resolve_workspace_path(root, relative, must_exist=True)
    except (OSError, ValueError) as error:
        raise EvidenceError(f"evidence path invalid: {relative}: {error}") from error


def validate_evidence_artifact(
    evidence_root: Path,
    manifest: Mapping[str, str],
    relative: str,
    expected_sha256: str,
    *,
    label: str,
) -> bytes:
    """Verify one evidence artifact exists and its bytes match the manifest.

    `expected_sha256` is the `sha256:<64hex>` digest the adapter declares.
    The manifest entry must exist and equal the same digest; then the on-disk
    bytes must hash to it.
    """
    if not isinstance(expected_sha256, str) or not expected_sha256.startswith("sha256:"):
        raise EvidenceError(f"{label}: malformed evidence digest {expected_sha256!r}")
    manifest_digest = manifest.get(relative)
    if manifest_digest is None:
        raise EvidenceError(f"{label}: evidence {relative!r} missing from manifest")
    if "sha256:" + manifest_digest != expected_sha256:
        raise EvidenceError(
            f"{label}: digest mismatch for {relative!r} "
            f"(adapter {expected_sha256}, manifest sha256:{manifest_digest})"
        )
    path = _ensure_within(evidence_root, relative)
    if not path.is_file():
        raise EvidenceError(f"{label}: evidence file missing: {relative}")
    data = path.read_bytes()
    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise EvidenceError(f"{label}: on-disk hash mismatch for {relative}")
    return data


def validate_adapter_provenance(
    adapter: object,
    evidence_root: Path,
    manifest: Mapping[str, str],
) -> None:
    """Validate a `ComponentAdapter`'s declared evidence against the bundle.

    Each adapter must declare `evidence_result_path` and `evidence_source_path`
    (relative to the evidence root), plus `evidence_source_sha256`.
    `evidence_sha256` must equal the manifest digest of the result path.
    """
    kind = getattr(adapter, "kind", None)
    if not isinstance(kind, str) or not kind:
        raise EvidenceError("adapter has no kind")

    result_path = getattr(adapter, "evidence_result_path", None)
    source_path = getattr(adapter, "evidence_source_path", None)
    source_sha256 = getattr(adapter, "evidence_source_sha256", None)
    if not isinstance(result_path, str) or not isinstance(source_path, str):
        raise EvidenceError(
            f"adapter {kind}: evidence_result_path/evidence_source_path required"
        )
    if not isinstance(source_sha256, str) or not source_sha256.startswith("sha256:"):
        raise EvidenceError(f"adapter {kind}: evidence_source_sha256 required")

    expected = getattr(adapter, "evidence_sha256", None)
    if not isinstance(expected, str):
        raise EvidenceError(f"adapter {kind}: evidence_sha256 required")
    validate_evidence_artifact(
        evidence_root, manifest, result_path, expected, label=f"adapter {kind} result"
    )
    validate_evidence_artifact(
        evidence_root, manifest, source_path, source_sha256,
        label=f"adapter {kind} source",
    )


def validate_version_record(evidence_root: Path, manifest: Mapping[str, str]) -> str:
    """Verify `pcb-version.txt` against the manifest and return the pcbc version.

    The record must be listed in the manifest, the on-disk bytes must hash to
    the manifest entry, and the bytes must be exactly one `pcbc X.Y.Z\n` line.
    A symlinked version file, a manifest/evidence-root symlink, missing entry,
    digest mismatch, missing file, invalid UTF-8, missing newline, extra line,
    or malformed record is a fail-closed `EvidenceError`.
    """
    if evidence_root.is_symlink():
        raise EvidenceError("evidence root is a symlink")
    relative = "pcb-version.txt"
    if relative not in manifest:
        raise EvidenceError("pcb-version.txt missing from manifest")
    path = _ensure_within(evidence_root, relative)
    if path.is_symlink():
        raise EvidenceError("pcb-version.txt is a symlink")
    if not path.is_file():
        raise EvidenceError("evidence file missing: pcb-version.txt")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest[relative]:
        raise EvidenceError("pcb-version.txt on-disk hash differs from manifest")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvidenceError("pcb-version.txt is not valid UTF-8") from error
    match = _PCBC_VERSION_LINE.match(text)
    if match is None:
        raise EvidenceError(
            "pcb-version.txt must be exactly one pcbc <major>.<minor>.<patch> line"
        )
    return match.group(1)


def validate_registry_provenance(
    registry: Mapping[str, object],
    evidence_root: Path,
    manifest_path: Path,
) -> None:
    """Validate every adapter in a registry against the evidence bundle.

    Fails closed on the first missing file, missing manifest entry, digest
    mismatch, or malformed digest. The manifest must also cover the version
    record used by the adapters, and the parsed pcbc version must be verified
    by every adapter that declares a version set.
    """
    if not evidence_root.is_dir():
        raise EvidenceError(f"evidence root missing: {evidence_root}")
    manifest = load_evidence_manifest(manifest_path)
    captured_version = validate_version_record(evidence_root, manifest)

    for adapter in registry.values():
        if not isinstance(adapter, object):
            continue
        kind = getattr(adapter, "kind", None)
        verified = getattr(adapter, "verified_pcbc_versions", frozenset())
        if isinstance(verified, frozenset) and verified and captured_version not in verified:
            raise EvidenceError(
                f"adapter {kind}: evidence version {captured_version} not verified"
            )
        validate_adapter_provenance(adapter, evidence_root, manifest)
