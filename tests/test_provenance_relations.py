"""Exact provenance relations across the retained Diode evidence bundle."""

from __future__ import annotations

import hashlib
import json
import unittest

from pcb_agent.evidence import load_evidence_manifest
from pcb_agent.generated_testbench import captured_adapter_registry, evidence_root


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ProvenanceRelationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = evidence_root()
        self.manifest = load_evidence_manifest(self.root / "manifest.sha256")
        self.capture = json.loads(
            (self.root / "capture-provenance.json").read_text(encoding="utf-8")
        )
        self.commands = json.loads(
            (self.root / "commands.json").read_text(encoding="utf-8")
        )

    def test_capture_script_hash_matches_bundled_script(self) -> None:
        bundled = (self.root / "scripts" / "capture-spike-evidence.py").read_bytes()
        self.assertEqual(self.capture["script_sha256"], _sha256(bundled))

    def test_production_script_hash_matches_bundled_script(self) -> None:
        bundled = (self.root / "scripts" / "capture-production-expression.py").read_bytes()
        self.assertEqual(self.capture["production_script_sha256"], _sha256(bundled))

    def test_commands_runs_share_capture_revision(self) -> None:
        for run in self.commands["runs"]:
            with self.subTest(kind=run.get("kind")):
                self.assertEqual(run["repo_revision"], self.capture["repo_revision"])

    def test_run_provenance_script_hash_matches_capture(self) -> None:
        for run in self.commands["runs"]:
            with self.subTest(kind=run.get("kind")):
                prov = json.loads(
                    (self.root / run["dir"].rstrip("/") / "run-provenance.json").read_text(
                        encoding="utf-8"
                    )
                )
                expected = (
                    self.capture["production_script_sha256"]
                    if run["kind"] == "production-expression"
                    else self.capture["script_sha256"]
                )
                self.assertEqual(prov["script_sha256"], expected)

    def test_adapter_evidence_hashes_match_manifest_entries(self) -> None:
        for adapter in captured_adapter_registry().values():
            for rel in (adapter.evidence_result_path, adapter.evidence_source_path):
                with self.subTest(kind=adapter.kind, path=rel):
                    self.assertIn(rel, self.manifest)
                    data = (self.root / rel).read_bytes()
                    self.assertEqual(_sha256(data), self.manifest[rel])

    def test_repo_revision_and_commands_agree_with_manifest(self) -> None:
        revision = (self.root / "repo-revision.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(revision, self.capture["repo_revision"])
        self.assertIn("repo-revision.txt", self.manifest)


if __name__ == "__main__":
    unittest.main()