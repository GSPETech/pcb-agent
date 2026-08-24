"""Atomic machine and human verification reports."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import VerificationReport


WARNING = (
    "Verification PASS does not mean production-ready. "
    "Fabrication requires review and approval by a human engineer."
)


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def render_markdown(report: VerificationReport) -> str:
    lines = [
        "# PCB Verification Report",
        "",
        f"> **{WARNING}**",
        "",
        f"- Project: `{report.project}`",
        f"- Status: **{report.status}**",
        "- Production ready: **false**",
        "- Fabrication approved: **false**",
        f"- Timestamp: `{report.timestamp}`",
        "",
        "## Checks",
        "",
        "| ID | Status | Severity | Required | Message |",
        "|---|---|---|---:|---|",
    ]
    for check in report.checks:
        message = check.message.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{check.id}` | {check.status} | {check.severity} | "
            f"{str(check.required).lower()} | {message} |"
        )
    return "\n".join(lines) + "\n"


def write_report(
    report: VerificationReport,
    json_path: Path | str,
    markdown_path: Path | str,
) -> None:
    json_data = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    _atomic_write(Path(json_path), json_data)
    _atomic_write(Path(markdown_path), render_markdown(report))
