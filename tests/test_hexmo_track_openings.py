"""Tests for HexmoHexagon track openings in joint walls (``--track_openings``).

A track that crosses a joint below deck level needs an opening in the wall
there, at its offset along the edge and its height.  When a 40 mm train on it
fits under one thickness of wall below the deck the opening is a closed hole;
otherwise it is a notch open at the top of the wall, and the deck edge above
is left plain over it.  The wall's and the deck's finger joints are split
round the notch so they still mate finger for finger.

Hex side walls are drawn with x up the wall from the floor panel (0) to the
deck underside (l), and y along the wall in the pattern frame (wall centre at
side_orig / 2).

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

from hexmo_testutil import IGNORE_CORE_MATMUL, PLAIN_WALLS

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_track_openings import (
    SplitJointEdge, TrackOpening, parse_track_openings, wall_and_deck_pieces,
)
from boxes.generators.hexmohexagon import HexmoHexagon

T = 3.0
N_HEX = ["--radius=220", "--thickness=3", "--h=100"]
L = 100 - 2 * T                          # wall body: floor panel top to deck underside
SIDE_ORIG = 2 * (220 - T / math.cos(math.radians(30))) * math.sin(math.radians(30))
SIDE = SIDE_ORIG - 2 * T                 # wall top-edge length


def render(args):
    """Render; return (rectangularHole calls, SplitJointEdge calls)."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    holes, splits = [], []
    orig_rect = box.rectangularHole

    def rect_spy(x, y, dx, dy, r=0, center_x=True, center_y=True):
        holes.append((x, y, dx, dy))
        return orig_rect(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

    orig_call = SplitJointEdge.__call__

    def split_spy(self, length, **kw):
        splits.append((type(self.base).__name__, length, list(self.pieces)))
        return orig_call(self, length, **kw)

    box.rectangularHole = rect_spy
    SplitJointEdge.__call__ = split_spy
    try:
        box.open()
        box.render()
        box.close()
    finally:
        SplitJointEdge.__call__ = orig_call
    return holes, splits


class TestParsing:

    def test_entries(self) -> None:
        assert parse_track_openings("5:17.5:92.5:26, 3:-35:85.2", 30) == [
            TrackOpening(5, 17.5, 92.5, 26.0), TrackOpening(3, -35.0, 85.2, 30.0)]

    @pytest.mark.parametrize("text", ["5:17.5", "7:0:50", "5:a:50", "5:0:50:0"])
    def test_bad_entries(self, text) -> None:
        with pytest.raises(ValueError, match="--track_openings"):
            parse_track_openings(text, 30)


class TestPieces:

    def test_wall_and_deck_cover_the_same_stretches(self) -> None:
        wall, deck = wall_and_deck_pieces(SIDE, SIDE_ORIG, [(17.5, 26.0, 20.0)])
        assert sum(p[1] for p in wall) == pytest.approx(SIDE)
        assert sum(p[1] for p in deck) == pytest.approx(SIDE_ORIG)
        # Deck: plain stub, joint, plain gap, joint, plain stub.
        assert [p[0] for p in deck] == ["plain", "joint", "plain", "joint", "plain"]
        assert [p[0] for p in wall] == ["joint", "notch", "joint"]
        assert deck[0][1] == deck[-1][1] == pytest.approx(T)
        # Matching joint pieces are exactly the same length, so their fingers
        # are spaced identically.
        assert deck[1][1] == pytest.approx(wall[0][1])
        assert deck[3][1] == pytest.approx(wall[2][1])
        # The notch sits 17.5 mm from the middle, 26 wide, 20 deep.
        assert wall[0][1] + 13 == pytest.approx(SIDE / 2 + 17.5)
        assert wall[1] == ("notch", pytest.approx(26.0), 20.0)
        assert deck[2] == ("plain", pytest.approx(26.0))

    def test_overlapping_notches_are_refused(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            wall_and_deck_pieces(SIDE, SIDE_ORIG, [(0, 30, 10), (10, 30, 10)])


class TestClosedOpening:

    def test_low_track_gets_a_closed_hole(self) -> None:
        # 30 + 43 = 73, under the 91 mm limit (one thickness below the deck).
        holes, splits = render(N_HEX + ["--track_openings=1:-20:30:26"])
        assert splits == []
        opening = [h for h in holes if h[2:] == (pytest.approx(L - T - 30), pytest.approx(26))]
        assert len(opening) == 1
        x, y, dx, dy = opening[0]
        assert x - dx / 2 == pytest.approx(30)
        assert y == pytest.approx(SIDE_ORIG / 2 - 20)


class TestNotch:

    def test_high_track_gets_a_notch_in_wall_and_plain_deck_edge(self) -> None:
        holes, splits = render(N_HEX + ["--track_openings=5:17.5:80:26"])
        bases = sorted(b for b, _, _ in splits)
        # One split wall top edge (positive fingers) and one split deck edge
        # (the counterpart).
        assert bases == ["FingerJointEdge", "FingerJointEdgeCounterPart"]
        wall = next(p for b, _, p in splits if b == "FingerJointEdge")
        assert wall[1] == ("notch", pytest.approx(26.0), pytest.approx(L - 80))
        # No hole is cut for a notch.
        assert not [h for h in holes if pytest.approx(26) in h[2:]]

    def test_trapezoid_ring_module(self) -> None:
        # M1 of the helix ring at h=80 (trains run edge 3 → 5): the spur enters
        # at edge 3, 17.5 towards edge 4 (−17.5 anticlockwise), and leaves at
        # edge 5, 35 towards edge 4 (+35), both above the 43 mm train
        # envelope → two notches.
        _, splits = render(["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1",
                            "--track_openings=3:-17.5:72.5:26,5:35:65.2:26"])
        assert len([s for s in splits if s[0] == "FingerJointEdge"]) == 2
        assert len([s for s in splits if s[0] == "FingerJointEdgeCounterPart"]) == 2


class TestFlushWithTheWallTop:
    """A track crossing the joint exactly at the deck underside rests on the wall top.

    Nothing is cut out of the wall: its top edge just goes plain (no fingers)
    across the opening, as does the deck edge above it, so a deck slot can
    still run out over the joint.  This avoids a sliver of a notch where a
    descending track has only just left the deck (the helix ring's M6/M1
    joint).
    """

    def test_zero_depth_notch_is_a_plain_stretch_of_wall_top(self) -> None:
        wall, deck = wall_and_deck_pieces(SIDE, SIDE_ORIG, [(17.5, 35.0, 0.0)])
        assert [p[0] for p in wall] == ["joint", "plain", "joint"]
        assert wall[1] == ("plain", pytest.approx(35.0))
        assert deck[2] == ("plain", pytest.approx(35.0))

    def test_opening_at_the_deck_underside_cuts_nothing_from_the_wall(self) -> None:
        holes, splits = render(N_HEX + [f"--track_openings=5:17.5:{L:g}:35"])
        wall = next(p for b, _, p in splits if b == "FingerJointEdge")
        assert [p[0] for p in wall] == ["joint", "plain", "joint"]
        assert not [p for p in wall if p[0] == "notch"]
        assert not [h for h in holes if pytest.approx(35) in h[2:]]

    def test_a_deck_slot_can_run_out_over_it(self) -> None:
        # Helix ring M1 at h=80 with the spur crossing from M6 on the wall top.
        render(["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1",
                "--track_lead_in=26", "--supports=0",
                "--track_openings=3:-17.5:74:35,5:35:66.1:35",
                "--deck_slots=3:-17.5-5:-35/35"])

    def test_above_the_deck_underside_is_still_refused(self) -> None:
        with pytest.raises(ValueError, match="deck"):
            render(N_HEX + [f"--track_openings=5:17.5:{L + 0.1:g}:35"])


class TestRefused:

    @pytest.mark.parametrize("spec, match", [
        ("5:0:2", "floor"),
        ("5:0:95", "deck"),
        ("1:0:50", "trapezoid"),
        # Over a small pin (63 mm off centre, 15 and 59 mm up): still refused.
        ("3:-50:30:30", "registration"),
        ("5:0:60:26,5:10:60:26", "overlap"),
    ])
    def test_refused(self, spec, match) -> None:
        args = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1",
                f"--track_openings={spec}"]
        if spec == "5:0:95":
            args = N_HEX + ["--trapezoid=1", f"--track_openings={spec}"]
        with pytest.raises(ValueError, match=match):
            render(args)


class TestMediumHolesGiveWay:
    """A medium (cable) hole an opening needs the room of is left out."""

    def test_m5_at_h80_with_35mm_notches(self) -> None:
        # The M4/M5 (43.9) and M5/M6 (36.5) joints: each notch takes one
        # medium hole's room on its wall, and nothing else gives way.
        box = HexmoHexagon()
        box.parseArgs(["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1",
                       "--track_openings=3:-35:43.9:35,5:35:36.5:35"] + PLAIN_WALLS)
        box.metadata["reproducible"] = True
        dropped = []
        orig = box._checkTrackOpenings
        box._checkTrackOpenings = lambda *a, **kw: (dropped.append(orig(*a, **kw)), dropped[-1])[1]
        box.open()
        box.render()
        box.close()
        assert [len(d) for d in dropped] == [1, 1]
        assert all(r == HexmoHexagon._R2 for d in dropped for _, _, r in d)
