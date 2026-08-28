"""A fully green verification run.

The PASS path through `_persist` and `EXIT_CODES` had no coverage at all, which
is exactly where the `production_ready` and `fabrication_approved` invariants
could leak without anyone noticing. These tests register a stub adapter so the
generated gates can reach PASS, then assert the safety fields are still false.

The project is built here rather than copied from `fixtures/valid-blinky`,
because that fixture declares a `package` on `D1` with no requirement covering
it, which the ownership guard correctly reports as BLOCKED. Locked fixtures are
never edited to make a test pass.

The stub adapter exists only here. The production registry stays empty until a
real Diode spike captures the mappings. See docs/spike-diode-net-naming.md.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import make_fake_pcb
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
    }


def _write_green_project(root: Path) -> None:
    """A contract where every declared property has a covering requirement.

    The acceptance test names match what the fake `pcb` emits for a
    non-generated test run.
    """
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "board.zen").write_text("Board()\n", encoding="utf-8")
    (root / "tests" / "board_test.zen").write_text(
        "TestBench(name='BlinkyTest')\n", encoding="utf-8"
    )
    (root / "SPEC.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "project": {"name": "green-board", "pcb_version": "0.4", "layers": 4},
                "requirements": [
                    {
                        "id": "REQ-001",
                        "type": "component",
                        "description": "R1 shall be 1kohm in package 0402",
                        "subject": "R1",
                        "constraints": {"value": "1kohm", "package": "0402"},
                        "severity": "error",
                        "evidence_required": ["zener_test"],
                    },
                    {
                        "id": "REQ-002",
                        "type": "connectivity",
                        "description": "R1.P1 shall sit on VCC",
                        "subject": "VCC",
                        "constraints": {"members": ["R1.P1"]},
                        "severity": "error",
                        "evidence_required": ["zener_test"],
                    },
                ],
                "fabrication": {
                    "automatic_approval": False,
                    "human_approval_required": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "ACCEPTANCE.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "checks": [
                    {
                        "id": "ACC-001",
                        "requirement": "REQ-001",
                        "kind": "zener_test",
                        "test": "BlinkyTest.component_value",
                        "expected": "PASS",
                    },
                    {
                        "id": "ACC-002",
                        "requirement": "REQ-002",
                        "kind": "zener_test",
                        "test": "BlinkyTest.connectivity",
                        "expected": "PASS",
                    },
                ],
                "production_ready": False,
                "fabrication_approved": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "expected-connectivity.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "components": {
                    "R1": {"kind": "resistor", "value": "1kohm", "package": "0402"},
                },
                "nets": {
                    "VCC": {"members": ["R1.P1"]},
                    "GND": {"members": ["R1.P2"]},
                },
                "rules": {
                    "forbid_unlisted_members": False,
                    "required_power_nets": ["VCC", "GND"],
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "project.toml").write_text(
        '[project]\n'
        'name = "green-board"\n'
        'profile = "schematic"\n'
        'source = "src/board.zen"\n'
        'test = "tests/board_test.zen"\n'
        '\n'
        '[toolchain]\n'
        'pcb_version = "0.4"\n'
        '\n'
        '[layout]\n'
        'required = false\n',
        encoding="utf-8",
    )


class GreenRunTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.tools = self.base / "tools"
        self.tools.mkdir()
        make_fake_pcb(self.tools)
        self.fixture = self.base / "green-board"
        _write_green_project(self.fixture)
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
        code, report = self._verify()
        self.assertEqual(
            code,
            0,
            msg=[(c["id"], c["status"], c["message"]) for c in report["checks"]],
        )

    def test_valid_fixture_reports_pass(self) -> None:
        _, report = self._verify()
        self.assertEqual(report["status"], "PASS")

    def test_every_required_gate_passes(self) -> None:
        _, report = self._verify()
        for check in report["checks"]:
            if check["required"]:
                with self.subTest(check=check["id"]):
                    self.assertEqual(check["status"], "PASS", msg=check["message"])

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
        seen = 0
        for check in report["checks"]:
            evidence = check.get("evidence") or {}
            for key in ("generated_testbench", "result"):
                artifact = evidence.get(key)
                if not isinstance(artifact, dict):
                    continue
                seen += 1
                path = artifact["path"]
                with self.subTest(check=check["id"], artifact=key):
                    self.assertFalse(Path(path).is_absolute())
                    self.assertNotIn("\\", path)
        self.assertGreater(seen, 0)


if __name__ == "__main__":
    unittest.main()
