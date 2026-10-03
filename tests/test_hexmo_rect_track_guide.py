"""Tests for the HexmoRectangle track-laying guide plate (``--track_guide``).

The rectangle's short (end) walls join HexmoHexagon / trapezoid side walls
face to face, so its guide must be the *same* plate as the hexagon's: one jig
that fits either module and holds the track at the same place across the
joint.  The strongest check is to draw the guide from both generators with
the same settings and compare what they cut.  A second check confirms that
the guide's pins land on real holes of the rectangle's end wall (measured
through the drawing transform by the wall-alignment harness).

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from hexmo_testutil import IGNORE_CORE_MATMUL

# Silence only the matmul deprecation raised by upstream's boxes/drawing.py
# (see hexmo_testutil); every other warning still shows.
pytestmark = IGNORE_CORE_MATMUL

from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hexmo_wall_alignment import rect_end_wall_holes  # noqa: E402

# Fixed N-scale-sized base build (the original radius-190 preset); the
# "n-preferred" variant below adds the current README settings on top.
N_SCALE = ["--radius=190", "--thickness=3", "--track_width=20"]

# Guide-affecting settings to cover: plain N scale, a double track in 'outer'
# mode with a centre bias (asymmetric, so the arrow label is drawn), --outside
# off, and the reduced corner-hole pattern.
VARIANTS = {
    "n-single": [],
    # Current preferred N-scale settings (docs/hexmohexagon/README-N-scale.md).
    # Current preferred HO settings (docs/hexmohexagon/README-HO-scale.md).
    "ho-preferred": ["--radius=500", "--thickness=6", "--h=100", "--track_width=30",
                     "--track_line_count=2", "--track_spacing=80", "--track_lead_in=23",
                     "--corner_holes=g2", "--gap_holes=g2", "--big_hole_shape=rounded_rect",
                     "--FingerJoint_play=0.1", "--FingerJoint_extra_length=0.05"],
    "n-preferred": ["--radius=220", "--h=100", "--track_width=17", "--track_lead_in=26",
                    "--track_spacing=35", "--corner_holes=g2", "--gap_holes=g4",
                    "--big_hole_shape=rounded_rect", "--big_hole_width=50",
                    "--big_hole_height=70", "--FingerJoint_extra_length=0.1"],
    "double-outer-biased": ["--track_line_count=2", "--track_spacing=40",
                            "--track_offset=outer", "--track_center_offset=-10"],
    "outside-off": ["--outside=0"],
    "g2-clearance": ["--corner_holes=g2", "--track_guide_clearance=45"],
}


def record_guide(cls, extra):
    """Render ``cls`` with a guide and record everything the guide draws.

    Spies record calls made only while ``drawTrackGuide`` runs, in the
    guide's own callback frame, so two generators' guides can be compared
    call for call.

    @param cls   - HexmoHexagon or HexmoRectangle.
    @param extra - Extra CLI args on top of N-scale defaults.
    @returns Dict with the plate size, pin holes, windows and label texts.
    """
    box = cls()
    box.parseArgs(N_SCALE + ["--track_guide=1"] + extra)
    box.open()
    rec = {"plates": [], "holes": [], "windows": [], "texts": []}
    inside = [False]
    o_hole, o_rhole, o_wall, o_text, o_guide = (
        box.hole, box.rectangularHole, box.rectangularWall, box.text, box.drawTrackGuide)

    def rnd(*v):
        return tuple(round(float(x), 3) for x in v)

    def hole(x, y, r=0.0, d=0.0, **kw):
        if inside[0]:
            rec["holes"].append(rnd(x, y, r))
        return o_hole(x, y, r=r, d=d, **kw)

    def rhole(x, y, dx, dy, *a, **kw):
        if inside[0]:
            rec["windows"].append(rnd(x, y, dx, dy))
        return o_rhole(x, y, dx, dy, *a, **kw)

    def wall(x, y, *a, **kw):
        if inside[0]:
            rec["plates"].append(rnd(x, y))
        return o_wall(x, y, *a, **kw)

    def text(t, *a, **kw):
        if inside[0]:
            rec["texts"].append(t)
        return o_text(t, *a, **kw)

    def guide(*a, **kw):
        inside[0] = True
        try:
            return o_guide(*a, **kw)
        finally:
            inside[0] = False

    box.hole, box.rectangularHole, box.rectangularWall, box.text, box.drawTrackGuide = (
        hole, rhole, wall, text, guide)
    box.render()
    box.close()
    return rec


class TestRectGuideIsTheHexGuide:

    @pytest.mark.parametrize("variant", VARIANTS, ids=list(VARIANTS))
    def test_same_plate_as_hexagon(self, variant) -> None:
        extra = VARIANTS[variant]
        rect = record_guide(HexmoRectangle, extra)
        hexa = record_guide(HexmoHexagon, extra)
        assert len(rect["plates"]) == 1, "exactly one guide plate"
        assert rect == hexa

    @pytest.mark.parametrize("variant", VARIANTS, ids=list(VARIANTS))
    def test_same_plate_as_trapezoid(self, variant) -> None:
        extra = VARIANTS[variant]
        assert (record_guide(HexmoRectangle, extra)
                == record_guide(HexmoHexagon, extra + ["--trapezoid=1"]))

    def test_flag_off_draws_no_guide(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(N_SCALE)
        calls = []
        box.drawTrackGuide = lambda *a, **kw: calls.append(a)
        box.open()
        box.render()
        box.close()
        assert calls == []


class TestRectGuidePinsHitRectEndWall:

    @pytest.mark.parametrize("outside", [1, 0])
    def test_every_guide_pin_is_a_rect_end_wall_hole(self, outside) -> None:
        """Map guide pins back to the wall and look them up in the measured holes.

        The guide pins are defined in the hex wall hole frame (x up the wall,
        y along it, s long, l high).  On the wall they sit at
        ``along = y − s/2`` from the centre and ``from_deck = l − x``.
        """
        box = HexmoRectangle()
        box.parseArgs(N_SCALE + [f"--outside={outside}", "--track_guide=1"])
        s, l = box._hexWallLength(), box._hexWallHeight()
        pins = {(round(y - s / 2, 2), round(l - x, 2), r)
                for x, y, r in box._trackGuidePins(s, l)}
        wall = {(round(a, 2), round(fd, 2), r)
                for a, fd, r in rect_end_wall_holes(190, 3, outside)}
        assert len(pins) == 2
        assert pins <= wall
