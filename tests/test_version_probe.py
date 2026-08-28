"""Tests for the strict pcbc version probe."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcb_agent import diode
from pcb_agent.process import ProcessResult
from pcb_agent.state import load_project

from helpers import write_contract


def _version_result(stdout: str, returncode: int = 0, timed_out: bool = False) -> ProcessResult:
    return ProcessResult(
        ("pcb", "--version"),
        returncode,
        stdout,
        "",
        0.1,
        timed_out,
        False,
        {},
    )


class ProbePcbcVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _probe(self, result: ProcessResult) -> str:
        with patch("pcb_agent.diode.run_process", return_value=result):
            return diode.probe_pcbc_version(self.project)

    def test_parses_version_from_output(self) -> None:
        self.assertEqual(self._probe(_version_result("pcbc 0.4.34")), "0.4.34")

    def test_parses_version_with_surrounding_text(self) -> None:
        stdout = "pcb 0.2.6\npcbc 0.4.34 (release)\n"
        self.assertEqual(self._probe(_version_result(stdout)), "0.4.34")

    def test_rejects_unparseable_output(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError) as ctx:
            self._probe(_version_result("some unrelated banner"))
        self.assertIn("cannot parse", str(ctx.exception))

    def test_rejects_partial_version(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError):
            self._probe(_version_result("pcbc 0.4"))

    def test_rejects_nonzero_exit(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError) as ctx:
            self._probe(_version_result("pcbc 0.4.34", returncode=1))
        self.assertIn("exited 1", str(ctx.exception))

    def test_rejects_timeout(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError) as ctx:
            self._probe(_version_result("", timed_out=True))
        self.assertIn("timed out", str(ctx.exception))


class VersionProbeGatesGeneratedChecksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_connectivity_blocked_when_version_probe_fails(self) -> None:
        from pcb_agent import cli
        from pcb_agent.models import Check, CheckStatus, Severity

        passing_test = Check(
            "ZENER_TEST", CheckStatus.PASS, Severity.ERROR, "ok", "tool", (), 0, 0.1, {}, True
        )
        with patch(
            "pcb_agent.diode.probe_pcbc_version",
            side_effect=diode.GeneratedCompatibilityError("cannot parse pcbc version"),
        ):
            check = cli._connectivity_check(self.project, passing_test, None)
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("toolchain version unknown", check.message)

    def test_specification_blocked_when_version_probe_fails(self) -> None:
        from pcb_agent import cli
        from pcb_agent.models import Check, CheckStatus, Severity

        passing_test = Check(
            "ZENER_TEST", CheckStatus.PASS, Severity.ERROR, "ok", "tool", (), 0, 0.1, {}, True
        )
        with patch(
            "pcb_agent.diode.probe_pcbc_version",
            side_effect=diode.GeneratedCompatibilityError("cannot parse pcbc version"),
        ):
            check = cli._specification_check(self.project, passing_test, None)
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("toolchain version unknown", check.message)


if __name__ == "__main__":
    unittest.main()
