from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from helpers import copy_python
from pcb_agent.paths import PathViolation, require_regular_file, resolve_workspace_path, validate_executable


class PathTests(unittest.TestCase):
    def test_workspace_path_accepts_inside_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            inside = root / "file.txt"
            inside.write_text("ok", encoding="utf-8")
            self.assertEqual(resolve_workspace_path(root, "file.txt", must_exist=True), inside.resolve())
            with self.assertRaises(PathViolation):
                resolve_workspace_path(root, "../escape.txt")
            with self.assertRaises(PathViolation):
                resolve_workspace_path(root, ".")

    def test_symlink_escape_and_regular_file_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "workspace"
            root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            link = root / "link.txt"
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink unavailable: {error}")
            with self.assertRaises(PathViolation):
                resolve_workspace_path(root, link, must_exist=True)
            with self.assertRaises(PathViolation):
                require_regular_file(link)

    def test_executable_must_be_outside_workspace_and_in_trusted_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            trusted = base / "trusted"
            other = base / "other"
            workspace.mkdir()
            trusted.mkdir()
            other.mkdir()
            inside = copy_python(workspace, "inside")
            outside = copy_python(trusted, "outside")
            with self.assertRaises(PathViolation):
                validate_executable(str(inside), workspace=workspace)
            self.assertEqual(
                validate_executable(str(outside), workspace=workspace, trusted_roots=(trusted,)),
                outside.absolute(),
            )
            with self.assertRaises(PathViolation):
                validate_executable(str(outside), workspace=workspace, trusted_roots=(other,))

    def test_missing_executable_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                validate_executable("certainly-not-a-real-pcb-agent-tool", workspace=temporary)


if __name__ == "__main__":
    unittest.main()
