"""Tests for the N helix ring at radius 250 (BOX-68).

The ring presets are built per module size by ``helix_ring`` from a few
numbers that depend on the size (:class:`RingSize`).  The original 220 ring
must come out exactly as before (the other tests are built on it); the 250 ring
must render, close every cut, keep its tracks meeting at every joint, and
build in 3D.

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
    HELIX_ENTRY_N, HELIX_ENTRY_N250, HELIX_RING_N, HELIX_RING_N250, HELIX_RING_N250_GROUND,
    SIZE_250,
)
from boxes.generators._hexmo_risers import point_at
from boxes.generators._hexmo_track_routes import route_geometry
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle


def open_ends(box):
    """The largest gap between a drawn cut path's start and end."""
    worst = 0.0
    for part in box.surface.parts:
        for path in part.pathes:
            if not _hexmo_step._is_cut(path.params.get("rgb")):
                continue
            start = end = None
            for cmd in path.path:
                if cmd[0] == "M":
                    if start is not None:
                        worst = max(worst, math.dist(start, end))
                    start = end = (cmd[1], cmd[2])
                elif cmd[0] in "LC":
                    end = (cmd[1], cmd[2])
            if start is not None:
                worst = max(worst, math.dist(start, end))
    return worst


class TestPresets:

    def test_220_ring_unchanged(self) -> None:
        # Spot checks of the original ring's hand-worked numbers.
        assert "--radius=220" in HELIX_RING_N["M1"]
        assert "--support_edges=4@132,4@30/90" in HELIX_RING_N["M3"]
        assert "--risers=3:-35-5:-35~58.5..50.8/35" in HELIX_RING_N["M3"]
        assert ("--deck_slots=1:0-5:17.5@169../35,3:35-1:0@..186/35"
                in HELIX_RING_N["M6"])
        assert "--radius=220" in HELIX_ENTRY_N

    def test_250_ring_numbers(self) -> None:
        assert "--radius=250" in HELIX_RING_N250["M2"]
        assert "--track_lead_in=20" in HELIX_RING_N250["M2"]
        assert "--risers=3:-35-5:-35~66.2..58.6/35" in HELIX_RING_N250["M2"]
        assert ("--risers=1:0-5:17.5@178..~77..74/35,3:35-1:0@..233~36..31/35,"
                "3:35-1:0@233..~31..27.8/35") in HELIX_RING_N250["M6"]
        assert "--radius=250" in HELIX_ENTRY_N250
        assert "--track_lead_in=20" in HELIX_ENTRY_N250
        assert "--track_lead_in=26" in HELIX_RING_N["M2"]

    def test_250_joints_are_one_steady_grade(self) -> None:
        # 74 at the M6/M1 joint down to 31.0 at the end of the return's slot.
        apothem = (250 - 3 / math.cos(math.radians(30))) * math.sqrt(3) / 2

        def length(*route):
            return sum(s.length for s in route_geometry(*route, apothem, 20).segments)
        m1, m2 = length(3, -17.5, 5, -35), length(3, -35, 5, -35)
        grade = (74 - 31) / (m1 + 4 * m2 + SIZE_250.return_end)
        expect = [74.0]
        for run in [m1] + [m2] * 4:
            expect.append(expect[-1] - grade * run)
        assert list(SIZE_250.joints) == pytest.approx(expect, abs=0.06)

    def test_250_spur_curve_is_bigger(self) -> None:
        # The spur's arc (35 mm in) is about R300 (20 mm lead-ins), against
        # about R245 at 220 (26 mm).
        for radius, lead, expect in ((220, 26, 245), (250, 20, 300)):
            apothem = (radius - 3 / math.cos(math.radians(30))) * math.sqrt(3) / 2
            g = route_geometry(3, -35, 5, -35, apothem, lead)
            assert g.radius == pytest.approx(expect, abs=1)


class TestN250Ring:

    @pytest.mark.parametrize("name", ["M1", "M2", "M3", "M4", "M5", "M6"])
    @pytest.mark.parametrize("ring", [HELIX_RING_N250, HELIX_RING_N250_GROUND],
                             ids=["plain", "ground"])
    def test_module_renders_and_closes(self, ring, name) -> None:
        box = HexmoHexagon()
        box.parseArgs(ring[name])
        box.open()
        box.render()
        assert open_ends(box) < 1e-6

    def test_entry_renders_and_closes(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(HELIX_ENTRY_N250)
        box.open()
        box.render()
        assert open_ends(box) < 1e-6

    @pytest.mark.parametrize("ring", ["N250", "N250-ground"])
    def test_tracks_meet_at_every_joint(self, ring) -> None:
        pytest.importorskip("build123d")
        ends = _hexmo_step.ring_track_ends(ring)
        unmatched = sorted(
            (m, round(z, 1)) for i, (m, p, z) in enumerate(ends)
            if not any(j != i and mm != m and math.dist(pp, p) < 0.5 and abs(zz - z) < 0.05
                       for j, (mm, pp, zz) in enumerate(ends)))
        # Only the line's two ends: the lower level leaving M6 at edge 1, and
        # the entry line's far end.
        assert unmatched == [("M6", 27.8), ("entry", 77.0)]

    def test_m6_spur_starts_clear_of_the_return(self) -> None:
        # The spur's riser starts 178 mm along its route on M6; much earlier
        # and its first support would stand in the return's track.
        box = HexmoHexagon()
        box.parseArgs([a.replace("@178", "@166") for a in HELIX_RING_N250["M6"]])
        with pytest.raises(ValueError, match="would stand in the track"):
            box.open()
            box.render()

    def test_ground_ring_builds_in_3d(self) -> None:
        pytest.importorskip("build123d")
        for name in ("M1", "M6"):
            box = HexmoHexagon()
            box.parseArgs(HELIX_RING_N250_GROUND[name])
            parts = _hexmo_step.exact_hexmo_parts(box, clearance="none")
            assert all(p.solid.is_valid for p in parts if p.kind not in ("track", "clearance"))


def test_main_line_mid_is_just_outside_the_turned_support() -> None:
    # The turned support (38 mm out) sits just inside the main line, as the
    # 220 ring's does (30 mm, main line 25.8 mm out).
    apothem = (250 - 3 / math.cos(math.radians(30))) * math.sqrt(3) / 2
    g = route_geometry(3, 17.5, 5, 17.5, apothem, 20)
    total = sum(s.length for s in g.segments)
    (_, y), _ = point_at(g.segments, total / 2)
    assert 32 < -y < 38
