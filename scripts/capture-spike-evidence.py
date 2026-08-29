#!/usr/bin/env python3
"""Re-capture the Diode net-naming spike evidence bundle from a clean tree.

Runs the real pcbc 0.4.40 toolchain and the harness's own renderers, writes
every retained artifact under `tests/evidence/diode-0.4.40/`, records exact
per-run provenance (argv, cwd, executable, exit code, timestamp, git revision,
clean git status), regenerates sanitized companions, rebuilds
`manifest.sha256`, and exits non-zero on any mismatch.

The executed tree MUST be clean: the script aborts unless
`git status --short` and `git diff --binary` are both empty, and it records
that clean state per run.

Run from the repository root on WSL2 ext4 with the real `pcbc 0.4.40` on PATH:

    python3 scripts/capture-spike-evidence.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from pcb_agent.source_cleanliness import measure_source_cleanliness

_EVIDENCE_ROOT = _REPO_ROOT / "tests" / "evidence" / "diode-0.4.40"
_PCBC_VERSION = "0.4.40"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

_HOST_PREFIXES = (
    ("/home/rendra/pcbagent-full", "<sanitized>"),
    ("/home/rendra/.local/bin", "<sanitized>"),
)
_TMP_PATTERN = re.compile(r"/tmp/pcb-agent-(connectivity|specification)-([A-Za-z0-9]+)")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True, timeout=120,
    )


def _run(argv: list[str], cwd: Path, env: dict[str, str], timeout: int = 900) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _sanitize_string(text: str) -> str:
    for prefix, replacement in _HOST_PREFIXES:
        text = text.replace(prefix, replacement)
    return _TMP_PATTERN.sub(lambda match: f"<sanitized>-{match.group(2)}", text)


def _sanitize_value(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def sanitize_json(raw_bytes: bytes) -> bytes:
    payload = json.loads(raw_bytes.decode("utf-8"))
    return (json.dumps(_sanitize_value(payload), indent=2, sort_keys=True) + "\n").encode("utf-8")


def _assert_result_json(raw_bytes: bytes, bench_name: str, case_name: str, expected_passed: int) -> None:
    payload = json.loads(raw_bytes.decode("utf-8"))
    summary = payload.get("summary") or {}
    if summary.get("passed") != expected_passed:
        raise SystemExit(
            f"expected {expected_passed} passed, got summary {summary}"
        )
    records = payload.get("results") or []
    if len(records) != expected_passed:
        raise SystemExit(f"expected {expected_passed} records, got {len(records)}")
    for record in records:
        if record.get("test_bench_name") != bench_name:
            raise SystemExit(f"unexpected bench {record.get('test_bench_name')!r}")
        if record.get("case_name") != case_name:
            raise SystemExit(f"unexpected case {record.get('case_name')!r}")
        if str(record.get("status", "")).lower() != "pass":
            raise SystemExit(f"record not passing: {record}")


def _capture_environment(repo_root: Path, revision: str) -> str:
    uname = subprocess.run(
        ["uname", "-s", "-n", "-r", "-v", "-m", "-p", "-o"],
        capture_output=True, text=True, timeout=30,
    ).stdout.rstrip("\n")
    os_release = Path("/etc/os-release").read_text(encoding="utf-8").rstrip("\n")
    findmnt = subprocess.run(
        ["findmnt", "-T", "."], cwd=str(repo_root),
        capture_output=True, text=True, timeout=30,
    ).stdout.rstrip("\n")
    which = subprocess.run(
        ["bash", "-lc", "command -v pcb"],
        capture_output=True, text=True, timeout=30,
    ).stdout.rstrip("\n")
    return (
        f"pwd={repo_root}\n"
        f"git_commit={revision}\n"
        f"{uname}\n"
        f"{os_release}\n"
        f"=== findmnt -T . ===\n"
        f"{findmnt}\n"
        f"=== command -v pcb ===\n"
        f"{which}\n"
    )


def _run_record(
    kind: str, run_dir: str, argv: list[str], cwd: str, executable: str,
    exit_code: int, timestamp: str, revision: str, git_status: str,
    stdout_rel: str, stderr_rel: str, stdout_sha256: str, stderr_sha256: str,
    script_sha256: str, cleanliness: dict,
) -> dict:
    return {
        "kind": kind,
        "dir": run_dir,
        "argv": argv,
        "cwd": cwd,
        "executable": executable,
        "exit_code": exit_code,
        "timestamp": timestamp,
        "repo_revision": revision,
        "git_status": git_status,
        "git_status_sha256": _sha256(git_status.encode("utf-8")),
        "stdout": stdout_rel,
        "stderr": stderr_rel,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "script_sha256": script_sha256,
        "cleanliness": cleanliness,
    }


def _write_run_provenance(evidence_root: Path, run_dir: str, record: dict) -> None:
    _write_text(
        evidence_root / run_dir / "run-provenance.json",
        json.dumps(record, indent=2, sort_keys=True) + "\n",
    )


def _capture_pcb_test(
    evidence_root: Path,
    fixture: Path,
    run_dir: str,
    prefix: str,
    testfile: str,
    bench_name: str,
    case_name: str,
    expected_passed: int,
    fixture_copies: dict[str, str],
    pcb: str,
    timestamp: str,
    script_sha256: str,
    env: dict[str, str],
    kind: str,
) -> dict:
    cleanliness = measure_source_cleanliness(_REPO_ROOT, _EVIDENCE_ROOT)
    if not cleanliness["source_clean"]:
        raise SystemExit(
            f"{kind}: source not clean before capture: "
            f"{cleanliness['filtered_source_status']}"
        )
    revision = cleanliness["repo_revision"]
    git_status = bytes.fromhex(cleanliness["raw_status"]).decode("utf-8", "replace")
    argv = [pcb, "test", testfile, "-f", "json"]
    exit_code, stdout, stderr = _run(argv, cwd=fixture, env=env)
    target = evidence_root / run_dir
    _write_bytes(target / f"{prefix}.json", stdout)
    _write_bytes(target / f"{prefix}.stderr", stderr)
    _write_bytes(target / f"{prefix}.exit", str(exit_code).encode("utf-8") + b"\n")
    _write_bytes(target / f"{prefix}.sanitized.json", sanitize_json(stdout))
    _assert_result_json(stdout, bench_name, case_name, expected_passed)
    for source, destination in fixture_copies.items():
        _write_bytes(target / destination, (fixture / source).read_bytes())
    record = _run_record(
        kind, run_dir, argv, str(fixture), pcb, exit_code, timestamp,
        revision, git_status, f"{run_dir}/{prefix}.json", f"{run_dir}/{prefix}.stderr",
        _sha256(stdout), _sha256(stderr), script_sha256, cleanliness,
    )
    _write_run_provenance(evidence_root, run_dir, record)
    return record


def _capture_verify(
    evidence_root: Path,
    repo_root: Path,
    run_dir: str,
    prefix: str,
    fixture_rel: str,
    expected_status: str,
    expected_gates: dict[str, str],
    fixture_copies: dict[str, str],
    python_exe: str,
    revision: str,
    timestamp: str,
    git_status: str,
    script_sha256: str,
    env: dict[str, str],
    kind: str,
    *,
    sanitize_run_raw: bool,
) -> dict:
    cleanliness = measure_source_cleanliness(_REPO_ROOT, _EVIDENCE_ROOT)
    if not cleanliness["source_clean"]:
        raise SystemExit(
            f"{kind}: source not clean before capture: "
            f"{cleanliness['filtered_source_status']}"
        )
    argv = [python_exe, "-m", "pcb_agent.cli", "verify", fixture_rel, "--format", "json"]
    exit_code, stdout, stderr = _run(argv, cwd=repo_root, env=env)
    target = evidence_root / run_dir
    _write_bytes(target / f"{prefix}-report.json", stdout)
    _write_bytes(target / f"{prefix}-report.stderr", stderr)
    _write_bytes(target / f"{prefix}-report.exit", str(exit_code).encode("utf-8") + b"\n")

    report = json.loads(stdout.decode("utf-8"))
    if report.get("status") != expected_status:
        raise SystemExit(
            f"{kind}: expected status {expected_status}, got {report.get('status')}"
        )
    for gate, status in expected_gates.items():
        found = next((c for c in report.get("checks", []) if c.get("id") == gate), None)
        if found is None or found.get("status") != status:
            raise SystemExit(f"{kind}: gate {gate} expected {status}, got {found}")

    reports_root = repo_root / fixture_rel / "reports"
    run_dirs = sorted(
        (path for path in reports_root.glob("*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
    )
    if not run_dirs:
        raise SystemExit(f"{kind}: no run directory produced under {reports_root}")
    newest = run_dirs[-1]
    shutil.copytree(newest, target / "run", dirs_exist_ok=True)
    _write_text(
        target / "run-directory.txt",
        f"run-dir={fixture_rel}/reports/{newest.name}/\n",
    )

    for source, destination in fixture_copies.items():
        _write_bytes(target / destination, (repo_root / fixture_rel / source).read_bytes())

    _write_text(target / "version.txt", f"pcbc {_PCBC_VERSION}\n")
    _write_text(target / "repo-revision.txt", f"{revision}\n")
    _write_text(target / "environment.txt", _capture_environment(repo_root, revision))

    if sanitize_run_raw:
        _write_bytes(
            target / f"{prefix}-report.sanitized.json",
            sanitize_json(stdout),
        )
        for name in ("connectivity-result", "specification-result"):
            raw = target / "run" / "raw" / f"{name}.json"
            if raw.exists():
                _write_bytes(raw.with_name(f"{name}.sanitized.json"), sanitize_json(raw.read_bytes()))

    shutil.rmtree(reports_root, ignore_errors=True)

    stdout_rel = f"{run_dir}/{prefix}-report.json"
    stderr_rel = f"{run_dir}/{prefix}-report.stderr"
    record = _run_record(
        kind, run_dir, argv, str(repo_root), python_exe, exit_code, timestamp,
        revision, git_status, stdout_rel, stderr_rel, _sha256(stdout), _sha256(stderr),
        script_sha256, cleanliness,
    )
    _write_run_provenance(evidence_root, run_dir, record)
    return record


def _rebuild_manifest(evidence_root: Path) -> None:
    """Rebuild manifest.sha256 and verify it; fail closed on any mismatch."""
    result = subprocess.run(
        "find . -type f ! -name manifest.sha256 ! -name manifest-attestation.json "
        "! -name windows-manifest.txt ! -name wsl-manifest.txt "
        "-print0 | sort -z | xargs -0 sha256sum > manifest.sha256",
        cwd=str(evidence_root), shell=True, timeout=120,
    )
    if result.returncode != 0:
        raise SystemExit("manifest rebuild failed")
    check_result = subprocess.run(
        ["sha256sum", "-c", "manifest.sha256"],
        cwd=str(evidence_root), capture_output=True, text=True, timeout=300,
    )
    if check_result.returncode != 0:
        raise SystemExit("manifest verification failed:\n" + check_result.stdout)


def main() -> int:
    revision_result = _git(_REPO_ROOT, "rev-parse", "HEAD")
    if revision_result.returncode != 0:
        raise SystemExit("git rev-parse HEAD failed; run inside the repository")
    revision = revision_result.stdout.strip()

    cleanliness = measure_source_cleanliness(_REPO_ROOT, _EVIDENCE_ROOT)
    if not cleanliness["source_clean"]:
        raise SystemExit(
            "refusing to capture from a dirty source tree; changes outside the "
            "evidence root:\n" + bytes.fromhex(cleanliness["filtered_source_status"]).decode("utf-8", "replace")
        )
    git_status = bytes.fromhex(cleanliness["raw_status"]).decode("utf-8", "replace")

    env = os.environ.copy()
    home_local = Path.home() / ".local" / "bin"
    if str(home_local) not in env.get("PATH", ""):
        env["PATH"] = str(home_local) + os.pathsep + env.get("PATH", "")
    python_dir = str(Path(sys.executable).resolve().parent)
    if python_dir not in env.get("PATH", ""):
        env["PATH"] = python_dir + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(_REPO_ROOT / "src")

    version_result = subprocess.run(
        ["pcb", "--version"], capture_output=True, text=True, timeout=60,
    )
    if version_result.returncode != 0 or f"pcbc {_PCBC_VERSION}" not in version_result.stdout:
        raise SystemExit(
            f"expected pcbc {_PCBC_VERSION} on PATH, got rc={version_result.returncode} "
            f"stdout={version_result.stdout!r}"
        )
    findmnt = subprocess.run(
        ["findmnt", "-T", str(_REPO_ROOT)], capture_output=True, text=True, timeout=30,
    )
    if "ext4" not in findmnt.stdout:
        raise SystemExit("evidence must be captured on an ext4 filesystem (WSL2)")

    pcb = shutil.which("pcb")
    if not pcb:
        raise SystemExit("pcb not found on PATH")
    python_exe = sys.executable
    script_path = Path(__file__).resolve()
    script_sha256 = _sha256(script_path.read_bytes())
    prod_script_sha256 = _sha256((_REPO_ROOT / "scripts" / "capture-production-expression.py").read_bytes())
    timestamp = datetime.now(timezone.utc).isoformat()

    shutil.rmtree(_EVIDENCE_ROOT, ignore_errors=True)
    _EVIDENCE_ROOT.mkdir(parents=True)

    _write_text(_EVIDENCE_ROOT / "pcb-version.txt", version_result.stdout.rstrip("\n") + "\n")
    _write_text(_EVIDENCE_ROOT / "repo-revision.txt", f"{revision}\n")
    _write_text(_EVIDENCE_ROOT / "environment.txt", _capture_environment(_REPO_ROOT, revision))

    records: list[dict] = []

    records.append(_capture_pcb_test(
        _EVIDENCE_ROOT, _REPO_ROOT / "fixtures/valid-blinky", "valid-blinky", "valid-blinky",
        "tests/blinky_test.zen", "BlinkyTest", "default", 2,
        {
            "tests/blinky_test.zen": "valid-blinky-testbench.zen",
            "src/blinky.zen": "valid-blinky-source.zen",
            "ACCEPTANCE.json": "valid-blinky-ACCEPTANCE.json",
            "SPEC.json": "valid-blinky-SPEC.json",
            "expected-connectivity.json": "valid-blinky-connectivity.json",
            "project.toml": "valid-blinky-project.toml",
            "pcb.toml": "valid-blinky-pcb.toml",
        },
        pcb, timestamp, script_sha256, env, "valid-blinky-locked-testbench",
    ))
    _rebuild_manifest(_EVIDENCE_ROOT)

    records.append(_capture_pcb_test(
        _EVIDENCE_ROOT, _REPO_ROOT / "fixtures/spike-generics", "spike-generics", "spike-generics",
        "tests/spike_evidence.zen", "SpikeAllGenerics", "default", 1,
        {
            "tests/spike_evidence.zen": "spike-generics-testbench.zen",
            "src/all_generics.zen": "spike-generics-module.zen",
            "src/generics.zen": "spike-generics-extra-source.zen",
            "pcb.toml": "spike-generics-pcb.toml",
        },
        pcb, timestamp, script_sha256, env, "spike-generics-evidence-testbench",
    ))
    _rebuild_manifest(_EVIDENCE_ROOT)

    records.append(_capture_pcb_test(
        _EVIDENCE_ROOT, _REPO_ROOT / "fixtures/spike-generics", "prefix", "prefix-renamed-alt-case",
        "tests/prefix_evidence.zen", "RenamedBench", "alt_case", 1,
        {
            "tests/prefix_evidence.zen": "prefix-evidence.zen",
            "src/all_generics.zen": "prefix-module.zen",
            "pcb.toml": "prefix-pcb.toml",
        },
        pcb, revision, timestamp, git_status, script_sha256, env, "prefix-variation",
    ))
    _rebuild_manifest(_EVIDENCE_ROOT)

    records.append(_capture_verify(
        _EVIDENCE_ROOT, _REPO_ROOT, "green-real", "green-real", "fixtures/green-real",
        "PASS", {"CONNECTIVITY": "PASS", "SPECIFICATION": "PASS"},
        {
            "ACCEPTANCE.json": "green-real-ACCEPTANCE.json",
            "SPEC.json": "green-real-SPEC.json",
            "expected-connectivity.json": "green-real-connectivity.json",
            "project.toml": "green-real-project.toml",
            "pcb.toml": "green-real-pcb.toml",
            "src/board.zen": "green-real-source.zen",
            "tests/board_test.zen": "green-real-testbench.zen",
        },
        python_exe, revision, timestamp, git_status, script_sha256, env,
        "green-real-verify", sanitize_run_raw=True,
    ))
    _rebuild_manifest(_EVIDENCE_ROOT)

    for name, status, gates in (
        ("negative-invalid-syntax", "BLOCKED", {"DIODE_BUILD": "FAIL"}),
        ("negative-invalid-connectivity", "BLOCKED", {"ZENER_TEST": "FAIL"}),
        ("negative-invalid-value", "BLOCKED", {"ZENER_TEST": "FAIL"}),
    ):
        records.append(_capture_verify(
            _EVIDENCE_ROOT, _REPO_ROOT, name, "verify", f"fixtures/{name[len('negative-'):]}",
            status, gates,
            {
                "ACCEPTANCE.json": "ACCEPTANCE.json",
                "SPEC.json": "SPEC.json",
                "expected-connectivity.json": "expected-connectivity.json",
                "project.toml": "project.toml",
                "pcb.toml": "pcb.toml",
                "src/blinky.zen": "src/blinky.zen",
                "tests/blinky_test.zen": "tests/blinky_test.zen",
            },
            python_exe, revision, timestamp, git_status, script_sha256, env,
            name, sanitize_run_raw=False,
        ))
        _rebuild_manifest(_EVIDENCE_ROOT)

    prod_argv = [python_exe, str(_REPO_ROOT / "scripts" / "capture-production-expression.py")]
    prod_rc, prod_stdout, prod_stderr = _run(prod_argv, cwd=_REPO_ROOT, env=env)
    prod_output = _EVIDENCE_ROOT / "production-expression" / "run"
    _write_bytes(prod_output / "output.stdout", prod_stdout)
    _write_bytes(prod_output / "output.stderr", prod_stderr)
    if prod_rc != 0:
        raise SystemExit(
            f"production-expression capture failed rc={prod_rc}: {prod_stderr.decode()}"
        )
    prod_provenance_path = _EVIDENCE_ROOT / "production-expression" / "run-provenance.json"
    prod_record = json.loads(prod_provenance_path.read_text(encoding="utf-8"))
    prod_record["dir"] = "production-expression"
    prod_record["stdout"] = "production-expression/run/output.stdout"
    prod_record["stderr"] = "production-expression/run/output.stderr"
    prod_record["exit_code"] = prod_rc
    prod_record["repo_revision"] = revision
    prod_record["git_status"] = git_status
    prod_record["git_status_sha256"] = _sha256(git_status.encode("utf-8"))
    _write_run_provenance(_EVIDENCE_ROOT, "production-expression", prod_record)
    records.append(prod_record)
    _rebuild_manifest(_EVIDENCE_ROOT)

    capture_provenance = {
        "repo_revision": revision,
        "git_status": git_status,
        "git_status_sha256": _sha256(git_status.encode("utf-8")),
        "git_diff_binary": "",
        "git_diff_binary_sha256": _EMPTY_SHA256,
        "captured_at": timestamp,
        "cwd": str(_REPO_ROOT),
        "filesystem": "ext4",
        "pcbc_version": _PCBC_VERSION,
        "executable_pcb": pcb,
        "python_executable": python_exe,
        "script": "scripts/capture-spike-evidence.py",
        "script_sha256": script_sha256,
        "production_script_sha256": prod_script_sha256,
        "evidence_root": "tests/evidence/diode-0.4.40",
    }
    _write_text(
        _EVIDENCE_ROOT / "capture-provenance.json",
        json.dumps(capture_provenance, indent=2, sort_keys=True) + "\n",
    )

    commands = {
        "tool": f"pcbc {_PCBC_VERSION}",
        "environment": "environment.txt",
        "pcb_version": "pcb-version.txt",
        "repo_revision": "repo-revision.txt",
        "capture_provenance": "capture-provenance.json",
        "runs": records,
    }
    _write_text(
        _EVIDENCE_ROOT / "commands.json",
        json.dumps(commands, indent=2, sort_keys=True) + "\n",
    )

    script_target = _EVIDENCE_ROOT / "scripts"
    _write_bytes(script_target / "capture-spike-evidence.py", script_path.read_bytes())
    _write_bytes(
        script_target / "capture-production-expression.py",
        (_REPO_ROOT / "scripts" / "capture-production-expression.py").read_bytes(),
    )

    _rebuild_manifest(_EVIDENCE_ROOT)

    print(f"capture OK at {revision}, {len(records)} runs, manifest verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
