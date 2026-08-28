"""Tests that every advertised `check` scope actually runs."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pcb_agent.cli import main

from helpers import write_contract


class CheckScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, *argv: str) -> tuple[int, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(argv))
        return code, stdout.getvalue()

    def _report(self, output: str) -> dict:
        return json.loads(output.strip().splitlines()[-1])

    def test_schematic_scope_does_not_crash(self) -> None:
        code, _ = self._run("check", "schematic", str(self.root), "--format", "json")
        self.assertNotEqual(code, 4)

    def test_spec_scope_does_not_crash(self) -> None:
        code, _ = self._run("check", "spec", str(self.root), "--format", "json")
        self.assertNotEqual(code, 4)

    def test_connectivity_scope_does_not_crash(self) -> None:
        code, _ = self._run("check", "connectivity", str(self.root), "--format", "json")
        self.assertNotEqual(code, 4)

    def test_spec_scope_selects_specification_check(self) -> None:
        _, output = self._run("check", "spec", str(self.root), "--format", "json")
        report = self._report(output)
        self.assertEqual([item["id"] for item in report["checks"]], ["SPECIFICATION"])

    def test_connectivity_scope_selects_connectivity_check(self) -> None:
        _, output = self._run("check", "connectivity", str(self.root), "--format", "json")
        report = self._report(output)
        self.assertEqual([item["id"] for item in report["checks"]], ["CONNECTIVITY"])

    def test_report_profile_stays_valid_for_every_scope(self) -> None:
        for scope in ("schematic", "spec", "connectivity"):
            with self.subTest(scope=scope):
                _, output = self._run("check", scope, str(self.root), "--format", "json")
                report = self._report(output)
                self.assertIn(report["profile"], {"schematic", "layout"})

    def test_safety_fields_remain_false_for_every_scope(self) -> None:
        for scope in ("schematic", "spec", "connectivity"):
            with self.subTest(scope=scope):
                _, output = self._run("check", scope, str(self.root), "--format", "json")
                report = self._report(output)
                self.assertIs(report["production_ready"], False)
                self.assertIs(report["fabrication_approved"], False)


if __name__ == "__main__":
    unittest.main()
