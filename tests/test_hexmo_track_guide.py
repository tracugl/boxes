"""Tests for the HexmoHexagon track-laying guide plate (``--track_guide``).

The guide is a flat plate pinned to a side wall's outer face through the
wall's corner-hole groups.  It carries one rectangular window per track, so
the laid track is held at exactly the position the etched deck guide marks
where it crosses the module joint.

These tests deliberately avoid lxml (unlike ``test_svg.py``), so they run in
the Docker image, which ships without the SVG test extras.
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

from boxes.generators.hexmohexagon import HexmoHexagon

# N-scale reference build from docs/hexmohexagon/README-N-scale.md.
N_SCALE_ARGS = [
    "--radius=190", "--thickness=3", "--h=100",
    "--edge_width=22", "--spoke_width=45", "--support_length=55",
    "--track_width=20",
]


def make_box(extra_args: list[str]) -> HexmoHexagon:
    """Build a HexmoHexagon with N-scale defaults plus ``extra_args``.

    @param extra_args - Additional ``--name=value`` CLI arguments.
    @returns The parsed (but not yet rendered) generator instance.
    """
    box = HexmoHexagon()
    box.parseArgs(N_SCALE_ARGS + extra_args)
    box.metadata["reproducible"] = True
    return box


class TestTrackOffsets:
    """``_trackOffsets`` is shared by the etched lines and the guide windows."""

    def test_centred_is_symmetric(self) -> None:
        box = make_box(["--track_line_count=3", "--track_spacing=50"])
        assert box._trackOffsets() == [-50.0, 0.0, 50.0]

    def test_outer_steps_outward_only(self) -> None:
        box = make_box(["--track_line_count=3", "--track_spacing=50",
                        "--track_offset=outer"])
        assert box._trackOffsets() == [0.0, 50.0, 100.0]

    def test_center_offset_biases_whole_family(self) -> None:
        box = make_box(["--track_line_count=2", "--track_spacing=40",
                        "--track_center_offset=10"])
        assert box._trackOffsets() == [-10.0, 30.0]


def guide_holes(box: HexmoHexagon) -> list[float]:
    """Render ``box`` and return the radius of every hole the guide plate cuts.

    ``hole`` is spied on only while ``drawTrackGuide`` runs, so the wall and
    panel holes are excluded.

    @param box - A parsed generator instance with ``--track_guide=1``.
    @returns Hole radii, in drawing order.
    """
    radii: list[float] = []
    inside = [False]
    original_hole, original_guide = box.hole, box.drawTrackGuide

    def hole_spy(x, y, r=0.0, d=0.0, **kw):
        if inside[0]:
            radii.append(r)
        return original_hole(x, y, r=r, d=d, **kw)

    def guide_spy(*args, **kw):
        inside[0] = True
        try:
            return original_guide(*args, **kw)
        finally:
            inside[0] = False

    box.hole, box.drawTrackGuide = hole_spy, guide_spy
    box.open()
    box.render()
    box.close()
    return radii


class TestTrackGuideWindows:
    """Window and plate geometry, in the guide frame (plate bottom at y = 0)."""

    S = 190.0   # wall reference length (hex side)
    L = 100.0   # wall body height
    SP = HexmoHexagon._SPACER
    T = 3.0

    def test_one_window_per_track_exact_width(self) -> None:
        box = make_box(["--track_line_count=3", "--track_spacing=50",
                        "--track_guide_clearance=30"])
        windows = box._trackGuideWindows(self.S, self.L)
        assert [w[0] for w in windows] == [45.0, 95.0, 145.0]
        deck_y = box._trackGuideDeckY(self.S, self.L)
        for cx, y0, width, height in windows:
            assert width == 20.0
            assert y0 == pytest.approx(deck_y)
            assert height == 30.0

    def test_single_track_is_centred(self) -> None:
        box = make_box([])
        (cx, _, _, _), = box._trackGuideWindows(self.S, self.L)
        assert cx == pytest.approx(self.S / 2)

    def test_window_past_plate_edge_raises(self) -> None:
        box = make_box(["--track_line_count=3", "--track_spacing=90"])
        with pytest.raises(ValueError, match="track guide"):
            box._trackGuideWindows(self.S, self.L)

    def test_non_positive_clearance_raises(self) -> None:
        box = make_box(["--track_guide_clearance=0"])
        with pytest.raises(ValueError, match="clearance"):
            box._trackGuideWindows(self.S, self.L)

    @pytest.mark.parametrize("corner_holes, lowest_pin", [
        ("g6", 100.0 - 2 * 15),   # top L-cluster inner leg at l - 2·sp
        ("g2", 100.0 - 15),       # centre-line pins only, at l - sp
    ])
    def test_plate_starts_one_spacer_below_lowest_pin(self, corner_holes, lowest_pin) -> None:
        box = make_box([f"--corner_holes={corner_holes}", "--track_guide_clearance=30"])
        base = lowest_pin - self.SP
        assert box._trackGuideBase(self.S, self.L) == pytest.approx(base)
        # Deck top is wall-frame l + t, measured up from the plate bottom.
        deck_y = self.L + self.T - base
        assert box._trackGuideDeckY(self.S, self.L) == pytest.approx(deck_y)
        width, height = box._trackGuideSize(self.S, self.L)
        assert width == self.S
        assert height == pytest.approx(deck_y + 30.0 + self.SP)


class TestTrackGuidePins:
    """The guide dowels through the small pilot holes nearest the deck only."""

    S, L = 190.0, 100.0

    @pytest.mark.parametrize("corner_holes, count", [("g6", 8), ("g2", 2)])
    def test_top_row_small_holes_only(self, corner_holes, count) -> None:
        box = make_box([f"--corner_holes={corner_holes}"])
        pins = box._trackGuidePins(self.S, self.L)
        wall = box._cornerGroupHoles(self.S, self.L)
        assert len(pins) == count
        assert all(p in wall for p in pins)                 # same holes as the wall
        assert all(r == HexmoHexagon._R3 for _, _, r in pins)  # no mediums
        assert all(x > self.L / 2 for x, _, _ in pins)      # deck-side row only

    def test_pins_symmetric_along_wall(self) -> None:
        # Symmetry is what lets the plate be flipped for the other curve end.
        box = make_box([])
        ys = sorted(y for _, y, _ in box._trackGuidePins(self.S, self.L))
        assert ys == pytest.approx(sorted(self.S - y for y in ys))


class TestTrackGuideRender:
    """The guide is an optional extra part, cut with small holes only."""

    @pytest.mark.parametrize("trapezoid", ["0", "1"])
    def test_guide_cuts_only_small_pins(self, trapezoid: str) -> None:
        radii = guide_holes(make_box([f"--trapezoid={trapezoid}", "--track_guide=1"]))
        assert radii == [HexmoHexagon._R3] * 8

    @pytest.mark.parametrize("trapezoid", ["0", "1"])
    def test_flag_off_draws_no_guide(self, trapezoid: str) -> None:
        assert guide_holes(make_box([f"--trapezoid={trapezoid}"])) == []
