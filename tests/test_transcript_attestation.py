"""Non-circular verification-transcript attestation model.

The primary manifest must not include the files that assert its own digest:
`windows-manifest.txt`, `wsl-manifest.txt`, and `manifest-attestation.json`.
The attestation JSON stores the primary manifest SHA-256 plus independent
per-platform check metadata, so the attestation verifies a prior immutable
digest instead of a self-referential one.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from pcb_agent.evidence import load_evidence_manifest
from pcb_agent.generated_testbench import evidence_root

_EXCLUDED_NAMES = (
    "manifest-attestation.json",
    "windows-manifest.txt",
    "wsl-manifest.txt",
)


class TranscriptAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = evidence_root()
        self.manifest = load_evidence_manifest(self.root / "manifest.sha256")

    def test_rebuild_command_excludes_self_attesting_names(self) -> None:
        from pathlib import Path

        script = Path(__file__).resolve().parents[1] / "scripts" / "capture-spike-evidence.py"
        text = script.read_text(encoding="utf-8")
        start = text.index("find . -type f")
        end = text.index("> manifest.sha256") + len("> manifest.sha256")
        rebuild = text[start:end]
        for name in _EXCLUDED_NAMES:
            with self.subTest(name=name):
                self.assertIn(f"! -name {name} ", f" {rebuild} ")

    def test_pytest_and_pyright_transcripts_have_separate_records(self) -> None:
        for rel in ("verification/windows-pytest.txt", "verification/wsl-pytest.txt",
                    "verification/pyright.txt"):
            with self.subTest(rel=rel):
                self.assertIn(rel, self.manifest)
                self.assertTrue((self.root / rel).is_file())

    def test_attestation_stores_primary_manifest_digest(self) -> None:
        attestation_path = self.root / "manifest-attestation.json"
        if not attestation_path.is_file():
            self.skipTest("attestation generated in task 10")
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(
            (self.root / "manifest.sha256").read_bytes()
        ).hexdigest()
        self.assertEqual(attestation["primary_manifest_sha256"], digest)

    def test_attestation_windows_and_wsl_records_present(self) -> None:
        attestation_path = self.root / "manifest-attestation.json"
        if not attestation_path.is_file():
            self.skipTest("attestation generated in task 10")
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        for platform in ("windows", "wsl"):
            with self.subTest(platform=platform):
                record = attestation[platform]
                self.assertTrue(record["command"])
                self.assertTrue(record["cwd"])
                self.assertTrue(record["timestamp"])
                self.assertTrue(record["revision"])
                self.assertIsInstance(record["exit"], int)
                self.assertTrue(record["transcript"])
                self.assertTrue(record["transcript_sha256"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()