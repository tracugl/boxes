"""Tests for --lower_ground / --upper_edge_gap: upper and lower ground (BOX-66).

On a helix-ring trapezoid the inner side opens up for scenery: the deck (upper
ground) is cut back to the outer edge of the spur's deck slot, a new lower
ground plate (top at --lower_ground) runs from the edge-4 wall to the slot's
inner edge, and the strip under the spur stays open to the floor for its
risers.  The edge-4 wall, the side walls from edge 4 to the spur and the
supports under the plate come down to carry it; across the spur the side walls
keep the spur's opening.  On the full hexagon (M6) only the walls on edges 3
and 5 step down, to meet the trapezoids beside it.

Parts are read in their own frames, as the 3D export reads them: a wall's
local x is the height above the floor panel, a panel's local frame is the deck
frame one thickness below the hexagon centre.  These tests avoid lxml (and,
except where marked, build123d), so they run in the Docker image.
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
from boxes.generators._hexmo_helix_ring import HELIX_RING_N
from boxes.generators._hexmo_track_routes import route_geometry
from boxes.generators._hexmo_deck_slots import centreline_points
from boxes.generators.hexmohexagon import HexmoHexagon

T = 3.0
GROUND = 27.8
BODY = GROUND - T
L = 74.0
SLOT = 35.0
# The deck's inner radius r (220 outside, less t / cos 30°) and apothem.
R_IN = 220 - T / math.cos(math.radians(30))
APOTHEM = R_IN * math.sqrt(3) / 2
SIDE_ORIG = R_IN


def module(name, *extra):
    box = HexmoHexagon()
    box.parseArgs(HELIX_RING_N[name] + [f"--lower_ground={GROUND:g}", *extra])
    return box


def frames(box):
    return {f.name: f for f in _hexmo_step._render_frames(box)}


def points(frame):
    """Every cut-loop point of a part, in its own frame, per loop."""
    return [[p for seg in loop for p in seg[1:]] for loop in _hexmo_step._frame_loops(frame)]


def outline(frame):
    """The part's outline points (the loop spanning most), in its own frame."""
    def area(loop):
        xs, ys = [p[0] for p in loop], [p[1] for p in loop]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))
    return max(points(frame), key=area)


def top_at(pts, y):
    """A wall outline's top (greatest height, local x) along the wall at ``y``."""
    best = -math.inf
    for a, b in zip(pts, pts[1:] + pts[:1]):
        if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
            best = max(best, a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]))
    return best


def deck_frame(p):
    """A panel-frame point → the deck frame (hexagon centre, y up)."""
    return (p[0], p[1] - T)


def slot_centre(start=3, so=-35, end=5, eo=-35):
    return centreline_points(route_geometry(start, so, end, eo, APOTHEM, 26).segments)


def distance(p, pts):
    return min(math.dist(p, q) for q in pts)


@pytest.fixture(scope="module")
def m2():
    return frames(module("M2"))


