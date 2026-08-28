"""Capability-probed Diode command adapter."""

from __future__ import annotations

from pathlib import Path
import json
import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any, Mapping

from .models import Check, CheckStatus, Severity
from .process import ProcessResult, run_process
from .state import ConfigurationError, ProjectState


_COMMAND_KEYS = {"build-command", "test-command", "layout-command", "layout-check-command"}

GENERATED_TESTS: Mapping[str, tuple[str, str]] = {
    "CONNECTIVITY": (
        "tests/.pcb-agent-connectivity.generated.zen",
        "connectivity-testbench.zen",
    ),
    "SPECIFICATION": (
        "tests/.pcb-agent-specification.generated.zen",
        "specification-testbench.zen",
    ),
}

_GENERATED_TEST_ENVIRONMENT_FRAGMENTS = (
    "a required privilege is not held by the client",
)


@dataclass(frozen=True)
class GeneratedTestResult:
    process: ProcessResult
    generated_path: str
    generated_sha256: str
    result_path: str
    result_sha256: str


class GeneratedEvidenceError(ValueError):
    pass


class GeneratedCompatibilityError(GeneratedEvidenceError):
    pass


class GeneratedAssertionFailure(GeneratedEvidenceError):
    pass


def configured_command(project: ProjectState, key: str) -> tuple[str, ...]:
    if key not in _COMMAND_KEYS:
        raise ConfigurationError(f"unsupported Diode command key: {key}")
    defaults = {
        "build-command": ["pcb", "build", project.source],
        "test-command": ["pcb", "test", project.test, "-f", "json"],
        "layout-command": ["pcb", "layout", project.source, "--no-open", "-f", "json"],
        "layout-check-command": ["pcb", "layout", project.source, "--check", "-f", "json"],
    }
    value = defaults[key]
    if not isinstance(value, list) or not value or any(not isinstance(arg, str) or not arg for arg in value):
        raise ConfigurationError(f"{key} must be a non-empty string array")
    if value[0] not in {"pcb", "pcbc"}:
        raise ConfigurationError(f"{key} executable must be pcb or pcbc")
    forbidden = {"--netlist", "simulate", "publish", "erc", "autoroute"}
    if any(arg.lower() in forbidden for arg in value[1:]):
        raise ConfigurationError(f"{key} requests unsupported or unsafe capability")
    return tuple(value)


def probe(
    project: ProjectState, executable: str = "pcb", command: str | None = None
) -> ProcessResult:
    argv = [executable, *([command] if command else []), "--help"]
    return run_process(project.root, argv, timeout=30)


def doctor_probes(project: ProjectState) -> tuple[ProcessResult, ...]:
    commands = (
        ("pcb", "--version"), ("pcb", "help"), ("pcb", "help", "build"),
        ("pcb", "help", "test"), ("pcb", "help", "layout"),
        ("pcb", "help", "simulate"), ("pcb", "toolchain", "show"),
    )
    results: list[ProcessResult] = []
    for command in commands:
        results.append(run_process(project.root, list(command), timeout=30))
    return tuple(results)


_PASS_STATUSES = frozenset({"PASS", "PASSED", "OK"})
_FAIL_STATUSES = frozenset({"FAIL", "FAILED", "ERROR"})

def _top_level_record_counts(payload: Mapping[str, Any]) -> tuple[int, int] | None:
    passed = 0
    failed = 0
    for record in payload.get("results", []):
        if not isinstance(record, dict):
            return None
        status = str(record.get("status", "")).upper()
        if not status:
            return None
        if status in _PASS_STATUSES:
            passed += 1
        elif status in _FAIL_STATUSES:
            failed += 1
        else:
            return None
    return passed, failed

