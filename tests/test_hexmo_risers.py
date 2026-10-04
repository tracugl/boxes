"""Tests for riser boards under a descending track (``--risers``).

A riser is a track-bed strip along the track's route plus supports standing
across the track on the floor panel, each cut to the bed's height there.  The
supports' bottom tabs go into floor-panel slots and their top tabs into slots
in the bed.

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

from boxes.generators._hexmo_risers import (
    END_INSET, RiserSpec, parse_risers, strip_outline, support_stations,
)
from boxes.generators._hexmo_track_routes import route_geometry
from boxes.generators.hexmohexagon import HexmoHexagon

T = 3.0
R_IN = 220 - T / math.cos(math.radians(30))
APOTHEM = R_IN * math.sqrt(3) / 2

# Helix ring M1 at h=80 (trains run edge 3 → 5): the spur moves in from 17.5 to
# 35 mm inside and falls from 72.5 to 65.2 across the module.
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--track_lead_in=26",
      "--track_width=17", "--bottom=closed", "--support_length=55",
      "--support_position=125", "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
      "--track_openings=3:-17.5:72.5:26,5:35:65.2:26", "--deck_slots=3:-17.5-5:-35/26"]
M1_RISER = "--risers=3:-17.5-5:-35~72.5..65.2"


def walk(start, heading, steps):
    x, y = start
    h = math.radians(heading)
    for step in steps:
        if step[0] == "edge":
            x += step[1] * math.cos(h)
            y += step[1] * math.sin(h)
            continue
        a, radius = math.radians(step[1]), step[2]
        if radius:
            sign = 1 if a > 0 else -1
            cx, cy = x - sign * radius * math.sin(h), y + sign * radius * math.cos(h)
            ang = math.atan2(y - cy, x - cx) + a
            x, y = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
        h += a
    return x, y


def render(args):
    """Render; return (support wall calls (width, height), floor holes, bed holes)."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    supports, floor, bed = [], [], []
    orig_wall, orig_floor, orig_draw = (box.rectangularWall, box.drawRiserFloorHoles,
                                        box.drawRiser)

    def wall_spy(x, y, edges="eeee", *a, **kw):
        if str(kw.get("label", "")).startswith("riser "):
            supports.append((x, y))
        return orig_wall(x, y, edges, *a, **kw)

    def floor_spy(plan, isTrapezoid):
        floor.append(sum(len(r["stations"]) for r in plan))
        return orig_floor(plan, isTrapezoid)

    def draw_spy(riser, move="right"):
        bed.append(len(riser["stations"]))
        return orig_draw(riser, move)

    box.rectangularWall, box.drawRiserFloorHoles, box.drawRiser = wall_spy, floor_spy, draw_spy
    box.open()
    box.render()
    box.close()
    return supports, floor, bed


class TestParsing:

    def test_entry(self) -> None:
        assert parse_risers("3:-17.5-5:-35~72.5..65.2, 1:-17.5-5:17.5@157..~97..92.5/20") == [
            RiserSpec(3, -17.5, 5, -35.0, None, None, 72.5, 65.2, None),
            RiserSpec(1, -17.5, 5, 17.5, 157.0, None, 97.0, 92.5, 20.0),
        ]

    @pytest.mark.parametrize("text", ["3-5", "3-5~70", "3-5~70..60/0", "3-5@9..2~70..60"])
    def test_bad(self, text) -> None:
        with pytest.raises(ValueError, match="--risers"):
            parse_risers(text)


class TestGeometry:

    def test_stations(self) -> None:
        stations = support_stations(330.0, 80.0)
        assert stations[0] == pytest.approx(END_INSET)
        assert stations[-1] == pytest.approx(330 - END_INSET)
        assert max(b - a for a, b in zip(stations, stations[1:])) <= 80.0 + 1e-9

    def test_short_bed_gets_one_support(self) -> None:
        assert support_stations(20.0, 80.0) == [10.0]

    @pytest.mark.parametrize("route", [(3, -17.5, 5, -35.0), (1, -17.5, 5, 17.5), (4, 0, 1, 20)])
    def test_strip_outline_closes(self, route) -> None:
        g = route_geometry(*route, APOTHEM, 26.0)
        start, heading, steps = strip_outline(list(g.segments), 17.0)
        assert walk(start, heading, steps) == pytest.approx(start, abs=1e-6)


class TestRender:

    def test_m1_riser(self) -> None:
        supports, floor, bed = render(M1 + [M1_RISER])
        assert bed == floor == [len(supports)]
        # Each support: the bed's width wide, up to the bed's underside, and
        # the heights fall from near 72.5 towards 65.2 along the bed.
        widths = {w for w, _ in supports}
        heights = [h + T for _, h in supports]
        assert widths == {17.0}
        assert heights == sorted(heights, reverse=True)
        assert 65.2 < heights[-1] < heights[0] < 72.5

    def test_off_by_default(self) -> None:
        assert render(M1) == ([], [], [])


class TestRefused:


    def test_height_above_the_deck(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            render(M1 + ["--risers=3:-17.5-5:-35~90..65"])

    def test_support_on_a_support_wall(self) -> None:
        # The default support position (≈94 mm out) is under the spur.
        args = [a for a in M1 if a not in ("--support_position=125",
                                           "--deck_slots=3:-17.5-5:-35/26")]
        with pytest.raises(ValueError, match="support wall"):
            render(args + [M1_RISER])

    def test_support_in_another_track(self) -> None:
        with pytest.raises(ValueError, match="stand in the track"):
            render(M1 + ["--risers=3:-17.5-5:-35~72.5..65.2,3:-35-5:-35~40..40"])
