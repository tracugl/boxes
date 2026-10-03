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

from hexmo_testutil import IGNORE_CORE_MATMUL

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
        # M1 of the helix ring at h=80: the spur crosses edge 5 at +17.5 and
        # edge 3 at −35, both above the 43 mm train envelope → two notches.
        _, splits = render(["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1",
                            "--track_openings=5:17.5:72.5:26,3:-35:65.2:26"])
        assert len([s for s in splits if s[0] == "FingerJointEdge"]) == 2
        assert len([s for s in splits if s[0] == "FingerJointEdgeCounterPart"]) == 2


class TestRefused:

    @pytest.mark.parametrize("spec, match", [
        ("5:0:2", "floor"),
        ("5:0:95", "deck"),
        ("1:0:50", "trapezoid"),
        ("3:-35:30:30", "registration"),
        ("5:0:60:26,5:10:60:26", "overlap"),
    ])
    def test_refused(self, spec, match) -> None:
        args = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1",
                f"--track_openings={spec}"]
        if spec == "5:0:95":
            args = N_HEX + ["--trapezoid=1", f"--track_openings={spec}"]
        with pytest.raises(ValueError, match=match):
            render(args)
