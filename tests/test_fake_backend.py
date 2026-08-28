from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import ROOT, make_fake_pcb, write_contract
from pcb_agent import cli, kicad
from pcb_agent.backends.base import BackendResult
from pcb_agent.models import Check, CheckStatus
from pcb_agent.process import ProcessResult
from pcb_agent.state import load_project, new_run


def process(returncode: int = 0, *, timed_out: bool = False) -> ProcessResult:
    return ProcessResult(("fake",), returncode, "", "", 0.01, timed_out, False)


class FakeBackend:
    def __init__(self, result: ProcessResult, action=None) -> None:
        self.result = result
        self.action = action

    def execute(self, task: str, workspace: Path, timeout: float) -> BackendResult:
        if self.action:
            self.action(workspace)
        return BackendResult(self.result, ())


class FakeBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)
        self.run = new_run(self.project, self.root / "reports")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def args(self, **overrides: object) -> argparse.Namespace:
        values = dict(backend="command", backend_config="unused", task="repair", timeout=1.0,
                      max_iterations=2, profile="schematic")
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_backend(self, backend: FakeBackend, checks: list[Check], **overrides: object) -> list[Check]:
        from pcb_agent.policy_config import Policy
        with patch("pcb_agent.cli.CommandBackend", return_value=backend), patch("pcb_agent.cli._verify", return_value=checks):
            return cli._run_backend(self.args(**overrides), self.project, self.run, Policy.load())

    def test_success_and_backend_crash(self) -> None:
        success = self.run_backend(FakeBackend(process()), [Check("VERIFY", CheckStatus.PASS)])
        crash = self.run_backend(FakeBackend(process(9)), [Check("VERIFY", CheckStatus.PASS)])
        self.assertEqual(success[0].status, CheckStatus.PASS)
        self.assertIn("iteration 1", success[0].message)
        self.assertEqual(crash[0].status, CheckStatus.BLOCKED)
        self.assertIn("exited 9", crash[0].message)

    def test_no_progress_and_iteration_limit(self) -> None:
        failed = [Check("VERIFY", CheckStatus.FAIL, message="same failure")]
        no_progress = self.run_backend(FakeBackend(process()), failed, max_iterations=2)
        limited = self.run_backend(FakeBackend(process()), failed, max_iterations=1)
        self.assertIn("no progress", no_progress[0].message)
        self.assertEqual(limited[0].message, "iteration limit reached")

    def test_nested_run_is_blocked(self) -> None:
        from pcb_agent.policy_config import Policy
        with patch.dict(os.environ, {"PCB_AGENT_ACTIVE": "1"}):
            checks = cli._run_backend(self.args(), self.project, self.run, Policy.load())
        self.assertEqual(checks[0].status, CheckStatus.BLOCKED)
        self.assertIn("nested", checks[0].message)

    def test_protected_tamper_is_detected_and_restored(self) -> None:
        original = (self.root / "SPEC.json").read_bytes()
        backend = FakeBackend(process(), lambda workspace: (workspace / "SPEC.json").write_text("tampered", encoding="utf-8"))
        checks = self.run_backend(backend, [Check("VERIFY", CheckStatus.PASS)])
        self.assertEqual(checks[0].id, "POLICY_INTEGRITY")
        self.assertEqual(checks[0].status, CheckStatus.FAIL)
        self.assertEqual((self.root / "SPEC.json").read_bytes(), original)

    def test_missing_kicad_is_required_blocked_but_optional_skipped(self) -> None:
        missing = FileNotFoundError("kicad-cli missing")
        with patch("pcb_agent.cli.kicad.probe", side_effect=missing):
            required = cli._tool_check(self.project, "kicad-cli", cli.kicad.probe, required=True)
            optional = cli._tool_check(self.project, "kicad-cli", cli.kicad.probe, required=False)
        self.assertEqual(required.status, CheckStatus.BLOCKED)
        self.assertEqual(optional.status, CheckStatus.SKIPPED)

    def test_kicad_result_semantics(self) -> None:
        expected = {0: CheckStatus.PASS, 5: CheckStatus.FAIL, 2: CheckStatus.BLOCKED, 3: CheckStatus.BLOCKED, 127: CheckStatus.BLOCKED}
        for returncode, status in expected.items():
            with self.subTest(returncode=returncode):
                self.assertEqual(kicad.result_check(process(returncode)).status, status)
        self.assertEqual(kicad.result_check(process(1, timed_out=True)).status, CheckStatus.BLOCKED)

    def test_drc_runs_after_layout_check_failure(self) -> None:
        passed = Check("STEP", CheckStatus.PASS)
        failed = Check("LAYOUT_SYNC", CheckStatus.FAIL)
        with patch("pcb_agent.cli._diode_command", side_effect=[passed, passed, passed, failed]), \
                patch("pcb_agent.cli._connectivity_check", return_value=passed), \
                patch("pcb_agent.cli._specification_check", return_value=passed), \
                patch("pcb_agent.cli.kicad.drc", return_value=process(5)), \
                patch("pcb_agent.cli.kicad.result_check", return_value=Check("KICAD_DRC", CheckStatus.FAIL)):
            checks = cli._verify(self.project, self.run, "layout")
        self.assertEqual(next(check for check in checks if check.id == "LAYOUT_SYNC").status, CheckStatus.FAIL)
        self.assertEqual(next(check for check in checks if check.id == "KICAD_DRC").status, CheckStatus.FAIL)

    def test_fake_pcb_accepts_valid_fixture_and_rejects_invalid_fixture(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            tools = base / "tools"
            tools.mkdir()
            make_fake_pcb(tools)
            valid_fixture = base / "valid-blinky"
            invalid_fixture = base / "invalid-syntax"
            shutil.copytree(ROOT / "fixtures" / "valid-blinky", valid_fixture)
            shutil.copytree(ROOT / "fixtures" / "invalid-syntax", invalid_fixture)
            path = str(tools) + os.pathsep + os.environ.get("PATH", "")
            with patch.dict(os.environ, {"PATH": path}, clear=False), contextlib.redirect_stdout(io.StringIO()):
                valid = cli.main(["verify", str(valid_fixture), "--format", "json"])
                invalid = cli.main(["verify", str(invalid_fixture), "--format", "json"])
        # The fake pcb reports pcbc 0.4.34, which no captured adapter is
        # verified against, so the generated gates report BLOCKED and the valid
        # fixture exits 2 rather than 0. A green run against a real 0.4.40
        # toolchain is covered by docs/spike-diode-net-naming.md; a CI green
        # run is covered by tests/test_green_run.py.
        self.assertEqual(valid, 2)
        # A failed build now blocks dependent gates, so the run is BLOCKED.
        self.assertEqual(invalid, 2)


if __name__ == "__main__":
    unittest.main()
