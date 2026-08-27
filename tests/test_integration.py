"""Integration tests that actually run the fake pcb to exercise verification paths."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import make_fake_pcb, write_contract
from pcb_agent import cli
from pcb_agent.diode import GeneratedCompatibilityError
from pcb_agent.models import CheckStatus
from pcb_agent.state import load_project, new_run


class RealExecutionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.fake_pcb = make_fake_pcb(self.tools)

        # Inject fake tools into path
        os.environ["PATH"] = f"{self.tools}{os.pathsep}{os.environ.get('PATH', '')}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_verify_passes_with_valid_blinky(self) -> None:
        fixture = self.root / "valid-blinky"
        write_contract(fixture)
        
        project = load_project(fixture)
        run = new_run(project, self.root / "reports")
        
        # Patch the adapter registry to know about "test" component
        with patch("pcb_agent.generated_testbench._ADAPTERS", {"test": __import__("pcb_agent.generated_testbench", fromlist=["ComponentAdapter"]).ComponentAdapter("U", {"P1": "1"}, frozenset({"0.4.34"}), "evidence")}):
            with patch("pcb_agent.diode.probe") as mock_probe:
                # Mock capability probe to say "0.4.34" verified
                from pcb_agent.process import ProcessResult
                mock_probe.return_value = ProcessResult(["pcb", "--help"], 0, "", "", 0.1, False, False, {})
                checks = cli._verify(project, run, "schematic")
        
        statuses = {check.id: check.status for check in checks}
        self.assertEqual(statuses.get("DIODE_BUILD"), CheckStatus.PASS)
        self.assertEqual(statuses.get("ZENER_TEST"), CheckStatus.PASS)
        self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.PASS)
        self.assertEqual(statuses.get("SPECIFICATION"), CheckStatus.PASS)

    def test_invalid_syntax_build_fails(self) -> None:
        fixture = self.root / "invalid-syntax"
        write_contract(fixture, name="invalid-syntax")
        (fixture / "src" / "board.zen").write_text("invalid_syntax", encoding="utf-8")
        
        project = load_project(fixture)
        run = new_run(project, self.root / "reports")
        
        with patch("pcb_agent.diode.probe") as mock_probe:
            from pcb_agent.process import ProcessResult
            mock_probe.return_value = ProcessResult(["pcb", "--help"], 0, "", "", 0.1, False, False, {})
            checks = cli._verify(project, run, "schematic")
            
        statuses = {check.id: check.status for check in checks}
        self.assertEqual(statuses.get("DIODE_BUILD"), CheckStatus.FAIL)
        self.assertEqual(statuses.get("ZENER_TEST"), CheckStatus.FAIL)
        self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.FAIL)
        self.assertEqual(statuses.get("SPECIFICATION"), CheckStatus.FAIL)

    def test_missing_evidence_makes_generated_checks_blocked(self) -> None:
        fixture = self.root / "valid-blinky"
        write_contract(fixture)
        
        project = load_project(fixture)
        run = new_run(project, self.root / "reports")
        
        # Don't patch the adapter registry, so "test" component is unknown
        with patch("pcb_agent.diode.probe") as mock_probe:
            from pcb_agent.process import ProcessResult
            mock_probe.return_value = ProcessResult(["pcb", "--help"], 0, "", "", 0.1, False, False, {})
            checks = cli._verify(project, run, "schematic")
            
        statuses = {check.id: check.status for check in checks}
        self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.BLOCKED)
        self.assertEqual(statuses.get("SPECIFICATION"), CheckStatus.BLOCKED)

    def test_malformed_json_from_diode_makes_generated_check_blocked(self) -> None:
        fixture = self.root / "valid-blinky"
        write_contract(fixture)
        
        # Overwrite the fake_pcb to emit broken JSON
        self.fake_pcb.write_text(
            """import sys
print("not json")
raise SystemExit(0)
""", encoding="utf-8")
        
        project = load_project(fixture)
        run = new_run(project, self.root / "reports")
        
        with patch("pcb_agent.generated_testbench._ADAPTERS", {"test": __import__("pcb_agent.generated_testbench", fromlist=["ComponentAdapter"]).ComponentAdapter("U", {"P1": "1"}, frozenset({"0.4.34"}), "evidence")}):
            with patch("pcb_agent.diode.probe") as mock_probe:
                from pcb_agent.process import ProcessResult
                mock_probe.return_value = ProcessResult(["pcb", "--help"], 0, "", "", 0.1, False, False, {})
                checks = cli._verify(project, run, "schematic")
                
        statuses = {check.id: check.status for check in checks}
        self.assertEqual(statuses.get("ZENER_TEST"), CheckStatus.BLOCKED)
        self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.BLOCKED)

if __name__ == "__main__":
    unittest.main()