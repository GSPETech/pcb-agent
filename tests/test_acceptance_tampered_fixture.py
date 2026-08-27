"""Tests for tamper detection across protected files in a fixture."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pcb_agent.policy import PolicyViolation, ProtectedHashes


ROOT = Path(__file__).resolve().parent.parent


def _copy_fixture_to(target: Path) -> None:
    src = ROOT / "fixtures" / "acceptance-tampered"
    shutil.copytree(src, target)


class TamperDetectionTests(unittest.TestCase):
    def test_tampering_acceptance_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fixture"
            _copy_fixture_to(root)
            captured = ProtectedHashes.capture(root, ("ACCEPTANCE.json",))
            payload = json.loads((root / "ACCEPTANCE.json").read_text())
            payload["checks"][0]["expected"] = "FAIL"
            (root / "ACCEPTANCE.json").write_text(json.dumps(payload, indent=2))
            with self.assertRaises(PolicyViolation) as ctx:
                captured.verify()
            self.assertIn("ACCEPTANCE.json", str(ctx.exception))

    def test_tampering_test_file_is_detected_when_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fixture"
            _copy_fixture_to(root)
            captured = ProtectedHashes.capture(root, ("tests/blinky_test.zen",))
            test_path = root / "tests" / "blinky_test.zen"
            original = test_path.read_text(encoding="utf-8")
            test_path.write_text(original + "\n# tampered comment\n", encoding="utf-8")
            with self.assertRaises(PolicyViolation):
                captured.verify()

    def test_unmodified_capture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fixture"
            _copy_fixture_to(root)
            captured = ProtectedHashes.capture(root, ("SPEC.json", "ACCEPTANCE.json"))
            captured.verify()


if __name__ == "__main__":
    unittest.main()