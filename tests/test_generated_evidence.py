"""Tests that generated evidence artifacts are written byte-exact.

These must run on every platform. Windows newline translation previously made
the retained-artifact digest impossible to match, which would have made both
generated gates permanently BLOCKED once an adapter registry existed.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcb_agent import diode
from pcb_agent.process import ProcessResult
from pcb_agent.state import load_project

from helpers import write_contract


MULTILINE_SOURCE = 'M = Module("../src/board.zen")\ndef _check(m, i):\n    check(True, "ok")\n'
MULTILINE_RESULT = json.dumps(
    {
        "results": [
            {
                "test_bench_name": "PcbAgentConnectivity",
                "check_name": "_check_connectivity",
                "status": "PASS",
            }
        ],
        "summary": {"total": 1, "passed": 1, "failed": 0, "failures": 0, "errors": 0},
    },
    indent=2,
)


def _probe_ok(*args: object, **kwargs: object) -> ProcessResult:
    return ProcessResult(("pcb", "--help"), 0, "", "", 0.1, False, False, {})


class GeneratedEvidenceByteExactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)
        self.evidence_root = self.root / "reports" / "run" / "raw"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self) -> diode.GeneratedTestResult:
        run_result = ProcessResult(
            ("pcb", "test", "generated.zen", "-f", "json"),
            0,
            MULTILINE_RESULT,
            "",
            0.1,
            False,
            False,
            {},
        )
        with patch("pcb_agent.diode.probe", _probe_ok), patch(
            "pcb_agent.diode.run_process", return_value=run_result
        ):
            return diode.execute_generated_test(
                self.project,
                MULTILINE_SOURCE,
                self.evidence_root,
                "CONNECTIVITY",
                "PcbAgentConnectivity",
                "contract",
            )

    def test_generated_source_digest_matches_in_memory_digest(self) -> None:
        outcome = self._run()
        expected = "sha256:" + hashlib.sha256(MULTILINE_SOURCE.encode("utf-8")).hexdigest()
        self.assertEqual(outcome.generated_sha256, expected)

    def test_result_digest_matches_in_memory_digest(self) -> None:
        outcome = self._run()
        expected = "sha256:" + hashlib.sha256(MULTILINE_RESULT.encode("utf-8")).hexdigest()
        self.assertEqual(outcome.result_sha256, expected)

    def test_retained_source_contains_no_carriage_return(self) -> None:
        outcome = self._run()
        data = (self.root / outcome.generated_path).read_bytes()
        self.assertNotIn(b"\r", data)

    def test_retained_result_contains_no_carriage_return(self) -> None:
        outcome = self._run()
        data = (self.root / outcome.result_path).read_bytes()
        self.assertNotIn(b"\r", data)

    def test_round_trip_verification_accepts_retained_artifacts(self) -> None:
        outcome = self._run()
        diode._verify_retained_artifact(
            self.root, outcome.generated_path, outcome.generated_sha256
        )
        diode._verify_retained_artifact(
            self.root, outcome.result_path, outcome.result_sha256
        )

    def test_execute_does_not_raise_compatibility_error(self) -> None:
        outcome = self._run()
        self.assertIsInstance(outcome, diode.GeneratedTestResult)


if __name__ == "__main__":
    unittest.main()