def _summary_matches_records(payload: Mapping[str, Any]) -> bool:
    counts = _top_level_record_counts(payload)
    if counts is None:
        return False
    passed, failed = counts
    summary = payload.get("summary", {})
    return (
        summary.get("total") == len(payload.get("results", []))
        and summary.get("passed") == passed
        and summary.get("failed") == failed
        and passed + failed == summary.get("total")
    )


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _validate_test_payload(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, dict):
        raise GeneratedEvidenceError("pcb test JSON root is not an object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise GeneratedEvidenceError("pcb test JSON results is not an array")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise GeneratedEvidenceError("pcb test JSON summary is not an object")
    if not results:
        raise GeneratedEvidenceError("pcb test JSON results is empty")
    for record in results:
        if not isinstance(record, dict):
            raise GeneratedEvidenceError("pcb test JSON contains non-object record")
    total = _int_or_none(summary.get("total"))
    passed = _int_or_none(summary.get("passed"))
    failed = _int_or_none(summary.get("failed"))
    if total is None or passed is None or failed is None:
        raise GeneratedEvidenceError("pcb test JSON summary is incomplete")
    if total != len(results):
        raise GeneratedEvidenceError("pcb test JSON summary total mismatches results length")
    if passed + failed != total:
        raise GeneratedEvidenceError("pcb test JSON summary passed+failed mismatches total")
    for key in ("failures", "errors"):
        if key in summary:
            value = _int_or_none(summary[key])
            if value is None or value < 0:
                raise GeneratedEvidenceError(f"pcb test JSON summary {key} must be non-negative integer")
    return payload


def _record_identity(record: Mapping[str, Any]) -> tuple[str | None, str | None]:
    bench = record.get("test_bench_name")
    check = record.get("check_name")
    if isinstance(bench, str) and isinstance(check, str):
        return bench, check
    return None, None


def _find_record(payload: Mapping[str, Any], bench_name: str, check_name: str) -> Mapping[str, Any] | None:
    matches: list[Mapping[str, Any]] = []
    for record in payload["results"]:
        if not isinstance(record, dict):
            return None
        rb, rc = _record_identity(record)
        if rb == bench_name and rc == check_name:
            matches.append(record)
    if len(matches) != 1:
        return None
    return matches[0]


def execute(project: ProjectState, key: str, *, trusted_root: Path | None = None) -> ProcessResult:
    command = configured_command(project, key)
    if len(command) == 0:
        raise ConfigurationError(f"project.toml does not define {key}")
    exe = command[0]
    capability = probe(project, exe, command[1] if len(command) > 1 else None)
    if capability.timed_out or capability.returncode != 0:
        raise FileNotFoundError(f"{exe} capability probe failed")
    if key != "test-command" or trusted_root is None:
        return run_process(project.root, command, timeout=300)
    with tempfile.TemporaryDirectory(prefix="pcb-agent-trusted-test-") as temporary:
        snapshot = Path(temporary)
        closure = [path.relative_to(project.root).as_posix() for path in (project.root / "src").rglob("*") if path.is_file()]
        closure.extend((project.test, "pcb.toml", "pcb-version"))
        for relative in dict.fromkeys(closure):
            source = project.root / relative
            if source.exists():
                target = snapshot / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        snapshot_command = list(command)
        snapshot_command[snapshot_command.index(project.test)] = project.test
        result = run_process(snapshot, snapshot_command, timeout=300)
        snapshot_test_hash = "sha256:" + hashlib.sha256((snapshot / project.test).read_bytes()).hexdigest()
        result = ProcessResult(result.argv, result.returncode, result.stdout, result.stderr,
                               result.duration_seconds, result.timed_out, result.output_truncated,
                               {"testbench": snapshot_test_hash})
    if result.returncode == 0:
        if result.output_truncated:
            raise ValueError("pcb test JSON output was truncated")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("pcb test returned malformed JSON") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list) or not isinstance(payload.get("summary"), dict):
            raise ValueError("pcb test JSON lacks results/summary contract")
        expected = [item["test"] for item in project.acceptance["checks"]
                    if item["kind"] == "zener_test" and item["expected"] == "PASS"]
        if any(item["expected"] == "FAIL" for item in project.acceptance["checks"]):
            raise ValueError("negative fixture unexpectedly passed its locked acceptance")
        def records(value: object):
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from records(child)
            elif isinstance(value, list):
                for child in value:
                    yield from records(child)
        all_records = tuple(records(payload["results"]))
        for name in expected:
            matches = [record for record in all_records if name in {
                record.get("name"), record.get("test"),
                f"{record.get('test_bench_name')}.{record.get('check_name')}",
            }]
            if not matches or not all(str(record.get("status", "")).upper() in {"PASS", "PASSED", "OK"}
                                      for record in matches):
                raise ValueError(f"pcb test JSON lacks passing acceptance result: {name}")
        summary = payload["summary"]
        if (any(not isinstance(summary.get(key), int) for key in ("total", "passed", "failed"))
                or summary["total"] != len(payload["results"])
                or summary["passed"] + summary["failed"] != summary["total"]):
            raise ValueError("pcb test JSON summary is inconsistent")
        if any(isinstance(summary.get(key), int) and summary[key] > 0 for key in ("failed", "failures", "errors")):
            raise ValueError("pcb test JSON reports failures despite zero exit")
    return result


