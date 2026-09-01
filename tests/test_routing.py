"""Freerouting adapter: probes, evidence, and failure classification."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pcb_agent import routing
from pcb_agent.models import CheckStatus
from pcb_agent.process import ProcessResult
from pcb_agent.state import ProjectState, RunState


def _ok(argv: list[str]) -> ProcessResult:
    return ProcessResult(tuple(argv), 0, "", "", 0.1, False, False, {})


def _fail(argv: list[str], code: int = 1, stderr: str = "boom") -> ProcessResult:
    return ProcessResult(tuple(argv), code, "", stderr, 0.1, False, False, {})


def _project(root: Path) -> ProjectState:
    return ProjectState(
        root=root, name="board", config={}, hashes={}, profile="layout",
        source="board.zen", test="tests/board_test.zen",
        board="layout/board.kicad_pcb",
        acceptance={"checks": []}, specification={}, connectivity={},
    )


class Probes(unittest.TestCase):
    def test_missing_router_is_not_a_pass(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = RunState("r", root / "reports" / "r", root / "reports" / "r" / "raw")
            run.raw_directory.mkdir(parents=True)
            with mock.patch.object(routing, "run_process",
                                   side_effect=lambda *a, **k: _fail(list(a[1]))):
                with self.assertRaises(FileNotFoundError):
                    routing.route(_project(root), run, root / "board.kicad_pcb")

    def test_missing_converter_is_not_a_pass(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = RunState("r", root / "reports" / "r", root / "reports" / "r" / "raw")
            run.raw_directory.mkdir(parents=True)

            def dispatch(_root, argv, **_kwargs):
                if argv[0] == "freerouting":
                    return _ok(list(argv))
                return _fail(list(argv))

            with mock.patch.object(routing, "run_process", side_effect=dispatch):
                with self.assertRaises(FileNotFoundError):
                    routing.route(_project(root), run, root / "board.kicad_pcb")


class SessionValidation(unittest.TestCase):
    def _route_with(self, dispatch, session_text: str | None):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = RunState("r", root / "reports" / "r", root / "reports" / "r" / "raw")
            run.raw_directory.mkdir(parents=True)
            if session_text is not None:
                (run.raw_directory / "route.ses").write_text(session_text, encoding="utf-8")
            with mock.patch.object(routing, "run_process", side_effect=dispatch):
                return routing.route(_project(root), run, root / "board.kicad_pcb")

    def test_absent_session_is_rejected(self) -> None:
        def dispatch(_root, argv, **_kwargs):
            if argv[0] == "python3" and "pcbnew" in argv[-1]:
                return _ok(list(argv))
            if argv[0] == "python3":
                # DSN export: create the file the caller expects.
                Path(argv[3]).write_text("(pcb)", encoding="utf-8")
                return _ok(list(argv))
            return _ok(list(argv))

        with self.assertRaises(routing.RoutingError):
            self._route_with(dispatch, None)

    def test_session_without_wires_is_rejected(self) -> None:
        def dispatch(_root, argv, **_kwargs):
            if argv[0] == "python3" and "pcbnew" in argv[-1]:
                return _ok(list(argv))
            if argv[0] == "python3":
                Path(argv[3]).write_text("(pcb)", encoding="utf-8")
                return _ok(list(argv))
            return _ok(list(argv))

        with self.assertRaises(routing.RoutingError):
            self._route_with(dispatch, "(session)\n")


class ResultCheck(unittest.TestCase):
    def test_reports_wire_and_via_counts_as_evidence(self) -> None:
        outcome = routing.RoutingResult(
            process=_ok(["freerouting", "-de", "x.dsn"]),
            session_path="route.ses",
            session_sha256="sha256:" + "0" * 64,
            wires=310,
            vias=37,
        )
        check = routing.result_check(outcome)
        self.assertEqual(check.id, "ROUTE")
        self.assertEqual(check.status, CheckStatus.PASS)
        self.assertTrue(check.required)
        self.assertIn("310", check.message)
        self.assertIn("37", check.message)
        self.assertEqual(check.evidence["path"], "route.ses")


if __name__ == "__main__":
    unittest.main()
