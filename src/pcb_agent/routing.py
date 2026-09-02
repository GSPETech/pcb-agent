"""Freerouting autorouter adapter.

`pcb layout` produces an unrouted board. Routing is what makes the board
manufacturable, so it belongs inside the harness gate rather than in a manual
step whose result nobody attests.

Freerouting consumes Specctra DSN and emits a session (SES). KiCad's CLI has no
DSN/SES converter, so the pcbnew Python API performs both conversions. Every
external step is capability-probed first and its evidence retained, matching how
the Diode and KiCad adapters behave.

Determinism was measured before making this a gate: two runs on byte-identical
DSN produced byte-identical SES (sha256 2e8667b7..., 310 wires, 37 vias), so the
verdict is reproducible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import Check, CheckStatus, Severity
from .process import ProcessResult, run_process
from .state import ProjectState, RunState


class RoutingError(ValueError):
    pass


# Freerouting stops improving long before this; the cap only bounds runtime.
_DEFAULT_PASSES = 10
_ROUTE_TIMEOUT_SECONDS = 3600
_CONVERT_TIMEOUT_SECONDS = 600
# KiCad does not export its copper-to-edge clearance into DSN (freerouting #558),
# so it must be supplied explicitly or traces are cut into the board edge.
_COPPER_TO_EDGE_UM = 500

_EXPORT_SCRIPT = '''
import sys
import pcbnew

board = pcbnew.LoadBoard(sys.argv[1])
box = board.GetBoardEdgesBoundingBox()
if box.GetWidth() == 0 or box.GetHeight() == 0:
    sys.stderr.write("board has no outline\\n")
    raise SystemExit(2)
if not pcbnew.ExportSpecctraDSN(board, sys.argv[2]):
    sys.stderr.write("DSN export failed\\n")
    raise SystemExit(3)
sys.stdout.write("width_mm=%.3f height_mm=%.3f\\n"
                 % (pcbnew.ToMM(box.GetWidth()), pcbnew.ToMM(box.GetHeight())))
'''

_IMPORT_SCRIPT = '''
import sys
import pcbnew

def counts(board):
    tracks = vias = 0
    for item in board.GetTracks():
        if item.Type() == pcbnew.PCB_VIA_T:
            vias += 1
        else:
            tracks += 1
    return tracks, vias

board = pcbnew.LoadBoard(sys.argv[1])
before = counts(board)
if not pcbnew.ImportSpecctraSES(board, sys.argv[2]):
    sys.stderr.write("SES import failed\\n")
    raise SystemExit(3)
after = counts(board)
if after[0] <= before[0]:
    sys.stderr.write("SES import added no tracks\\n")
    raise SystemExit(4)
board.Save(sys.argv[1])
sys.stdout.write("tracks=%d vias=%d\\n" % after)
'''


@dataclass(frozen=True)
class RoutingResult:
    process: ProcessResult
    session_path: str
    session_sha256: str
    wires: int
    vias: int


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def probe(project: ProjectState) -> ProcessResult:
    """Capability probe for the router itself."""
    return run_process(project.root, ["freerouting", "--help"], timeout=60)


def probe_converter(project: ProjectState) -> ProcessResult:
    """Capability probe for the pcbnew Python bindings used for DSN/SES."""
    return run_process(
        project.root,
        ["python3", "-c", "import pcbnew; print(pcbnew.GetBuildVersion())"],
        timeout=60,
    )


def _run_python(project: ProjectState, script: str, *args: str, timeout: int) -> ProcessResult:
    return run_process(project.root, ["python3", "-c", script, *args], timeout=timeout)


def route(project: ProjectState, run: RunState, board: Path, *,
          passes: int = _DEFAULT_PASSES) -> RoutingResult:
    """Autoroute `board` in place and retain the routing evidence."""
    router = probe(project)
    if router.timed_out or router.returncode != 0:
        raise FileNotFoundError("freerouting capability probe failed")
    converter = probe_converter(project)
    if converter.timed_out or converter.returncode != 0:
        raise FileNotFoundError("pcbnew Python capability probe failed")

    dsn = run.raw_directory / "route.dsn"
    session = run.raw_directory / "route.ses"

    export = _run_python(project, _EXPORT_SCRIPT, str(board), str(dsn),
                         timeout=_CONVERT_TIMEOUT_SECONDS)
    if export.returncode != 0 or not dsn.is_file():
        raise RoutingError(f"DSN export failed: {export.stderr.strip()[:200]}")

    result = run_process(
        project.root,
        [
            "freerouting",
            "-de", str(dsn),
            "-do", str(session),
            "-mp", str(int(passes)),
            "-l", "en",
            f"--router.copperToEdgeClearanceUm={_COPPER_TO_EDGE_UM}",
        ],
        timeout=_ROUTE_TIMEOUT_SECONDS,
    )
    if result.timed_out:
        raise RoutingError("freerouting timed out")
    if not session.is_file() or session.is_symlink():
        raise RoutingError("freerouting produced no session file")

    text = session.read_text(encoding="utf-8", errors="replace")
    wires = text.count("(wire")
    vias = text.count("(via")
    if wires == 0:
        raise RoutingError("freerouting session contains no wires")

    imported = _run_python(project, _IMPORT_SCRIPT, str(board), str(session),
                           timeout=_CONVERT_TIMEOUT_SECONDS)
    if imported.returncode != 0:
        raise RoutingError(f"SES import failed: {imported.stderr.strip()[:200]}")

    return RoutingResult(
        process=result,
        session_path=session.name,
        session_sha256=_sha256(session),
        wires=wires,
        vias=vias,
    )


def result_check(outcome: RoutingResult) -> Check:
    """Routing reports PASS when the session was applied to the board.

    Whether the routed board is acceptable is decided by KiCad DRC, which runs
    as its own gate. Routing only attests that traces were produced and applied.
    """
    return Check(
        id="ROUTE",
        status=CheckStatus.PASS,
        severity=Severity.ERROR,
        message=f"routed {outcome.wires} wires and {outcome.vias} vias",
        command=tuple(outcome.process.argv),
        exit_code=outcome.process.returncode,
        duration=outcome.process.duration_seconds,
        evidence={"path": outcome.session_path, "sha256": outcome.session_sha256},
        provenance="tool",
        required=True,
    )
