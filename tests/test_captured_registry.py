"""Tests for the production captured adapter registry and its provenance.

The production registry is built from captured Diode 0.4.40 evidence and is
repository-owned. These tests validate it WITHOUT replacing it with a stub:
exact kind set, per-adapter fields, crystal absence, and evidence bundle
provenance (manifest entry + file bytes + version record).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
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
    set_adapter_registry,
    validate_captured_registry,
)


EXPECTED_KINDS = frozenset({
    "resistor", "led", "capacitor", "inductor", "ferrite_bead",
    "thermistor", "zener", "rectifier", "tvs",
})

# Repo root resolved from this file so fixture paths never depend on the
# process working directory (pytest may be launched from anywhere).
ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


class CapturedRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        # These tests read the module-global active registry; restore the
        # captured snapshot so they never depend on a prior test's teardown.
        reset_registry_provenance()

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


class DigestSyntaxTests(unittest.TestCase):
    """The canonical sha256 digest syntax is defined once and shared.

    The captured-adapter validator (manifest entry + manifest digest agreement
    + rooted path + regular file + byte hash) and the per-run generated
    validator (rooted path + regular file + digest syntax + byte hash) remain
    separate functions with distinct trust contracts; only the syntax check is
    shared via ``evidence.is_sha256_digest``.
    """

    def test_malformed_captured_adapter_digest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            entries = load_evidence_manifest(manifest)
            adapter = dataclasses.replace(
                _generics_adapter(), evidence_sha256="sha256:" + "a" * 63
            )
            with self.assertRaises(EvidenceError) as ctx:
                validate_adapter_provenance(adapter, root, entries)
            self.assertIn("malformed", str(ctx.exception))

    def test_captured_adapter_byte_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, result, _ = _write_bundle(Path(temporary))
            result.write_bytes(b"tampered result bytes")
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_adapter_provenance(_generics_adapter(), root, entries)
            self.assertIn("hash mismatch", str(ctx.exception))

    def test_malformed_per_run_generated_digest_fails_closed(self) -> None:
        from pcb_agent import diode
        from pcb_agent.diode import GeneratedCompatibilityError

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "result.json").write_bytes(b'{"ok": true}')
            with self.assertRaises(GeneratedCompatibilityError) as ctx:
                diode._verify_retained_artifact(
                    root, "result.json", "sha256:" + "a" * 63
                )
            self.assertIn("malformed", str(ctx.exception))

    def test_per_run_generated_byte_hash_mismatch_fails_closed(self) -> None:
        from pcb_agent import diode
        from pcb_agent.diode import GeneratedCompatibilityError

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "result.json").write_bytes(b'{"ok": true}')
            with self.assertRaises(GeneratedCompatibilityError) as ctx:
                diode._verify_retained_artifact(
                    root, "result.json", "sha256:" + "b" * 64
                )
            self.assertIn("hash mismatch", str(ctx.exception))

    def test_uppercase_hex_digest_is_rejected(self) -> None:
        from pcb_agent.evidence import is_sha256_digest
        from pcb_agent.generated_testbench import build_adapter_registry

        canonical = "sha256:" + hashlib.sha256(b"x").hexdigest()
        self.assertTrue(is_sha256_digest(canonical))
        self.assertFalse(is_sha256_digest("sha256:" + "A" * 64))
        self.assertFalse(is_sha256_digest(canonical.upper()))
        self.assertFalse(is_sha256_digest("sha256:" + "a" * 63))
        self.assertFalse(is_sha256_digest("sha256:" + "a" * 65))
        self.assertFalse(is_sha256_digest(None))
        adapter = dataclasses.replace(
            _generics_adapter(), evidence_sha256="sha256:" + "A" * 64
        )
        with self.assertRaises(ValueError) as ctx:
            build_adapter_registry([adapter])
        self.assertIn("evidence_sha256", str(ctx.exception))


class RegistryValueValidationTests(unittest.TestCase):
    """Every registry value is validated; malformed entries fail closed.

    The former ``if not isinstance(adapter, object): continue`` branch was
    dead code (``isinstance(x, object)`` is always true) and would have
    silently skipped malformed entries. A non-adapter value must raise
    ``EvidenceError`` instead.
    """

    def _registry_root(self) -> tuple[Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        root, manifest, _, _ = _write_bundle(Path(temporary.name))
        self.addCleanup(temporary.cleanup)
        return root, manifest

    def test_none_registry_value_fails_closed(self) -> None:
        root, manifest = self._registry_root()
        with self.assertRaises(EvidenceError) as ctx:
            validate_registry_provenance({"resistor": None}, root, manifest)
        self.assertIn("kind", str(ctx.exception).lower())

    def test_string_registry_value_fails_closed(self) -> None:
        root, manifest = self._registry_root()
        with self.assertRaises(EvidenceError) as ctx:
            validate_registry_provenance(
                {"resistor": "not-an-adapter"}, root, manifest
            )
        self.assertIn("kind", str(ctx.exception).lower())

    def test_kindless_object_registry_value_fails_closed(self) -> None:
        root, manifest = self._registry_root()
        with self.assertRaises(EvidenceError) as ctx:
            validate_registry_provenance({"resistor": object()}, root, manifest)
        self.assertIn("kind", str(ctx.exception).lower())


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

    def test_missing_newline_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            _rewrite_version(root, manifest, "pcbc 0.4.40", refresh_manifest=True)
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("exactly one", str(ctx.exception))

    def test_invalid_utf8_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            version_path = root / "pcb-version.txt"
            version_path.write_bytes(b"pcbc 0.4.40\n\xff\xfe")
            entries = load_evidence_manifest(manifest)
            entries["pcb-version.txt"] = hashlib.sha256(version_path.read_bytes()).hexdigest()
            lines = [f"{digest}  ./{relative}\n" for relative, digest in sorted(entries.items())]
            manifest.write_text("".join(lines), encoding="utf-8")
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("UTF-8", str(ctx.exception))

    @unittest.skipUnless(os.name == "posix", "symlink creation requires privilege on Windows")
    def test_version_symlink_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            (root / "pcb-version.txt").unlink()
            target = root / "real-version.txt"
            target.write_text("pcbc 0.4.40\n", encoding="utf-8", newline="\n")
            (root / "pcb-version.txt").symlink_to(target)
            entries = load_evidence_manifest(manifest)
            with self.assertRaises(EvidenceError) as ctx:
                validate_version_record(root, entries)
            self.assertIn("symlink", str(ctx.exception))

    @unittest.skipUnless(os.name == "posix", "symlink creation requires privilege on Windows")
    def test_manifest_symlink_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest, _, _ = _write_bundle(Path(temporary))
            real = root / "real-manifest.sha256"
            manifest.rename(real)
            manifest.symlink_to(real)
            with self.assertRaises(EvidenceError) as ctx:
                load_evidence_manifest(manifest)
            self.assertIn("symlink", str(ctx.exception))

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


class ActiveRegistryProvenanceTests(unittest.TestCase):
    """The *active* (module-global) adapter registry is provenance-validated.

    `render_connectivity_testbench`/`render_specification_testbench` call
    `ensure_registry_provenance`, which validates the active `_ADAPTERS`
    snapshot against the repository-owned bundle. These tests prove that it is
    the active registry (not a throwaway captured copy) that is validated, that
    any tamper blocks rendering, that registry replacement invalidates cached
    verdicts, and that a failure fails closed and stays failed.
    """

    def setUp(self) -> None:
        reset_registry_provenance()

    def tearDown(self) -> None:
        reset_registry_provenance()

    def _render(self) -> str:
        from pcb_agent.state import load_project

        project = load_project(FIXTURES / "production-expression")
        return render_connectivity_testbench(project, "0.4.40")

    def _tampered_resistor(self, **overrides: object) -> ComponentAdapter:
        return dataclasses.replace(captured_adapter_registry()["resistor"], **overrides)

    def test_captured_active_registry_validates(self) -> None:
        ensure_registry_provenance()
        self.assertEqual(known_kinds(), EXPECTED_KINDS)
        self.assertIn("PcbAgentConnectivity", self._render())

    def test_modified_evidence_sha256_blocks_renderer(self) -> None:
        set_adapter_registry(
            {**captured_adapter_registry(),
             "resistor": self._tampered_resistor(evidence_sha256="sha256:" + "0" * 64)}
        )
        with self.assertRaises(GeneratorError) as ctx:
            self._render()
        self.assertIn("provenance invalid", str(ctx.exception))

    def test_modified_evidence_source_sha256_blocks_renderer(self) -> None:
        set_adapter_registry(
            {**captured_adapter_registry(),
             "resistor": self._tampered_resistor(evidence_source_sha256="sha256:" + "1" * 64)}
        )
        with self.assertRaises(GeneratorError) as ctx:
            self._render()
        self.assertIn("provenance invalid", str(ctx.exception))

    def test_unsupported_version_blocks_renderer(self) -> None:
        set_adapter_registry(
            {**captured_adapter_registry(),
             "resistor": self._tampered_resistor(verified_pcbc_versions=frozenset({"9.9.9"}))}
        )
        with self.assertRaises(GeneratorError) as ctx:
            self._render()
        self.assertIn("provenance invalid", str(ctx.exception))

    def test_registry_replacement_invalidates_cached_success(self) -> None:
        self._render()  # primes a successful cached verdict for the captured registry
        bad = self._tampered_resistor(evidence_sha256="sha256:" + "0" * 64)
        set_adapter_registry({**captured_adapter_registry(), "resistor": bad})
        with self.assertRaises(GeneratorError):
            self._render()

    def test_restoring_captured_registry_allows_rendering(self) -> None:
        bad = self._tampered_resistor(evidence_sha256="sha256:" + "0" * 64)
        set_adapter_registry({**captured_adapter_registry(), "resistor": bad})
        with self.assertRaises(GeneratorError):
            self._render()
        self.assertEqual(known_kinds(), frozenset())
        reset_registry_provenance()
        self.assertEqual(known_kinds(), EXPECTED_KINDS)
        self.assertIn("PcbAgentConnectivity", self._render())

    def test_failed_provenance_stays_fail_closed(self) -> None:
        bad = self._tampered_resistor(evidence_sha256="sha256:" + "0" * 64)
        set_adapter_registry({**captured_adapter_registry(), "resistor": bad})
        with self.assertRaises(GeneratorError):
            self._render()
        with self.assertRaises(GeneratorError):
            ensure_registry_provenance()
        with self.assertRaises(GeneratorError):
            self._render()
        self.assertEqual(known_kinds(), frozenset())

    def test_active_registry_snapshot_is_supplied_to_validator(self) -> None:
        from unittest.mock import patch

        marker = ComponentAdapter(
            kind="marker",
            instance_suffix="M",
            pins={"P1": "1"},
            verified_pcbc_versions=frozenset({"0.4.40"}),
            evidence_sha256="sha256:" + "a" * 64,
        )
        received: dict[str, object] = {}

        def fake_validate(registry, evidence_root, manifest_path):
            received.update(dict(registry))

        with patch(
            "pcb_agent.evidence.validate_registry_provenance",
            side_effect=fake_validate,
        ):
            set_adapter_registry({"marker": marker})
            ensure_registry_provenance()
        self.assertEqual(set(received), {"marker"})
        self.assertIs(received["marker"], marker)

    def test_end_to_end_renderer_regression(self) -> None:
        from pcb_agent.state import load_project

        project = load_project(FIXTURES / "production-expression")
        source = render_connectivity_testbench(project, "0.4.40")
        retained = (
            evidence_root()
            / "production-expression"
            / "production-connectivity-testbench.generated.zen"
        ).read_bytes()
        self.assertEqual(source.encode("utf-8"), retained)
        spec = render_specification_testbench(project, "0.4.40")
        retained_spec = (
            evidence_root()
            / "production-expression"
            / "production-specification-testbench.generated.zen"
        ).read_bytes()
        self.assertEqual(spec.encode("utf-8"), retained_spec)


class ProductionProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry_provenance()

    def tearDown(self) -> None:
        reset_registry_provenance()

    def test_lazy_validation_success(self) -> None:
        from pcb_agent.state import load_project

        project = load_project(FIXTURES / "production-expression")
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

        project = load_project(FIXTURES / "production-expression")
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

        project = load_project(FIXTURES / "valid-blinky")
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
    def test_connectivity_renderer_output_matches_retained_generated_source(self) -> None:
        """The exact production connectivity expression was executed on real Diode.

        `render_connectivity_testbench` must keep producing the byte-exact
        source that passed against pcbc 0.4.40, whose result is retained under
        `tests/evidence/diode-0.4.40/production-expression/`.
        """
        from pcb_agent.state import load_project

        project = load_project(FIXTURES / "production-expression")
        source = render_connectivity_testbench(project, "0.4.40")
        retained = (
            evidence_root() / "production-expression" / "production-connectivity-testbench.generated.zen"
        ).read_bytes()
        self.assertEqual(source.encode("utf-8"), retained)

    def test_retained_connectivity_generated_source_contains_production_expression(self) -> None:
        source = (
            evidence_root() / "production-expression" / "production-connectivity-testbench.generated.zen"
        ).read_text(encoding="utf-8")
        self.assertIn("\"R1.R\" in components", source)
        self.assertIn("\"D3.D\" in components", source)
        self.assertIn("PcbAgentConnectivity__contract.R1.R", source)
        self.assertIn("PcbAgentConnectivity", source)

    def test_retained_connectivity_result_passes(self) -> None:
        result = json.loads(
            (evidence_root() / "production-expression" / "production-connectivity-result.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["results"][0]["test_bench_name"], "PcbAgentConnectivity")
        self.assertEqual(result["results"][0]["status"], "pass")

    def test_production_generated_sources_and_results_appear_in_manifest(self) -> None:
        from pcb_agent.evidence import load_evidence_manifest

        manifest = load_evidence_manifest(evidence_root() / "manifest.sha256")
        for relative in (
            "production-expression/production-connectivity-testbench.generated.zen",
            "production-expression/production-connectivity-result.json",
            "production-expression/production-specification-testbench.generated.zen",
            "production-expression/production-specification-result.json",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, manifest)

    def test_specification_renderer_output_matches_retained_generated_source(self) -> None:
        """The exact production package expression was executed on real Diode.

        `render_specification_testbench` must keep producing the byte-exact
        source that passed against pcbc 0.4.40, whose result is retained under
        `tests/evidence/diode-0.4.40/production-expression/`.
        """
        from pathlib import Path

        from pcb_agent.state import load_project

        project = load_project(FIXTURES / "production-expression")
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
