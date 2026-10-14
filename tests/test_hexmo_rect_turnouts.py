"""Tests for turnouts etched on a HexmoRectangle deck (``--turnouts``).

A turnout's through road is one of the rectangle's straight track lines; its
diverging leg leaves at the toe on a ``--turnout_radius`` curve to the
``--turnout_angle`` crossing angle, runs straight past the heel, and a
``--turnout_reverse_radius`` curve brings it back parallel at its target
offset, which it keeps to the end of the module.  The N helix ring's entry
rectangle carries two Peco N Code 80 medium turnouts: T1 splits loop A off to
−40, T2 (toe at T1's heel) loop B to +40, and the centre line runs on as the
spur.

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

from boxes.generators._hexmo_turnouts import (
    TurnoutSpec, crossover_leg, parse_turnouts, turnout_leg,
)
from boxes.generators.hexmorectangle import HexmoRectangle

# Peco N Code 80 medium (SL-E395/396) and the N rectangle's 427 mm deck.
PECO_N = dict(length=123.7, radius=457.0, angle=12.0, reverse_radius=300.0)
DECK = 427.0
N_RECT = ["--radius=250", "--thickness=3", "--h=80", "--track_width=17", "--track_lead_in=20",
          "--num_rows=3", "--reference=0",
          # Peco N medium (the turnout defaults are HO's).
          "--turnout_length=123.7", "--turnout_radius=457", "--turnout_angle=12",
          "--turnout_reverse_radius=300"]
HELIX = "--turnouts=10:0:-40,133.7:0:40"
# The N deck is the short wall (250 − 2t) less the two long walls: 238 mm.
DECK_WIDTH = 250 - 4 * 3


def joined(segments):
    """True when every piece starts where the previous one ends."""
    return all(math.dist(a.p1, b.p0) < 1e-6 for a, b in zip(segments, segments[1:]))


class TestParsing:

    def test_entries(self) -> None:
        assert parse_turnouts("10:0:-35, 133.7:0:35") == [
            TurnoutSpec(10.0, 0.0, -35.0), TurnoutSpec(133.7, 0.0, 35.0)]

    def test_blank_is_none(self) -> None:
        assert parse_turnouts("") == []

    @pytest.mark.parametrize("text", ["10:0", "a:0:3", "10:0:0", "-5:0:35", "10:0:35:1"])
    def test_bad(self, text) -> None:
        with pytest.raises(ValueError, match="--turnouts"):
            parse_turnouts(text)


class TestLeg:

    def test_helix_t1(self) -> None:
        leg = turnout_leg(TurnoutSpec(10, 0, -40), DECK, **PECO_N)
        assert joined(leg.segments)
        # Leaves the through road at the toe, heading straight on.
        assert leg.segments[0].p0 == pytest.approx((10, 0))
        # Peco medium: 16.1 mm off the through road at the heel, 123.7 mm on.
        assert leg.heel == pytest.approx((133.7, -16.1), abs=0.05)
        # Back parallel at −40 by 278 mm, and on to the end of the module.
        assert leg.parallel_from == pytest.approx(277.7, abs=0.1)
        assert leg.segments[-1].p1 == pytest.approx((DECK, -40))
        assert leg.segments[-1].direction == pytest.approx((1, 0))

    def test_helix_t2_mirrors_t1(self) -> None:
        leg = turnout_leg(TurnoutSpec(133.7, 0, 40), DECK, **PECO_N)
        assert leg.heel == pytest.approx((257.4, 16.1), abs=0.05)
        assert leg.parallel_from == pytest.approx(401.4, abs=0.1)
        assert leg.segments[-1].p1 == pytest.approx((DECK, 40))

    def test_too_close_to_spread(self) -> None:
        with pytest.raises(ValueError, match="too close"):
            turnout_leg(TurnoutSpec(10, 0, 20), DECK, **PECO_N)

    def test_runs_past_the_end(self) -> None:
        with pytest.raises(ValueError, match="past the end"):
            turnout_leg(TurnoutSpec(200, 0, 40), DECK, **PECO_N)


def render(args):
    """Render; return the leg centrelines handed to the etcher (deck frame)."""
    box = HexmoRectangle()
    box.parseArgs(N_RECT + args)
    box.metadata["reproducible"] = True
    legs = []
    orig = box._etchTurnoutLeg

    def spy(segments, **kwargs):
        legs.append(segments)
        return orig(segments, **kwargs)

    box._etchTurnoutLeg = spy
    box.open()
    box.render()
    box.close()
    return legs


class TestRender:

    def test_helix_entry(self) -> None:
        legs = render([HELIX])
        assert len(legs) == 2
        a, b = legs
        centre = DECK_WIDTH / 2
        # Both legs end at the M6 end of the deck, 40 mm either side of the
        # centre line, parallel to it.
        assert a[-1].p1[1] == pytest.approx(centre - 40)
        assert b[-1].p1[1] == pytest.approx(centre + 40)
        assert a[-1].p1[0] == pytest.approx(b[-1].p1[0])

    def test_off_by_default(self) -> None:
        assert render([]) == []

    def test_leg_off_the_deck_is_refused(self) -> None:
        with pytest.raises(ValueError, match="deck"):
            render(["--turnouts=10:0:-100"])

    def test_with_the_lower_level_passage(self) -> None:
        legs = render([HELIX, "--under_track=1", "--under_track_height=27.8",
                       "--under_track_width=35"])
        assert len(legs) == 2


class TestTrackGuides:
    """With turnouts the two end walls carry different tracks: the toe end
    only the straight lines, the far end those and every diverging leg.  Each
    end gets its own guide plate, with a window for each track crossing it."""

    @staticmethod
    def guides(args):
        box = HexmoRectangle()
        box.parseArgs(args)
        calls = []
        orig = box.drawTrackGuide

        def spy(s, l, move="right", offsets=None, label="track guide", arrow=None):
            used = offsets if offsets is not None else box._trackOffsets()
            calls.append((label, len(box._trackGuideWindows(s, l, used))))
            return orig(s, l, move, offsets, label, arrow)

        box.drawTrackGuide = spy
        box.open()
        box.render()
        return calls

    def test_helix_entry_has_a_plate_per_end(self) -> None:
        from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N250
        assert self.guides(HELIX_ENTRY_N250) == [("track guide turnout toe end", 1),
                                              ("track guide turnout leg end", 3)]

    def test_without_turnouts_one_plate(self) -> None:
        assert self.guides(["--track_guide=1"]) == [("track guide", 1)]


class TestCrossover:
    """Two Peco N Code 80 medium turnouts heel to heel between tracks 40 mm apart
    (--crossovers): the first's diverging road, a straight, and the second's
    back onto the other track, ending at its toe."""

    N = dict(length=123.7, radius=457.0, angle=12.0)
    TRACKS = ["--track_line_count=2", "--track_spacing=40"]

    def test_geometry(self) -> None:
        leg = crossover_leg(TurnoutSpec(71, -20, 20), DECK, **self.N)
        first, straight, second = leg.segments
        assert joined(leg.segments)
        assert first.p0 == pytest.approx((71, -20))
        # Ends on the other track, parallel to it, 284.3 mm on: nothing runs
        # past the second toe.
        assert second.p1 == pytest.approx((71 + 284.3, 20), abs=0.1)
        assert first.radius == second.radius == pytest.approx(457)
        # Both heels (123.7 mm from each toe) lie on the straight.
        assert straight.p0[0] < 71 + 123.7 and straight.p1[0] > 71 + 284.3 - 123.7

    def test_too_close(self) -> None:
        with pytest.raises(ValueError, match="at least 32.2"):
            crossover_leg(TurnoutSpec(71, -15, 15), DECK, **self.N)

    def test_past_the_end(self) -> None:
        with pytest.raises(ValueError, match="past the end"):
            crossover_leg(TurnoutSpec(200, -20, 20), DECK, **self.N)

    def test_render(self) -> None:
        legs = render(self.TRACKS + ["--crossovers=50:-20:20"])
        assert len(legs) == 1
        leg = legs[0]
        centre = DECK_WIDTH / 2
        assert leg[0].p0[1] == pytest.approx(centre - 20)
        assert leg[-1].p1[1] == pytest.approx(centre + 20)

    def test_must_join_two_tracks(self) -> None:
        with pytest.raises(ValueError, match="no straight track at offset 0"):
            render(self.TRACKS + ["--crossovers=50:0:20"])

    def test_a_track_piece_ending_on_the_other_track(self) -> None:
        from boxes.generators import _hexmo_step as S
        box = HexmoRectangle()
        box.parseArgs(N_RECT + self.TRACKS + ["--crossovers=50:-20:20"])
        piece = next(p for p in S.rect_pieces(box) if p.name == "crossover 1")
        # It ends mid-deck on the +20 track, not at a module edge.
        assert piece.ends == []
        assert piece.segments[-1].p1[1] == pytest.approx(20)
