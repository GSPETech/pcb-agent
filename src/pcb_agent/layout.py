"""Deterministic placement and board-outline generation.

`pcb layout` emits every footprint at the origin with no `Edge.Cuts` geometry,
which is not a routable board: pads overlap, and KiCad DRC reports
`invalid_outline`. This module gives the harness a reproducible starting board.

The placer is deliberately simple and deterministic: components are grouped by
their hierarchical module path, laid out on a grid sized from real footprint
extents, and modules are packed left to right. It produces a board with no
overlapping courtyards so routing is meaningful; it does not reason about signal
integrity, thermals, or mechanical constraints.

The outline is derived from the resulting placement, so it always encloses the
board and moves with it.

ponytail: grid block placement, not a force-directed or annealing placer. Upgrade
when routing quality rather than routability becomes the goal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class LayoutError(ValueError):
    pass


# Placement grid: gap between footprint courtyards, and margin from board edge.
# The component gap must exceed the board's clearance rule (0.2 mm at 4 layers)
# by enough that a router can also fit a trace between neighbours.
_COMPONENT_GAP_MM = 2.0
_MODULE_GAP_MM = 4.0
_EDGE_MARGIN_MM = 2.0
# Target aspect: modules wrap once the row exceeds this width.
_MAX_ROW_WIDTH_MM = 60.0
_EDGE_LINE_WIDTH_MM = 0.1

_FOOTPRINT_OPEN = "(footprint "
_PLACEMENT_RE = re.compile(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)")
_REFERENCE_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
# `pcb layout` records the Zener instance path, e.g. "POWER.U6.BQ25185DLHR".
# `(path ...)` holds KiCad UUIDs, which carry no grouping information.
_ZENER_PATH_RE = re.compile(r'\(property\s+"Path"\s+"([^"]+)"')
_PAD_AT_RE = re.compile(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)")
_SIZE_RE = re.compile(r"\(size\s+([\d.]+)\s+([\d.]+)\)")
_XY_RE = re.compile(r"\(xy\s+(-?[\d.]+)\s+(-?[\d.]+)\)")
_START_END_RE = re.compile(
    r"\((?:start|end|center|mid)\s+(-?[\d.]+)\s+(-?[\d.]+)\)"
)
_COURTYARD_LAYERS = ('"F.CrtYd"', '"B.CrtYd"')


def _sexp_end(text: str, start: int) -> int:
    """Index just past the balanced s-expression beginning at `start`."""
    depth = 0
    in_string = False
    pos = start
    while pos < len(text):
        char = text[pos]
        if in_string:
            if char == "\\":
                pos += 2
                continue
            if char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    raise LayoutError("unbalanced s-expression in board file")


@dataclass(frozen=True)
class Footprint:
    reference: str
    module: str
    start: int
    end: int
    width: float
    height: float
    # Pad-box centre relative to the footprint origin. Pads are rarely centred
    # on the origin, so placing the origin at a cell centre would put the copper
    # somewhere else and let neighbours collide.
    offset_x: float
    offset_y: float
    rotation: float


def _pad_extent(block: str) -> tuple[float, float, float, float]:
    """Footprint width, height and pad-box centre offset, in mm.

    Derived from pad geometry: pad positions are footprint-local, so the extent
    is the pad bounding box grown by each pad's own size. Courtyard graphics are
    not consulted because they are optional and inconsistently present in
    imported footprints.
    """
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    cursor = 0
    while True:
        index = block.find("(pad ", cursor)
        if index == -1:
            break
        pad_end = _sexp_end(block, index)
        pad = block[index:pad_end]
        cursor = pad_end

        at = _PAD_AT_RE.search(pad)
        size = _SIZE_RE.search(pad)
        if at is None:
            continue
        x, y = float(at.group(1)), float(at.group(2))
        half_w = float(size.group(1)) / 2.0 if size else 0.0
        half_h = float(size.group(2)) / 2.0 if size else 0.0
        min_x = min(min_x, x - half_w)
        max_x = max(max_x, x + half_w)
        min_y = min(min_y, y - half_h)
        max_y = max(max_y, y + half_h)

    if min_x == float("inf"):
        # No pads: a graphic-only footprint such as a logo or fiducial.
        return 1.0, 1.0, 0.0, 0.0
    return (
        max(max_x - min_x, 0.1),
        max(max_y - min_y, 0.1),
        (min_x + max_x) / 2.0,
        (min_y + max_y) / 2.0,
    )


def _courtyard_extent(block: str) -> tuple[float, float, float, float] | None:
    """Bounding box of the footprint courtyard, if it declares one.

    KiCad DRC reports `courtyards_overlap` against this geometry rather than
    against pads, so honouring it is what stops the placer producing overlap
    errors. Returns None when the footprint has no courtyard graphics.
    """
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    found = False

    for keyword in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
        marker = "(%s" % keyword
        cursor = 0
        while True:
            index = block.find(marker, cursor)
            if index == -1:
                break
            end = _sexp_end(block, index)
            graphic = block[index:end]
            cursor = end
            if not any(layer in graphic for layer in _COURTYARD_LAYERS):
                continue
            points = [(float(x), float(y)) for x, y in _XY_RE.findall(graphic)]
            points += [(float(x), float(y)) for x, y in _START_END_RE.findall(graphic)]
            for x, y in points:
                found = True
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)

    if not found:
        return None
    return (
        max(max_x - min_x, 0.1),
        max(max_y - min_y, 0.1),
        (min_x + max_x) / 2.0,
        (min_y + max_y) / 2.0,
    )


def _footprint_extent(block: str) -> tuple[float, float, float, float]:
    """Extent used for placement: courtyard when declared, otherwise pads."""
    courtyard = _courtyard_extent(block)
    return courtyard if courtyard is not None else _pad_extent(block)


def _module_of(block: str) -> str:
    """Hierarchical module a footprint belongs to, or "" at the top level.

    Grouping comes from the Zener instance path ("POWER.U6.BQ25185DLHR" ->
    "POWER"). KiCad's own `(path ...)` holds UUIDs, so using it would put every
    footprint in a module of its own and defeat the grouping.
    """
    match = _ZENER_PATH_RE.search(block)
    if match and match.group(1):
        segments = [s for s in match.group(1).split(".") if s]
        if len(segments) > 2:
            return segments[0]
    return ""


def read_footprints(text: str) -> list[Footprint]:
    found: list[Footprint] = []
    cursor = 0
    while True:
        start = text.find(_FOOTPRINT_OPEN, cursor)
        if start == -1:
            return found
        end = _sexp_end(text, start)
        block = text[start:end]
        cursor = end

        reference = _REFERENCE_RE.search(block)
        if reference is None:
            continue
        width, height, offset_x, offset_y = _footprint_extent(block)
        placement = _PLACEMENT_RE.search(block)
        rotation = float(placement.group(3)) if placement and placement.group(3) else 0.0
        # A footprint rotated by an odd multiple of 90 degrees occupies a
        # transposed bounding box on the board.
        if int(round(rotation)) % 180 == 90:
            width, height = height, width
            offset_x, offset_y = offset_y, offset_x
        found.append(Footprint(
            reference=reference.group(1),
            module=_module_of(block),
            start=start,
            end=end,
            width=width,
            height=height,
            offset_x=offset_x,
            offset_y=offset_y,
            rotation=rotation,
        ))


def _sort_key(footprint: Footprint) -> tuple[str, str, int, str]:
    """Stable ordering: module, then designator prefix, then numeric index."""
    match = re.match(r"^([A-Za-z]+)(\d*)", footprint.reference)
    prefix = match.group(1) if match else footprint.reference
    number = int(match.group(2)) if match and match.group(2) else 0
    return (footprint.module, prefix, number, footprint.reference)


def compute_placement(footprints: list[Footprint]) -> dict[str, tuple[float, float]]:
    """Reference -> (x, y) in mm, grouped by module and packed into rows.

    Each component gets its own cell sized from its own extent, so a large
    module does not overlap the small passives beside it. Rows are packed
    greedily and wrap at `_MAX_ROW_WIDTH_MM`.
    """
    if not footprints:
        raise LayoutError("board contains no footprints to place")

    ordered = sorted(footprints, key=_sort_key)
    modules: dict[str, list[Footprint]] = {}
    for footprint in ordered:
        modules.setdefault(footprint.module, []).append(footprint)

    placement: dict[str, tuple[float, float]] = {}
    row_x = _EDGE_MARGIN_MM
    row_y = _EDGE_MARGIN_MM
    row_height = 0.0

    for module in sorted(modules):
        members = modules[module]

        # Lay the module out in its own rows, advancing by each part's real
        # width. A uniform cell would either waste space or overlap, because
        # extents in one module span 0.6 mm passives and 14 mm modules.
        columns = max(1, int(len(members) ** 0.5 + 0.999))
        block_x = row_x
        block_y = row_y
        cursor_x = block_x
        cursor_y = block_y
        line_height = 0.0
        placed_in_line = 0
        block_right = block_x

        for footprint in members:
            if placed_in_line == columns:
                cursor_x = block_x
                cursor_y += line_height + _COMPONENT_GAP_MM
                line_height = 0.0
                placed_in_line = 0

            # Place the pad box, not the origin: `offset` is where the copper
            # sits relative to the footprint origin, so subtract it.
            placement[footprint.reference] = (
                round(cursor_x + footprint.width / 2.0 - footprint.offset_x, 4),
                round(cursor_y + footprint.height / 2.0 - footprint.offset_y, 4),
            )
            cursor_x += footprint.width + _COMPONENT_GAP_MM
            block_right = max(block_right, cursor_x)
            line_height = max(line_height, footprint.height)
            placed_in_line += 1

        block_w = block_right - block_x
        block_h = (cursor_y + line_height) - block_y

        row_x = block_x + block_w + _MODULE_GAP_MM
        row_height = max(row_height, block_h)

        if row_x > _MAX_ROW_WIDTH_MM:
            row_x = _EDGE_MARGIN_MM
            row_y += row_height + _MODULE_GAP_MM
            row_height = 0.0

    return placement


def apply_placement(text: str, footprints: list[Footprint],
                    placement: dict[str, tuple[float, float]]) -> str:
    """Rewrite each footprint's top-level `(at ...)` to its placed position.

    Blocks are rewritten back to front so earlier offsets stay valid. Rotation
    is preserved: only the coordinates change.
    """
    updated = text
    for footprint in sorted(footprints, key=lambda item: item.start, reverse=True):
        if footprint.reference not in placement:
            continue
        x, y = placement[footprint.reference]
        block = updated[footprint.start:footprint.end]
        match = _PLACEMENT_RE.search(block)
        if match is None:
            raise LayoutError(f"footprint {footprint.reference} has no placement")
        rotation = match.group(3)
        replacement = f"(at {x} {y} {rotation})" if rotation else f"(at {x} {y})"
        block = block[:match.start()] + replacement + block[match.end():]
        updated = updated[:footprint.start] + block + updated[footprint.end:]
    return updated


def placed_bounds(footprints: list[Footprint],
                  placement: dict[str, tuple[float, float]]) -> tuple[float, float, float, float]:
    """Bounding box of the placed copper, in board coordinates."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for footprint in footprints:
        if footprint.reference not in placement:
            continue
        x, y = placement[footprint.reference]
        centre_x = x + footprint.offset_x
        centre_y = y + footprint.offset_y
        min_x = min(min_x, centre_x - footprint.width / 2.0)
        max_x = max(max_x, centre_x + footprint.width / 2.0)
        min_y = min(min_y, centre_y - footprint.height / 2.0)
        max_y = max(max_y, centre_y + footprint.height / 2.0)
    if min_x == float("inf"):
        raise LayoutError("no placed footprints to bound")
    return min_x, min_y, max_x, max_y


