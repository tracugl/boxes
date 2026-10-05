"""Tests for the solid spine left in the spoke floor's kites under a riser (BOX-52).

On a spoke floor the kite cut-outs would leave nothing for a riser support to
slot into.  So the kites keep their full size apart from a solid band (the
spine) along each riser's path, the bed's width plus a margin each side wide.
Supports can then stand anywhere along the track.

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

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_risers import _clear_width, spine_kites, split_by_polyline
from boxes.generators.hexmohexagon import HexmoHexagon

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
# A spine running up the middle of the square, 20 mm wide: left edge at
# x = 40, right edge at x = 60 (travel is +y, so left is −x).
SPINE = ([(40.0, -50.0), (40.0, 150.0)], [(60.0, -50.0), (60.0, 150.0)])

# Helix ring M1 at h=80 on a spoke floor, with its riser.
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--track_lead_in=26",
      "--track_width=17", "--bottom=spoke", "--edge_width=22", "--spoke_width=60",
      "--support_length=55", "--support_position=125",
      "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
      "--track_openings=3:-17.5:72.5:26,5:35:65.2:26", "--deck_slots=3:-17.5-5:-35/26"]
M1_RISER = "--risers=3:-17.5-5:-35~72.5..65.2"


def area(poly):
    pts = poly + poly[:1]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:]))) / 2


def inside(poly, p):
    """Ray-casting point-in-polygon (any simple polygon)."""
    x, y = p
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def render(args):
    """Render; return (kite openings, spines, riser stations) from the spoke floor."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    cut, spines, stations = [], [], []
    orig_cut, orig_plan = box._cutKites, box._riserPlan

    def cut_spy(kites, spine_list):
        spines.extend(spine_list)
        cut.extend(spine_kites(kites, spine_list, box._KITE_MIN_PIECE) if spine_list else kites)
        return orig_cut(kites, spine_list)

    def plan_spy(*a, **kw):
        plan = orig_plan(*a, **kw)
        lift = box.thickness if box.trapezoid else 0.0
        for riser in plan:
            for (x, y), (dx, dy), _ in riser["stations"]:
                stations.append(((x, y + lift), (dy, -dx), riser["width"]))
        return plan

    box._cutKites, box._riserPlan = cut_spy, plan_spy
    box.open()
    box.render()
    box.close()
    return cut, spines, stations


class TestSplitting:

    def test_split_a_square_in_two(self) -> None:
        a, b = split_by_polyline(SQUARE, [(50.0, -10.0), (50.0, 110.0)])
        assert area(a) + area(b) == pytest.approx(100 * 100)
        assert area(a) == pytest.approx(50 * 100)

    def test_spine_removes_its_band(self) -> None:
        pieces = spine_kites([SQUARE], [SPINE], 15.0)
        assert len(pieces) == 2
        assert sum(area(p) for p in pieces) == pytest.approx(100 * 100 - 20 * 100)
        assert not any(inside(p, (50.0, 50.0)) for p in pieces)
        assert any(inside(p, (20.0, 50.0)) for p in pieces)
        assert any(inside(p, (80.0, 50.0)) for p in pieces)

    def test_curved_spine(self) -> None:
        # A gently curving spine (a polyline arc) still splits cleanly.
        import math
        arc = lambda r: [(150 - r * math.cos(math.radians(a)), r * math.sin(math.radians(a)) - 20)
                         for a in range(-10, 80, 2)]
        pieces = spine_kites([SQUARE], [(arc(110.0), arc(90.0))], 15.0)
        assert len(pieces) == 2
        assert 0 < sum(area(p) for p in pieces) < 100 * 100

    def test_spine_missing_the_kite_leaves_it(self) -> None:
        far = ([(240.0, -50.0), (240.0, 150.0)], [(260.0, -50.0), (260.0, 150.0)])
        assert spine_kites([SQUARE], [far], 15.0) == [SQUARE]

    def test_thin_pieces_are_left_solid(self) -> None:
        near_edge = ([(5.0, -50.0), (5.0, 150.0)], [(25.0, -50.0), (25.0, 150.0)])
        pieces = spine_kites([SQUARE], [near_edge], 15.0)
        assert len(pieces) == 1 and area(pieces[0]) == pytest.approx(75 * 100)


class TestPieceWidth:
    """A piece is judged by the largest circle that fits in it, so a strip
    and a triangle of the same real width are treated alike."""

    def test_strip(self) -> None:
        strip = [(0.0, 0.0), (200.0, 0.0), (200.0, 10.0), (0.0, 10.0)]
        assert _clear_width(strip) == pytest.approx(10, abs=0.6)

    def test_triangle_is_its_incircle(self) -> None:
        # Legs 35 and 84: inradius (35 + 84 - 91) / 2 = 14, so 28 across;
        # 2·area / perimeter alone says 14 and would drop it.
        tri = [(0.0, 0.0), (35.0, 0.0), (0.0, 84.0)]
        assert _clear_width(tri) == pytest.approx(28, abs=1.0)

    def test_triangle_left_by_a_spine_is_cut(self) -> None:
        # A spine across a square leaves a corner triangle with 50 mm legs:
        # 29 mm across its incircle, so it is cut at 15 (2·area / perimeter
        # says 14.6 and used to leave it solid).  The far corner, legs 10, is
        # too small and stays solid.
        square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        # Travel up-left, so the corner at the origin is left of the left edge.
        spine = ([(60.0, -10.0), (-10.0, 60.0)], [(200.0, -10.0), (-10.0, 200.0)])
        pieces = spine_kites([square], [spine], 15.0)
        assert len(pieces) == 1
        assert max(x + y for x, y in pieces[0]) == pytest.approx(50)


class TestSpokeFloor:

    def test_without_risers_the_kites_are_unchanged(self) -> None:
        cut, spines, _ = render(M1)
        assert spines == [] and len(cut) == 2

    def test_m1_kites_keep_their_size_minus_the_spine(self) -> None:
        plain, _, _ = render(M1)
        cut, spines, stations = render(M1 + [M1_RISER])
        assert len(spines) == 1
        assert sum(area(p) for p in cut) < sum(area(p) for p in plain)
        # Every support's slot lands on solid floor (in no opening).
        for (x, y), (ax, ay), length in stations:
            for k in range(-10, 11):
                p = (x + ax * length / 2 * k / 10, y + ay * length / 2 * k / 10)
                assert not any(inside(poly, p) for poly in cut)

    def test_closed_floor_still_works(self) -> None:
        args = [a for a in M1 if a != "--bottom=spoke"] + ["--bottom=closed"]
        cut, spines, _ = render(args + [M1_RISER])
        assert cut == [] and spines == []


def test_helix_m6_keeps_all_six_kites() -> None:
    # M6's lower-level return riser cuts one kite down to a triangle about
    # 35 × 84 mm; it is cut, not left solid.
    from boxes.generators import _hexmo_step
    from boxes.generators._hexmo_helix_ring import HELIX_RING_N
    box = HexmoHexagon()
    box.parseArgs(HELIX_RING_N["M6"])
    floor = next(f for f in _hexmo_step._render_frames(box) if f.name == "floor")
    big = []
    for loop in _hexmo_step._frame_loops(floor):
        xs = [p[0] for seg in loop for p in seg[1:]]
        if 25 < max(xs) - min(xs) < 300:
            big.append(loop)
    assert len(big) == 6
