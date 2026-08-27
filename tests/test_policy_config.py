"""Tests for the locked policy configuration loader."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from pcb_agent.policy_config import Policy, PolicyConfigError


SAMPLE = textwrap.dedent("""
    contract_version = 1
    max_iterations = 5
    network = "deny"
    production_ready = false
    fabrication_approved = false

    [workspace]
    allow_symlinks = false
    allow_path_escape = false
    max_changed_files = 20

    [files]
    allow = ["src/**/*.zen", "layout/**/*.kicad_pcb"]
    deny = ["SPEC.json", "ACCEPTANCE.json", "expected-connectivity.json"]
""").strip() + "\n"


def write_toml(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


class LoadTests(unittest.TestCase):
    def test_load_real_policy(self) -> None:
        config = Path(__file__).resolve().parent.parent / "config" / "policies.toml"
        policy = Policy.load(config)
        self.assertEqual(policy.max_iterations, 5)
        self.assertEqual(policy.max_changed_files, 20)
        self.assertFalse(policy.allow_symlinks)
        self.assertFalse(policy.allow_path_escape)
        self.assertEqual(policy.network, "deny")

    def test_normalize_validates_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE)
            policy = Policy.load(path)
        self.assertIn("src/**/*.zen", policy.allow_files)

    def test_invalid_max_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace("max_iterations = 5", "max_iterations = 6"))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_allow_symlinks_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace("allow_symlinks = false", "allow_symlinks = true"))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_allow_path_escape_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace("allow_path_escape = false", "allow_path_escape = true"))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_network_allow_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace('network = "deny"', 'network = "allow"'))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_production_ready_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace("production_ready = false", "production_ready = true"))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_fabrication_approved_true_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace("fabrication_approved = false", "fabrication_approved = true"))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_files_allow_missing_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE.replace('allow = ["src/**/*.zen", "layout/**/*.kicad_pcb"]\n', ''))
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_invalid_toml_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, "this is = = not valid toml")
            with self.assertRaises(PolicyConfigError):
                Policy.load(path)

    def test_nested_path_match_via_policy(self) -> None:
        from pcb_agent.policy_config import matches

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.toml"
            write_toml(path, SAMPLE)
            policy = Policy.load(path)

        self.assertTrue(any(matches("src/blinky.zen", p) for p in policy.allow_files))
        self.assertTrue(any(matches("src/a/blinky.zen", p) for p in policy.allow_files))
        self.assertTrue(any(matches("src/a/b/blinky.zen", p) for p in policy.allow_files))
        self.assertTrue(any(matches("layout/foo.kicad_pcb", p) for p in policy.allow_files))
        self.assertTrue(any(matches("layout/a/b.kicad_pcb", p) for p in policy.allow_files))

        self.assertFalse(any(matches("SPEC.json", p) for p in policy.allow_files))
        self.assertFalse(any(matches("srcx/a.zen", p) for p in policy.allow_files))
        self.assertFalse(any(matches("source/a.zen", p) for p in policy.allow_files))
        self.assertFalse(any(matches("testsx/a.py", p) for p in policy.allow_files))
        self.assertFalse(any(matches("reports/rawx/data.json", p) for p in policy.allow_files))
        
        self.assertFalse(any(matches("../src/a.zen", p) for p in policy.allow_files))
        self.assertFalse(any(matches("src/../a.zen", p) for p in policy.allow_files))
        self.assertFalse(any(matches("/src/a.zen", p) for p in policy.allow_files))


if __name__ == "__main__":
    unittest.main()