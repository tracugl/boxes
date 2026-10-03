"""Tests for --big_hole_width / --big_hole_height (rounded_rect big holes).

The big holes double as the under-board train pass-through, so they must line
up from module to module: HexmoHexagon side wall → HexmoRectangle end wall →
short dividers → next module.  The two options shrink every rounded-rect big
hole around its existing centre on both generators.  Centres and counts stay
exactly as they are, so the holes still line up.

Holes are recorded from what the generators draw, as in
test_hexmo_wall_alignment.py:

* hex wall holes, while ``drawAlignmentHoles`` runs, in the hex wall pattern
  frame (x up the wall, y along it; so ``dx`` is the height, ``dy`` the width);
* rect end-wall and divider holes, while their callbacks run, mapped through
  the drawing transform to the callback origin (x along the wall, y up from the
  deck side; so ``dx`` is the width, ``dy`` the height).

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from hexmo_testutil import IGNORE_CORE_MATMUL, apply

# Silence only the matmul deprecation raised by upstream's boxes/drawing.py
# (see hexmo_testutil); every other warning still shows.
pytestmark = IGNORE_CORE_MATMUL

from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

# A box tall enough for 70 mm big holes, rounded_rect so the options apply.
HO = ["--radius=500", "--thickness=6", "--h=100", "--big_hole_shape=rounded_rect"]
# The user's N-scale rectangle: r=220 with 3 lanes, where the 70 mm hole would
# cut the long-support slots at ±35.2 mm and is therefore dropped.
N3 = ["--radius=220", "--thickness=3", "--h=100", "--num_rows=3", "--num_columns=2",
      "--big_hole_shape=rounded_rect"]
BIG = 25.0   # holes wider/taller than this are big holes (mediums are Ø25)


def hex_wall_big_holes(args):
    """Big holes on the first HexmoHexagon side wall.

    @returns Sorted ``(along, from_deck, width, height)`` tuples.
    """
    box = HexmoHexagon()
    box.parseArgs(args)
    box.open()
    frames, found, inside = [], [], [False]
    o_rhole, o_align = box.rectangularHole, box.drawAlignmentHoles

    def rhole(x, y, dx, dy, r=0, center_x=True, center_y=True):
        if inside[0] and len(frames) == 1 and dx > BIG and dy > BIG:
            found.append((x, y, dx, dy))
        return o_rhole(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

    def align(s, l, text):
        frames.append((s, l))
        inside[0] = True
        try:
            return o_align(s, l, text)
        finally:
            inside[0] = False

    box.rectangularHole, box.drawAlignmentHoles = rhole, align
    box.render()
    s, l = frames[0]
    return sorted((round(y - s / 2, 2), round(l - x, 2), round(dy, 2), round(dx, 2))
                  for x, y, dx, dy in found)


def rect_big_holes(args):
    """Big holes on the first rect end wall and first short divider.

    @returns ``{"end": [...], "div": [...]}`` of sorted ``(along, from_deck,
             width, height)`` tuples, ``along`` measured from the wall centre.
    """
    box = HexmoRectangle()
    box.parseArgs(args)
    box.open()
    found = {"end": [], "div": []}
    cur = {"kind": None, "origin": None, "half": 0.0}
    long_len = []
    o_wall, o_rhole = box.rectangularWall, box.rectangularHole

    def wall(x, y, edges="eeee", *a, callback=None, **kw):
        cbs = list(callback or [])
        if not (cbs and callable(cbs[0])):
            return o_wall(x, y, edges, *a, callback=callback, **kw)
        name = getattr(cbs[0], "__name__", "?")
        if name == "long_wall_cb":
            long_len.append(x)
        kind = {"short_wall_cb": "end"}.get(name)
        if name == "<lambda>" and long_len and abs(x - long_len[0]) > 1e-6:
            kind = "div"
        inner = cbs[0]

        def tagged():
            if kind is None or found[kind] or cur["kind"]:
                return inner()
            cur.update(kind=kind, origin=box.ctx._m, half=x / 2)
            try:
                return inner()
            finally:
                cur["kind"] = None
                if not found[kind]:
                    found[kind] = []

        cbs[0] = tagged
        return o_wall(x, y, edges, *a, callback=cbs, **kw)

    def rhole(x, y, dx, dy, r=0, center_x=True, center_y=True):
        if cur["kind"] and dx > BIG and dy > BIG:
            px, py = apply(~cur["origin"], apply(box.ctx._m, (x, y)))
            found[cur["kind"]].append((round(px - cur["half"], 2), round(py, 2),
                                       round(dx, 2), round(dy, 2)))
        return o_rhole(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

    box.rectangularWall, box.rectangularHole = wall, rhole
    box.render()
    box.close()
    return {k: sorted(v) for k, v in found.items()}


def centres(holes):
    return [(a, fd) for a, fd, _, _ in holes]


class TestDefaultsUnchanged:

    def test_zero_means_auto_size(self) -> None:
        auto = hex_wall_big_holes(HO)
        assert auto and all((w, h) == (70.0, 70.0) for _, _, w, h in auto)
        assert hex_wall_big_holes(HO + ["--big_hole_width=0", "--big_hole_height=0"]) == auto


class TestShrinkAroundCentre:

    @pytest.mark.parametrize("w, h", [(50, 70), (70, 40), (45, 55)])
    def test_hex_wall_holes_shrink_in_place(self, w, h) -> None:
        auto = hex_wall_big_holes(HO)
        sized = hex_wall_big_holes(HO + [f"--big_hole_width={w}", f"--big_hole_height={h}"])
        assert centres(sized) == centres(auto)
        assert all((hw, hh) == (w, h) for _, _, hw, hh in sized)

    @pytest.mark.parametrize("w, h", [(50, 70), (45, 55)])
    def test_rect_end_wall_and_dividers_match_hex(self, w, h) -> None:
        size = [f"--big_hole_width={w}", f"--big_hole_height={h}"]
        rect = rect_big_holes(HO + size)
        hexa = set(hex_wall_big_holes(HO + size))
        assert rect["end"] and set(rect["end"]) <= hexa
        assert rect["div"] == rect["end"]

    def test_hex_support_holes_use_the_size_too(self) -> None:
        # Hex internal supports draw big holes with x along the support.
        box = HexmoHexagon()
        box.parseArgs(HO + ["--big_hole_width=50", "--big_hole_height=40"])
        box.open()
        seen, inside = [], [False]
        o_rhole, o_sup = box.rectangularHole, box.drawSupports

        def rhole(x, y, dx, dy, r=0, center_x=True, center_y=True):
            if inside[0] and dx > BIG and dy > BIG:
                seen.append((round(dx, 2), round(dy, 2)))
            return o_rhole(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

        def sup(*a, **kw):
            inside[0] = True
            try:
                return o_sup(*a, **kw)
            finally:
                inside[0] = False

        box.rectangularHole, box.drawSupports = rhole, sup
        box.render()
        assert seen and set(seen) == {(50.0, 40.0)}


class TestNScaleThreeRows:

    def test_auto_size_drops_the_centre_hole(self) -> None:
        holes = rect_big_holes(N3)
        assert holes["end"] == holes["div"] == []

    def test_narrow_hole_fits_between_the_supports(self) -> None:
        holes = rect_big_holes(N3 + ["--big_hole_width=50"])
        assert holes["end"] == holes["div"] == [(0.0, 47.0, 50.0, 70.0)]

    def test_too_wide_is_still_dropped(self) -> None:
        # Supports at ±35.2 mm: half-width 30 + 1.5 (half thickness) + 5 (clear) > 35.2.
        holes = rect_big_holes(N3 + ["--big_hole_width=60"])
        assert holes["end"] == holes["div"] == []


class TestValidation:

    @pytest.mark.parametrize("opt", ["--big_hole_width=71", "--big_hole_height=80",
                                     "--big_hole_width=-5"])
    @pytest.mark.parametrize("cls", [HexmoHexagon, HexmoRectangle])
    def test_bad_size_is_refused(self, cls, opt) -> None:
        box = cls()
        box.parseArgs(HO + [opt])
        box.open()
        with pytest.raises(ValueError, match="big_hole"):
            box.render()

    def test_circle_shape_ignores_the_size(self) -> None:
        circle = ["--radius=500", "--thickness=6", "--h=100", "--big_hole_shape=circle"]

        def render(args):
            box = HexmoHexagon()
            box.parseArgs(args)
            box.metadata["reproducible"] = True
            box.open()
            box.render()
            return [l for l in box.close().getvalue().decode().splitlines()
                    if l.strip().startswith("<path")]

        assert render(circle + ["--big_hole_width=40"]) == render(circle)


def test_preferred_n_pass_through_lines_up_hex_to_rect() -> None:
    """The preferred N modules (README-N-scale.md): one 50 × 70 tunnel, end to end."""
    shared = ["--radius=220", "--thickness=3", "--h=100", "--big_hole_shape=rounded_rect",
              "--big_hole_width=50", "--big_hole_height=70"]
    hexa = hex_wall_big_holes(shared + ["--trapezoid=1"])
    rect = rect_big_holes(shared + ["--num_rows=3", "--num_columns=2"])
    assert hexa == rect["end"] == rect["div"] == [(0.0, 47.0, 50.0, 70.0)]