def strip_edge_cuts(text: str) -> str:
    """Remove existing top-level Edge.Cuts graphics.

    A derived outline replaces any previous one; leaving both would produce a
    malformed board with two overlapping boundaries.
    """
    keywords = ("gr_line", "gr_arc", "gr_circle", "gr_rect", "gr_poly", "gr_curve")
    result = text
    for keyword in keywords:
        marker = f"\t({keyword}"
        cursor = 0
        parts: list[str] = []
        while True:
            index = result.find(marker, cursor)
            if index == -1:
                parts.append(result[cursor:])
                break
            end = _sexp_end(result, index)
            block = result[index:end]
            if '"Edge.Cuts"' in block:
                parts.append(result[cursor:index])
                while end < len(result) and result[end] == "\n":
                    end += 1
            else:
                parts.append(result[cursor:end])
            cursor = end
        result = "".join(parts)
    return result


def render_outline(bounds: tuple[float, float, float, float]) -> str:
    """Rectangular Edge.Cuts outline enclosing `bounds` with an edge margin."""
    min_x, min_y, max_x, max_y = bounds
    left = round(min_x - _EDGE_MARGIN_MM, 4)
    top = round(min_y - _EDGE_MARGIN_MM, 4)
    right = round(max_x + _EDGE_MARGIN_MM, 4)
    bottom = round(max_y + _EDGE_MARGIN_MM, 4)

    corners = [
        ((left, top), (right, top)),
        ((right, top), (right, bottom)),
        ((right, bottom), (left, bottom)),
        ((left, bottom), (left, top)),
    ]
    lines: list[str] = []
    for (sx, sy), (ex, ey) in corners:
        lines.append(
            f"\t(gr_line\n"
            f"\t\t(start {sx} {sy})\n"
            f"\t\t(end {ex} {ey})\n"
            f"\t\t(stroke\n"
            f"\t\t\t(width {_EDGE_LINE_WIDTH_MM})\n"
            f"\t\t\t(type solid)\n"
            f"\t\t)\n"
            f'\t\t(layer "Edge.Cuts")\n'
            f"\t)"
        )
    return "\n".join(lines) + "\n"


def insert_outline(text: str, outline: str) -> str:
    tail = text.rstrip()
    if not tail.endswith(")"):
        raise LayoutError("board file does not end with a closing paren")
    return tail[:-1] + outline + ")\n"


@dataclass(frozen=True)
class PlacementResult:
    placed: int
    width_mm: float
    height_mm: float


def place_and_outline(board: Path) -> PlacementResult:
    """Place every footprint and derive the board outline, in place."""
    text = board.read_text(encoding="utf-8", errors="strict")
    footprints = read_footprints(text)
    placement = compute_placement(footprints)

    text = apply_placement(text, footprints, placement)
    bounds = placed_bounds(footprints, placement)
    text = strip_edge_cuts(text)
    text = insert_outline(text, render_outline(bounds))
    board.write_text(text, encoding="utf-8")

    min_x, min_y, max_x, max_y = bounds
    return PlacementResult(
        placed=len(placement),
        width_mm=round((max_x - min_x) + 2 * _EDGE_MARGIN_MM, 3),
        height_mm=round((max_y - min_y) + 2 * _EDGE_MARGIN_MM, 3),
    )
