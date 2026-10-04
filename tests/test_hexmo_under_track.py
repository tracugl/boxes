"""Tests for the under-deck track opening (``--under_track_*``).

A lower-level track can pass under a module's deck, through a joint wall.
Instead of the centre big hole (centred halfway up the wall), the chosen
walls get a rectangular opening on the wall's centre line that hangs from
just under the deck: its top is one material thickness below the deck
underside, its bottom at the track height.  HexmoHexagon picks the walls by
edge (``--under_track_edges``); HexmoRectangle cuts it through both end walls
and every short divider (``--under_track``), so the track can run end to end.

Hex side walls are drawn with x running up the wall from the floor panel
(x = 0) to the deck underside (x = l).  Rect end walls and dividers are drawn
with y running down from the deck underside (y = 0).  Both generators must
cut the same opening relative to the deck and the wall centre, so joined
modules line up.

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

from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

T = 3.0
N_HEX = ["--radius=220", "--thickness=3", "--h=100"]
# Three column compartments → two short (horizontal) dividers.
N_RECT = ["--radius=220", "--thickness=3", "--h=100", "--num_columns=3"]
WIDTH = 30.0          # default opening width
ENVELOPE = 43.0       # track (3) + a 40 mm train: the automatic opening height


def rendered(cls, args):
    """Render and return (box, openings, big_circle_count).

    ``openings`` are the rectangularHole calls of opening size, as
    ``(x, y, dx, dy)`` in the calling wall's frame.  Big holes are circles by
    default, so every rectangularHole of at least the opening width (and not
    the track guide's) is an opening.
    """
    box = cls()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    calls, circles = [], [0]
    orig_rect, orig_hole = box.rectangularHole, box.hole

    def rect_spy(x, y, dx, dy, r=0, center_x=True, center_y=True):
        calls.append((x, y, dx, dy))
        return orig_rect(x, y, dx, dy, r=r, center_x=center_x, center_y=center_y)

    def hole_spy(x, y, r=0.0, d=0.0, **kw):
        if (r or d / 2) == pytest.approx(box_big_r(box)):
            circles[0] += 1
        return orig_hole(x, y, r=r, d=d, **kw)

    box.rectangularHole, box.hole = rect_spy, hole_spy
    box.open()
    box.render()
    box.close()
    width = getattr(box, "under_track_width", WIDTH)
    openings = [c for c in calls
                if min(c[2], c[3]) > 10 and pytest.approx(width) in (c[2], c[3])]
    return box, openings, circles[0]


def box_big_r(box):
    return (box.h - 2 * box._SPACER) / 2


def hex_span(opening):
    """(bottom, top) of a hex-wall opening, in mm above the floor panel."""
    x, _, dx, _ = opening
    return x - dx / 2, x + dx / 2


class TestHexagon:

    def test_off_by_default(self) -> None:
        _, openings, _ = rendered(HexmoHexagon, N_HEX)
        assert openings == []

    def test_one_wall_gets_the_opening_instead_of_its_centre_hole(self) -> None:
        _, plain, plain_bigs = rendered(HexmoHexagon, N_HEX)
        box, openings, bigs = rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1"])
        assert len(openings) == 1
        assert bigs == plain_bigs - 1

    def test_automatic_height_fits_track_and_train_under_the_deck(self) -> None:
        box, (opening,), _ = rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1"])
        l = 100 - 2 * T                      # wall body: floor top to deck underside
        bottom, top = hex_span(opening)
        assert top == pytest.approx(l - T)    # one thickness of wall under the deck
        assert bottom == pytest.approx(l - T - ENVELOPE)
        assert opening[3] == pytest.approx(WIDTH)

    def test_opening_is_on_the_wall_centre_line(self) -> None:
        box, (opening,), _ = rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1"])
        r_in = 220 - T / math.cos(math.radians(30))
        side = 2 * r_in * math.sin(math.radians(30))
        assert opening[1] == pytest.approx(side / 2)

    def test_explicit_height_and_width(self) -> None:
        _, (opening,), _ = rendered(HexmoHexagon, N_HEX + [
            "--under_track_edges=1", "--under_track_height=48.5",
            "--under_track_width=26"])
        bottom, top = hex_span(opening)
        assert bottom == pytest.approx(48.5)
        assert top == pytest.approx(100 - 2 * T - T)
        assert opening[3] == pytest.approx(26)

    def test_several_edges(self) -> None:
        _, openings, _ = rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1,4"])
        assert len(openings) == 2

    def test_works_at_h80(self) -> None:
        _, (opening,), _ = rendered(HexmoHexagon, ["--radius=220", "--thickness=3",
                                                   "--h=80", "--under_track_edges=1"])
        bottom, top = hex_span(opening)
        assert top == pytest.approx(80 - 3 * T)
        assert bottom == pytest.approx(80 - 3 * T - ENVELOPE)

    def test_trapezoid_edges(self) -> None:
        _, openings, _ = rendered(HexmoHexagon, N_HEX + ["--trapezoid=1",
                                                         "--under_track_edges=3,5"])
        assert len(openings) == 2

    def test_trapezoid_has_no_edge_1(self) -> None:
        with pytest.raises(ValueError, match="trapezoid"):
            rendered(HexmoHexagon, N_HEX + ["--trapezoid=1", "--under_track_edges=1"])

    @pytest.mark.parametrize("extra, match", [
        (["--under_track_height=2"], "floor"),
        (["--under_track_height=95"], "deck"),
        (["--under_track_width=120"], "corner"),
        (["--under_track_width=-5"], "width"),
        (["--under_track_edges=7"], "edge"),
    ])
    def test_refused(self, extra, match) -> None:
        args = N_HEX + ["--under_track_edges=1"] + extra
        if "--under_track_edges=7" in extra:
            args = N_HEX + extra
        with pytest.raises(ValueError, match=match):
            rendered(HexmoHexagon, args)


class TestRectangle:

    def test_off_by_default(self) -> None:
        _, openings, _ = rendered(HexmoRectangle, N_RECT)
        assert openings == []

    def test_end_walls_and_dividers_get_it(self) -> None:
        box, openings, _ = rendered(HexmoRectangle, N_RECT + ["--under_track=1"])
        # Two end walls plus the two short dividers.
        assert len(openings) == 4

    def test_matches_the_hexagon_opening(self) -> None:
        """Same distance below the deck, same width, same place on the wall."""
        _, (hex_open,), _ = rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1"])
        box, openings, _ = rendered(HexmoRectangle, N_RECT + ["--under_track=1"])
        l = 100 - 2 * T
        hex_bottom, hex_top = hex_span(hex_open)
        # End walls are drawn in the hex wall-pattern frame (centre s_hex/2);
        # dividers in their own (centre (W − 2t)/2), so pick an end wall.
        centre = box._hexWallLength() / 2
        x, y, dx, dy = next(o for o in openings if o[0] == pytest.approx(centre))
        # Rect frame: y measured down from the deck underside.
        assert y - dy / 2 == pytest.approx(l - hex_top)
        assert y + dy / 2 == pytest.approx(l - hex_bottom)
        assert dx == pytest.approx(hex_open[3])

    def test_long_support_on_the_centre_line_is_refused(self) -> None:
        with pytest.raises(ValueError, match="support"):
            # (With a spoke, two rows are already refused for the spoke's sake.)
            rendered(HexmoRectangle, N_RECT + ["--under_track=1", "--num_rows=2",
                                               "--spoke_width=0"])


class TestTrainEnvelope:
    """--train_envelope: the room a lower track needs above its track height."""

    def test_default_is_43(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(N_HEX)
        assert box.train_envelope == 43.0

    def test_sets_the_automatic_opening_height(self) -> None:
        _, (opening,), _ = rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1",
                                                           "--train_envelope=60"])
        bottom, top = hex_span(opening)
        assert bottom == pytest.approx(top - 60)

    def test_decides_hole_or_notch(self) -> None:
        # A track at 40 mm: with 43 mm a train fits under one thickness of wall
        # below the deck (40 + 43 ≤ 91), so it is a closed hole; with 70 it does
        # not, so it becomes a notch (no hole is cut for it).
        from boxes.generators.hexmohexagon import HexmoHexagon as Hex
        def opening_holes(envelope):
            _, openings, _ = rendered(Hex, N_HEX + ["--track_openings=1:0:40:30",
                                                   f"--train_envelope={envelope}"])
            return len(openings)
        assert opening_holes(43) == 1
        assert opening_holes(70) == 0

    def test_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="train_envelope"):
            rendered(HexmoHexagon, N_HEX + ["--under_track_edges=1", "--train_envelope=0"])
