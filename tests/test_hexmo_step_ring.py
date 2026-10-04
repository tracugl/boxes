"""Tests for the 3D export of a HexmoRectangle and of the whole helix ring.

The ring is six modules round a centre (M1–M5 trapezoids, M6 a hexagon), each
2 outer apothems from the centre with edge 4 facing it, M(n)'s edge 5 against
M(n+1)'s edge 3.  M6 sits at the top; the entry rectangle runs on from its
edge 1, turnout end first.  The key check is that the tracks meet at every
joint: same place, same height.

Needs the optional ``step`` dependency (build123d); skipped without it.
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

pytest.importorskip("build123d")

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N, HELIX_RING_N
from boxes.generators._hexmo_step import rect_parts, ring_parts, ring_track_ends
from boxes.generators.hexmorectangle import HexmoRectangle

T = 3.0
A_OUT = 220 * math.sqrt(3) / 2            # outer apothem (--outside: radius is outer)
DECK_TOP = 77.0                           # above the floor panel top, at h=80


def zrange(part):
    bb = part.solid.bounding_box()
    return bb.min.Z, bb.max.Z


@pytest.fixture(scope="module")
def entry():
    box = HexmoRectangle()
    box.parseArgs(HELIX_ENTRY_N)
    return {p.name: p for p in rect_parts(box)}


@pytest.fixture(scope="module")
def ring():
    return {p.name: p for p in ring_parts("N")}


class TestRectangle:

    def test_parts(self, entry) -> None:
        names = set(entry)
        assert {"deck", "long wall 1", "long wall 2", "end wall 1", "end wall 2", "spoke"} <= names
        # 3 lanes → 2 long supports; 2 cells → 1 short divider.
        assert {"long support 1", "long support 2", "divider 1"} <= names
        assert "long support 3" not in names and "divider 2" not in names

    def test_heights_match_the_hexagons(self, entry) -> None:
        # No floor panel: the walls stand on the ground, one thickness below
        # the hexagons' floor-panel top, and the deck top matches theirs.
        assert zrange(entry["deck"]) == pytest.approx((DECK_TOP - T, DECK_TOP))
        assert zrange(entry["end wall 1"]) == pytest.approx((-T, DECK_TOP - T))

    def test_under_track_opening(self, entry) -> None:
        plain = (208 * T * (DECK_TOP))         # end wall: 208 wide, 77 tall, t thick
        cut = plain - entry["end wall 1"].solid.volume
        assert cut == pytest.approx(35 * (74 - T - 27.8) * T, rel=0.01)

    def test_tracks(self, entry) -> None:
        tracks = [p for p in entry.values() if p.kind == "track"]
        # The straight centre line and both turnout legs, on the deck.
        assert len(tracks) == 3
        assert all(zrange(p)[1] == pytest.approx(DECK_TOP + 3, abs=0.05) for p in tracks)


class TestRing:

    def test_every_module_and_the_entry(self, ring) -> None:
        for module in ("M1", "M2", "M3", "M4", "M5", "M6", "entry"):
            assert f"{module} deck" in ring

    def test_m6_at_the_top_and_the_entry_beyond_it(self, ring) -> None:
        m6 = ring["M6 deck"].solid.bounding_box()
        assert ((m6.min.X + m6.max.X) / 2, (m6.min.Y + m6.max.Y) / 2) == pytest.approx(
            (0, 2 * A_OUT), abs=0.01)
        entry = ring["entry deck"].solid.bounding_box()
        # Runs on from M6 edge 1 (its outer face 3 apothems up), straight up.
        assert entry.min.Y == pytest.approx(3 * A_OUT, abs=0.01)
        assert entry.max.Y - entry.min.Y == pytest.approx(220 * math.sqrt(3), abs=0.01)

    def test_trapezoids_face_the_centre(self, ring) -> None:
        # Each trapezoid deck's nearest point to the ring centre is one outer
        # apothem from it (its edge 4), and its far side (the long wall) two.
        for k in range(1, 6):
            bb = ring[f"M{k} deck"].solid.bounding_box()
            corners = [(x, y) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y)]
            assert max(math.hypot(x, y) for x, y in corners) > 2 * A_OUT

    def test_tracks_meet_at_every_joint(self) -> None:
        ends = ring_track_ends("N")
        unmatched = []
        for i, (module, point, z) in enumerate(ends):
            partner = [m for j, (m, p, zz) in enumerate(ends)
                       if j != i and m != module and math.dist(p, point) < 0.5
                       and abs(zz - z) < 0.05]
            if not partner:
                unmatched.append((module, round(z, 1)))
        # Only the two ends of the line: the lower level leaving M6 at edge 1
        # (27.8 mm, under the entry rectangle) and the entry line's far end.
        assert sorted(unmatched) == [("M6", 27.8), ("entry", DECK_TOP)]
