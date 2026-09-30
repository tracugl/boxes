"""Tests for the HexmoHexagon track-laying guide plate (``--track_guide``).

The guide is a flat plate pinned to a side wall's outer face through the
wall's corner-hole groups.  It carries one rectangular window per track, so
the laid track is held at exactly the position the etched deck guide marks
where it crosses the module joint.

These tests deliberately avoid lxml (unlike ``test_svg.py``), so they run in
the Docker image, which ships without the SVG test extras.
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


def render_counting_corner_groups(box: HexmoHexagon) -> list[tuple[float, float]]:
    """Render ``box`` and record every ``_drawCornerGroup8(s, l)`` call.

    The guide must reuse the wall's own corner-group routine so its dowel
    holes are identical by construction; counting the calls (and comparing
    their arguments) is how the tests check that without parsing SVG paths.

    @param box - A parsed generator instance.
    @returns The ``(s, l)`` argument pairs, in call order.
    """
    calls: list[tuple[float, float]] = []
    original = box._drawCornerGroup8

    def spy(s, l):
        calls.append((s, l))
        return original(s, l)

    box._drawCornerGroup8 = spy
    box.open()
    box.render()
    box.close()
    return calls


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


class TestTrackGuideWindows:
    """Window geometry, in the guide's own frame (box underside at y = 0)."""

    S = 190.0   # wall reference length (hex side) for radius=190
    L = 100.0   # wall body height (== --h)

    def test_one_window_per_track_exact_width(self) -> None:
        box = make_box(["--track_line_count=3", "--track_spacing=50",
                        "--track_guide_clearance=30"])
        windows = box._trackGuideWindows(self.S, self.L)
        assert [w[0] for w in windows] == [45.0, 95.0, 145.0]
        for cx, y0, width, height in windows:
            assert width == 20.0
            # Window floor is the deck top surface: bottom panel (t) + wall
            # body (l) + deck panel (t) above the box underside.
            assert y0 == pytest.approx(self.L + 2 * 3.0)
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

    def test_plate_size(self) -> None:
        box = make_box(["--track_guide_clearance=30"])
        width, height = box._trackGuideSize(self.S, self.L)
        assert width == self.S
        # Deck surface + window clearance + one spacer of material above.
        assert height == pytest.approx(self.L + 2 * 3.0 + 30.0 + HexmoHexagon._SPACER)


class TestTrackGuideRender:
    """The guide is an optional extra part that reuses the wall hole pattern."""

    @pytest.mark.parametrize("trapezoid, walls", [("0", 6), ("1", 4)])
    def test_flag_off_adds_nothing(self, trapezoid: str, walls: int) -> None:
        calls = render_counting_corner_groups(make_box([f"--trapezoid={trapezoid}"]))
        assert len(calls) == walls

    @pytest.mark.parametrize("trapezoid, walls", [("0", 6), ("1", 4)])
    def test_guide_reuses_standard_wall_corner_groups(self, trapezoid: str, walls: int) -> None:
        calls = render_counting_corner_groups(
            make_box([f"--trapezoid={trapezoid}", "--track_guide=1"]))
        assert len(calls) == walls + 1
        # Every standard wall is drawn with (side_orig, l); the guide must
        # match those exactly.  (The trapezoid's long wall uses 2·side_orig.)
        standard = calls[-2]
        assert calls[-1] == standard
        # Never the long-wall frame: every wall call is either s or 2·s.
        assert all(math.isclose(c[0], standard[0]) or math.isclose(c[0], 2 * standard[0])
                   for c in calls)
        assert not math.isclose(calls[-1][0], 2 * standard[0])
