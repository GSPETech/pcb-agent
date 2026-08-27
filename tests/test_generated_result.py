from __future__ import annotations

import json
import unittest
from pathlib import Path

from pcb_agent.diode import GeneratedTestResult, generated_check
from pcb_agent.models import CheckStatus
from pcb_agent.process import ProcessResult


def outcome(payload: dict, returncode: int = 0) -> GeneratedTestResult:
    process = ProcessResult(
        ("pcb", "test", "generated.zen", "-f", "json"),
        returncode,
        json.dumps(payload),
        "",
        0.1,
        False,
        False,
        {},
    )
    return GeneratedTestResult(
        process,
        Path("connectivity-testbench.zen"),
        "sha256:" + "a" * 64,
        Path("connectivity-result.json"),
        "sha256:" + "b" * 64,
    )


def record(status: str, name: str = "_check_connectivity") -> dict:
    return {
        "test_bench_name": "PcbAgentConnectivity",
        "check_name": name,
        "status": status,
    }


class GeneratedPassClassificationTests(unittest.TestCase):
    def classify(self, payload: dict) -> CheckStatus:
        return generated_check(
            "CONNECTIVITY",
            outcome(payload),
            "PcbAgentConnectivity",
            "_check_connectivity",
        ).status

    def test_clean_expected_result_passes(self) -> None:
        payload = {
            "results": [record("PASS")],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 0,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.PASS)

    def test_unrelated_failed_record_blocks_zero_exit_pass(self) -> None:
        payload = {
            "results": [record("PASS"), record("FAIL", "other_check")],
            "summary": {
                "total": 2,
                "passed": 1,
                "failed": 1,
                "failures": 1,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)

    def test_duplicate_expected_failure_blocks_zero_exit_pass(self) -> None:
        payload = {
            "results": [record("PASS"), record("FAIL")],
            "summary": {
                "total": 2,
                "passed": 1,
                "failed": 1,
                "failures": 1,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)

    def test_positive_failure_counter_blocks_zero_exit_pass(self) -> None:
        payload = {
            "results": [record("PASS")],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 1,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)

    def test_positive_error_counter_blocks_zero_exit_pass(self) -> None:
        payload = {
            "results": [record("PASS")],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 0,
                "errors": 1,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
