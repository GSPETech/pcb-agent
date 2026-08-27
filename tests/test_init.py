"""Tests for the `init` command."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pcb_agent.cli import main
from pcb_agent.state import load_project


class InitTests(unittest.TestCase):
    def _run_main(self, *argv: str) -> tuple[int, str]:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(list(argv))
        return code, stderr.getvalue()

    def test_init_creates_template_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self._run_main("init", "demo-board", "--into", tmp)
            self.assertEqual(code, 0, msg=err)
            target = Path(tmp) / "demo-board"
            self.assertTrue(target.is_dir())
            for relative in (
                "src/board.zen", "tests/board_test.zen", "SPEC.json",
                "ACCEPTANCE.json", "expected-connectivity.json",
                "project.toml", "pcb.toml",
            ):
                self.assertTrue((target / relative).exists(), msg=relative)

    def test_init_loads_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run_main("init", "loadable", "--into", tmp)
            self.assertEqual(code, 0)
            project = load_project(Path(tmp) / "loadable")
            self.assertEqual(project.name, "loadable")

    def test_init_replaces_template_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run_main("init", "abc-1", "--into", tmp)
            spec = json.loads((Path(tmp) / "abc-1" / "SPEC.json").read_text())
            self.assertEqual(spec["project"]["name"], "abc-1")
            zen = (Path(tmp) / "abc-1" / "src" / "board.zen").read_text()
            self.assertIn("Board(name=\"abc_1\"", zen)
            self.assertNotIn("template-board", zen)
            self.assertNotIn("template_board", zen)

    def test_init_rejects_invalid_name(self) -> None:
        for bad in ("../evil", "A_B", "abc/def", "a;b"):
            with self.subTest(name=bad), tempfile.TemporaryDirectory() as tmp:
                code, _ = self._run_main("init", bad, "--into", tmp)
                self.assertEqual(code, 3)
                self.assertFalse((Path(tmp) / bad).exists())

    def test_init_rejects_non_empty_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "taken"
            target.mkdir()
            (target / "leftover.txt").write_text("x", encoding="utf-8")
            code, _ = self._run_main("init", "taken", "--into", tmp)
            self.assertNotEqual(code, 0)
            self.assertTrue((target / "leftover.txt").exists())

    def test_init_json_output_contains_safety_fields(self) -> None:
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            original_stdout = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                code = main(["init", "json-test", "--into", tmp, "--format", "json"])
            finally:
                sys.stdout = original_stdout
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["production_ready"], False)
            self.assertEqual(payload["fabrication_approved"], False)


if __name__ == "__main__":
    unittest.main()