def _relative_evidence_path(path: Path, project_root: Path) -> str:
    resolved_path = path.resolve(strict=True)
    resolved_root = project_root.resolve(strict=True)
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise GeneratedCompatibilityError(
            "generated evidence escapes project root"
        ) from error
    return relative.as_posix()

def execute_generated_test(
    project: ProjectState,
    generated_source: str,
    evidence_root: Path,
    check_id: str,
    bench_name: str,
    case_name: str,
) -> GeneratedTestResult:
    if check_id not in GENERATED_TESTS:
        raise ConfigurationError(f"unknown generated check_id: {check_id}")
    if not isinstance(generated_source, str) or not generated_source:
        raise ConfigurationError("generated_source must be non-empty string")
    rel_path, evidence_name = GENERATED_TESTS[check_id]

    command = ["pcb", "test", rel_path, "-f", "json"]
    capability = probe(project, command[0], command[1])
    if capability.timed_out or capability.returncode != 0:
        raise GeneratedCompatibilityError(f"{command[0]} capability probe failed")

    with tempfile.TemporaryDirectory(prefix=f"pcb-agent-{check_id.lower()}-") as temporary:
        snapshot = Path(temporary)
        closure = [
            path.relative_to(project.root).as_posix()
            for path in (project.root / "src").rglob("*")
            if path.is_file()
        ]
        closure.extend(("pcb.toml", "pcb-version"))
        for relative in dict.fromkeys(closure):
            source = project.root / relative
            if source.exists():
                target = snapshot / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        test_rel = rel_path.replace("\\", "/")
        test_path = snapshot / test_rel
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(generated_source, encoding="utf-8")

        result = run_process(snapshot, command, timeout=300)

        evidence_root.mkdir(parents=True, exist_ok=True)
        evidence_source = evidence_root / evidence_name
        evidence_source.write_text(generated_source, encoding="utf-8")
        retained_hash = hashlib.sha256(evidence_source.read_bytes()).hexdigest()
        if retained_hash != hashlib.sha256(generated_source.encode("utf-8")).hexdigest():
            raise GeneratedCompatibilityError("retained generated source hash mismatch")

        raw_path = evidence_root / f"{check_id.lower()}-result.json"
        raw_path.write_text(result.stdout, encoding="utf-8")
        raw_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()

        input_hashes = {
            "testbench": f"sha256:{retained_hash}",
            "result": f"sha256:{raw_hash}",
        }

        process = ProcessResult(
            result.argv,
            result.returncode,
            result.stdout,
            result.stderr,
            result.duration_seconds,
            result.timed_out,
            result.output_truncated,
            input_hashes,
        )

    return GeneratedTestResult(
        process=process,
        generated_path=_relative_evidence_path(evidence_source, project.root),
        generated_sha256=f"sha256:{retained_hash}",
        result_path=_relative_evidence_path(raw_path, project.root),
        result_sha256=f"sha256:{raw_hash}",
    )


