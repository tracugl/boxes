"""Tests for the track-following spoke floor (``--bottom=spoke``, BOX-71).

The floor keeps its rim and a strip ``--spoke_width`` wide under every track
(deck routes, risers, subways), and the rest is cut away.  The support walls
stand across the deck tracks, spaced along them (``--support_spacing``),
slid along themselves or turned along the track where they must be, with
fill-ins on the half-spokes for deck no track runs over.  The old floor is
``--bottom=kites``.

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

from shapely.geometry import LineString, Point, Polygon

from boxes.generators import _hexmo_step
from boxes.generators._hexmo_helix_ring import (
    HELIX_RING_N250, HELIX_RING_N250_GROUND, helix_ring_ho,
)
from boxes.generators._hexmo_track_floor import TrackSupport
from boxes.generators._hexmo_track_routes import segments_polyline
from boxes.generators.hexmohexagon import HexmoHexagon

MODULES = {"N250 M2": HELIX_RING_N250["M2"], "N250 M6": HELIX_RING_N250["M6"],
           "N250 ground M2": HELIX_RING_N250_GROUND["M2"], "HO M6": helix_ring_ho()["M6"],
           "default trapezoid": ["--trapezoid=1"]}


def rendered(args):
    """A rendered box, with its riser and deck slot plans, inside radius and height."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.open()
    box.render()
    trap = box.trapezoid
    r, l = box._innerSize()
    notches = {}
    for edge, entries in box._trackOpeningPlan(trap, l).items():
        cut = [(o.position, o.width, l - o.height) for o, notch in entries if notch]
        if cut:
            notches[edge] = cut
    risers = box._riserPlan(r, trap, l, notches)
    slots = box._deckSlotPlan(r, trap, notches)
    return box, r, risers, slots


def openings(box, r, risers):
    return [Polygon(pts) for pts in box._trackFloorOpenings(r, box.trapezoid, risers)]


@pytest.fixture(scope="module", params=list(MODULES), ids=list(MODULES))
def module(request):
    return rendered(MODULES[request.param])


class TestChoice:

    def test_default_spoke_floor_follows_the_tracks(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(["--trapezoid=1"])
        box.open()
        assert box.bottom == "spoke" and box._trackFloor(True)

    def test_kites_keep_the_old_floor(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(["--trapezoid=1", "--bottom=kites"])
        box.open()
        assert not box._trackFloor(True)

    def test_no_routes_falls_back_to_kites(self) -> None:
        # The default full hexagon has no track routes switched on.
        box, r, risers, _ = rendered([])
        assert not box._trackFloor(False)
        assert all(not isinstance(sp, TrackSupport) for sp in box._supportLayout(r, False))


class TestSupports:

    def test_every_support_stands_on_solid_floor(self, module) -> None:
        box, r, risers, _ = module
        holes = openings(box, r, risers)
        supports = box._supportLayout(r, box.trapezoid)
        assert supports
        for sp in supports:
            slot = LineString(box._supportPoints(sp, 1)).buffer(box.thickness / 2)
            assert not any(slot.intersects(h) for h in holes)

    def test_riser_floor_slots_stand_on_solid_floor(self, module) -> None:
        box, r, risers, _ = module
        holes = openings(box, r, risers)
        for rp in risers:
            for point, _, _ in rp["stations"]:
                assert not any(h.contains(Point(point)) for h in holes)

    def test_supports_clear_slots_risers_and_each_other(self, module) -> None:
        box, r, risers, slots = module
        t = box.thickness
        lines = [LineString(box._supportPoints(sp, 1)) for sp in box._supportLayout(r, box.trapezoid)]
        for slot in slots:
            band = LineString(segments_polyline(slot["segments"], 32)).buffer(slot["width"] / 2)
            assert not any(line.intersects(band) for line in lines)
        for rp in risers:
            band = LineString(segments_polyline(rp["segments"], 32)).buffer(rp["width"] / 2)
            assert not any(line.intersects(band) for line in lines)
        for i, a in enumerate(lines):
            for b in lines[i + 1:]:
                assert a.distance(b) >= t

    def test_supports_clear_the_walls(self, module) -> None:
        box, r, _, _ = module
        apothem = r * math.sqrt(3) / 2
        for sp in box._supportLayout(r, box.trapezoid):
            for x, y in box._supportPoints(sp):
                assert math.hypot(x, y) < apothem - box.thickness
                if box.trapezoid:
                    assert y < -box.thickness

    def test_spacing_sets_how_many(self) -> None:
        few = rendered(HELIX_RING_N250["M2"] + ["--support_spacing=300"])
        many = rendered(HELIX_RING_N250["M2"] + ["--support_spacing=80"])
        count = lambda m: len(m[0]._supportLayout(m[1], True))
        assert count(few) < count(many)

    def test_ground_supports_never_straddle_the_deck_edge(self) -> None:
        box, r, _, _ = rendered(HELIX_RING_N250_GROUND["M2"])
        supports = box._supportLayout(r, True)
        assert supports and box._lower_plan is not None

    def test_supports_are_drawn_and_slotted(self) -> None:
        # One support wall per placed support, in floor and deck alike.
        box = HexmoHexagon()
        box.parseArgs(HELIX_RING_N250["M2"])
        frames = {f.name: f for f in _hexmo_step._render_frames(box)}
        r, _ = box._innerSize()
        names = [n for n in frames if n.startswith("support ")]
        assert len(names) == len(box._supportLayout(r, True))


class TestOpenings:

    def test_openings_are_worth_cutting(self, module) -> None:
        box, r, risers, _ = module
        for hole in openings(box, r, risers):
            assert hole.is_valid and not hole.interiors
            assert not hole.buffer(-box._FLOOR_MIN_OPENING / 2 + 0.5).is_empty

    def test_openings_inside_the_rim(self, module) -> None:
        box, r, risers, _ = module
        interior = box._floorInterior(r, box.trapezoid).buffer(0.01)
        assert all(interior.contains(h) for h in openings(box, r, risers))

    def test_tracks_keep_their_strip(self, module) -> None:
        # Nothing is cut under a deck route's centreline.
        box, r, risers, _ = module
        holes = openings(box, r, risers)
        for g in box._trackRouteGeometries(r, box.trapezoid):
            line = LineString(segments_polyline(g.segments, 32))
            assert not any(line.intersects(h) for h in holes)


class Test3D:

    def test_support_tabs_mesh_with_floor_and_deck(self) -> None:
        pytest.importorskip("build123d")
        box = HexmoHexagon()
        box.parseArgs(HELIX_RING_N250["M2"])
        parts = {p.name: p for p in _hexmo_step.exact_hexmo_parts(box)}
        support = parts["support 1"]
        for panel in ("floor", "deck"):
            common = support.solid & parts[panel].solid
            volume = sum(s.volume for s in common.solids()) if common else 0.0
            assert volume < 5.0
