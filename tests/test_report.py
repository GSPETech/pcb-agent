from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pcb_agent.cli import EXIT_CODES
from pcb_agent.models import Check, CheckStatus, VerificationReport, aggregate_status
from pcb_agent.report import WARNING, render_markdown, write_report


class ReportTests(unittest.TestCase):
    def test_required_status_precedence_and_optional_failures(self) -> None:
        make = lambda status, required=True: Check(status.value, status, required=required)
        self.assertEqual(aggregate_status((make(CheckStatus.FAIL), make(CheckStatus.BLOCKED))), CheckStatus.BLOCKED)
        self.assertEqual(aggregate_status((make(CheckStatus.HUMAN_REVIEW),)), CheckStatus.HUMAN_REVIEW)
        self.assertEqual(aggregate_status((make(CheckStatus.SKIPPED),)), CheckStatus.BLOCKED)
        self.assertEqual(aggregate_status((make(CheckStatus.FAIL, False),)), CheckStatus.BLOCKED)

    def test_exit_contract_includes_human_review(self) -> None:
        self.assertEqual(EXIT_CODES[CheckStatus.PASS], 0)
        self.assertEqual(EXIT_CODES[CheckStatus.FAIL], 1)
        self.assertEqual(EXIT_CODES[CheckStatus.BLOCKED], 2)
        self.assertEqual(EXIT_CODES[CheckStatus.HUMAN_REVIEW], 5)
        self.assertEqual(EXIT_CODES[CheckStatus.SKIPPED], 0)

    def test_report_safety_fields_and_markdown_warning(self) -> None:
        report = VerificationReport("board", (Check("ok", CheckStatus.PASS),))
        data = report.to_dict()
        self.assertIs(data["production_ready"], False)
        self.assertIs(data["fabrication_approved"], False)
        self.assertIs(data["human_review_required"], True)
        markdown = render_markdown(report)
        self.assertIn(WARNING, markdown)
        self.assertIn("Production ready: **false**", markdown)
        self.assertIn("Fabrication approved: **false**", markdown)

    def test_written_json_contains_required_report_fields(self) -> None:
        report = VerificationReport(
            "board", (Check("ok", CheckStatus.PASS),), run_id="run-1",
            versions={"pcb": "0.4"}, hashes={"SPEC.json": "sha256:test"}
        )
        with tempfile.TemporaryDirectory() as temporary:
            json_path = Path(temporary) / "report.json"
            markdown_path = Path(temporary) / "report.md"
            write_report(report, json_path, markdown_path)
            data = json.loads(json_path.read_text(encoding="utf-8"))
            for field in ("project", "checks", "status", "run_id", "versions", "hashes", "timestamp"):
                self.assertIn(field, data)
            self.assertIn(WARNING, markdown_path.read_text(encoding="utf-8"))

    def test_explicit_status_must_match_aggregation(self) -> None:
        with self.assertRaises(ValueError):
            VerificationReport("board", (Check("bad", CheckStatus.FAIL),), status=CheckStatus.PASS)


if __name__ == "__main__":
    unittest.main()
