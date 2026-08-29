"""Tests for the production captured adapter registry and its provenance.

The production registry is built from captured Diode 0.4.40 evidence and is
repository-owned. These tests validate it WITHOUT replacing it with a stub:
exact kind set, per-adapter fields, crystal absence, and evidence bundle
provenance (manifest entry + file bytes + version record).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pcb_agent.evidence import (
    EvidenceError,
    load_evidence_manifest,
    validate_adapter_provenance,
    validate_registry_provenance,
    validate_version_record,
)
from pcb_agent.generated_testbench import (
    ComponentAdapter,
    GeneratorError,
    adapter_for,
    captured_adapter_registry,
    ensure_registry_provenance,
    evidence_root,
    known_kinds,
    render_connectivity_testbench,
    render_specification_testbench,
    reset_registry_provenance,
    validate_captured_registry,
)


EXPECTED_KINDS = frozenset({
    "resistor", "led", "capacitor", "inductor", "ferrite_bead",
    "thermistor", "zener", "rectifier", "tvs",
})


class CapturedRegistryTests(unittest.TestCase):
    def test_registered_kinds_exactly_match_documentation(self) -> None:
        self.assertEqual(known_kinds(), EXPECTED_KINDS)

    def test_crystal_is_absent(self) -> None:
        self.assertNotIn("crystal", known_kinds())

    def test_crystal_contract_raises_generator_error(self) -> None:
        with self.assertRaises(GeneratorError) as ctx:
            adapter_for("crystal", "0.4.40")
        self.assertIn("unsupported component kind", str(ctx.exception))

    def test_adapter_fields_for_every_registered_kind(self) -> None:
        registry = captured_adapter_registry()
        expected_suffix = {
            "resistor": "R", "led": "LED", "capacitor": "C", "inductor": "L",
            "ferrite_bead": "FB", "thermistor": "TH", "zener": "D",
            "rectifier": "D", "tvs": "D",
        }
        expected_pins = {
            "resistor": {"P1": "1", "P2": "2"}, "led": {"A": "A", "K": "K"},
            "capacitor": {"P1": "1", "P2": "2"}, "inductor": {"P1": "1", "P2": "2"},
            "ferrite_bead": {"P1": "1", "P2": "2"},
            "thermistor": {"P1": "1", "P2": "2"},
            "zener": {"A": "A", "K": "K"}, "rectifier": {"A": "A", "K": "K"},
            "tvs": {"A": "A", "K": "K"},
        }
        expected_accessors = {
            "resistor": ("resistance", "properties['package']"),
            "led": (None, "properties['package']"),
            "capacitor": ("capacitance", "properties['package']"),
            "inductor": ("inductance", "properties['package']"),
            "ferrite_bead": ("impedance", "properties['package']"),
            "thermistor": ("resistance", "properties['package']"),
            "zener": ("zener_voltage", "properties['package']"),
            "rectifier": ("reverse_voltage", "properties['package']"),
            "tvs": ("reverse_standoff_voltage", "properties['package']"),
        }
        for kind in EXPECTED_KINDS:
            with self.subTest(kind=kind):
                adapter = registry[kind]
                self.assertEqual(adapter.kind, kind)
                self.assertEqual(adapter.instance_suffix, expected_suffix[kind])
                self.assertEqual(dict(adapter.pins), expected_pins[kind])
                self.assertEqual(adapter.verified_pcbc_versions, frozenset({"0.4.40"}))
                self.assertTrue(adapter.evidence_sha256.startswith("sha256:"))
                self.assertTrue(adapter.evidence_result_path)
                self.assertTrue(adapter.evidence_source_path)
                self.assertTrue(adapter.evidence_source_sha256.startswith("sha256:"))
                value_accessor, package_accessor = expected_accessors[kind]
                self.assertEqual(adapter.value_accessor, value_accessor)
                self.assertEqual(adapter.package_accessor, package_accessor)
                self.assertIsNone(adapter.mpn_accessor)

    def test_only_resistor_has_pullup_pair(self) -> None:
        registry = captured_adapter_registry()
        self.assertEqual(registry["resistor"].pullup_pin_pair, ("P1", "P2"))
        for kind in EXPECTED_KINDS - {"resistor"}:
            with self.subTest(kind=kind):
                self.assertIsNone(registry[kind].pullup_pin_pair)


class EvidenceManifestTests(unittest.TestCase):
    def test_load_manifest_parses_entries_and_ignores_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.sha256"
            manifest.write_text(
                "# comment\n"
                "a" + "b" * 63 + "  ./a/file.json\n"
                "c" + "d" * 63 + "  b/file.zen\n",
                encoding="utf-8",
            )
            entries = load_evidence_manifest(manifest)
        self.assertEqual(
            entries, {"a/file.json": "a" + "b" * 63, "b/file.zen": "c" + "d" * 63}
        )

    def test_duplicate_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.sha256"
            digest = "ab" + "0" * 62
            manifest.write_text(
                f"{digest}  a/file.json\n{digest}  a/file.json\n", encoding="utf-8"
            )
            with self.assertRaises(EvidenceError) as ctx:
                load_evidence_manifest(manifest)
            self.assertIn("duplicate", str(ctx.exception))

    def test_malformed_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.sha256"
            manifest.write_text("not-a-digest  a/file.json\n", encoding="utf-8")
            with self.assertRaises(EvidenceError) as ctx:
                load_evidence_manifest(manifest)
            self.assertIn("malformed", str(ctx.exception))


def _write_bundle(
    root: Path, version: str = "0.4.40"
) -> tuple[Path, Path, Path, dict[str, str]]:
    """Write a minimal evidence bundle; returns (root, manifest, result, source)."""
    result = root / "spike-generics.json"
    source = root / "spike-generics-testbench.zen"
    result.write_bytes(b'{"results": [{"status": "pass"}]}')
    source.write_bytes(b'check(True, "ok")\n')
    version_path = root / "pcb-version.txt"
    version_path.write_text(f"pcbc {version}\n", encoding="utf-8", newline="\n")
    manifest = root / "manifest.sha256"
    manifest.write_text(
        "# bundle\n"
        f"{hashlib.sha256(result.read_bytes()).hexdigest()}  ./spike-generics.json\n"
        f"{hashlib.sha256(source.read_bytes()).hexdigest()}  ./spike-generics-testbench.zen\n"
        f"{hashlib.sha256(version_path.read_bytes()).hexdigest()}  ./pcb-version.txt\n",
        encoding="utf-8",
    )
    return root, manifest, result, source


def _rewrite_version(root: Path, manifest: Path, text: str, *, refresh_manifest: bool) -> None:
    """Overwrite pcb-version.txt and optionally refresh its manifest hash."""
    version_path = root / "pcb-version.txt"
    version_path.write_text(text, encoding="utf-8", newline="\n")
    if refresh_manifest:
        entries = load_evidence_manifest(manifest)
        entries["pcb-version.txt"] = hashlib.sha256(version_path.read_bytes()).hexdigest()
        lines = [f"{digest}  ./{relative}\n" for relative, digest in sorted(entries.items())]
        manifest.write_text("".join(lines), encoding="utf-8")


def _generics_adapter() -> ComponentAdapter:
    return ComponentAdapter(
        kind="capacitor",
        instance_suffix="C",
        pins={"P1": "1", "P2": "2"},
        verified_pcbc_versions=frozenset({"0.4.40"}),
        evidence_sha256="sha256:" + hashlib.sha256(b'{"results": [{"status": "pass"}]}').hexdigest(),
        evidence_result_path="spike-generics.json",
        evidence_source_path="spike-generics-testbench.zen",
        evidence_source_sha256="sha256:" + hashlib.sha256(b'check(True, "ok")\n').hexdigest(),
        value_accessor="capacitance",
        package_accessor="properties['package']",
    )


class AdapterProvenanceTests(unittest.TestCase):
    def test_valid_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            entries = load_evidence_manifest(manifest)
            validate_adapter_provenance(_generics_adapter(), root, entries)

    def test_missing_result_file_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            (root / "spike-generics.json").unlink()
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_adapter_provenance(_generics_adapter(), root, entries)
            self.assertIn("invalid", str(ctx.exception).lower())
            self.assertIn("spike-generics.json", str(ctx.exception))

    def test_wrong_digest_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            (root / "spike-generics.json").write_text("tampered", encoding="utf-8")
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_adapter_provenance(_generics_adapter(), root, entries)
            self.assertIn("hash mismatch", str(ctx.exception))

    def test_missing_manifest_entry_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            entries = load_evidence_manifest(manifest)
            del entries["spike-generics.json"]
            with self.assertRaises(EvidenceError) as ctx:
                validate_adapter_provenance(_generics_adapter(), root, entries)
            self.assertIn("missing from manifest", str(ctx.exception))

    def test_duplicate_kind_is_rejected_by_builder(self) -> None:
        from pcb_agent.generated_testbench import build_adapter_registry

        with self.assertRaises(ValueError) as ctx:
            build_adapter_registry([_generics_adapter(), _generics_adapter()])
        self.assertIn("duplicate", str(ctx.exception))


class VersionRecordTests(unittest.TestCase):
    def test_valid_exact_version_passes_and_parses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            entries = load_evidence_manifest(manifest)
            self.assertEqual(validate_version_record(root, entries), "0.4.40")
            validate_registry_provenance({"capacitor": _generics_adapter()}, root, manifest)

    def test_missing_manifest_entry_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            entries = load_evidence_manifest(manifest)
            del entries["pcb-version.txt"]
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("missing from manifest", str(ctx.exception))

    def test_wrong_digest_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            _rewrite_version(root, manifest, "pcbc 0.4.40", refresh_manifest=False)
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("hash differs", str(ctx.exception))

    def test_multiple_conflicting_versions_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            _rewrite_version(root, manifest, "pcbc 0.4.40\npcbc 0.4.41\n", refresh_manifest=True)
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("exactly one", str(ctx.exception))

    def test_malformed_version_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            _rewrite_version(root, manifest, "pcbc 0.4\n", refresh_manifest=True)
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("exactly one", str(ctx.exception))

    def test_adapter_version_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary), version="0.4.41")
            with self.assertRaises(EvidenceError) as ctx:
                validate_registry_provenance(
                    {"capacitor": _generics_adapter()}, root, manifest
                )
            self.assertIn("not verified", str(ctx.exception))


class CapturedRegistryProvenanceTests(unittest.TestCase):
    def test_evidence_root_is_repository_owned(self) -> None:
        root = evidence_root()
        self.assertTrue(root.is_absolute())
        self.assertIn("tests", root.parts)
        self.assertIn("evidence", root.parts)

    def test_captured_registry_validates_against_bundle(self) -> None:
        validate_captured_registry()

    def test_every_adapter_evidence_hashes_match_bundle(self) -> None:
        registry = captured_adapter_registry()
        entries = load_evidence_manifest(evidence_root() / "manifest.sha256")
        for adapter in registry.values():
            with self.subTest(kind=adapter.kind):
                validate_adapter_provenance(adapter, evidence_root(), entries)


class ProductionProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry_provenance()

    def tearDown(self) -> None:
        reset_registry_provenance()

    def test_lazy_validation_success(self) -> None:
        from pcb_agent.state import load_project

        project = load_project(Path("fixtures/production-expression"))
        source = render_connectivity_testbench(project, "0.4.40")
        self.assertIn("PcbAgentConnectivity", source)
        ensure_registry_provenance()

    def test_missing_evidence_bundle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(EvidenceError) as ctx:
                validate_captured_registry(root_override=Path(temporary))
            self.assertIn("manifest", str(ctx.exception))

    def test_incomplete_bundle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _, _ = _write_bundle(Path(temporary))
            with self.assertRaises(EvidenceError):
                validate_captured_registry(root_override=root)

    def test_failed_provenance_empties_registry(self) -> None:
        from unittest.mock import patch

        from pcb_agent.evidence import EvidenceError as EvidenceErrorCls

        with patch(
            "pcb_agent.generated_testbench._run_provenance_validation",
            side_effect=EvidenceErrorCls("evidence root missing"),
        ):
            with self.assertRaises(GeneratorError) as ctx:
                ensure_registry_provenance()
            self.assertIn("provenance invalid", str(ctx.exception))
        self.assertEqual(known_kinds(), frozenset())

    def test_generated_render_is_blocked_after_provenance_failure(self) -> None:
        from unittest.mock import patch

        from pcb_agent.evidence import EvidenceError as EvidenceErrorCls
        from pcb_agent.state import load_project

        project = load_project(Path("fixtures/production-expression"))
        with patch(
            "pcb_agent.generated_testbench._run_provenance_validation",
            side_effect=EvidenceErrorCls("evidence root missing"),
        ):
            with self.assertRaises(GeneratorError):
                render_connectivity_testbench(project, "0.4.40")
            with self.assertRaises(GeneratorError):
                render_specification_testbench(project, "0.4.40")

    def test_doctor_works_while_generated_registry_blocked(self) -> None:
        from unittest.mock import patch

        from pcb_agent import cli
        from pcb_agent.evidence import EvidenceError as EvidenceErrorCls
        from pcb_agent.state import load_project

        project = load_project(Path("fixtures/valid-blinky"))
        with patch(
            "pcb_agent.generated_testbench._run_provenance_validation",
            side_effect=EvidenceErrorCls("evidence root missing"),
        ):
            with self.assertRaises(GeneratorError):
                ensure_registry_provenance()
            checks = cli._doctor(project, "schematic")
        self.assertIsInstance(checks, list)
        self.assertTrue(checks)


class ProductionExpressionEvidenceTests(unittest.TestCase):
    def test_renderer_output_matches_retained_generated_source(self) -> None:
        """The exact production package expression was executed on real Diode.

        `render_specification_testbench` must keep producing the byte-exact
        source that passed against pcbc 0.4.40, whose result is retained under
        `tests/evidence/diode-0.4.40/production-expression/`.
        """
        from pathlib import Path

        from pcb_agent.state import load_project

        project = load_project(Path("fixtures/production-expression"))
        source = render_specification_testbench(project, "0.4.40")
        retained = (
            evidence_root() / "production-expression" / "production-specification-testbench.generated.zen"
        ).read_bytes()
        self.assertEqual(source.encode("utf-8"), retained)

    def test_retained_generated_source_contains_production_package_expression(self) -> None:
        source = (
            evidence_root() / "production-expression" / "production-specification-testbench.generated.zen"
        ).read_text(encoding="utf-8")
        self.assertIn("components[\"R1.R\"].properties['package'].value == \"0402\"", source)
        self.assertIn("components[\"D3.D\"].properties['package'].value == \"DO-219AB\"", source)

    def test_retained_production_result_passes(self) -> None:
        result = json.loads(
            (evidence_root() / "production-expression" / "production-specification-result.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["results"][0]["test_bench_name"], "PcbAgentSpecification")


if __name__ == "__main__":
    unittest.main()