def _classify_generated_check(check_id: str, outcome: GeneratedTestResult, bench_name: str, check_name: str) -> CheckStatus:
    proc = outcome.process
    if proc.timed_out:
        return CheckStatus.BLOCKED
    lower = proc.stderr.lower()
    if any(fragment in lower for fragment in _GENERATED_TEST_ENVIRONMENT_FRAGMENTS):
        return CheckStatus.BLOCKED

    if proc.output_truncated:
        return CheckStatus.BLOCKED
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return CheckStatus.BLOCKED
    try:
        _validate_test_payload(payload)
    except GeneratedEvidenceError:
        return CheckStatus.BLOCKED

    if not _summary_matches_records(payload):
        return CheckStatus.BLOCKED

    record = _find_record(payload, bench_name, check_name)
    if record is None:
        return CheckStatus.BLOCKED

    status_text = str(record.get('status', '')).upper()

    summary = payload.get('summary', {})
    failed_count = _int_or_none(summary.get('failed')) or 0
    failures_count = _int_or_none(summary.get('failures')) or 0
    errors_count = _int_or_none(summary.get('errors')) or 0

    if proc.returncode == 0:
        if status_text in _PASS_STATUSES and failed_count == 0 and failures_count == 0 and errors_count == 0:
            return CheckStatus.PASS
        if status_text in _FAIL_STATUSES and errors_count == 0:
            return CheckStatus.FAIL
        return CheckStatus.BLOCKED
    else:
        if status_text in _FAIL_STATUSES and failed_count > 0 and errors_count == 0:
            return CheckStatus.FAIL
        return CheckStatus.BLOCKED
    lower = proc.stderr.lower()
    if any(fragment in lower for fragment in _GENERATED_TEST_ENVIRONMENT_FRAGMENTS):
        return CheckStatus.BLOCKED
    if proc.returncode != 0:
        if proc.output_truncated:
            return CheckStatus.BLOCKED
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return CheckStatus.BLOCKED
        try:
            _validate_test_payload(payload)
        except GeneratedEvidenceError as error:
            return CheckStatus.BLOCKED
        record = _find_record(payload, bench_name, check_name)
        if record is None:
            return CheckStatus.BLOCKED
        status_text = str(record.get("status", "")).upper()
        if status_text in {"PASS", "PASSED", "OK"}:
            return CheckStatus.BLOCKED
        if status_text in {"FAIL", "FAILED", "ERROR"}:
            return CheckStatus.FAIL
        return CheckStatus.BLOCKED
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return CheckStatus.BLOCKED
    try:
        _validate_test_payload(payload)
    except GeneratedEvidenceError:
        return CheckStatus.BLOCKED
    if _payload_has_failure(payload):
        return CheckStatus.BLOCKED
    record = _find_record(payload, bench_name, check_name)
    if record is None:
        return CheckStatus.BLOCKED
    status_text = str(record.get("status", "")).upper()
    if status_text in {"PASS", "PASSED", "OK"}:
        return CheckStatus.PASS
    return CheckStatus.BLOCKED


def _verify_retained_artifact(project_root: Path, relative_path: str, expected_sha256: str) -> None:
    from .paths import resolve_workspace_path, require_regular_file
    try:
        path = resolve_workspace_path(project_root, relative_path, must_exist=True)
        require_regular_file(path)
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise GeneratedCompatibilityError(f"evidence hash mismatch for {relative_path}")
    except Exception as error:
        raise GeneratedCompatibilityError(f"evidence validation failed: {error}") from error


def generated_check(
    check_id: str,
    outcome: GeneratedTestResult,
    bench_name: str,
    check_name: str,
    project_root: Path,
    required: bool = True,
) -> Check:
    try:
        _verify_retained_artifact(project_root, outcome.generated_path, outcome.generated_sha256)
        _verify_retained_artifact(project_root, outcome.result_path, outcome.result_sha256)
    except GeneratedCompatibilityError as error:
        status = CheckStatus.BLOCKED
        message = str(error)
    else:
        status = _classify_generated_check(check_id, outcome, bench_name, check_name)
        if status == CheckStatus.PASS:
            message = f"{check_id.lower()} generated assertion passed"
        elif status == CheckStatus.FAIL:
            message = f"{check_id.lower()} generated assertion failed"
        elif status == CheckStatus.BLOCKED:
            if outcome.process.timed_out:
                message = "generated test timed out"
            else:
                message = "generated test evidence is missing or malformed"
        else:
            message = f"generated test status {status}"

    evidence = {
        "generated_testbench": {
            "path": outcome.generated_path,
            "sha256": outcome.generated_sha256,
        },
        "result": {
            "path": outcome.result_path,
            "sha256": outcome.result_sha256,
        },
        "stdout": outcome.process.stdout,
        "stderr": outcome.process.stderr,
    }
    return Check(
        check_id,
        status,
        Severity.ERROR,
        message,
        "harness",
        outcome.process.argv,
        outcome.process.returncode,
        outcome.process.duration_seconds,
        evidence,
        required,
    )


def result_check(check_id: str, result: ProcessResult, *, required: bool = True) -> Check:
    environment_error = any(text in result.stderr.lower() for text in (
        "a required privilege is not held by the client",
    ))
    status = (CheckStatus.BLOCKED if result.timed_out or environment_error else
              (CheckStatus.PASS if result.returncode == 0 else CheckStatus.FAIL))
    message = ("command timed out" if result.timed_out else
               "command blocked by environment" if environment_error else
               f"command exited {result.returncode}")
    return Check(
        check_id,
        status,
        Severity.ERROR,
        message,
        "tool", result.argv, result.returncode, result.duration_seconds,
        {"stdout": result.stdout, "stderr": result.stderr},
        required,
    )
