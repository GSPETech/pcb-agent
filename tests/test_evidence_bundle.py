"""Completeness tests for the Diode evidence bundle.

Every file listed in the manifest must exist and hash to its entry; every
manifest entry must correspond to a real file; every report-referenced artifact
must exist with a matching hash; every adapter evidence path must exist and be
covered; the version record must establish pcbc 0.4.40; and safety fields must
stay false.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from pcb_agent.evidence import load_evidence_manifest, validate_version_record
from pcb_agent.generated_testbench import (
    captured_adapter_registry,
    ensure_registry_provenance,
    evidence_root,
    render_connectivity_testbench,
    render_specification_testbench,
    reset_registry_provenance,
)


def _evidence_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "manifest.sha256"
    )


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


class EvidenceBundleCompletenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = evidence_root()
        self.manifest = load_evidence_manifest(self.root / "manifest.sha256")

    def test_every_evidence_file_is_listed_exactly_once(self) -> None:
        listed = set(self.manifest)
        present = {_relative(self.root, path) for path in _evidence_files(self.root)}
        self.assertEqual(listed, present)
        self.assertEqual(len(self.manifest), len(present))

    def test_every_manifest_entry_exists(self) -> None:
        for relative in self.manifest:
            with self.subTest(relative=relative):
                self.assertTrue((self.root / relative).is_file())

    def test_every_hash_matches_current_bytes(self) -> None:
        for relative, digest in self.manifest.items():
            with self.subTest(relative=relative):
                data = (self.root / relative).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)

    def test_version_record_establishes_pcbc_0_4_40(self) -> None:
        version = (self.root / "pcb-version.txt").read_text(encoding="utf-8").strip()
        self.assertIn("pcbc 0.4.40", version)

    def test_version_record_is_bound_to_manifest(self) -> None:
        self.assertIn("pcb-version.txt", self.manifest)
        self.assertEqual(validate_version_record(self.root, self.manifest), "0.4.40")
        data = (self.root / "pcb-version.txt").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.manifest["pcb-version.txt"])

    def test_version_record_is_exactly_one_strict_pcbc_line(self) -> None:
        text = (self.root / "pcb-version.txt").read_text(encoding="utf-8")
        import re
        records = re.findall(r"\bpcbc\s+(\d+\.\d+\.\d+)\b", text)
        self.assertEqual(records, ["0.4.40"])

    def test_capture_provenance_records_clean_tree(self) -> None:
        provenance = json.loads(
            (self.root / "capture-provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(provenance["git_status"], "")
        self.assertEqual(
            provenance["git_status_sha256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        self.assertEqual(provenance["git_diff_binary"], "")
        self.assertEqual(provenance["filesystem"], "ext4")
        self.assertEqual(provenance["pcbc_version"], "0.4.40")

    def test_every_run_records_revision_matching_capture(self) -> None:
        revision = (self.root / "repo-revision.txt").read_text(encoding="utf-8").strip()
        capture = json.loads(
            (self.root / "capture-provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(revision, capture["repo_revision"])
        commands = json.loads((self.root / "commands.json").read_text(encoding="utf-8"))
        run_dirs = [run["dir"].rstrip("/") for run in commands["runs"]]
        self.assertEqual(len(run_dirs), 8)
        for run_dir in run_dirs:
            with self.subTest(run_dir=run_dir):
                provenance_path = self.root / run_dir / "run-provenance.json"
                self.assertTrue(provenance_path.is_file())
                provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
                self.assertEqual(provenance["repo_revision"], revision)
                self.assertEqual(provenance["git_status"], "")

    def test_every_command_has_full_metadata(self) -> None:
        commands = json.loads((self.root / "commands.json").read_text(encoding="utf-8"))
        required = ("kind", "argv", "cwd", "executable", "timestamp",
                    "repo_revision", "stdout", "stderr")
        for run in commands["runs"]:
            with self.subTest(kind=run.get("kind")):
                self.assertIsInstance(run.get("exit_code"), int)
                for field in required:
                    self.assertIn(field, run)
                    self.assertTrue(run[field], f"{field} empty for {run.get('kind')}")

    def test_production_command_metadata_is_executable_not_placeholder(self) -> None:
        commands = json.loads((self.root / "commands.json").read_text(encoding="utf-8"))
        production = next(run for run in commands["runs"] if run["kind"] == "production-expression")
        argv = production["argv"]
        self.assertNotIn("render+execute", " ".join(argv))
        self.assertIn("scripts/capture-production-expression.py", " ".join(argv))
        self.assertIsInstance(production["exit_code"], int)
        self.assertTrue(production["cwd"])
        self.assertTrue(production["executable"])
        self.assertTrue(production["timestamp"])
        self.assertIn("scripts/capture-production-expression.py", self.manifest)

    def test_hashed_bundle_script_matches_tracked_capture_script(self) -> None:
        for name in ("capture-spike-evidence.py", "capture-production-expression.py"):
            with self.subTest(name=name):
                bundled = self.root / "scripts" / name
                tracked = Path(__file__).resolve().parents[1] / "scripts" / name
                self.assertIn(f"scripts/{name}", self.manifest)
                self.assertEqual(bundled.read_bytes(), tracked.read_bytes())

    def test_both_renderers_byte_match_retained_generated_sources(self) -> None:
        from pcb_agent.state import load_project

        project = load_project(Path("fixtures/production-expression"))
        connectivity = render_connectivity_testbench(project, "0.4.40")
        specification = render_specification_testbench(project, "0.4.40")
        retained_connectivity = (
            self.root / "production-expression" / "production-connectivity-testbench.generated.zen"
        ).read_bytes()
        retained_specification = (
            self.root / "production-expression" / "production-specification-testbench.generated.zen"
        ).read_bytes()
        self.assertEqual(connectivity.encode("utf-8"), retained_connectivity)
        self.assertEqual(specification.encode("utf-8"), retained_specification)

    def test_retained_production_generated_source_digests_match_summary(self) -> None:
        summary = json.loads(
            (self.root / "production-expression" / "production-summary.json").read_text(encoding="utf-8")
        )
        for gate in ("connectivity", "specification"):
            with self.subTest(gate=gate):
                generated = (
                    self.root / "production-expression" / f"production-{gate}-testbench.generated.zen"
                ).read_bytes()
                self.assertEqual(
                    summary[gate]["generated_sha256"],
                    "sha256:" + hashlib.sha256(generated).hexdigest(),
                )
                result = (
                    self.root / "production-expression" / f"production-{gate}-result.json"
                ).read_bytes()
                self.assertEqual(
                    summary[gate]["result_sha256"],
                    "sha256:" + hashlib.sha256(result).hexdigest(),
                )

    def test_lazy_provenance_validation_passes_against_bundle(self) -> None:
        reset_registry_provenance()
        try:
            ensure_registry_provenance()
        finally:
            reset_registry_provenance()

    def test_repo_revision_is_nonempty(self) -> None:
        revision = (self.root / "repo-revision.txt").read_text(encoding="utf-8").strip()
        self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_environment_establishes_ext4(self) -> None:
        env = (self.root / "environment.txt").read_text(encoding="utf-8")
        self.assertIn("ext4", env)

    def test_green_and_negative_reports_exist(self) -> None:
        for relative in (
            "green-real/green-real-report.json",
            "negative-invalid-syntax/verify-report.json",
            "negative-invalid-connectivity/verify-report.json",
            "negative-invalid-value/verify-report.json",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, self.manifest)
                self.assertTrue((self.root / relative).is_file())

    def test_prefix_variation_artifact_exists(self) -> None:
        for relative in (
            "prefix/prefix-evidence.zen",
            "prefix/prefix-renamed-alt-case.json",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, self.manifest)
        payload = json.loads((self.root / "prefix/prefix-renamed-alt-case.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["test_bench_name"], "RenamedBench")
        self.assertEqual(payload["results"][0]["case_name"], "alt_case")
        self.assertEqual(payload["results"][0]["status"], "pass")

    def test_negative_reports_have_expected_classifications(self) -> None:
        cases = {
            "negative-invalid-syntax": ("BLOCKED", "DIODE_BUILD", "FAIL"),
            "negative-invalid-connectivity": ("BLOCKED", "ZENER_TEST", "FAIL"),
            "negative-invalid-value": ("BLOCKED", "ZENER_TEST", "FAIL"),
        }
        for relative, (status, gate_id, gate_status) in cases.items():
            with self.subTest(relative=relative):
                report = json.loads(
                    (self.root / relative / "verify-report.json").read_text(encoding="utf-8")
                )
                self.assertEqual(report["status"], status)
                gate = next(check for check in report["checks"] if check["id"] == gate_id)
                self.assertEqual(gate["status"], gate_status)

    def test_green_report_safety_fields_stay_false(self) -> None:
        report = json.loads(
            (self.root / "green-real/green-real-report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "PASS")
        self.assertIs(report["production_ready"], False)
        self.assertIs(report["fabrication_approved"], False)
        self.assertIs(report["human_review_required"], True)
        for gate in ("CONNECTIVITY", "SPECIFICATION"):
            check = next(item for item in report["checks"] if item["id"] == gate)
            self.assertEqual(check["status"], "PASS")

    def test_every_report_referenced_artifact_exists_and_hashes_match(self) -> None:
        cases = {
            "green-real/green-real-report.json": "green-real/run/raw",
            "negative-invalid-syntax/verify-report.json": "negative-invalid-syntax/run/raw",
            "negative-invalid-connectivity/verify-report.json": "negative-invalid-connectivity/run/raw",
            "negative-invalid-value/verify-report.json": "negative-invalid-value/run/raw",
        }
        for relative, raw_dir in cases.items():
            with self.subTest(relative=relative):
                report = json.loads((self.root / relative).read_text(encoding="utf-8"))
                for artifact in report.get("artifacts", []):
                    self._check_artifact(artifact, raw_dir)

    def _check_artifact(self, artifact: object, raw_dir: str) -> None:
        if not isinstance(artifact, dict):
            return
        if isinstance(artifact.get("path"), str) and isinstance(artifact.get("sha256"), str):
            relative = f"{raw_dir}/{artifact['path']}"
            self.assertIn(relative, self.manifest)
            data = (self.root / relative).read_bytes()
            self.assertEqual("sha256:" + hashlib.sha256(data).hexdigest(), artifact["sha256"])
        for key in ("generated_testbench", "result"):
            nested = artifact.get(key)
            if isinstance(nested, dict):
                self._check_artifact(nested, raw_dir)

    def test_every_adapter_evidence_path_is_covered_by_manifest(self) -> None:
        for adapter in captured_adapter_registry().values():
            with self.subTest(kind=adapter.kind):
                self.assertIn(adapter.evidence_result_path, self.manifest)
                self.assertIn(adapter.evidence_source_path, self.manifest)

    def test_exact_registered_kind_set_matches_documentation(self) -> None:
        expected = frozenset({
            "resistor", "led", "capacitor", "inductor", "ferrite_bead",
            "thermistor", "zener", "rectifier", "tvs",
        })
        self.assertEqual(set(captured_adapter_registry()), expected)

    def test_crystal_is_absent_and_documented_blocked(self) -> None:
        self.assertNotIn("crystal", captured_adapter_registry())
        doc = Path(__file__).resolve().parents[1] / "docs" / "spike-diode-net-naming.md"
        text = doc.read_text(encoding="utf-8")
        self.assertIn("crystal", text.lower())
        self.assertIn("OBSERVED", text)
        self.assertIn("unsupported", text)

    def test_sanitized_companions_exist_and_hide_host_paths(self) -> None:
        for relative in (
            "valid-blinky/valid-blinky.sanitized.json",
            "spike-generics/spike-generics.sanitized.json",
            "green-real/green-real-report.sanitized.json",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, self.manifest)
                text = (self.root / relative).read_text(encoding="utf-8")
                self.assertNotIn("/home/", text)
                self.assertNotIn("pcbagent-full", text)
                self.assertNotIn("C:\\\\", text)
                self.assertNotIn("C:/", text)

    def test_raw_evidence_keeps_original_bytes(self) -> None:
        raw = (self.root / "valid-blinky/valid-blinky.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "02c6cb60bfaf371e640e34ed0ff7b707074cfad0789b38a25c014cfa66cfac11",
        )
        raw = (self.root / "spike-generics/spike-generics.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "3320a8aa668f5f28dc19b4240f9f92e22333805ead12e36cb4c5a3c3b1636267",
        )


if __name__ == "__main__":
    unittest.main()
