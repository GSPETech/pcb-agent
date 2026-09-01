"""Deterministic placement and outline generation."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pcb_agent.layout import (
    LayoutError,
    compute_placement,
    place_and_outline,
    read_footprints,
    strip_edge_cuts,
)

_BOARD = """(kicad_pcb
\t(version 20260206)
\t(generator "pcbnew")
\t(footprint "lib:R_0402"
\t\t(layer "F.Cu")
\t\t(at 0 0)
\t\t(property "Path" "AAA.R1.R"
\t\t\t(at 0 0 0)
\t\t)
\t\t(property "Reference" "R1"
\t\t\t(at 0 0 0)
\t\t)
\t\t(pad "1" smd roundrect
\t\t\t(at -0.5 0)
\t\t\t(size 0.6 0.7)
\t\t)
\t\t(pad "2" smd roundrect
\t\t\t(at 0.5 0)
\t\t\t(size 0.6 0.7)
\t\t)
\t)
\t(footprint "lib:C_0603"
\t\t(layer "F.Cu")
\t\t(at 0 0)
\t\t(property "Path" "AAA.C1.C"
\t\t\t(at 0 0 0)
\t\t)
\t\t(property "Reference" "C1"
\t\t\t(at 0 0 0)
\t\t)
\t\t(pad "1" smd roundrect
\t\t\t(at -0.8 0)
\t\t\t(size 0.9 1.0)
\t\t)
\t\t(pad "2" smd roundrect
\t\t\t(at 0.8 0)
\t\t\t(size 0.9 1.0)
\t\t)
\t)
)
"""

_BOARD_WITH_OUTLINE = _BOARD.rstrip()[:-1] + """\t(gr_line
\t\t(start 0 0)
\t\t(end 10 0)
\t\t(layer "Edge.Cuts")
\t)
\t(gr_line
\t\t(start 0 0)
\t\t(end 0 10)
\t\t(layer "F.SilkS")
\t)
)
"""


class ReadFootprints(unittest.TestCase):
    def test_reads_reference_module_and_extent(self) -> None:
        footprints = read_footprints(_BOARD)
        self.assertEqual([f.reference for f in footprints], ["R1", "C1"])
        self.assertEqual([f.module for f in footprints], ["AAA", "AAA"])
        # Pad span plus pad size: 0.5 + 0.3 either side.
        self.assertAlmostEqual(footprints[0].width, 1.6, places=3)
        self.assertAlmostEqual(footprints[0].height, 0.7, places=3)

    def test_top_level_footprint_has_no_module(self) -> None:
        board = _BOARD.replace('(property "Path" "AAA.R1.R"',
                               '(property "Path" "R1.R"', 1)
        footprints = read_footprints(board)
        self.assertEqual(footprints[0].module, "")

    def test_footprint_without_pads_gets_nonzero_extent(self) -> None:
        board = _BOARD.replace('(pad "1" smd roundrect', '(fp_text user "x"', 1)
        footprints = read_footprints(board)
        self.assertTrue(all(f.width > 0 and f.height > 0 for f in footprints))


class ComputePlacement(unittest.TestCase):
    def test_is_deterministic(self) -> None:
        footprints = read_footprints(_BOARD)
        first = compute_placement(footprints)
        second = compute_placement(footprints)
        self.assertEqual(first, second)

    def test_places_every_footprint_without_overlap(self) -> None:
        footprints = read_footprints(_BOARD)
        placement = compute_placement(footprints)
        self.assertEqual(set(placement), {"R1", "C1"})

        by_ref = {f.reference: f for f in footprints}
        refs = sorted(placement)
        for index, left in enumerate(refs):
            for right in refs[index + 1:]:
                lf, rf = by_ref[left], by_ref[right]
                lx = placement[left][0] + lf.offset_x
                ly = placement[left][1] + lf.offset_y
                rx = placement[right][0] + rf.offset_x
                ry = placement[right][1] + rf.offset_y
                gap_x = abs(lx - rx) - (lf.width + rf.width) / 2.0
                gap_y = abs(ly - ry) - (lf.height + rf.height) / 2.0
                self.assertTrue(gap_x >= 0 or gap_y >= 0,
                                f"{left} and {right} overlap")

    def test_pad_offset_is_measured(self) -> None:
        # Both pads sit right of the origin, so the pad box centre is offset.
        board = _BOARD.replace("(at -0.5 0)", "(at 1.0 0)", 1).replace("(at 0.5 0)", "(at 2.0 0)", 1)
        footprints = read_footprints(board)
        self.assertAlmostEqual(footprints[0].offset_x, 1.5, places=3)

    def test_rotated_footprint_transposes_extent(self) -> None:
        board = _BOARD.replace("(at 0 0)\n\t\t(property \"Path\" \"AAA.R1.R\"",
                               "(at 0 0 90)\n\t\t(property \"Path\" \"AAA.R1.R\"", 1)
        footprints = read_footprints(board)
        self.assertAlmostEqual(footprints[0].width, 0.7, places=3)
        self.assertAlmostEqual(footprints[0].height, 1.6, places=3)

    def test_empty_board_is_rejected(self) -> None:
        with self.assertRaises(LayoutError):
            compute_placement([])


class StripEdgeCuts(unittest.TestCase):
    def test_removes_only_edge_cuts_graphics(self) -> None:
        stripped = strip_edge_cuts(_BOARD_WITH_OUTLINE)
        self.assertNotIn('(layer "Edge.Cuts")', stripped)
        self.assertIn('(layer "F.SilkS")', stripped)


class PlaceAndOutline(unittest.TestCase):
    def test_writes_outline_and_reports_dimensions(self) -> None:
        with TemporaryDirectory() as temporary:
            board = Path(temporary) / "board.kicad_pcb"
            board.write_text(_BOARD, encoding="utf-8")
            outcome = place_and_outline(board)

            self.assertEqual(outcome.placed, 2)
            self.assertGreater(outcome.width_mm, 0)
            self.assertGreater(outcome.height_mm, 0)

            text = board.read_text(encoding="utf-8")
            self.assertEqual(text.count('(layer "Edge.Cuts")'), 4)
            self.assertNotIn('(at 0 0)\n\t\t(property "Path"', text)

    def test_is_idempotent(self) -> None:
        with TemporaryDirectory() as temporary:
            board = Path(temporary) / "board.kicad_pcb"
            board.write_text(_BOARD, encoding="utf-8")

            first = place_and_outline(board)
            after_first = board.read_text(encoding="utf-8")
            second = place_and_outline(board)
            after_second = board.read_text(encoding="utf-8")

            self.assertEqual(first, second)
            self.assertEqual(after_first, after_second)

    def test_board_without_footprints_is_blocked(self) -> None:
        with TemporaryDirectory() as temporary:
            board = Path(temporary) / "board.kicad_pcb"
            board.write_text("(kicad_pcb\n\t(version 20260206)\n)\n", encoding="utf-8")
            with self.assertRaises(LayoutError):
                place_and_outline(board)


if __name__ == "__main__":
    unittest.main()