class TestOutlines:

    @pytest.mark.parametrize("name, extra", [
        ("M1", []), ("M2", []), ("M5", []), ("M6", []),
        ("M2", ["--upper_edge_gap=5"]), ("M1", ["--upper_edge_gap=15"]),
        ("M2", ["--upper_edge_gap=200"])])
    def test_every_cut_closes_with_burn(self, name, extra) -> None:
        # The default burn puts an arc at every corner; the outlines are drawn
        # as nominal closed paths, so they still close.
        box = module(name, *extra)
        box.open()
        box.render()
        # Measured on the drawn paths themselves: each cut path ends where it
        # started.
        open_ends = []
        for part in box.surface.parts:
            for path in part.pathes:
                if not _hexmo_step._is_cut(path.params.get("rgb")):
                    continue
                start = end = None
                for cmd in path.path:
                    if cmd[0] == "M":
                        if start is not None:
                            open_ends.append(math.dist(start, end))
                        start = end = (cmd[1], cmd[2])
                    elif cmd[0] in "LC":
                        end = (cmd[1], cmd[2])
                if start is not None:
                    open_ends.append(math.dist(start, end))
        assert max(open_ends) < 1e-6

    def test_off_by_default(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(HELIX_RING_N["M2"])
        assert "lower ground" not in frames(box)


class TestTrapezoid:

    def test_lower_plate_at_its_height(self, m2) -> None:
        f = m2["lower ground"]
        assert f.origin[2] == pytest.approx(BODY)
        assert f.depth == (0.0, T)

    def test_deck_stops_at_the_slot_outer_edge(self, m2) -> None:
        centre = slot_centre()
        deck = [deck_frame(p) for p in outline(m2["deck"])]
        assert min(distance(p, centre) for p in deck) == pytest.approx(SLOT / 2, abs=0.05)

    def test_lower_plate_stops_at_the_slot_inner_edge(self, m2) -> None:
        centre = slot_centre()
        plate = [deck_frame(p) for p in outline(m2["lower ground"])]
        assert min(distance(p, centre) for p in plate) == pytest.approx(SLOT / 2, abs=0.05)
        # …on the edge-4 side: it reaches the edge-4 wall's outer face.
        assert min(p[1] for p in plate) == pytest.approx(-APOTHEM - T, abs=0.05)

    def test_strip_under_the_spur_is_open(self, m2) -> None:
        # Neither panel covers the spur's centreline (its risers stand there).
        for name in ("deck", "lower ground"):
            poly = [deck_frame(p) for p in outline(m2[name])]
            mid = slot_centre()[len(slot_centre()) // 2]
            assert not _inside(poly, mid)

    def test_spur_slot_is_not_cut_in_the_deck(self, m2) -> None:
        # Only the deck's outline and the support's slot: no slot outline.
        assert len(points(m2["deck"])) == 2

    def test_the_riser_gets_its_own_bed(self, m2) -> None:
        assert any(n.startswith("riser bed") for n in m2)


class TestWalls:

    def test_edge_4_wall_lowered_all_along(self, m2) -> None:
        heights = [p[0] for p in outline(m2["wall edge 4"])]
        assert max(heights) == pytest.approx(BODY + T)      # fingers into the plate

    @pytest.mark.parametrize("edge, band", [(3, 66.1), (5, 58.5)])
    def test_side_walls_step(self, m2, edge, band) -> None:
        pts = outline(m2[f"wall edge {edge}"])
        inward = -1 if edge == 3 else 1
        spur = -35 if edge == 3 else 35
        pos_in = spur + inward * SLOT / 2
        y_in = SIDE_ORIG / 2 + pos_in

        # Sample the top: inside the lowered part (a finger or a gap between
        # fingers, so at most a thickness above the body), across the spur,
        # and outside it.
        lowered = y_in + inward * 20
        across = y_in - inward * SLOT / 2
        outer = y_in - inward * (SLOT + 20)
        assert BODY - 0.01 <= top_at(pts, lowered) <= BODY + T + 0.01
        assert top_at(pts, across) == pytest.approx(band, abs=0.01)
        assert L - 0.01 <= top_at(pts, outer) <= L + T + 0.01

    def test_holes_match_across_a_joint(self) -> None:
        # M2's edge 5 meets M3's edge 3 back to back: the same holes are kept
        # (mirrored), so the registration pins still line up.
        def holes(name, edge):
            f = frames(module(name))[f"wall edge {edge}"]
            loops = points(f)
            out = max(loops, key=len)
            centres = []
            for loop in loops:
                if loop is out:
                    continue
                xs, ys = [p[0] for p in loop], [p[1] for p in loop]
                centres.append((round((min(xs) + max(xs)) / 2, 1), round((min(ys) + max(ys)) / 2, 1)))
            return centres
        m2_5 = holes("M2", 5)
        m3_3 = sorted((x, round(SIDE_ORIG - y, 1)) for x, y in holes("M3", 3))
        assert sorted(m2_5) == pytest.approx(m3_3, abs=0.2)

    def test_no_hole_crosses_the_lowered_top(self, m2) -> None:
        for edge in (3, 4, 5):
            loops = points(m2[f"wall edge {edge}"])
            out = max(loops, key=len)
            for loop in loops:
                if loop is out:
                    continue
                assert all(_inside(out, q) for q in loop)


class TestSupports:

    def test_support_under_the_plate_is_shortened(self, m2) -> None:
        heights = [p[1] for p in outline(m2["support edge 4"])]
        assert max(heights) == pytest.approx(BODY + T)

    def test_support_under_the_deck_is_unchanged(self, m2) -> None:
        heights = [p[1] for p in outline(m2["support edge 4 #2"])]
        assert max(heights) == pytest.approx(L + T)

    def test_each_panel_carries_its_own_supports_slots(self, m2) -> None:
        # The lower plate: outline, the shortened support's slot and two kites.
        assert len(points(m2["lower ground"])) == 4
        assert len(points(m2["deck"])) == 2


class TestLowerPlateKites:
    """The floor's kites, cut short at the plate's curved edge, keeping the
    same --edge_width frame inside it as along its walls."""

    def kites(self, frame):
        out = outline(frame)
        return [l for l in points(frame) if l != out
                and max(p[0] for p in l) - min(p[0] for p in l) > 20]

    def test_two_kites_beside_the_support(self, m2) -> None:
        kites = self.kites(m2["lower ground"])
        assert len(kites) == 2
        # Either side of the central spoke (--spoke_width 60).
        assert sorted(round(min(abs(p[0]) for p in k), 1) for k in kites) == [30.0, 30.0]

    def test_kites_keep_the_frame_from_the_curved_edge(self, m2) -> None:
        centre = slot_centre()
        for kite in self.kites(m2["lower ground"]):
            gap = min(distance(deck_frame(p), centre) for p in kite) - SLOT / 2
            assert gap == pytest.approx(22, abs=0.05)

    def test_kites_follow_the_floor_s(self, m2) -> None:
        # Away from the curved edge each kite is the floor's: same edge-4 side.
        floor = [l for l in points(m2["floor"]) if l != outline(m2["floor"])]
        lows = sorted(round(min(p[1] for p in k), 2) for k in self.kites(m2["lower ground"]))
        floor_lows = {round(min(p[1] for p in k), 2) for k in floor}
        assert set(lows) <= floor_lows


class TestUpperEdgeGap:

    def test_edge_follows_the_main_line(self) -> None:
        f = frames(module("M2", "--upper_edge_gap=5"))["deck"]
        main = centreline_points(route_geometry(3, 17.5, 5, 17.5, APOTHEM, 26).segments)
        deck = [deck_frame(p) for p in outline(f)]
        inner = [p for p in deck if abs(p[0]) < 100 and p[1] < -20]   # the curved edge
        assert min(distance(p, main) for p in inner) == pytest.approx(17 / 2 + 5, abs=0.05)

    def test_never_inside_the_spur_slot(self) -> None:
        # M1's spur swings to 9 mm from the main line's rail near edge 3; a
        # 15 mm gap would reach into its slot there, so the edge keeps to it.
        f = frames(module("M1", "--upper_edge_gap=15"))["deck"]
        centre = slot_centre(3, -17.5, 5, -35)
        deck = [deck_frame(p) for p in outline(f)]
        assert min(distance(p, centre) for p in deck) >= SLOT / 2 - 0.05


@pytest.fixture(scope="module")
def m6():
    return frames(module("M6"))


class TestHexagon:

    def test_only_the_side_walls_step(self, m6) -> None:
        assert "lower ground" not in m6
        assert max(p[0] for p in outline(m6["wall edge 4"])) == pytest.approx(L + T)
        # Edge 3's spur opening is at -35, edge 5's at +17.5; inside them the
        # walls are lowered, with a plain top (no lower plate to joint into:
        # one cut by hand sits on it, flush with the trapezoids' plates).
        for edge, lowered in ((3, SIDE_ORIG / 2 - 35 - SLOT / 2 - 20),
                              (5, SIDE_ORIG / 2 + 17.5 + SLOT / 2 + 20)):
            pts = outline(m6[f"wall edge {edge}"])
            assert top_at(pts, lowered) == pytest.approx(BODY, abs=0.01)
            assert top_at(pts, lowered + (12 if edge == 3 else -12)) == pytest.approx(
                BODY, abs=0.01)


class TestErrors:

    def test_needs_the_spur_slot(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(["--trapezoid=1", "--lower_ground=27.8"])
        with pytest.raises(ValueError, match="deck slot"):
            box.open(); box.render()

    def test_needs_the_spur_openings(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(["--lower_ground=27.8"])
        with pytest.raises(ValueError, match="track_openings on edge 3"):
            box.open(); box.render()

    def test_ground_above_the_spur(self) -> None:
        box = module("M5")
        box.lower_ground = 40                      # the spur leaves at 35.6
        with pytest.raises(ValueError, match="above the spur's opening"):
            box.open(); box.render()

    def test_gap_without_lower_ground(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(HELIX_RING_N["M2"] + ["--upper_edge_gap=5"])
        with pytest.raises(ValueError, match="only applies with --lower_ground"):
            box.open(); box.render()

    def test_gap_on_the_hexagon(self) -> None:
        with pytest.raises(ValueError, match="only applies to the trapezoid"):
            b = module("M6", "--upper_edge_gap=5")
            b.open(); b.render()

    def test_support_neither_under_plate_nor_deck(self) -> None:
        # Turned across the spoke 55 mm out: clear of the spur's slot, but with
        # a 15 mm gap the deck's edge is further out than it.
        box = module("M2", "--upper_edge_gap=15")
        box.support_edges = "4@132,4@55/90"
        with pytest.raises(ValueError, match="neither under the lower plate nor under the deck"):
            box.open(); box.render()

    def test_other_opening_on_a_stepped_wall(self) -> None:
        box = module("M2")
        box.track_openings += ",3:60:70:20"
        with pytest.raises(ValueError, match="only has room for the spur's opening"):
            box.open(); box.render()

    @pytest.mark.parametrize("edit", [
        {"track_openings": "3:-35:66.1:35,5:35:58.5:35,4:0:5:10"},
        {"under_track_edges": "4", "under_track_height": 27.8}])
    def test_opening_on_the_lowered_edge_4(self, edit) -> None:
        box = module("M2")
        for k, v in edit.items():
            setattr(box, k, v)
        with pytest.raises(ValueError, match="edge-4 wall all along"):
            box.open(); box.render()


class Test3D:

    def test_parts_mesh(self) -> None:
        bd = pytest.importorskip("build123d")
        del bd
        parts = {p.name: p for p in _hexmo_step.exact_hexmo_parts(module("M2"), clearance="none")}
        plate = parts["lower ground"]
        for other in ("wall edge 3", "wall edge 4", "wall edge 5", "support edge 4"):
            common = plate.solid & parts[other].solid
            assert (sum(s.volume for s in common.solids()) if common else 0.0) < 5.0
        bb = plate.solid.bounding_box()
        assert (bb.min.Z, bb.max.Z) == pytest.approx((BODY, GROUND))


def _inside(polygon, p):
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > p[1]) != (y1 > p[1]):
            if x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0) > p[0]:
                inside = not inside
    return inside


class TestRing:

    def test_tracks_still_meet_at_every_joint(self) -> None:
        pytest.importorskip("build123d")
        ends = _hexmo_step.ring_track_ends("N-ground")
        unmatched = sorted(
            (m, round(z, 1)) for i, (m, p, z) in enumerate(ends)
            if not any(j != i and mm != m and math.dist(pp, p) < 0.5 and abs(zz - z) < 0.05
                       for j, (mm, pp, zz) in enumerate(ends)))
        assert unmatched == [("M6", 27.8), ("entry", 77.0)]

    def test_simple_parts_refuse(self) -> None:
        pytest.importorskip("build123d")
        with pytest.raises(ValueError, match="exact"):
            _hexmo_step.hexmo_parts(module("M2"))


def test_m1_with_the_preset_gap_builds_in_3d() -> None:
    # M1's deck edge at --upper_edge_gap 15 switches from the main line's
    # offset to the spur slot's edge; the switch must not leave an edge too
    # short to model (the 3D faces need closed outlines).
    pytest.importorskip("build123d")
    from boxes.generators._hexmo_helix_ring import HELIX_RING_N_GROUND
    box = HexmoHexagon()
    box.parseArgs(HELIX_RING_N_GROUND["M1"])
    parts = {p.name: p for p in _hexmo_step.exact_hexmo_parts(box, clearance="none")}
    assert parts["deck"].solid.is_valid
