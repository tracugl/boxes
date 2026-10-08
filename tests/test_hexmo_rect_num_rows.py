"""Tests for HexmoRectangle ``--num_rows``: lanes across the short axis.

The rectangle splits its width into ``num_rows`` lanes with ``num_rows − 1``
long internal supports (the vertical dividers, spanning H).  They slot into
both short end walls and the base plate, and cross the short internal
dividers.  Before this option there were always 3 lanes.  At N scale
(radius 220) that put the two long supports' finger slots inside the end
wall's centred big hole.

The helpers here record what the generator actually draws.  Each
rectangularWall panel is tagged, and every fingerHoles run and big hole
(circle or rounded rectangle) is mapped to page coordinates through the
drawing transform, so overlaps are measured, not assumed.

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from hexmo_testutil import IGNORE_CORE_MATMUL, apply, PLAIN_WALLS

# Silence only the matmul deprecation raised by upstream's boxes/drawing.py
# (see hexmo_testutil); every other warning still shows.
pytestmark = IGNORE_CORE_MATMUL

from boxes import edges as box_edges
from boxes.generators.hexmorectangle import HexmoRectangle

# Big holes are anything larger than a medium registration hole (12.5 mm);
# their radius follows --h (see HexmoRectangle._bigHoleRadius).
BIG_MIN = 12.5

# The user's N-scale build that exposed the clash.
USER_N = ["--radius=220", "--h=100", "--thickness=3", "--spoke_width=45",
          "--corner_holes=g2", "--big_hole_shape=rounded_rect", "--outside=1"]


def render_recorded(args, monkeypatch):
    """Render a HexmoRectangle and record panels, slots, big holes and crossing slots.

    @param args        - CLI arguments.
    @param monkeypatch - pytest fixture, used to count ``edges.Slot`` draws.
    @returns Dict: ``panels`` (kind, x, y) per rectangularWall with a
             callback; ``slots`` (kind, bbox) per fingerHoles run; ``big``
             (kind, bbox) per big hole; ``crossings`` (kind, count) of
             crossing-slot notches drawn while each panel's outline was drawn.
    """
    box = HexmoRectangle()
    box.parseArgs(args + PLAIN_WALLS)
    box.open()
    rec = {"panels": [], "slots": [], "big": [], "crossings": {}}
    cur = {"kind": None}
    t = box.thickness

    o_wall, o_hole, o_rhole, o_fh = (box.rectangularWall, box.hole,
                                     box.rectangularHole, box.fingerHolesAt)

    def page(x, y):
        return apply(box.ctx._m, (x, y))

    def wall(x, y, edges="eeee", *a, callback=None, **kw):
        cbs = list(callback or [])
        if not (cbs and callable(cbs[0])):
            return o_wall(x, y, edges, *a, callback=callback, **kw)
        name = getattr(cbs[0], "__name__", "?")
        if name == "<lambda>":
            # vert_div_cb / horiz_div_cb are lambdas: tell them apart by length.
            # Long supports run the full length H, like the long walls (which
            # are drawn first); short dividers span W − 2t.
            long_len = next(px for k, px, _ in rec["panels"] if k == "long_wall_cb")
            name = "vert_div" if math.isclose(x, long_len) else "horiz_div"
        inner = cbs[0]

        def tagged():
            prev, cur["kind"] = cur["kind"], name
            try:
                return inner()
            finally:
                cur["kind"] = prev

        cbs[0] = tagged
        rec["panels"].append((name, x, y))
        prev, cur["kind"] = cur["kind"], name
        rec["crossings"].setdefault(name, 0)
        try:
            return o_wall(x, y, edges, *a, callback=cbs, **kw)
        finally:
            cur["kind"] = prev

    def hole(x, y, r=0.0, d=0.0, **kw):
        if cur["kind"] and r > BIG_MIN:
            cx, cy = page(x, y)
            rec["big"].append((cur["kind"], (cx - r, cy - r, cx + r, cy + r)))
        return o_hole(x, y, r=r, d=d, **kw)

    def rhole(x, y, dx, dy, r=0, center_x=True, center_y=True):
        if cur["kind"] and dx > 2 * BIG_MIN and dy > 2 * BIG_MIN:
            x0 = x - dx / 2 if center_x else x
            y0 = y - dy / 2 if center_y else y
            (ax, ay), (bx, by) = page(x0, y0), page(x0 + dx, y0 + dy)
            rec["big"].append((cur["kind"], (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))))
        return o_rhole(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

    def fh(x, y, length, angle=90, **kw):
        if cur["kind"]:
            ax, ay = page(x, y)
            bx, by = page(x + length * math.cos(math.radians(angle)),
                          y + length * math.sin(math.radians(angle)))
            rec["slots"].append((cur["kind"], (min(ax, bx) - t / 2, min(ay, by) - t / 2,
                                               max(ax, bx) + t / 2, max(ay, by) + t / 2)))
        return o_fh(x, y, length, angle, **kw)

    o_slot_call = box_edges.Slot.__call__

    def slot_call(self_, *a, **kw):
        if cur["kind"]:
            rec["crossings"][cur["kind"]] = rec["crossings"].get(cur["kind"], 0) + 1
        return o_slot_call(self_, *a, **kw)

    monkeypatch.setattr(box_edges.Slot, "__call__", slot_call)
    box.rectangularWall, box.hole, box.rectangularHole, box.fingerHolesAt = wall, hole, rhole, fh
    box.render()
    box.close()
    return rec


def overlaps(rec):
    """Big-hole/slot pairs on the same panel whose bounding boxes intersect."""
    def hit(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    return [(k, bb) for k, bb in rec["big"] for sk, sb in rec["slots"]
            if sk == k and hit(bb, sb)]


def count(rec, kind):
    return sum(1 for k, _, _ in rec["panels"] if k == kind)


class TestNumRows:

    def test_default_is_three_lanes(self, monkeypatch) -> None:
        rec = render_recorded(["--radius=500"], monkeypatch)
        assert count(rec, "vert_div") == 2
        assert HexmoRectangle().argparser.get_default("num_rows") == 3

    @pytest.mark.parametrize("rows, supports", [(1, 0), (3, 2), (5, 4)])
    def test_long_support_count(self, rows, supports, monkeypatch) -> None:
        rec = render_recorded(["--radius=500", f"--num_rows={rows}"], monkeypatch)
        assert count(rec, "vert_div") == supports
        # Each long support leaves one slot run in each end wall.
        short_slots = sum(1 for k, _ in rec["slots"] if k == "short_wall_cb")
        assert short_slots == 2 * supports

    def test_one_row_has_no_crossing_slots(self, monkeypatch) -> None:
        rec = render_recorded(["--radius=500", "--num_rows=1"], monkeypatch)
        assert count(rec, "horiz_div") > 0
        assert rec["crossings"]["horiz_div"] == 0

    def test_two_rows_with_spoke_is_refused(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(["--radius=500", "--num_rows=2", "--spoke_width=45"])
        box.open()
        with pytest.raises(ValueError, match="num_rows"):
            box.render()

    def test_two_rows_without_spoke_has_one_central_support(self, monkeypatch) -> None:
        rec = render_recorded(["--radius=500", "--num_rows=2", "--spoke_width=0"], monkeypatch)
        assert count(rec, "vert_div") == 1

    def test_zero_rows_is_refused(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(["--radius=500", "--num_rows=0"])
        box.open()
        with pytest.raises(ValueError, match="num_rows"):
            box.render()


class TestUserNScaleClash:

    def test_detector_finds_an_overlap(self) -> None:
        """Sanity check for the overlap detector on a known overlapping pair.

        (The user's real 3-row clash used to serve here; it is now fixed, see
        test_three_row_clash_is_resolved.)
        """
        rec = {"big": [("short_wall_cb", (0, 0, 70, 70))],
               "slots": [("short_wall_cb", (68, 0, 71, 97)),
                         ("other_panel", (0, 0, 70, 70))]}
        assert overlaps(rec) == [("short_wall_cb", (0, 0, 70, 70))]

    def test_one_row_has_no_clash(self, monkeypatch) -> None:
        assert overlaps(render_recorded(USER_N + ["--num_rows=1"], monkeypatch)) == []


def part_boxes(args):
    """Page-frame boxes of every part, including the scale-reference bar.

    Each part calls ``move(x, y, where, before=True)`` before it draws; the
    drawing transform at that moment is the part's origin, and ``(x, y)`` its
    declared size.  ``open()`` draws the ``--reference`` bar first, at the
    origin, 10 mm tall, before any part.

    @returns List of ``(x0, y0, x1, y1)`` boxes.
    """
    box = HexmoRectangle()
    box.parseArgs(args)
    box.open()
    found = [(0.0, 0.0, float(box.reference), 10.0)] if box.reference else []
    o_move = box.move

    def move(x, y, where, before=False, label=""):
        skip = o_move(x, y, where, before=before, label=label)
        if before and where and "only" not in where.split():
            (ax, ay), (bx, by) = apply(box.ctx._m, (0, 0)), apply(box.ctx._m, (x, y))
            found.append((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)))
        return skip

    box.move = move
    box.render()
    box.close()
    return found


class TestLayout:

    @pytest.mark.parametrize("rows", [1, 3])
    @pytest.mark.parametrize("cols", [1, 2, 3, 5])
    @pytest.mark.parametrize("spoke", [0, 45])
    def test_no_part_overlaps_another_or_the_reference_bar(self, rows, cols, spoke) -> None:
        eps = 0.01
        found = part_boxes(["--radius=220", "--thickness=3", f"--num_rows={rows}",
                            f"--num_columns={cols}", f"--spoke_width={spoke}"])
        clashes = [(a, b) for i, a in enumerate(found) for b in found[i + 1:]
                   if a[0] < b[2] - eps and b[0] < a[2] - eps
                   and a[1] < b[3] - eps and b[1] < a[3] - eps]
        assert clashes == []


def big_holes_by_panel(args):
    """Big-hole centres per panel kind, relative to that panel's callback origin.

    End walls (``short_wall_cb``) and short dividers (``horiz_div``) share the
    same frame: x along the wall from the inner face of a long wall, and y up
    from the deck-side edge.  So their big holes line up exactly when these
    coordinate sets are equal.

    @returns ``{kind: sorted [(x, y)]}`` using the first panel of each kind.
    """
    box = HexmoRectangle()
    box.parseArgs(args + PLAIN_WALLS)
    box.open()
    found: dict[str, list] = {}
    cur = {"kind": None, "origin": None}
    long_len = []
    o_wall, o_hole, o_rhole = box.rectangularWall, box.hole, box.rectangularHole

    def local(x, y):
        px, py = apply(~cur["origin"], apply(box.ctx._m, (x, y)))
        return round(px, 2), round(py, 2)

    def wall(x, y, edges="eeee", *a, callback=None, **kw):
        cbs = list(callback or [])
        if not (cbs and callable(cbs[0])):
            return o_wall(x, y, edges, *a, callback=callback, **kw)
        name = getattr(cbs[0], "__name__", "?")
        if name == "long_wall_cb":
            long_len.append(x)
        if name == "<lambda>":
            name = "vert_div" if long_len and math.isclose(x, long_len[0]) else "horiz_div"
        inner = cbs[0]

        def tagged():
            if name in found:            # first panel of each kind only
                return inner()
            found[name] = []
            cur["kind"], cur["origin"] = name, box.ctx._m
            try:
                return inner()
            finally:
                cur["kind"] = None

        cbs[0] = tagged
        return o_wall(x, y, edges, *a, callback=cbs, **kw)

    def hole(x, y, r=0.0, d=0.0, **kw):
        if cur["kind"] and r > BIG_MIN:
            found[cur["kind"]].append(local(x, y))
        return o_hole(x, y, r=r, d=d, **kw)

    def rhole(x, y, dx, dy, r=0, center_x=True, center_y=True):
        if cur["kind"] and dx > 2 * BIG_MIN and dy > 2 * BIG_MIN:
            found[cur["kind"]].append(local(x if center_x else x + dx / 2,
                                            y if center_y else y + dy / 2))
        return o_rhole(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

    box.rectangularWall, box.hole, box.rectangularHole = wall, hole, rhole
    box.render()
    box.close()
    return {k: sorted(v) for k, v in found.items()}


class TestDividerBigHolesAlignWithEndWall:

    @pytest.mark.parametrize("extra", [
        USER_N + ["--num_rows=1"],
        USER_N + ["--num_rows=1", "--big_hole_shape=circle"],
        ["--radius=500"],                       # HO default, 3 rows
        ["--radius=500", "--num_rows=1", "--num_columns=3"],
        ["--radius=400", "--num_rows=1", "--spoke_width=0", "--outside=0"],
    ], ids=["N-1row", "N-1row-circle", "HO-default", "HO-1row", "r400-1row-nospoke-outside0"])
    def test_same_big_holes_as_end_wall(self, extra) -> None:
        holes = big_holes_by_panel(extra)
        assert holes.get("horiz_div"), "expected short dividers with big holes"
        assert holes["horiz_div"] == holes["short_wall_cb"]

    def test_all_holes_dropped_consistently_when_every_one_hits_a_support(self) -> None:
        # r=400 with 5 lanes: each registration big hole would cross a support,
        # so neither panel cuts one (and they still agree).
        holes = big_holes_by_panel(["--radius=400", "--num_rows=5", "--spoke_width=0"])
        assert holes["short_wall_cb"] == holes.get("horiz_div", []) == []

    def test_three_row_clash_is_resolved(self, monkeypatch) -> None:
        """At 3 rows no big hole crosses a long-support slot, on either panel."""
        assert overlaps(render_recorded(USER_N, monkeypatch)) == []

    def test_divider_big_holes_clear_crossing_slots(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(["--radius=500"])
        t, r4 = 6.0, box._bigHoleRadius()
        holes = big_holes_by_panel(["--radius=500"])["horiz_div"]
        W = 500 - 2 * t
        col_w = (W - 2 * t - 2 * t) / 3
        slots = [(i + 1) * col_w + (2 * i + 1) * t / 2 for i in range(2)]
        assert all(abs(x - s) >= r4 + t / 2 for x, _ in holes for s in slots)
