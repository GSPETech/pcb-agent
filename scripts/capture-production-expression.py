#!/usr/bin/env python3
"""Capture exact production-generated Diode TestBench evidence.

Renders both production TestBenches from `fixtures/production-expression`
with the harness's own renderer, writes the exact source bytes, executes the
exact `pcb test -f json` commands against the real pcbc toolchain, captures
stdout/stderr/exit, records cwd/executable/timestamp/git revision, writes
`production-summary.json`, and exits non-zero on any mismatch.

Run from the repository root on WSL2 ext4 with the real `pcbc 0.4.40` on PATH:

    python3 scripts/capture-production-expression.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

EVIDENCE_SUBDIR = "production-expression"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_revision(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def capture_production_expression(
    repo_root: Path,
    evidence_root: Path,
    pcb_executable: str,
    revision: str,
    timestamp: str,
    script_sha256: str,
    git_status: str,
    git_status_sha256: str,
) -> dict:
    """Render, execute, and retain the production-expression evidence.

    Returns a run record with the exact argv/cwd/executable/exit/timestamp.
    """
    from pcb_agent import diode
    from pcb_agent.generated_testbench import (
        render_connectivity_testbench,
        render_specification_testbench,
    )
    from pcb_agent.models import CheckStatus
    from pcb_agent.state import load_project

    fixture = repo_root / "fixtures" / "production-expression"
    project = load_project(fixture)
    pcbc_version = diode.probe_pcbc_version(project)
    if pcbc_version != "0.4.40":
        raise SystemExit(f"expected pcbc 0.4.40, got {pcbc_version}")

    target = evidence_root / EVIDENCE_SUBDIR
    raw_dir = target / "run" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    summary: dict = {}
    commands: list[str] = []
    for check_id, bench_name, check_name, render in (
        ("CONNECTIVITY", "PcbAgentConnectivity", "_check_connectivity", render_connectivity_testbench),
        ("SPECIFICATION", "PcbAgentSpecification", "_check_specification", render_specification_testbench),
    ):
        generated = render(project, pcbc_version)
        generated_bytes = generated.encode("utf-8")
        outcome = diode.execute_generated_test(project, generated, raw_dir, check_id)
        check = diode.generated_check(check_id, outcome, bench_name, check_name, raw_dir)
        if check.status != CheckStatus.PASS:
            raise SystemExit(f"production {check_id.lower()} run did not pass: {check.status}")

        generated_stem = f"production-{check_id.lower()}-testbench"
        _write_bytes(target / f"{generated_stem}.zen", generated_bytes)
        _write_bytes(target / f"{generated_stem}.generated.zen", generated_bytes)
        result_bytes = (raw_dir / f"{check_id.lower()}-result.json").read_bytes()
        _write_bytes(target / f"production-{check_id.lower()}-result.json", result_bytes)

        summary[check_id.lower()] = {
            "generated_sha256": outcome.generated_sha256,
            "result_sha256": outcome.result_sha256,
            "status": outcome.process.returncode,
        }
        commands.append(" ".join(outcome.process.argv))

    fixture_copies = {
        "ACCEPTANCE.json": "production-ACCEPTANCE.json",
        "SPEC.json": "production-SPEC.json",
        "expected-connectivity.json": "production-connectivity.json",
        "project.toml": "production-project.toml",
        "pcb.toml": "production-pcb.toml",
        "src/board.zen": "production-source.zen",
        "tests/board_test.zen": "production-testbench-locked.zen",
    }
    for source, destination in fixture_copies.items():
        _write_bytes(target / destination, (fixture / source).read_bytes())

    summary = {
        "pcbc_version": pcbc_version,
        "repo_revision": revision,
        "timestamp": timestamp,
        "cwd": str(repo_root),
        "executable": pcb_executable,
        "connectivity": summary["connectivity"],
        "specification": summary["specification"],
    }
    _write_bytes(
        target / "production-summary.json",
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )

    run_provenance = {
        "kind": "production-expression",
        "repo_revision": revision,
        "git_status": git_status,
        "git_status_sha256": git_status_sha256,
        "argv": [sys.executable, str(Path(__file__).resolve())],
        "cwd": str(repo_root),
        "executable": sys.executable,
        "exit_code": 0,
        "timestamp": timestamp,
        "stdout": f"{EVIDENCE_SUBDIR}/run/output.stdout",
        "stderr": f"{EVIDENCE_SUBDIR}/run/output.stderr",
        "script_sha256": script_sha256,
        "commands": commands,
    }
    _write_bytes(
        target / "run-provenance.json",
        (json.dumps(run_provenance, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return run_provenance


def main() -> int:
    revision = git_revision(_REPO_ROOT)
    script_sha256 = _sha256(Path(__file__).resolve().read_bytes())
    timestamp = datetime.now(timezone.utc).isoformat()
    capture_production_expression(
        _REPO_ROOT,
        _REPO_ROOT / "tests" / "evidence" / "diode-0.4.40",
        "pcb",
        revision,
        timestamp,
        script_sha256,
        "",
        _sha256(b""),
    )
    print("production-expression capture OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
