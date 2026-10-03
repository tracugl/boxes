"""Tests for HexmoHexagon's general track routes (``--track_routes``).

A route runs from one edge to another, with its own offset at each end, and
is drawn as straight / one arc / straight with the largest arc that keeps a
``--track_lead_in`` straight at both ends.  The four old toggles
(``--track_left`` …) and the trapezoid's curve expand to routes, so their
etched output must not change: that is checked against a snapshot taken from
the pre-route implementation (``tests/data/hexmo_track_lines_golden.json``).

Edges follow the generator's flat-top numbering: 1 top, 2 upper-right,
3 lower-right, 4 bottom, 5 lower-left, 6 upper-left.  On a curve a positive
offset is away from the curve's centre (its outside), as for the existing
track families; on a straight it is to the right of travel.

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from hexmo_testutil import IGNORE_CORE_MATMUL
from hexmo_track_capture import etched_track_paths

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_track_routes import (
    EDGE_ANGLES, Arc, Line, RouteSpec, expand_routes, parse_track_routes,
    route_geometry, route_template_steps,
)
from boxes.generators.hexmohexagon import HexmoHexagon

GOLDEN = Path(__file__).resolve().parent / "data" / "hexmo_track_lines_golden.json"

# Preferred N-scale settings: deck apothem and lead-in as the generator uses them.
N_ARGS = ["--radius=220", "--thickness=3", "--h=100", "--track_lead_in=26",
          "--track_width=17", "--track_gauge=9"]
R_IN = 220 - 3 / math.cos(math.radians(30))
APOTHEM = R_IN * math.sqrt(3) / 2
LEAD = 26.0
RHO = (APOTHEM - LEAD) * math.sqrt(3)          # 279.8, the ring radius
# The helix-ring M6: two edge-1 tracks at ±17.5 as the loop legs, plus a spur
# turnout off the edge 1 → 5 leg that ends on the other side at edge 5.
M6 = "1:-17.5-5:-17.5, 3:-17.5-1:-17.5, 1:-17.5-5:17.5"


def edge_point(edge, along):
    """Point on edge ``edge`` at ``along`` mm anticlockwise from its midpoint."""
    th = math.radians(EDGE_ANGLES[edge])
    return (APOTHEM * math.cos(th) - along * math.sin(th),
            APOTHEM * math.sin(th) + along * math.cos(th))


def make_box(extra):
    box = HexmoHexagon()
    box.parseArgs(N_ARGS + extra)
    box.metadata["reproducible"] = True
    return box


class TestParsing:

    def test_routes_with_offsets(self) -> None:
        assert parse_track_routes(M6) == [
            RouteSpec(1, 5, -17.5, -17.5),
            RouteSpec(3, 1, -17.5, -17.5),
            RouteSpec(1, 5, -17.5, 17.5),
        ]

    def test_route_without_offsets_uses_the_track_family(self) -> None:
        (spec,) = parse_track_routes("4-6")
        assert spec == RouteSpec(4, 6, None, None)
        assert expand_routes([spec], [-17.5, 17.5]) == [(4, -17.5, 6, -17.5),
                                                        (4, 17.5, 6, 17.5)]

    def test_one_offset_applies_to_both_ends(self) -> None:
        assert parse_track_routes("2:+10-4") == [RouteSpec(2, 4, 10.0, 10.0)]
        assert parse_track_routes("2-4:-5") == [RouteSpec(2, 4, -5.0, -5.0)]

    def test_empty_is_no_routes(self) -> None:
        assert parse_track_routes("") == []
        assert parse_track_routes("  ") == []

    @pytest.mark.parametrize("text", ["7-1", "1-1", "abc", "1:x-5", "1-5,", "1--5"])
    def test_bad_specs_are_refused(self, text) -> None:
        with pytest.raises(ValueError, match="--track_routes"):
            parse_track_routes(text)


class TestCurveGeometry:

    def test_centreline_is_the_ring_curve(self) -> None:
        g = route_geometry(5, 0.0, 3, 0.0, APOTHEM, LEAD)
        assert g.radius == pytest.approx(RHO)
        assert g.segments[0].p0 == pytest.approx(edge_point(5, 0))
        assert g.segments[-1].p1 == pytest.approx(edge_point(3, 0))

    @pytest.mark.parametrize("off", [-35.0, -17.5, 17.5])
    def test_equal_offsets_give_the_concentric_curve(self, off) -> None:
        g = route_geometry(1, off, 5, off, APOTHEM, LEAD)
        assert g.radius == pytest.approx(RHO + off)
        first, arc, last = g.segments
        assert first.length == pytest.approx(LEAD)
        assert last.length == pytest.approx(LEAD)

    def test_m6_loop_leg_is_r262(self) -> None:
        g = route_geometry(1, -17.5, 5, -17.5, APOTHEM, LEAD)
        assert g.radius == pytest.approx(262.3, abs=0.1)

    def test_spur_turnout_route(self) -> None:
        g = route_geometry(1, -17.5, 5, 17.5, APOTHEM, LEAD)
        first, arc, last = g.segments
        # One arc between two straights; the shorter straight is the lead-in.
        assert isinstance(arc, Arc) and isinstance(first, Line) and isinstance(last, Line)
        assert min(first.length, last.length) == pytest.approx(LEAD)
        assert g.radius == pytest.approx(227, abs=1)
        # The arc is tangent to both straights: they end/start on its circle,
        # square to the radius there.
        for p in (first.p1, last.p0):
            assert math.dist(p, arc.centre) == pytest.approx(arc.radius)
        assert abs(arc.sweep) == pytest.approx(math.radians(60))

    def test_ends_cross_the_edges_square_at_their_offsets(self) -> None:
        g = route_geometry(1, -17.5, 5, 17.5, APOTHEM, LEAD)
        first, _, last = g.segments
        # Edge 1's curve-centre side is edge 6 (anticlockwise), so −17.5 there
        # is 17.5 towards edge 6; at edge 5 the centre side is edge 6 too
        # (clockwise from 5), so +17.5 is towards edge 4.
        assert first.p0 == pytest.approx(edge_point(1, 17.5))
        assert last.p1 == pytest.approx(edge_point(5, 17.5))
        for line, edge, sign in ((first, 1, -1), (last, 5, 1)):
            th = math.radians(EDGE_ANGLES[edge])
            d = line.direction
            assert d[0] * math.cos(th) + d[1] * math.sin(th) == pytest.approx(sign)

    def test_two_routes_from_one_start_share_the_lead_in(self) -> None:
        leg = route_geometry(1, -17.5, 5, -17.5, APOTHEM, LEAD)
        spur = route_geometry(1, -17.5, 5, 17.5, APOTHEM, LEAD)
        assert leg.segments[0].p0 == pytest.approx(spur.segments[0].p0)
        assert leg.segments[0].direction == pytest.approx(spur.segments[0].direction)

    def test_offsets_too_large_are_refused(self) -> None:
        with pytest.raises(ValueError, match="too tight"):
            route_geometry(1, -150.0, 5, 150.0, APOTHEM, LEAD)


class TestStraightGeometry:

    def test_middle_straight(self) -> None:
        g = route_geometry(4, 10.0, 1, 10.0, APOTHEM, LEAD)
        (line,) = g.segments
        assert g.radius is None
        assert line.p0 == pytest.approx((10.0, -APOTHEM))
        assert line.p1 == pytest.approx((10.0, APOTHEM))

    def test_offset_change_makes_an_s_curve(self) -> None:
        g = route_geometry(4, 0.0, 1, 20.0, APOTHEM, LEAD)
        kinds = [type(s).__name__ for s in g.segments]
        assert kinds == ["Line", "Arc", "Arc", "Line"]
        a1, a2 = g.segments[1], g.segments[2]
        assert a1.radius == pytest.approx(a2.radius) == pytest.approx(g.radius)
        assert a1.sweep == pytest.approx(-a2.sweep)
        d, delta = 2 * APOTHEM - 2 * LEAD, 20.0
        assert g.radius == pytest.approx((d * d + delta * delta) / (4 * delta))
        assert g.segments[-1].p1 == pytest.approx((20.0, APOTHEM))


class TestRefusedRoutes:

    @pytest.mark.parametrize("a, b", [(1, 2), (3, 4), (6, 1)])
    def test_adjacent_edges(self, a, b) -> None:
        with pytest.raises(ValueError, match="adjacent"):
            route_geometry(a, 0.0, b, 0.0, APOTHEM, LEAD)

    def test_trapezoid_has_only_its_curve(self) -> None:
        box = make_box(["--trapezoid=1", "--track_routes=1-5"])
        with pytest.raises(ValueError, match="trapezoid"):
            box.open()
            box.render()


class TestUnchangedToggles:
    """The old options expand to routes and etch exactly what they did."""

    @pytest.mark.parametrize("case", sorted(json.loads(GOLDEN.read_text())))
    def test_matches_the_pre_route_snapshot(self, case) -> None:
        golden = json.loads(GOLDEN.read_text())[case]
        box = HexmoHexagon()
        box.parseArgs(golden["args"])
        box.metadata["reproducible"] = True
        paths = etched_track_paths(box)
        expected = [tuple(map(tuple, p)) for p in golden["paths"]]
        assert len(paths) == len(expected)
        for got, want in zip(paths, expected):
            assert len(got) == len(want)
            flat = [c for point in got for c in point]
            assert flat == pytest.approx([c for point in want for c in point], abs=1e-3)


class TestDrawing:

    def test_m6_routes_are_etched(self) -> None:
        # Per route: two footprint edges (draw_track on, draw_center off)
        # and a transition tick at each end of its arc.
        paths = etched_track_paths(make_box([f"--track_routes={M6}"]))
        assert len(paths) == 3 * (2 + 2)

    def test_routes_replace_the_toggles(self) -> None:
        with_both = etched_track_paths(make_box(["--track_routes=4-1", "--track_left=1"]))
        routes_only = etched_track_paths(make_box(["--track_routes=4-1"]))
        assert with_both == routes_only

    def test_labels_report_each_radius(self) -> None:
        box = make_box([f"--track_routes={M6}"])
        texts = []
        orig = box.text
        box.text = lambda t, *a, **kw: (texts.append(t), orig(t, *a, **kw))[1]
        box.open()
        box.render()
        box.close()
        assert sorted(t for t in texts if t.endswith(" mm")) == ["227 mm", "262 mm", "262 mm"]


class TestTemplates:

    def test_template_steps_follow_the_route(self) -> None:
        g = route_geometry(1, -17.5, 5, 17.5, APOTHEM, LEAD)
        steps = route_template_steps(g)
        assert [s[0] for s in steps] == ["line", "arc", "line"]
        assert steps[1][2] == pytest.approx(g.radius)
        assert abs(steps[1][1]) == pytest.approx(60)

    def test_m6_templates_are_deduplicated(self) -> None:
        box = make_box([f"--track_routes={M6}", "--track_template=1"])
        labels = []
        orig = box.drawTrackTemplate
        box.drawTrackTemplate = lambda route, label, *a, **kw: (
            labels.append(label), orig(route, label, *a, **kw))[1]
        box.open()
        box.render()
        box.close()
        # Both loop legs are the same R262 piece; the spur is its own.
        assert sorted(labels) == ["R227 9mm", "R262 9mm"]


class TestGuides:

    def _guides(self, extra):
        box = make_box(extra + ["--track_guide=1"])
        calls = []
        orig = box.drawTrackGuide
        box.drawTrackGuide = lambda *a, **kw: (calls.append(kw), orig(*a, **kw))[1]
        box.open()
        box.render()
        box.close()
        return calls

    def test_one_guide_per_edge_with_its_own_tracks(self) -> None:
        calls = self._guides([f"--track_routes={M6}"])
        by_label = {c["label"]: sorted(c["offsets"]) for c in calls}
        # Positions are mm anticlockwise along each edge from its midpoint.
        # Edge 1 has the two legs (the spur shares the edge 1 → 5 leg's
        # window).  Edge 3's leg is on its curve's centre side, towards edge
        # 2, which is anticlockwise from 3.  Edge 5 has the leg towards edge 6
        # (clockwise) and the spur towards edge 4.
        assert by_label == {
            "track guide edge 1": pytest.approx([-17.5, 17.5]),
            "track guide edge 3": pytest.approx([17.5]),
            "track guide edge 5": pytest.approx([-17.5, 17.5]),
        }

    def test_without_routes_the_single_guide_is_unchanged(self) -> None:
        calls = self._guides(["--trapezoid=1"])
        assert calls == [{"move": "right"}]
