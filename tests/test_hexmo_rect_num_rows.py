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

from boxes import edges as box_edges
from boxes.generators.hexmorectangle import HexmoRectangle

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
    box.parseArgs(args)
    box.open()
    rec = {"panels": [], "slots": [], "big": [], "crossings": {}}
    cur = {"kind": None}
    t = box.thickness

    o_wall, o_hole, o_rhole, o_fh = (box.rectangularWall, box.hole,
                                     box.rectangularHole, box.fingerHolesAt)

    def page(x, y):
        return box.ctx._m * (x, y)

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
        if cur["kind"] and r >= 30:
            cx, cy = page(x, y)
            rec["big"].append((cur["kind"], (cx - r, cy - r, cx + r, cy + r)))
        return o_hole(x, y, r=r, d=d, **kw)

    def rhole(x, y, dx, dy, r=0, center_x=True, center_y=True):
        if cur["kind"] and dx >= 60 and dy >= 60:
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

    def test_detector_sees_the_three_row_clash(self, monkeypatch) -> None:
        """Sanity check for the overlap detector: the reported clash is found."""
        clash = overlaps(render_recorded(USER_N, monkeypatch))
        assert any(k == "short_wall_cb" for k, _ in clash)

    def test_one_row_has_no_clash(self, monkeypatch) -> None:
        assert overlaps(render_recorded(USER_N + ["--num_rows=1"], monkeypatch)) == []
