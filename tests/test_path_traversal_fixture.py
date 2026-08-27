"""Tests that the path-traversal fixture is rejected by the contract loader."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from pcb_agent.cli import main
from pcb_agent.contracts import ContractError, load_project_contract


ROOT = Path(__file__).resolve().parent.parent


class PathTraversalFixtureTests(unittest.TestCase):
    def test_loader_rejects_fixture(self) -> None:
        fixture = ROOT / "fixtures" / "path-traversal"
        with self.assertRaises((ContractError, ValueError)):
            load_project_contract(fixture)

    def test_cli_doctor_exits_invalid_config(self) -> None:
        fixture = ROOT / "fixtures" / "path-traversal"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["doctor", "--project", str(fixture)])
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()