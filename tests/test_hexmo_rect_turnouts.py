"""Tests for turnouts etched on a HexmoRectangle deck (``--turnouts``).

A turnout's through road is one of the rectangle's straight track lines; its
diverging leg leaves at the toe on a ``--turnout_radius`` curve to the
``--turnout_angle`` crossing angle, runs straight past the heel, and a
``--turnout_reverse_radius`` curve brings it back parallel at its target
offset, which it keeps to the end of the module.  The helix ring's entry
rectangle carries two Peco medium turnouts (the defaults): T1 splits loop A
off to −35, T2 (toe at T1's heel) loop B to +35, and the centre line runs on
as the spur.

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

from boxes.generators._hexmo_turnouts import TurnoutSpec, parse_turnouts, turnout_leg
from boxes.generators.hexmorectangle import HexmoRectangle

# Peco N medium (SL-E395/396) and the N rectangle's 375.1 mm deck.
PECO_N = dict(length=123.7, radius=457.0, angle=14.0, reverse_radius=300.0)
N_RECT = ["--radius=220", "--thickness=3", "--h=80", "--track_width=17", "--track_lead_in=26",
          "--num_rows=3", "--reference=0"]
HELIX = "--turnouts=10:0:-35,133.7:0:35"
# The N deck is the short wall (220 − 2t) less the two long walls: 208 mm.
DECK_WIDTH = 220 - 4 * 3


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
        leg = turnout_leg(TurnoutSpec(10, 0, -35), 375.0, **PECO_N)
        assert joined(leg.segments)
        # Leaves the through road at the toe, heading straight on.
        assert leg.segments[0].p0 == pytest.approx((10, 0))
        # Peco medium: 16.9 mm off the through road at the heel, 123.7 mm on.
        assert leg.heel == pytest.approx((133.7, -16.9), abs=0.05)
        # Back parallel at −35 by 243 mm, and on to the end of the module.
        assert leg.parallel_from == pytest.approx(243.3, abs=0.1)
        assert leg.segments[-1].p1 == pytest.approx((375.0, -35))
        assert leg.segments[-1].direction == pytest.approx((1, 0))

    def test_helix_t2_mirrors_t1(self) -> None:
        leg = turnout_leg(TurnoutSpec(133.7, 0, 35), 375.0, **PECO_N)
        assert leg.heel == pytest.approx((257.4, 16.9), abs=0.05)
        assert leg.parallel_from == pytest.approx(367.0, abs=0.1)
        assert leg.segments[-1].p1 == pytest.approx((375.0, 35))

    def test_too_close_to_spread(self) -> None:
        with pytest.raises(ValueError, match="too close"):
            turnout_leg(TurnoutSpec(10, 0, 20), 375.0, **PECO_N)

    def test_runs_past_the_end(self) -> None:
        with pytest.raises(ValueError, match="past the end"):
            turnout_leg(TurnoutSpec(200, 0, 35), 375.0, **PECO_N)


def render(args):
    """Render; return the leg centrelines handed to the etcher (deck frame)."""
    box = HexmoRectangle()
    box.parseArgs(N_RECT + args)
    box.metadata["reproducible"] = True
    legs = []
    orig = box._etchTurnoutLeg

    def spy(segments):
        legs.append(segments)
        return orig(segments)

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
        # Both legs end at the M6 end of the deck, 35 mm either side of the
        # centre line, parallel to it.
        assert a[-1].p1[1] == pytest.approx(centre - 35)
        assert b[-1].p1[1] == pytest.approx(centre + 35)
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
