"""Tests for deck slots along a descending track (``--deck_slots``).

A slot follows a track route (as in ``--track_routes``) over a stretch of its
length, at a set width, and is cut through the deck so the track can drop
away below it.  A slot reaching a deck edge needs a wall notch there
(``--track_openings``), and slots must keep clear of the support slots.

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

from boxes.generators._hexmo_deck_slots import (
    DeckSlot, parse_deck_slots, slot_outline, trim_segments,
)
from boxes.generators._hexmo_track_routes import route_geometry
from boxes.generators.hexmohexagon import HexmoHexagon

R_IN = 220 - 3 / math.cos(math.radians(30))
APOTHEM = R_IN * math.sqrt(3) / 2
LEAD = 26.0

# Helix-ring M1 at h=80 (trains run edge 3 → 5): the spur notches at both
# ends, and its slot from edge 3 to edge 5 (inside of the curve, so negative
# offsets: −17.5 at edge 3 moving in to −35 at edge 5).
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--track_lead_in=26",
      "--supports=0", "--track_openings=3:-17.5:72.5:26,5:35:65.2:26"]
M1_SLOT = "--deck_slots=3:-17.5-5:-35/26"


def walk(start, heading, steps):
    """Follow turtle steps without burn; return the end point."""
    x, y = start
    h = math.radians(heading)
    for step in steps:
        if step[0] == "edge":
            x += step[1] * math.cos(h)
            y += step[1] * math.sin(h)
        else:
            deg, radius = step[1], step[2]
            a = math.radians(deg)
            if radius == 0:
                h += a
                continue
            # Arc of `radius` turning by `a` (left positive).
            cx = x - radius * math.sin(h) * (1 if a > 0 else -1)
            cy = y + radius * math.cos(h) * (1 if a > 0 else -1)
            ang = math.atan2(y - cy, x - cx) + a
            x, y = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
            h += a
    return x, y


def render(args):
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    outlines = []
    orig = box._drawDeckSlotOutline
    box._drawDeckSlotOutline = lambda *a, **kw: (outlines.append(a), orig(*a, **kw))[1]
    box.open()
    box.render()
    box.close()
    return outlines


class TestParsing:

    def test_entries(self) -> None:
        assert parse_deck_slots("1:-17.5-5:17.5@157.., 3:35-1@..262/26", 30) == [
            DeckSlot(1, -17.5, 5, 17.5, 157.0, None, 30.0),
            DeckSlot(3, 35.0, 1, 35.0, None, 262.0, 26.0),
        ]

    def test_route_without_offsets_is_the_centre_line(self) -> None:
        (slot,) = parse_deck_slots("5-3", 30)
        assert (slot.start_offset, slot.end_offset, slot.lo, slot.hi) == (0.0, 0.0, None, None)

    @pytest.mark.parametrize("text", ["1-5@20..10", "1-5/0", "1-5@x..", "9-5"])
    def test_bad(self, text) -> None:
        with pytest.raises(ValueError, match="--deck_slots"):
            parse_deck_slots(text, 30)


class TestGeometry:

    def test_trim_keeps_the_stretch_length(self) -> None:
        g = route_geometry(1, -17.5, 5, 17.5, APOTHEM, LEAD)
        part = trim_segments(g.segments, 40.0, 200.0)
        assert sum(s.length for s in part) == pytest.approx(160.0)

    def test_trim_runs_on_past_the_ends(self) -> None:
        g = route_geometry(5, 0, 3, 0, APOTHEM, LEAD)
        total = sum(s.length for s in g.segments)
        part = trim_segments(g.segments, -1.0, total + 1.0)
        assert sum(s.length for s in part) == pytest.approx(total + 2.0)

    @pytest.mark.parametrize("route", [(5, -17.5, 3, -35.0), (1, -17.5, 5, 17.5), (4, 0, 1, 20)])
    def test_outline_closes(self, route) -> None:
        g = route_geometry(*route, APOTHEM, LEAD)
        start, heading, steps = slot_outline(list(g.segments), 26.0)
        assert walk(start, heading, steps) == pytest.approx(start, abs=1e-6)

    def test_outline_sides_are_offset_by_half_the_width(self) -> None:
        g = route_geometry(5, -17.5, 3, -17.5, APOTHEM, LEAD)
        _, _, steps = slot_outline(list(g.segments), 26.0)
        radii = sorted(st[2] for st in steps if st[0] == "corner" and st[2] > 0)
        assert radii == pytest.approx([g.radius - 13, g.radius + 13])


class TestRender:

    def test_m1_slot_is_cut(self) -> None:
        assert len(render(M1 + [M1_SLOT])) == 1

    def test_stretch_short_of_the_edges_needs_no_notch(self) -> None:
        args = [a for a in M1 if not a.startswith("--track_openings")]
        assert len(render(args + ["--deck_slots=3:-17.5-5:-35@60..250/26"])) == 1

    def test_slot_without_track_lines(self) -> None:
        assert len(render(M1 + [M1_SLOT, "--track_lines=0"])) == 1

    def test_off_by_default(self) -> None:
        assert render(M1) == []


class TestRefused:

    def test_reaching_an_edge_without_a_notch(self) -> None:
        args = [a for a in M1 if not a.startswith("--track_openings")]
        with pytest.raises(ValueError, match="notch"):
            render(args + [M1_SLOT])

    def test_notch_narrower_than_the_slot(self) -> None:
        with pytest.raises(ValueError, match="notch"):
            render(M1 + ["--deck_slots=3:-17.5-5:-35/30"])

    def test_crossing_a_support(self) -> None:
        args = [a for a in M1 if a != "--supports=0"] + ["--supports=1", "--support_length=55"]
        with pytest.raises(ValueError, match="support"):
            render(args + [M1_SLOT])

    def test_trapezoid_edges(self) -> None:
        with pytest.raises(ValueError, match="trapezoid"):
            render(M1 + ["--deck_slots=1-5"])

    def test_stretch_past_the_route(self) -> None:
        with pytest.raises(ValueError, match="stretch"):
            render(M1 + ["--deck_slots=3:-17.5-5:-35@10..900"])


class TestStripAtTheDeckEdge:
    """A slot reaching a deck edge leaves a strip of deck over the wall.

    The strip keeps an edge-to-edge slotted deck in one piece until it is
    fitted; it is cut away by hand afterwards.
    """

    def test_slot_stops_short_of_the_decks_outer_edge(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(M1 + [M1_SLOT])
        box.open()
        notches = {3: [(-17.5, 26.0, 7.5)], 5: [(35.0, 26.0, 15.0)]}
        ((segments, _),) = box._deckSlotPlan(R_IN, True, notches)
        # Routes end at the wall's inner face (the apothem); the slot runs
        # 1 mm past it, and the deck one thickness (3 mm), leaving 2 mm.
        for point, edge_angle in ((segments[0].p0, 330), (segments[-1].p1, 210)):
            n = (math.cos(math.radians(edge_angle)), math.sin(math.radians(edge_angle)))
            reach = point[0] * n[0] + point[1] * n[1]
            assert reach == pytest.approx(APOTHEM + 1)
            assert (APOTHEM + 3) - reach == pytest.approx(2)
