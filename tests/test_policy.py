from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pcb_agent.policy import PolicyViolation, ProtectedHashes, WorkspaceSnapshot


class PolicyTests(unittest.TestCase):
    def test_protected_hash_detects_tamper_and_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            protected = root / "SPEC.json"
            protected.write_text("original", encoding="utf-8")
            hashes = ProtectedHashes.capture(root, ("SPEC.json",))
            protected.write_text("tampered", encoding="utf-8")
            with self.assertRaises(PolicyViolation):
                hashes.verify()
            protected.unlink()
            with self.assertRaises(PolicyViolation):
                hashes.verify()

    def test_restore_reverts_only_sealed_backend_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changed = root / "changed.zen"
            untouched = root / "untouched.zen"
            created = root / "created.zen"
            changed.write_text("before", encoding="utf-8")
            untouched.write_text("keep", encoding="utf-8")
            snapshot = WorkspaceSnapshot.capture_before(root, ("changed.zen", "untouched.zen", "created.zen"))
            changed.write_text("backend", encoding="utf-8")
            created.write_text("backend-created", encoding="utf-8")
            sealed = snapshot.seal_backend_changes()
            self.assertEqual(sealed.changed_paths, ("changed.zen", "created.zen"))
            self.assertEqual(sealed.restore_backend_changes(), ("changed.zen", "created.zen"))
            self.assertEqual(changed.read_text(encoding="utf-8"), "before")
            self.assertEqual(untouched.read_text(encoding="utf-8"), "keep")
            self.assertFalse(created.exists())

    def test_restore_refuses_to_overwrite_post_backend_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "board.zen"
            path.write_text("before", encoding="utf-8")
            snapshot = WorkspaceSnapshot.capture_before(root, ("board.zen",))
            path.write_text("backend", encoding="utf-8")
            sealed = snapshot.seal_backend_changes()
            path.write_text("human", encoding="utf-8")
            with self.assertRaisesRegex(PolicyViolation, "post-backend"):
                sealed.restore_backend_changes()
            self.assertEqual(path.read_text(encoding="utf-8"), "human")

    def test_symlink_protected_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("data", encoding="utf-8")
            link = root / "SPEC.json"
            try:
                link.symlink_to(target)
            except OSError as error:
                self.skipTest(f"symlink unavailable: {error}")
            with self.assertRaises(PolicyViolation):
                ProtectedHashes.capture(root, ("SPEC.json",))


if __name__ == "__main__":
    unittest.main()
