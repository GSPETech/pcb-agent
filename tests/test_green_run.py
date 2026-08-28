"""A fully green verification run.

The PASS path through `_persist` and `EXIT_CODES` had no coverage at all, which
is exactly where the `production_ready` and `fabrication_approved` invariants
could leak without anyone noticing. These tests register a stub adapter so the
generated gates can reach PASS, then assert the safety fields are still false.

The stub adapter exists only here. The production registry stays empty until a
real Diode spike captures the mappings. See docs/spike-diode-net-naming.md.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import ROOT, make_fake_pcb
from pcb_agent import cli
from pcb_agent.generated_testbench import ComponentAdapter, set_adapter_registry


STUB_EVIDENCE = "sha256:" + "0" * 64
STUB_VERSION = "0.4.34"


def _stub_registry() -> dict[str, ComponentAdapter]:
    return {
        "resistor": ComponentAdapter(
            kind="resistor",
            instance_suffix="R",
            pins={"P1": "1", "P2": "2"},
            verified_pcbc_versions=frozenset({STUB_VERSION}),
            evidence_sha256=STUB_EVIDENCE,
            value_accessor="resistance",
            package_accessor="properties['package']",
            pullup_pin_pair=("P1", "P2"),
        ),
        "led": ComponentAdapter(
            kind="led",
            instance_suffix="LED",
            pins={"A": "A", "K": "K"},
            verified_pcbc_versions=frozenset({STUB_VERSION}),
            evidence_sha256=STUB_EVIDENCE,
            package_accessor="properties['package']",
        ),
    }


class GreenRunTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.tools = self.base / "tools"
        self.tools.mkdir()
        make_fake_pcb(self.tools)
        self.fixture = self.base / "valid-blinky"
        shutil.copytree(ROOT / "fixtures" / "valid-blinky", self.fixture)
        set_adapter_registry(_stub_registry())

    def tearDown(self) -> None:
        set_adapter_registry({})
        self.temporary.cleanup()

    def _verify(self) -> tuple[int, dict]:
        path = str(self.tools) + os.pathsep + os.environ.get("PATH", "")
        stdout = io.StringIO()
        with patch.dict(os.environ, {"PATH": path}, clear=False), contextlib.redirect_stdout(stdout):
            code = cli.main(["verify", str(self.fixture), "--format", "json"])
        report = json.loads(stdout.getvalue().strip().splitlines()[-1])
        return code, report

    def test_valid_fixture_exits_zero(self) -> None:
        code, _ = self._verify()
        self.assertEqual(code, 0)

    def test_valid_fixture_reports_pass(self) -> None:
        _, report = self._verify()
        self.assertEqual(report["status"], "PASS")

    def test_every_required_gate_passes(self) -> None:
        _, report = self._verify()
        for check in report["checks"]:
            if check["required"]:
                with self.subTest(check=check["id"]):
                    self.assertEqual(check["status"], "PASS")

    def test_production_ready_stays_false_on_pass(self) -> None:
        _, report = self._verify()
        self.assertIs(report["production_ready"], False)

    def test_fabrication_approved_stays_false_on_pass(self) -> None:
        _, report = self._verify()
        self.assertIs(report["fabrication_approved"], False)

    def test_human_review_still_required_on_pass(self) -> None:
        _, report = self._verify()
        self.assertIs(report["human_review_required"], True)

    def test_generated_evidence_paths_are_relative(self) -> None:
        _, report = self._verify()
        for check in report["checks"]:
            evidence = check.get("evidence") or {}
            for key in ("generated_testbench", "result"):
                artifact = evidence.get(key)
                if not isinstance(artifact, dict):
                    continue
                path = artifact["path"]
                with self.subTest(check=check["id"], artifact=key):
                    self.assertFalse(Path(path).is_absolute())
                    self.assertNotIn("\\", path)


if __name__ == "__main__":
    unittest.main()
