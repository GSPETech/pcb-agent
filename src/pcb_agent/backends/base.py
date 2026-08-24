"""Small backend contract."""

from __future__ import annotations

from dataclasses import dataclass

from ..process import ProcessResult


class BackendError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BackendResult:
    process: ProcessResult
    changed_paths: tuple[str, ...]
