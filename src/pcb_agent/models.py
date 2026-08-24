"""Stable verification data model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    status: CheckStatus
    severity: Severity = Severity.ERROR
    message: str = ""
    provenance: str = "harness"
    command: tuple[str, ...] = ()
    exit_code: int | None = None
    duration: float | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    required: bool = True

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("check id must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_status(checks: tuple[Check, ...]) -> CheckStatus:
    required = tuple(check for check in checks if check.required)
    if not required:
        return CheckStatus.BLOCKED
    for status in (
        CheckStatus.BLOCKED,
        CheckStatus.FAIL,
        CheckStatus.HUMAN_REVIEW,
    ):
        if any(check.status == status for check in required):
            return status
    if any(check.status == CheckStatus.SKIPPED for check in required):
        return CheckStatus.BLOCKED
    return CheckStatus.PASS


@dataclass(frozen=True, slots=True)
class VerificationReport:
    project: str
    checks: tuple[Check, ...]
    profile: str = "schematic"
    run_id: str = ""
    source_dirty: bool = False
    versions: Mapping[str, str] = field(default_factory=dict)
    hashes: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[Mapping[str, Any], ...] = ()
    status: CheckStatus | None = None
    schema_version: str = "1"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    production_ready: bool = field(default=False, init=False)
    fabrication_approved: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.project or not self.project.strip():
            raise ValueError("project must not be empty")
        calculated = aggregate_status(self.checks)
        if self.status is None:
            object.__setattr__(self, "status", calculated)
        elif self.status != calculated:
            raise ValueError(
                f"report status {self.status} does not match checks ({calculated})"
            )
        if self.profile not in {"schematic", "layout"}:
            raise ValueError("profile must be schematic or layout")

    @property
    def human_review_required(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["human_review_required"] = self.human_review_required
        return data
