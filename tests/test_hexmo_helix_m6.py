"""Regression tests for the helix ring's M6 with three deck tracks at edge 1.

The ring's turnouts sit on a HexmoRectangle at M6 edge 1, so M6 receives three
deck tracks there: the reversing loop's legs either side and the spur on the
centre line.  These tests pin the README's N and HO settings: both must render,
the deck tracks must keep their spacing, the spur's slot must start only once
it is clear of the lower-level return below, the return's slot must stay clear
of the spur's deck stretch, and the return must be low enough to pass under the
deck where its slot ends.

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

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_deck_slots import centreline_points, trim_segments
from boxes.generators._hexmo_track_routes import route_geometry
from boxes.generators.hexmohexagon import HexmoHexagon

# Per scale: the README's M6 settings, plus the numbers the checks need.
# ``bed`` is the slot/bed/envelope width, ``track`` the deck track width,
# ``deck_under`` the deck underside above the floor and ``envelope`` the
# track-plus-train height (--train_envelope).
SCALES = {
    "N": dict(
        radius=220, t=3, lead=26, spacing=35, bed=35, track=17, deck_under=74, envelope=43,
        spur=(1, 0, 5, 17.5), spur_from=169, ret=(3, 35, 1, 0), ret_to=186, ret_height=31.0,
        loops=((1, -35, 5, -17.5), (3, -17.5, 1, -35)),
        args=["--radius=220", "--thickness=3", "--h=80", "--edge_width=22", "--spoke_width=60",
              "--bottom=spoke", "--support_length=55", "--support_edges=2,4,6",
              "--track_lead_in=26", "--track_width=17",
              "--track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5",
              "--under_track_edges=1", "--under_track_height=27.8", "--under_track_width=35",
              "--track_openings=5:17.5:72.5:35,3:-35:35.4:35",
              "--deck_slots=1:0-5:17.5@169../35,3:35-1:0@..186/35",
              "--risers=1:0-5:17.5@169..~77..72.5/35,3:35-1:0@..186~35.4..31/35,"
              "3:35-1:0@186..~31..27.8/35"]),
    "HO": dict(
        radius=500, t=6, lead=23, spacing=80, bed=60, track=30, deck_under=88, envelope=70,
        spur=(1, 0, 5, 40), spur_from=359, ret=(3, 80, 1, 0), ret_to=536, ret_height=18.0,
        loops=((1, -80, 5, -40), (3, -40, 1, -80)),
        args=["--radius=500", "--h=100", "--thickness=6", "--edge_width=60", "--spoke_width=120",
              "--bottom=spoke", "--top=closed", "--corner_holes=g2", "--gap_holes=g2",
              "--big_hole_shape=rounded_rect", "--track_width=30", "--track_lead_in=23",
              "--support_length=110", "--train_envelope=70", "--under_track_width=60",
              "--support_edges=2,4,6", "--track_routes=1:-80-5:-40,3:-40-1:-80,1:0-5:40",
              "--under_track_edges=1", "--under_track_height=18",
              "--track_openings=5:40:86.6:60,3:-80:28.1:60",
              "--deck_slots=1:0-5:40@359../60,3:80-1:0@..536/60",
              "--risers=1:0-5:40@359..~94..86.6/60,3:80-1:0@..536~28.1..18/60,"
              "3:80-1:0@536..~18..18/60"]),
}


def geometry(scale, route):
    """Solve ``route`` on that scale's M6 deck."""
    p = SCALES[scale]
    r_in = p["radius"] - p["t"] / math.cos(math.radians(30))
    return route_geometry(*route, r_in * math.sqrt(3) / 2, p["lead"])


def points(g, lo=0.0, hi=None):
    """Centreline points (1 mm apart) of a stretch of a solved route."""
    total = sum(s.length for s in g.segments)
    return centreline_points(trim_segments(list(g.segments), lo, total if hi is None else hi), 1.0)


def gap(a, b):
    """Closest distance between two point lists."""
    return min(math.dist(p, q) for p in a for q in b)


@pytest.mark.parametrize("scale", SCALES)
class TestM6:

    def test_renders(self, scale) -> None:
        box = HexmoHexagon()
        box.parseArgs(SCALES[scale]["args"] + ["--reference=0"])
        box.metadata["reproducible"] = True
        box.open()
        box.render()
        box.close()

    def test_deck_tracks_keep_their_spacing(self, scale) -> None:
        p = SCALES[scale]
        spur = points(geometry(scale, p["spur"]))
        for loop in p["loops"]:
            assert gap(spur, points(geometry(scale, loop))) >= p["spacing"] - 0.1

    def test_spur_leaves_the_deck_only_clear_of_the_return(self, scale) -> None:
        # From the slot start on, the spur's bed and the return's train
        # envelope (both `bed` wide) must not overlap in plan.
        p = SCALES[scale]
        slot = points(geometry(scale, p["spur"]), p["spur_from"])
        assert gap(slot, points(geometry(scale, p["ret"]))) >= p["bed"]

    def test_return_slot_is_clear_of_the_spurs_deck_stretch(self, scale) -> None:
        # The spur's track runs on the deck there, so the hole must keep
        # half the track plus half the slot away from its centreline.
        p = SCALES[scale]
        deck = points(geometry(scale, p["spur"]), 0, p["spur_from"])
        hole = points(geometry(scale, p["ret"]), 0, p["ret_to"])
        assert gap(deck, hole) >= p["track"] / 2 + p["bed"] / 2

    def test_slots_leave_a_web_of_deck_between_them(self, scale) -> None:
        p = SCALES[scale]
        spur_slot = points(geometry(scale, p["spur"]), p["spur_from"])
        ret_slot = points(geometry(scale, p["ret"]), 0, p["ret_to"])
        assert gap(spur_slot, ret_slot) >= p["bed"] + 10

    def test_return_fits_under_the_deck_past_its_slot(self, scale) -> None:
        p = SCALES[scale]
        assert p["ret_height"] + p["envelope"] <= p["deck_under"]
