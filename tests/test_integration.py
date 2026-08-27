"""Integration tests that run the fake pcb to exercise verification paths."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import make_fake_pcb, write_contract
from pcb_agent import cli
from pcb_agent.models import CheckStatus
from pcb_agent.process import ProcessResult
from pcb_agent.state import load_project, new_run


def _probe_ok() -> ProcessResult:
    return ProcessResult(("pcb", "--help"), 0, "", "", 0.1, False, False, {})


class RealExecutionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.fake_pcb = make_fake_pcb(self.tools)
        self._original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.tools}{os.pathsep}{self._original_path}"

    def tearDown(self) -> None:
        os.environ["PATH"] = self._original_path
        self.temporary.cleanup()

    def test_generated_checks_block_without_verified_adapter(self) -> None:
        fixture = self.root / "valid-blinky"
        write_contract(fixture)

        project = load_project(fixture)
        run = new_run(project, self.root / "reports")

        with patch("pcb_agent.diode.probe", return_value=_probe_ok()):
            checks = cli._verify(project, run, "schematic")

        statuses = {check.id: check.status for check in checks}
        self.assertEqual(statuses.get("DIODE_BUILD"), CheckStatus.PASS)
        self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.BLOCKED)
        self.assertEqual(statuses.get("SPECIFICATION"), CheckStatus.BLOCKED)

    def test_invalid_syntax_build_fails_and_dependents_inherit(self) -> None:
        fixture = self.root / "invalid-syntax"
        write_contract(fixture, name="invalid-syntax")
        (fixture / "src" / "board.zen").write_text("invalid_syntax", encoding="utf-8")

        project = load_project(fixture)
        run = new_run(project, self.root / "reports")

        with patch("pcb_agent.diode.probe", return_value=_probe_ok()):
            checks = cli._verify(project, run, "schematic")

        statuses = {check.id: check.status for check in checks}
        self.assertEqual(statuses.get("DIODE_BUILD"), CheckStatus.FAIL)
        self.assertEqual(statuses.get("ZENER_TEST"), CheckStatus.FAIL)
        self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.FAIL)
        self.assertEqual(statuses.get("SPECIFICATION"), CheckStatus.FAIL)


if __name__ == "__main__":
    unittest.main()