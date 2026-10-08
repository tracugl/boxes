"""Tests for --subway: a level lower track under the deck (BOX-69).

On HexmoHexagon one setting, a route with a height, gives the wall openings at
both ends of the route and a level riser (bed and supports) along it.  On
HexmoRectangle the track runs down the centre line through the under-deck
openings, on one level bed per cell whose supports slot into the floor strip.

These tests avoid lxml (and, except where marked, build123d), so they run in
the Docker image.
"""
from __future__ import annotations

import itertools
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

from boxes.generators import _hexmo_step
from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N, HELIX_ENTRY_N250
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

T = 3.0
HEX = ["--radius=250", "--thickness=3", "--h=80", "--edge_width=22", "--spoke_width=60",
       "--bottom=spoke", "--support_length=55", "--track_lead_in=20", "--track_width=17",
       "--under_track_width=35", "--corner_holes=g2", "--gap_holes=g2"]
RECT = [a for a in HELIX_ENTRY_N250 if not a.startswith(("--subway", "--under_track="))]


def frames(cls, args):
    box = cls()
    box.parseArgs(args)
    return {f.name: f for f in _hexmo_step._render_frames(box)}


def render(cls, args):
    box = cls()
    box.parseArgs(args)
    box.open()
    box.render()
    return box


class TestHexagon:

    def test_one_setting_gives_openings_and_a_level_riser(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(HEX + ["--support_edges=2,6", "--subway=4:0-1:0~23.8"])
        assert box._withSubwayOpenings("") == "4:0:23.8:35,1:0:23.8:35"
        assert box._withSubwayRisers("") == "4:0-1:0~23.8..23.8/35"
        f = frames(HexmoHexagon, HEX + ["--support_edges=2,6", "--subway=4:0-1:0~23.8"])
        assert any(n.startswith("riser bed 4:0-1:0") for n in f)
        assert any(n.startswith("riser support 4:0-1:0") for n in f)

    def test_adds_to_the_existing_settings(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(HEX + ["--subway=3:0-5:0~23.8/30"])
        assert box._withSubwayOpenings("1:0:70:35") == "1:0:70:35,3:0:23.8:30,5:0:23.8:30"

    def test_offsets_map_to_positions_on_a_curve(self) -> None:
        # On a curve a positive offset is towards its outside; the openings
        # land where the route meets each edge.
        box = HexmoHexagon()
        box.parseArgs(HEX + ["--subway=4:10-2:-10~23.8"])
        openings = box._withSubwayOpenings("").split(",")
        assert [o.split(":")[0] for o in openings] == ["4", "2"]
        assert {abs(float(o.split(":")[1])) for o in openings} == {10.0}

    @pytest.mark.parametrize("args", [
        ["--support_edges=2,6", "--subway=4:0-1:0~23.8"],
        ["--support_edges=3,5,6", "--subway=4:10-2:-10~23.8/30"],
        ["--trapezoid=1", "--support_edges=4@140,4@38/90", "--track_routes=3:17.5-5:17.5",
         "--subway=3:0-5:0~23.8"]], ids=["straight", "curve", "trapezoid"])
    def test_renders(self, args) -> None:
        render(HexmoHexagon, HEX + args)

    @pytest.mark.parametrize("value", ["4-1~23.8", "4:0-1:0", "4:0-1:0~0", "9:0-1:0~20"])
    def test_malformed(self, value) -> None:
        with pytest.raises(ValueError, match="--subway"):
            render(HexmoHexagon, HEX + [f"--subway={value}"])


@pytest.fixture(scope="module")
def parts():
    return frames(HexmoRectangle, RECT + ["--subway=23.8"])


class TestRectangle:

    def test_a_bed_per_cell_and_supports(self, parts) -> None:
        assert sorted(n for n in parts if n.startswith("subway bed")) == [
            "subway bed 1", "subway bed 2"]
        assert len([n for n in parts if n.startswith("subway support")]) >= 4

    def test_bed_level_at_the_track_height(self, parts) -> None:
        for n in ("subway bed 1", "subway bed 2"):
            assert parts[n].origin[2] == pytest.approx(23.8 - T)

    def test_turns_on_the_under_deck_openings(self) -> None:
        box = render(HexmoRectangle, RECT + ["--subway=23.8"])
        assert box.under_track
        assert (box.under_track_height, box.under_track_width) == (23.8, 35)

    def test_floor_strip_carries_the_support_slots(self, parts) -> None:
        # One slot per support (and the divider's), and no weight holes.
        supports = len([n for n in parts if n.startswith("subway support")])
        loops = _hexmo_step._frame_loops(parts["spoke"])
        assert len(loops) == 1 + supports + 2   # outline, supports, divider slot pair

    def test_parts_fit_in_3d(self) -> None:
        pytest.importorskip("build123d")
        box = HexmoRectangle()
        box.parseArgs(RECT + ["--subway=23.8"])
        parts = [p for p in _hexmo_step.exact_rect_parts(box, clearance="none")
                 if p.kind not in ("track", "clearance")]
        bad = []
        for a, b in itertools.combinations(parts, 2):
            common = a.solid & b.solid
            if common and sum(s.volume for s in common.solids()) > 5.0:
                bad.append((a.name, b.name))
        assert bad == []
        beds = [p for p in parts if p.name.startswith("subway bed")]
        assert all(p.solid.bounding_box().max.Z == pytest.approx(23.8) for p in beds)

    def test_refuses_a_different_under_track(self) -> None:
        with pytest.raises(ValueError, match="under_track"):
            render(HexmoRectangle, RECT + ["--under_track=1", "--under_track_height=30",
                                           "--subway=23.8"])

    def test_needs_the_floor_strip(self) -> None:
        with pytest.raises(ValueError, match="spoke_width"):
            render(HexmoRectangle, RECT + ["--spoke_width=0", "--subway=23.8"])

    def test_bed_must_fit_the_strip(self) -> None:
        with pytest.raises(ValueError, match="floor strip"):
            render(HexmoRectangle, RECT + ["--subway=23.8/80"])


def test_helix_entry_presets() -> None:
    # The 250 ring's entry carries the lower level on a subway; the 220
    # ring's is unchanged.
    assert "--subway=23.8" in HELIX_ENTRY_N250
    assert not any(a.startswith("--subway=") for a in HELIX_ENTRY_N)
    render(HexmoRectangle, HELIX_ENTRY_N250)
