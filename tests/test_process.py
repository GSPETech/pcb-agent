from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from helpers import copy_python
from pcb_agent.paths import PathViolation
from pcb_agent.process import redact_secrets, run_process


class ProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace with spaces"
        self.tools = self.base / "tools with spaces"
        self.workspace.mkdir()
        self.tools.mkdir()
        self.python = copy_python(self.tools)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_python(self, code: str, *args: str, **kwargs: object):
        return run_process(
            self.workspace,
            [str(self.python), "-c", code, *args],
            trusted_executable_roots=(self.tools,),
            **kwargs,
        )

    def test_success_failure_and_paths_with_spaces(self) -> None:
        success = self.run_python("import sys; print(sys.argv[1])", "hello spaced world")
        failure = self.run_python("import sys; print('bad', file=sys.stderr); raise SystemExit(7)")
        self.assertEqual((success.returncode, success.stdout.strip()), (0, "hello spaced world"))
        self.assertEqual((failure.returncode, failure.stderr.strip()), (7, "bad"))

    def test_timeout_kills_process(self) -> None:
        result = self.run_python("import time; time.sleep(10)", timeout=0.1)
        self.assertTrue(result.timed_out)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_executable_is_reported(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run_process(self.workspace, ["missing-pcb-agent-executable"])

    def test_output_is_truncated_and_secrets_are_redacted(self) -> None:
        result = self.run_python(
            "print('TOKEN=topsecret ' + 'x' * 100)", output_limit=30
        )
        self.assertTrue(result.output_truncated)
        self.assertIn("[REDACTED]", result.stdout)
        self.assertNotIn("topsecret", result.stdout)
        self.assertIn("...[truncated", result.stdout)
        token = "ghp-abcdefghijklmnopqrstuvwxyz"
        self.assertEqual(redact_secrets(token), "[REDACTED]")

    def test_metacharacters_are_literal_arguments_not_executed(self) -> None:
        marker = self.workspace / "owned.txt"
        payload = f"; echo owned > {marker} & | $(touch owned.txt)"
        result = self.run_python("import sys; print(sys.argv[1])", payload)
        self.assertEqual(result.stdout.strip(), payload)
        self.assertFalse(marker.exists())

    def test_cwd_traversal_and_workspace_executable_are_rejected(self) -> None:
        with self.assertRaises(PathViolation):
            self.run_python("print('no')", cwd="..")
        local = copy_python(self.workspace, "local")
        with self.assertRaises(PathViolation):
            run_process(self.workspace, [str(local), "-c", "print('no')"])

    def test_argv_and_output_secrets_are_redacted(self) -> None:
        secret = "API_KEY=supersecret"
        result = self.run_python("import sys; print(sys.argv[1])", secret)
        self.assertEqual(result.argv[-1], "API_KEY=[REDACTED]")
        self.assertEqual(result.stdout.strip(), "API_KEY=[REDACTED]")


if __name__ == "__main__":
    unittest.main()
