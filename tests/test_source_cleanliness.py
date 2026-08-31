"""Tests for per-run source cleanliness measurement."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from pcb_agent.source_cleanliness import (
    SourceCleanlinessError,
    measure_source_cleanliness,
)


def _run(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr


def _make_repo() -> Path:
    tmp = Path(tempfile.mkdtemp())
    _run(tmp, "init", "-q")
    _run(tmp, "config", "user.name", "test")
    _run(tmp, "config", "user.email", "test@example.com")
    (tmp / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    (tmp / "evidence").mkdir()
    _run(tmp, "add", "tracked.py")
    _run(tmp, "commit", "-q", "-m", "init")
    return tmp


def _decode(record: dict, key: str) -> str:
    return bytes.fromhex(record[key]).decode("utf-8", "replace")


class MeasureSourceCleanlinessTests(unittest.TestCase):
    def test_clean_tree_is_clean(self) -> None:
        repo = _make_repo()
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertTrue(record["source_clean"])
        self.assertEqual(_decode(record, "filtered_source_status"), "")
        self.assertRegex(record["repo_revision"], r"^[0-9a-f]{40}$")

    def test_untracked_file_outside_evidence_dirties(self) -> None:
        repo = _make_repo()
        (repo / "new.py").write_text("y = 2\n", encoding="utf-8")
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertFalse(record["source_clean"])
        self.assertIn("new.py", _decode(record, "filtered_source_status"))

    def test_staged_change_dirties(self) -> None:
        repo = _make_repo()
        (repo / "tracked.py").write_text("x = 2\n", encoding="utf-8")
        _run(repo, "add", "tracked.py")
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertFalse(record["source_clean"])
        self.assertNotEqual(
            record["staged_diff_sha256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_unstaged_change_dirties(self) -> None:
        repo = _make_repo()
        (repo / "tracked.py").write_text("x = 3\n", encoding="utf-8")
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertFalse(record["source_clean"])
        self.assertNotEqual(
            record["unstaged_diff_sha256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_rename_dirties(self) -> None:
        repo = _make_repo()
        _run(repo, "mv", "tracked.py", "renamed.py")
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertFalse(record["source_clean"])

    def test_evidence_only_change_stays_clean(self) -> None:
        repo = _make_repo()
        (repo / "evidence" / "artifact.json").write_text("{}", encoding="utf-8")
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertTrue(record["source_clean"])
        self.assertEqual(_decode(record, "filtered_source_status"), "")
        self.assertIn("artifact.json", _decode(record, "raw_status"))

    def test_path_with_spaces_dirties(self) -> None:
        repo = _make_repo()
        (repo / "a b.py").write_text("z = 9\n", encoding="utf-8")
        record = measure_source_cleanliness(repo, repo / "evidence")
        self.assertFalse(record["source_clean"])
        self.assertIn("a b.py", _decode(record, "filtered_source_status"))

    def test_git_failure_aborts(self) -> None:
        repo = _make_repo()
        _run(repo, "mv", "tracked.py", "gone.py")
        _run(repo, "rm", "--cached", "gone.py")
        nonexistent = repo / "no-such"
        with self.assertRaises(SourceCleanlinessError):
            measure_source_cleanliness(nonexistent, repo / "evidence")

    def test_revision_drift_is_detected_via_revision_field(self) -> None:
        repo = _make_repo()
        first = measure_source_cleanliness(repo, repo / "evidence")["repo_revision"]
        (repo / "tracked.py").write_text("x = 4\n", encoding="utf-8")
        _run(repo, "add", "tracked.py")
        _run(repo, "commit", "-q", "-m", "second")
        second = measure_source_cleanliness(repo, repo / "evidence")["repo_revision"]
        self.assertNotEqual(first, second)

    def test_baseline_revision_drift_aborts(self) -> None:
        repo = _make_repo()
        first = measure_source_cleanliness(repo, repo / "evidence")["repo_revision"]
        (repo / "tracked.py").write_text("x = 5\n", encoding="utf-8")
        _run(repo, "add", "tracked.py")
        _run(repo, "commit", "-q", "-m", "third")
        with self.assertRaises(SourceCleanlinessError) as ctx:
            measure_source_cleanliness(repo, repo / "evidence", baseline_revision=first)
        self.assertIn("revision drift", str(ctx.exception))


class EvidenceExclusionTests(unittest.TestCase):
    def test_evidence_root_outside_repo_raises_source_cleanliness_error(self) -> None:
        repo = _make_repo()
        outside = Path(tempfile.mkdtemp())
        with self.assertRaises(SourceCleanlinessError) as ctx:
            measure_source_cleanliness(repo, outside)
        self.assertIn("strictly inside", str(ctx.exception))

    def test_missing_evidence_root_raises_source_cleanliness_error(self) -> None:
        repo = _make_repo()
        with self.assertRaises(SourceCleanlinessError) as ctx:
            measure_source_cleanliness(repo, repo / "no-such-evidence")
        self.assertIn("cannot resolve", str(ctx.exception))

    def test_repo_root_as_evidence_root_rejected(self) -> None:
        repo = _make_repo()
        with self.assertRaises(SourceCleanlinessError) as ctx:
            measure_source_cleanliness(repo, repo)
        self.assertIn("strictly inside", str(ctx.exception))

    def test_dot_segments_canonicalize_to_same_exclusion(self) -> None:
        repo = _make_repo()
        record = measure_source_cleanliness(repo, repo / "evidence" / ".." / "evidence")
        self.assertTrue(record["source_clean"])
        self.assertEqual(record["exclusion"], "evidence/**")


if __name__ == "__main__":
    unittest.main()