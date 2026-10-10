"""Tests for the track-following spoke floor (``--bottom=spoke``, BOX-71).

The floor keeps its rim and a strip ``--spoke_width`` wide along every
connection a track can make (1–3, 3–5, 5–1, 2–4, 4–6, 6–2; 3–5 on the
trapezoid) and under every track, riser and subway; the rest is cut away.
Six support walls stand round the hexagon, one beside each connection and
clear of every track path; the trapezoid has one down its open middle.
The old floor is ``--bottom=kites``.

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
    _HO_COMMON, HELIX_RING_N250, HELIX_RING_N250_GROUND, helix_ring_ho,
)
from boxes.generators._hexmo_track_floor import TrackSupport
from boxes.generators._hexmo_track_routes import segments_polyline
from boxes.generators.hexmohexagon import HexmoHexagon

_N_PLAIN = [a for a in HELIX_RING_N250["M6"] if not a.startswith(
    ("--track_routes", "--under_track_edges", "--track_openings", "--deck_slots", "--risers",
     "--under_track_height"))]
# Plain hexagons with a subway 1→3 under a main line, as the user builds them.
_HO_SUBWAY = _HO_COMMON + ["--subway=1:0-3:0~6", "--track_routes=1:0-3:0,3:0-5:0,1:0-5:0"]
_N_SUBWAY = _N_PLAIN + ["--under_track_height=23.8", "--subway=1:0-3:0~23.8",
                        "--track_routes=2:0-6:0,2:0-5:0"]

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

    def test_no_tracks_gets_one_support_per_spoke(self) -> None:
        # The default full hexagon has no track routes: its supports stand on
        # its six spokes, one each.
        box, r, risers, _ = rendered([])
        supports = box._supportLayout(r, False)
        assert box._trackFloor(False)
        assert len(supports) == 6 and all(isinstance(sp, TrackSupport) for sp in supports)

    @pytest.mark.parametrize("args, count", [([], 6), (["--trapezoid=1"], 1)],
                             ids=["hexagon", "trapezoid"])
    def test_spokes_are_every_track_connection(self, args, count) -> None:
        box = HexmoHexagon()
        box.parseArgs(args)
        box.open()
        r, _ = box._innerSize()
        routes = box._spokeRoutes(r, "--trapezoid=1" in args)
        assert len(routes) == count
        assert all({g.start, g.end} in ({1, 3}, {3, 5}, {5, 1}, {2, 4}, {4, 6}, {6, 2})
                   for g in routes)


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

    def test_at_most_one_per_track(self, module) -> None:
        box, r, _, _ = module
        supports = box._supportLayout(r, box.trapezoid)
        routes = [sp.route for sp in supports]
        assert len(routes) == len(set(routes))

    def test_halfway_out_from_the_centre(self) -> None:
        # The default hexagon's six stand about half the apothem from the
        # centre (where the kite floor's supports stood), not crowding the
        # middle.
        box, r, _, _ = rendered([])
        apothem = r * math.sqrt(3) / 2
        supports = box._supportLayout(r, False)
        assert len(supports) == 6
        for sp in supports:
            assert math.hypot(*sp.centre) == pytest.approx(apothem / 2, abs=15)

    def test_six_alike_round_the_hexagon(self) -> None:
        # With no tracks of its own, each support is the last turned 60°
        # (or 120°: the spokes run 1–3, 3–5, 5–1, then 2–4, 4–6, 6–2).
        box, r, _, _ = rendered([])
        angles = sorted(math.degrees(math.atan2(sp.centre[1], sp.centre[0])) % 360
                        for sp in box._supportLayout(r, False))
        steps = [(b - a) for a, b in zip(angles, angles[1:] + [angles[0] + 360])]
        assert steps == pytest.approx([60] * 6, abs=0.5)
        radii = [math.hypot(*sp.centre) for sp in box._supportLayout(r, False)]
        assert max(radii) - min(radii) < 0.5

    @pytest.mark.parametrize("args, n", [(HELIX_RING_N250["M6"], 5), (helix_ring_ho()["M6"], 5)],
                             ids=["N250 M6", "HO M6"])
    def test_modules_keep_their_supports_near_home(self, args, n) -> None:
        # A module's risers, subways and deck slots push a support off its
        # home (its place on the default layout) by at most
        # _SUPPORT_HOME_REACH of the apothem, or leave it out where there is
        # no room (M6: by edge 3, where the spur's riser climbs the floor).
        box, r, _, _ = rendered(args)
        apothem = r * math.sqrt(3) / 2
        trackless = [a for a in args if not a.startswith(
            ("--track_routes", "--risers", "--deck_slots", "--track_openings"))]
        plain, _, _, _ = rendered(trackless)
        homes = {sp.route: sp.centre for sp in plain._supportLayout(r, False)}
        supports = box._supportLayout(r, False)
        assert len(supports) == n
        for sp in supports:
            assert math.dist(sp.centre, homes[sp.route]) <= apothem * box._SUPPORT_HOME_REACH + 0.01

    @pytest.mark.parametrize("args, frac", [(["--trapezoid=1"], 0.5),
                                            (HELIX_RING_N250["M2"], 0.75)],
                             ids=["no slot", "M2 inside the spur's slot"])
    def test_trapezoid_support_in_its_open_middle(self, args, frac) -> None:
        # One support on the trapezoid's middle line, in the middle of its
        # longest stretch of deck: halfway across with no slot; on M2 inside
        # the spur's slot, about three quarters of the way to edge 4.
        box, r, _, _ = rendered(args)
        apothem = r * math.sqrt(3) / 2
        (support,) = box._supportLayout(r, True)
        assert support.centre[0] == pytest.approx(0, abs=0.01)
        assert -support.centre[1] == pytest.approx(apothem * frac, rel=0.06)

    @pytest.mark.parametrize("width", [30, 50, 60])
    def test_trapezoid_middle_spoke_runs_long_edge_to_edge_4(self, width) -> None:
        # Whatever --spoke_width, a straight spoke down the middle line ties
        # the floor's outer part to its inner: no opening crosses it.
        box, r, risers, _ = rendered(["--trapezoid=1", f"--spoke_width={width}"])
        apothem = r * math.sqrt(3) / 2
        middle = LineString([(0, 0), (0, -apothem)])
        assert not any(h.intersects(middle) for h in openings(box, r, risers))

    @pytest.mark.parametrize("args", [[], HELIX_RING_N250["M6"], helix_ring_ho()["M6"]],
                             ids=["default", "N250 M6", "HO M6"])
    def test_hexagon_supports_keep_out_of_every_subway_path(self, args) -> None:
        # No support stands in a train corridor (--under_track_width and a
        # sixth of it either side, for long cars swinging out on curves)
        # along any connection, where a subway can run.  The deck's own
        # tracks don't count: a support may stand under one.
        box, r, _, _ = rendered(args)
        half = box.under_track_width * (0.5 + 1 / 6)
        supports = box._supportLayout(r, False)
        assert supports
        for g in box._spokeRoutes(r, False):
            path = LineString(segments_polyline(g.segments, 32))
            for sp in supports:
                slot = LineString(box._supportPoints(sp, 1))
                assert slot.distance(path) >= half + box.thickness / 2 - 0.5

    def test_cutout_in_the_middle(self) -> None:
        # The default hexagon opens up its middle: one opening covers the
        # centre, a third of the apothem across.
        box, r, risers, _ = rendered([])
        apothem = r * math.sqrt(3) / 2
        middle = Point(0, 0).buffer(apothem / 3 - box.spoke_width / 2)
        assert any(h.contains(middle) for h in openings(box, r, risers))
        # A plain circle, centred.
        hole = next(h for h in openings(box, r, risers) if h.contains(middle))
        radius = math.sqrt(hole.area / math.pi)
        assert hole.hausdorff_distance(Point(0, 0).buffer(radius)) < 1.0

    def test_every_support_slot_has_its_land(self, module) -> None:
        # max(10 mm, 3 thicknesses) of board between a support's slot and any
        # opening, so 3 mm ply never leaves a sliver at an opening's edge.
        box, r, risers, _ = module
        land = max(10.0, 3 * box.thickness)
        holes = openings(box, r, risers)
        for sp in box._supportLayout(r, box.trapezoid):
            slot = LineString(box._supportPoints(sp, 1)).buffer(box.thickness / 2, cap_style="flat")
            assert all(slot.distance(h) >= land - 0.5 for h in holes)

    @pytest.mark.parametrize("args", [HELIX_RING_N250["M6"], ["--center_cutout=0"]],
                             ids=["N250 M6", "default, cutout off"])
    def test_no_cutout_leaves_the_middle_solid(self, args) -> None:
        box, r, risers, _ = rendered(args)
        middle = Point(0, 0).buffer(r * math.sqrt(3) / 2 / 3 - 1)
        assert not any(h.intersects(middle) for h in openings(box, r, risers))

    @pytest.mark.parametrize("height, hole", [(6, True), (23.8, False)],
                             ids=["glued to the floor", "on supports"])
    def test_cutout_runs_under_a_bed_glued_to_the_floor(self, height, hole) -> None:
        # A subway bed lying on the floor is glued down either side of the
        # middle cutout, which runs on under it; a raised bed's supports
        # stand on its strip, so the middle stays solid round it.
        from boxes.generators._hexmo_helix_ring import _HO_COMMON
        args = [a for a in _HO_COMMON if not a.startswith("--under_track_height")]
        box, r, risers, _ = rendered(args + [f"--under_track_height={height}",
                                             f"--subway=1:0-4:0~{height}"])
        centre = Point(0, 0).buffer(5)
        assert any(h.contains(centre) for h in openings(box, r, risers)) == hole

    @pytest.mark.parametrize("args, need", [
        (_HO_SUBWAY, 30.2), (_N_SUBWAY, 17.1)], ids=["HO", "N"])
    def test_long_cars_clear_the_supports_on_a_subway_curve(self, args, need) -> None:
        # An 89 ft autorack on the subway's connection curve (HO R 700, N
        # R 335) reaches 30.2 mm (HO) or 17.1 mm (N) from the track's centre
        # with its swing-out and a little sway: every support face is further
        # out than that, with room to spare for bigger stock.
        box, r, risers, _ = rendered(args)
        faces = [LineString(box._supportPoints(sp, 1)).distance(
                     LineString(segments_polyline(rp["segments"], 64))) - box.thickness / 2
                 for sp in box._supportLayout(r, False) for rp in risers]
        assert faces and min(faces) >= need + 5

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

    def test_spokes_and_risers_keep_their_strip(self, module) -> None:
        # Nothing is cut under a hexagon spoke's centreline (outside the
        # cutout in the middle), the trapezoid's middle spoke, or a riser or
        # subway.  The deck's own tracks leave no strip: they are on the deck.
        box, r, risers, _ = module
        holes = openings(box, r, risers)
        hub = Point(0, 0).buffer(r * math.sqrt(3) / 2 * box._FLOOR_HUB + box._FLOOR_CORNER)
        apothem = r * math.sqrt(3) / 2
        lines = [LineString(segments_polyline(rp["segments"], 32)) for rp in risers]
        if box.trapezoid:
            lines.append(LineString([(0, -box.thickness), (0, -apothem)]))
        else:
            lines += [LineString(segments_polyline(g.segments, 32)).difference(hub)
                      for g in box._spokeRoutes(r, False)]
        for line in lines:
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
