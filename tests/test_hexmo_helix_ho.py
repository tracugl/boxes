"""Tests for the HO helix ring preset (``--ring=HO``) and the lower level on the floor.

The HO README's ring (radius 500, 6 mm stock, h=100), with its lower level
taken all the way down to the floor: one steady grade from the M6/M1 joint
(88 mm, on the wall tops) to M6's edge 1 (6 mm, the bed lying on the floor).
Riser supports go down to 12 mm (2t); below that the bed slopes on to rest on
the floor.  The entry rectangle carries the lower level on the floor too
(``--subway 6``): a flat bed per cell on the floor strip, no supports.

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

from boxes.generators import _hexmo_step
from boxes.generators._hexmo_helix_ring import (
    RINGS, helix_entry_ho, helix_ring_ho, helix_ring_ho_ground,
)
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

T = 6.0
RING = helix_ring_ho()
ENTRY = helix_entry_ho()


def plan(args):
    """A HexmoHexagon's riser plan."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.open()
    r, _ = box._innerSize()
    return box._riserPlan(r, "--trapezoid=1" in args, box._wallSize()[1])


def frames(cls, args):
    box = cls()
    box.parseArgs(args)
    return {f.name: f for f in _hexmo_step._render_frames(box)}


class TestRing:

    @pytest.mark.parametrize("name", ["M1", "M2", "M3", "M4", "M5", "M6"])
    def test_module_renders(self, name) -> None:
        box = HexmoHexagon()
        box.parseArgs(RING[name])
        box.open()
        box.render()
        box.close()

    def test_entry_renders(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(ENTRY)
        box.open()
        box.render()
        box.close()

    def test_in_the_ring_export(self) -> None:
        assert RINGS["HO"][0]["M6"] == RING["M6"] and RINGS["HO"][1] == ENTRY

    def test_one_steady_grade_to_the_floor(self) -> None:
        # Every riser falls at the same 1.89 %, from 88 at the M6/M1 joint
        # down to 6 at M6's edge 1.
        risers = [rp for name in ("M1", "M2", "M3", "M4", "M5") for rp in plan(RING[name])]
        risers += [rp for rp in plan(RING["M6"]) if rp["route"][0] == 3]
        assert risers[0]["heights"][0] == 88 and risers[-1]["heights"][1] == 6
        for rp in risers:
            (h0, h1), (lo, hi) = rp["heights"], rp["stretch"]
            assert (h0 - h1) / (hi - lo) == pytest.approx(0.0189, abs=0.0002)

    def test_m6_supports_stop_at_twice_the_thickness(self) -> None:
        # The return's last riser (12.5 down to the floor) keeps one support;
        # the bed then slopes on to rest on the floor strip at edge 1.
        last = [rp for rp in plan(RING["M6"]) if rp["route"][0] == 3][-1]
        assert last["heights"] == (12.5, 6)
        heights = [h for _, _, h in last["stations"]]
        assert heights and min(heights) >= 2 * T

    def test_room_for_the_train_under_m6s_deck(self) -> None:
        # Past the return's deck slot the track is at most 12.5: a 70 mm
        # train clears the 88 mm deck underside.
        assert 12.5 + 70 <= 100 - 2 * T

    def test_tracks_meet_at_every_joint(self) -> None:
        pytest.importorskip("build123d")
        ends = _hexmo_step.ring_track_ends("HO")
        unmatched = sorted(
            (m, round(z, 1)) for i, (m, p, z) in enumerate(ends)
            if not any(j != i and mm != m and math.dist(pp, p) < 0.5 and abs(zz - z) < 0.05
                       for j, (mm, pp, zz) in enumerate(ends)))
        # Only the lower level leaving M6 at edge 1 (on the floor) and the
        # entry's three deck tracks at its far end.
        assert unmatched == [("M6", 6.0), ("entry", 94.0), ("entry", 94.0), ("entry", 94.0)]

    def test_m6_fits_in_3d(self) -> None:
        # The return's bed, sloping onto the floor, touches no wall or panel.
        pytest.importorskip("build123d")
        box = HexmoHexagon()
        box.parseArgs(RING["M6"])
        parts = [p for p in _hexmo_step.exact_hexmo_parts(box, clearance="none")
                 if p.kind not in ("track", "clearance")]
        beds = [p for p in parts if p.name.startswith("riser bed 3:80-1:0")]
        assert beds
        bad = [(b.name, p.name) for b in beds for p in parts
               if p is not b and not p.name.startswith("riser")
               and (common := b.solid & p.solid)
               and sum(x.volume for x in common.solids()) > 1.0]
        assert bad == []


class TestGround:
    """The HO ring opened up for scenery (``--ring=HO-ground``)."""

    GROUND = helix_ring_ho_ground()

    @pytest.mark.parametrize("name", ["M1", "M2", "M3", "M4", "M5", "M6"])
    def test_module_renders(self, name) -> None:
        args = self.GROUND[name]
        assert "--lower_ground=21.8" in args and "--upper_edge_gap=25" in args
        box = HexmoHexagon()
        box.parseArgs(args)
        box.open()
        box.render()
        box.close()

    def test_lower_ground_meets_the_spur_at_its_lowest_joint(self) -> None:
        # 21.8 is the spur's height at the M5/M6 joint; any higher and the
        # ground would stand above the spur where M5 and M6 step their walls.
        args = [a.replace("--lower_ground=21.8", "--lower_ground=22") for a in self.GROUND["M5"]]
        box = HexmoHexagon()
        box.parseArgs(args)
        box.open()
        with pytest.raises(ValueError, match="above the spur"):
            box.render()

    def test_supports_clear_of_the_deck_edge(self) -> None:
        # The track-following floor places the supports itself, each wholly
        # under the deck or wholly under the lower plate, never straddling
        # the deck's cut-back edge.
        box = HexmoHexagon()
        box.parseArgs(self.GROUND["M3"])
        box.open()
        box.render()
        plan = box._lower_plan
        r, _ = box._innerSize()
        supports = box._supportLayout(r, True)
        assert supports
        assert len(plan.lower) < len(supports)      # some under the deck

    def test_in_the_ring_export(self) -> None:
        assert RINGS["HO-ground"][0] == self.GROUND

    def test_tracks_meet_at_every_joint(self) -> None:
        pytest.importorskip("build123d")
        ends = _hexmo_step.ring_track_ends("HO-ground")
        unmatched = sorted(
            (m, round(z, 1)) for i, (m, p, z) in enumerate(ends)
            if not any(j != i and mm != m and math.dist(pp, p) < 0.5 and abs(zz - z) < 0.05
                       for j, (mm, pp, zz) in enumerate(ends)))
        assert unmatched == [("M6", 6.0), ("entry", 94.0), ("entry", 94.0), ("entry", 94.0)]

    @pytest.mark.parametrize("name", ["M1", "M6"])
    def test_builds_in_3d(self, name) -> None:
        pytest.importorskip("build123d")
        box = HexmoHexagon()
        box.parseArgs(self.GROUND[name])
        parts = _hexmo_step.exact_hexmo_parts(box, clearance="none")
        assert all(p.solid.is_valid for p in parts if p.kind not in ("track", "clearance"))


class TestOnTheFloor:
    """A subway or riser with its track one thickness up: the bed on the floor."""

    def test_entry_beds_lie_on_the_floor_strip(self) -> None:
        f = frames(HexmoRectangle, ENTRY)
        beds = [n for n in f if n.startswith("subway bed")]
        assert len(beds) == 3                       # one per cell
        assert all(f[n].origin[2] == pytest.approx(0) for n in beds)
        assert not any(n.startswith("subway support") for n in f)

    def test_floor_strip_stays_solid_under_them(self) -> None:
        # The outline and one finger slot per short divider (two): no
        # access openings, no support slots.
        f = frames(HexmoRectangle, ENTRY)
        assert len(_hexmo_step._frame_loops(f["spoke"])) == 1 + 2

    def test_hexagon_subway_on_the_floor_stays_inside(self) -> None:
        # Its bed can't run through the walls (their strip above the floor
        # joint is there); it stops at their inner faces.
        args = [a for a in RING["M6"]
                if not a.startswith(("--track_routes", "--track_openings", "--deck_slots",
                                     "--risers", "--under_track_edges", "--support_edges"))]
        args += ["--support_edges=2,6", "--subway=4:0-1:0~6"]
        (bed,) = plan(args)
        box = HexmoHexagon()
        box.parseArgs(args)
        box.open()
        r, _ = box._innerSize()
        inner = r * math.sqrt(3) / 2
        ends = [bed["segments"][0].p0, bed["segments"][-1].p1]
        assert sorted(abs(p[1]) for p in ends) == pytest.approx([inner, inner])
        assert bed["stations"] == []

    @pytest.mark.parametrize("height", [8, 10])
    def test_refuses_a_bed_end_in_the_air(self, height) -> None:
        # Between the floor (6) and the lowest support (12) nothing would hold
        # the bed's end up.
        with pytest.raises(ValueError, match="too low for a support"):
            plan(RING["M6"][:-1] + [f"--risers=3:80-1:0@490..~12.5..{height}/60"])

    def test_rectangle_refuses_between_floor_and_support(self) -> None:
        box = HexmoRectangle()
        box.parseArgs([a for a in ENTRY
                       if not a.startswith(("--subway", "--under_track=", "--under_track_height"))]
                      + ["--subway=9/60"])
        box.open()
        with pytest.raises(ValueError, match="no room for supports"):
            box.render()
