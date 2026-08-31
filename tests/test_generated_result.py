from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcb_agent.diode import (
    GeneratedTestResult,
    _canonical_record_key,
    _require_passing_acceptance,
    generated_check,
)
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
        "connectivity-testbench.zen",
        "sha256:" + "a" * 64,
        "connectivity-result.json",
        "sha256:" + "b" * 64,
    )


def record(status: str, name: str = "_check_connectivity") -> dict:
    return {
        "test_bench_name": "PcbAgentConnectivity",
        "check_name": name,
        "status": status,
    }


class GeneratedPassClassificationTests(unittest.TestCase):
    def classify(self, payload: dict, returncode: int = 0) -> CheckStatus:
        # The classifier now decides from the retained, hash-verified bytes.
        # Stubbing the verifier to return those bytes keeps these unit tests
        # focused on classification without needing a real evidence directory.
        result_bytes = json.dumps(payload).encode("utf-8")
        with patch(
            "pcb_agent.diode._verify_retained_artifact",
            return_value=result_bytes,
        ):
            return generated_check(
                "CONNECTIVITY",
                outcome(payload, returncode),
                "PcbAgentConnectivity",
                "_check_connectivity",
                Path("."),
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

    def test_nested_diagnostic_identity_does_not_satisfy_gate(self) -> None:
        payload = {
            "results": [
                {
                    "status": "PASS",
                    "diagnostic": record("PASS"),
                }
            ],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 0,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)

    def test_alias_identity_fields_do_not_satisfy_gate(self) -> None:
        payload = {
            "results": [
                {
                    "test_bench": "PcbAgentConnectivity",
                    "name": "_check_connectivity",
                    "status": "PASS",
                }
            ],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 0,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)

    def test_duplicate_passing_expected_records_block(self) -> None:
        payload = {
            "results": [record("PASS"), record("PASS")],
            "summary": {
                "total": 2,
                "passed": 2,
                "failed": 0,
                "failures": 0,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload), CheckStatus.BLOCKED)


    def test_expected_failure_with_nonzero_exit_is_fail(self) -> None:
        payload = {
            "results": [record("FAIL")],
            "summary": {
                "total": 1,
                "passed": 0,
                "failed": 1,
                "failures": 1,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload, returncode=1), CheckStatus.FAIL)

    def test_expected_failure_with_nonzero_exit_but_zero_failed_is_blocked(self) -> None:
        payload = {
            "results": [record("FAIL")],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 1,
                "errors": 0,
            },
        }
        self.assertEqual(self.classify(payload, returncode=1), CheckStatus.BLOCKED)

    def test_expected_failure_with_nonzero_exit_and_errors_is_blocked(self) -> None:
        payload = {
            "results": [record("FAIL")],
            "summary": {
                "total": 1,
                "passed": 0,
                "failed": 1,
                "failures": 0,
                "errors": 1,
            },
        }
        self.assertEqual(self.classify(payload, returncode=1), CheckStatus.BLOCKED)

    def test_evidence_hash_mismatch_blocks(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root

            (raw / "connectivity-testbench.zen").write_text("mutated", encoding="utf-8")
            (raw / "connectivity-result.json").write_text("{}", encoding="utf-8")
            check = generated_check(
                "CONNECTIVITY",
                outcome(payload),
                "PcbAgentConnectivity",
                "_check_connectivity",
                raw,
            )
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("evidence", check.message)

    def test_missing_evidence_file_blocks(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            check = generated_check(
                "CONNECTIVITY",
                outcome(payload),
                "PcbAgentConnectivity",
                "_check_connectivity",
                Path(tmp),
            )
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("evidence", check.message)

    def test_matching_evidence_hash_allows_pass(self) -> None:
        import hashlib

        source_text = "generated source"
        result_text = json.dumps(
            {
                "results": [record("PASS")],
                "summary": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "failures": 0,
                    "errors": 0,
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root

            (raw / "connectivity-testbench.zen").write_text(source_text, encoding="utf-8")
            (raw / "connectivity-result.json").write_text(result_text, encoding="utf-8")

            process = ProcessResult(
                ("pcb", "test", "generated.zen", "-f", "json"),
                0,
                result_text,
                "",
                0.1,
                False,
                False,
                {},
            )
            resolved = GeneratedTestResult(
                process,
                "connectivity-testbench.zen",
                "sha256:" + hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                "connectivity-result.json",
                "sha256:" + hashlib.sha256(result_text.encode("utf-8")).hexdigest(),
            )
            check = generated_check(
                "CONNECTIVITY",
                resolved,
                "PcbAgentConnectivity",
                "_check_connectivity",
                raw,
            )
        self.assertEqual(check.status, CheckStatus.PASS)


    def test_status_comes_from_retained_bytes_not_stdout(self) -> None:
        """Retained evidence, not stdout, decides the verdict.

        If these two ever disagree the report hash would attest bytes that did
        not produce the reported status.
        """
        import hashlib

        passing = {
            "results": [record("PASS")],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "failures": 0,
                "errors": 0,
            },
        }
        failing = {
            "results": [record("FAIL")],
            "summary": {
                "total": 1,
                "passed": 0,
                "failed": 1,
                "failures": 1,
                "errors": 0,
            },
        }
        failing_text = json.dumps(failing)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root

            (raw / "connectivity-testbench.zen").write_bytes(b"source")
            (raw / "connectivity-result.json").write_bytes(failing_text.encode("utf-8"))

            process = ProcessResult(
                ("pcb", "test", "generated.zen", "-f", "json"),
                0,
                json.dumps(passing),
                "",
                0.1,
                False,
                False,
                {},
            )
            resolved = GeneratedTestResult(
                process,
                "connectivity-testbench.zen",
                "sha256:" + hashlib.sha256(b"source").hexdigest(),
                "connectivity-result.json",
                "sha256:" + hashlib.sha256(failing_text.encode("utf-8")).hexdigest(),
            )
            check = generated_check(
                "CONNECTIVITY",
                resolved,
                "PcbAgentConnectivity",
                "_check_connectivity",
                raw,
            )
        self.assertEqual(check.status, CheckStatus.FAIL)

    def test_malformed_expected_digest_blocks(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root

            (raw / "connectivity-testbench.zen").write_bytes(b"source")
            (raw / "connectivity-result.json").write_bytes(b"{}")

            process = ProcessResult(
                ("pcb", "test", "generated.zen", "-f", "json"),
                0,
                json.dumps(payload),
                "",
                0.1,
                False,
                False,
                {},
            )
            resolved = GeneratedTestResult(
                process,
                "connectivity-testbench.zen",
                "not-a-digest",
                "connectivity-result.json",
                "sha256:" + "b" * 64,
            )
            check = generated_check(
                "CONNECTIVITY",
                resolved,
                "PcbAgentConnectivity",
                "_check_connectivity",
                raw,
            )
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("malformed evidence digest", check.message)


class LockedZenerAcceptanceMatchingTests(unittest.TestCase):
    """Strict locked-Zener acceptance matching used by diode.execute.

    The matcher must consider only the canonical top-level `results[]` records,
    identify records solely by `{test_bench_name}.{check_name}` (no `name`/`test`
    alias fields), require exactly one match per expected test, and require the
    real tool's canonical lowercase `"pass"` status.
    """

    def _payload(self, *records: dict) -> dict:
        return {"results": list(records)}

    def test_canonical_record_key_helper(self) -> None:
        self.assertEqual(
            _canonical_record_key(
                {"test_bench_name": "BlinkyTest", "check_name": "component_value"}
            ),
            "BlinkyTest.component_value",
        )
        # Alias fields alone do not form a canonical key.
        self.assertIsNone(_canonical_record_key({"name": "x.y"}))
        self.assertIsNone(_canonical_record_key({"test": "x.y"}))
        # A canonical key needs both fields.
        self.assertIsNone(_canonical_record_key({"test_bench_name": "x"}))
        self.assertIsNone(_canonical_record_key({"check_name": "y"}))

    def test_canonical_top_level_pass_satisfies(self) -> None:
        payload = self._payload(
            {"test_bench_name": "BlinkyTest", "check_name": "component_value",
             "status": "pass"},
        )
        _require_passing_acceptance(payload, ["BlinkyTest.component_value"])  # no raise

    def test_nested_record_identity_does_not_satisfy(self) -> None:
        # Only the top-level record is canonical; a nested diagnostic that
        # happens to carry the identity must not satisfy the gate.
        payload = self._payload(
            {"status": "pass",
             "diagnostic": {"test_bench_name": "BlinkyTest",
                            "check_name": "component_value", "status": "pass"}},
        )
        with self.assertRaises(ValueError):
            _require_passing_acceptance(payload, ["BlinkyTest.component_value"])

    def test_alias_identity_fields_do_not_satisfy(self) -> None:
        # `name`/`test` alias fields are not honored; only canonical fields count.
        payload = self._payload(
            {"name": "BlinkyTest.component_value", "status": "pass"},
            {"test": "BlinkyTest.component_value", "status": "pass"},
        )
        with self.assertRaises(ValueError):
            _require_passing_acceptance(payload, ["BlinkyTest.component_value"])

    def test_duplicate_canonical_records_block(self) -> None:
        rec = {"test_bench_name": "BlinkyTest", "check_name": "component_value",
               "status": "pass"}
        payload = self._payload(dict(rec), dict(rec))
        with self.assertRaises(ValueError):
            _require_passing_acceptance(payload, ["BlinkyTest.component_value"])

    def test_uppercase_status_is_rejected(self) -> None:
        # The real tool emits lowercase "pass"; "PASS" is not accepted.
        payload = self._payload(
            {"test_bench_name": "BlinkyTest", "check_name": "component_value",
             "status": "PASS"},
        )
        with self.assertRaises(ValueError):
            _require_passing_acceptance(payload, ["BlinkyTest.component_value"])

    def test_fail_status_is_rejected(self) -> None:
        payload = self._payload(
            {"test_bench_name": "BlinkyTest", "check_name": "component_value",
             "status": "fail"},
        )
        with self.assertRaises(ValueError):
            _require_passing_acceptance(payload, ["BlinkyTest.component_value"])

    def test_missing_record_is_rejected(self) -> None:
        payload = self._payload(
            {"test_bench_name": "BlinkyTest", "check_name": "connectivity",
             "status": "pass"},
        )
        with self.assertRaises(ValueError):
            _require_passing_acceptance(payload, ["BlinkyTest.component_value"])


if __name__ == "__main__":
    unittest.main()
