"""Tests for --access_openings, the access walls (BOX-69, default since BOX-70).

Hand access under the deck, e.g. to re-rail a train on the subway: each long
wall and long support gets one large rounded-rectangle opening per cell, all
lined up; the end walls, short dividers and every HexmoHexagon wall get them
either side of a spoke-wide middle post.  The Ø6 registration pilots beside
the openings stay.

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

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators import _hexmo_step
from boxes.generators._hexmo_helix_ring import (
    HELIX_ENTRY_N250, HELIX_RING_N250, HELIX_RING_N250_GROUND,
)
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

BASE = [a for a in HELIX_ENTRY_N250 if not a.startswith("--access_openings")]


def holes(args, name):
    """Hole bounding boxes ``(x0, x1, y0, y1)`` of a part, in its own frame."""
    box = HexmoRectangle()
    box.parseArgs(args)
    frame = next(f for f in _hexmo_step._render_frames(box) if f.name == name)
    loops = _hexmo_step._frame_loops(frame)
    out = max(loops, key=_area)
    boxes_ = []
    for loop in loops:
        if loop is out:
            continue
        pts = [p for seg in loop for p in seg[1:]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        boxes_.append((round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1)))
    return sorted(boxes_)


def _area(loop):
    """Bounding-box area of a loop: the part's outline is the biggest (a
    rounded opening can have more points than it)."""
    pts = [p for seg in loop for p in seg[1:]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def big(boxes_):
    return [b for b in boxes_ if b[1] - b[0] > 30]


def pilots(boxes_):
    """The Ø6 holes' centres, (along, across)."""
    return sorted((round((b[0] + b[1]) / 2, 1), round((b[2] + b[3]) / 2, 1))
                  for b in boxes_ if abs((b[1] - b[0]) - 6) < 0.5 and abs((b[3] - b[2]) - 6) < 0.5)


class TestAccessOpenings:

    def test_one_opening_per_cell(self) -> None:
        # Each cell's opening shrinks to keep the Ø6 pilot pairs nearest its
        # ends: about 126 × 44 mm at radius 250.
        openings = big(holes(BASE + ["--access_openings=1"], "long wall 1"))
        assert len(openings) == 2
        for x0, x1, y0, y1 in openings:
            assert x1 - x0 == pytest.approx(125.7, abs=0.5)
            assert y1 - y0 == pytest.approx(44, abs=0.5)

    def test_keeps_the_end_pilot_pairs_where_they_were(self) -> None:
        # The pairs at each end of each opening stay at their usual places
        # (a subset of the normal wall's Ø6 holes); the rest go.
        normal = pilots(holes(BASE + ["--access_openings=0"], "long wall 1"))
        kept = pilots(holes(BASE + ["--access_openings=1"], "long wall 1"))
        assert set(kept) < set(normal)
        assert sorted({a for a, _ in kept}) == pytest.approx([40.7, 188.4, 238.6, 386.3], abs=0.2)
        # …and each keeps PILOT_CLEAR (5 mm) of wood to its opening.
        for x0, x1, _, _ in big(holes(BASE + ["--access_openings=1"], "long wall 1")):
            for a, _ in kept:
                assert a + 3 + 5 - 0.1 <= x0 or a - 3 - 5 + 0.1 >= x1

    def test_drops_the_medium_and_weight_holes(self) -> None:
        wall = holes(BASE + ["--access_openings=1"], "long wall 1")
        # Openings, 8 pilots and the divider's finger slot.
        assert len(wall) == 2 + 8 + 1

    def test_lined_up_on_walls_and_supports(self) -> None:
        # The long supports have no pilots, but take the walls' openings.
        args = BASE + ["--access_openings=1"]
        wall = big(holes(args, "long wall 1"))
        for name in ("long wall 2", "long support 1", "long support 2"):
            assert big(holes(args, name)) == pytest.approx(wall, abs=0.05)
        assert pilots(holes(args, "long support 1")) == []

    def test_on_by_default(self) -> None:
        assert big(holes(BASE, "long wall 1")) == big(
            holes(BASE + ["--access_openings=1"], "long wall 1"))

    def test_off_gives_the_original_walls(self) -> None:
        # Only the usual holes (the biggest the 50 mm weight holes).
        assert max(b[1] - b[0] for b in holes(BASE + ["--access_openings=0"],
                                              "long wall 1")) < 60

    def test_too_small_for_a_hand_keeps_the_original_walls(self) -> None:
        # Five cells leave each opening narrower than a hand: the long walls
        # keep their usual holes rather than being refused.
        args = BASE + ["--num_columns=5"]
        assert holes(args, "long wall 1") == holes(args + ["--access_openings=0"],
                                                   "long wall 1")


class TestEndWalls:
    """The end walls and short dividers: an opening per lane, the middle
    lane's split round the spoke-wide post that carries the subway opening."""

    DEFAULT = ["--access_openings=1"]           # radius 500, three lanes

    def test_end_wall_openings_and_port(self) -> None:
        wall = holes(self.DEFAULT, "end wall 1")
        openings = [b for b in big(wall) if b[3] - b[2] > 50]
        # The two outer lanes (the middle lane's room is taken by the post).
        assert len(openings) == 2
        # The subway opening and its cable slot, on the centre line.
        centre = (openings[0][0] + openings[1][1]) / 2
        ports = [b for b in wall if b[1] - b[0] > 20 and b not in openings
                 and (b[0] + b[1]) / 2 == pytest.approx(centre, abs=0.1)]
        assert len(ports) == 1
        # An upright cable slot near each end (20 wide; 30 tall between the
        # end pilot pair at this size).
        pills = [b for b in wall if (round(b[1] - b[0]), round(b[3] - b[2])) == (20, 30)]
        assert len(pills) == 2
        assert pills[0][1] < openings[0][0] and pills[1][0] > openings[1][1]

    def test_dividers_take_the_full_lane(self) -> None:
        # Dividers register to nothing, so their openings needn't keep pilots.
        end = [b for b in big(holes(self.DEFAULT, "end wall 1")) if b[3] - b[2] > 50]
        div = [b for b in big(holes(self.DEFAULT, "divider 1")) if b[3] - b[2] > 50]
        assert len(div) == 2
        for e, d in zip(end, div):
            assert d[0] <= e[0] and d[1] >= e[1]
        assert pilots(holes(self.DEFAULT, "divider 1")) == []

    def test_end_wall_registers_with_the_hexagon(self) -> None:
        # The entry rectangle's end wall keeps exactly the Ø6 pilots of the
        # M6 wall it joins (edge 1), in the hex wall's frame: along from its
        # end, and from the deck.
        rect = HexmoRectangle()
        rect.parseArgs(HELIX_ENTRY_N250)
        rect.open()
        dx = (rect._hexWallLength() - (rect._rectLayout().W - 2 * rect.thickness)) / 2
        end = sorted((a + dx, b) for a, b in pilots(holes(HELIX_ENTRY_N250, "end wall 1")))
        hexagon = HexmoHexagon()
        hexagon.parseArgs(HELIX_RING_N250["M6"])
        hexagon.open()
        _, l = hexagon._wallSize()
        m6 = sorted((a, l - b) for a, b in
                    pilots(hex_holes(HELIX_RING_N250["M6"], "wall edge 1")))
        assert len(end) == len(m6) == 4
        for (a, b), (c, d) in zip(end, m6):
            assert (a, b) == pytest.approx((c, d), abs=0.15)


class TestFloorStrip:
    """The floor strip (the spoke) takes access openings too, in place of its
    round weight holes: one per cell, or one between each pair of subway
    supports."""

    def test_one_per_cell(self) -> None:
        # The default module: five cells, 15 mm of wood along each long edge
        # of the 100 mm strip (the HO default --spoke_width), 15 mm clear of
        # the dividers' slots.
        openings = big(holes(["--access_openings=1"], "spoke"))
        assert len(openings) == 5
        for x0, x1, y0, y1 in openings:
            assert (y0, y1) == pytest.approx((15, 85), abs=0.05)
            assert x1 - x0 == pytest.approx(136, abs=0.5)

    def test_between_the_subway_supports(self) -> None:
        # The entry: each cell's supports are 60.7 mm apart, so an opening
        # 37.7 long fits between each pair, 10 mm clear of their slots.
        openings = big(holes(HELIX_ENTRY_N250, "spoke"))
        assert len(openings) == 6
        assert all(x1 - x0 == pytest.approx(37.7, abs=0.15) for x0, x1, _, _ in openings)

    def test_off_keeps_the_round_holes(self) -> None:
        openings = big(holes(["--access_openings=0"], "spoke"))
        assert len(openings) == 5
        assert all(y0 > 12 + 1 for _, _, y0, _ in openings)

    def test_too_narrow_keeps_the_round_holes(self) -> None:
        # A 40 mm strip leaves 16 mm between the edge bands: no openings.
        args = ["--spoke_width=40"]
        assert holes(args, "spoke") == holes(args + ["--access_openings=0"], "spoke")


def test_helix_entry_has_access_openings() -> None:
    assert "--access_openings=1" in HELIX_ENTRY_N250


# ---------------------------------------------------------------- HexmoHexagon


def hex_holes(args, name):
    """As :func:`holes`, for a HexmoHexagon part (wall frame: x up, y along)."""
    box = HexmoHexagon()
    box.parseArgs(args)
    frame = next(f for f in _hexmo_step._render_frames(box) if f.name == name)
    loops = _hexmo_step._frame_loops(frame)
    out = max(loops, key=_area)
    found = []
    for loop in loops:
        if loop is out:
            continue
        pts = [p for seg in loop for p in seg[1:]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        found.append((round(min(ys), 1), round(max(ys), 1), round(min(xs), 1), round(max(xs), 1)))
    return sorted(found)


def plain(args):
    return [a for a in args if not a.startswith("--access")] + ["--access_openings=0"]


def access(holes_):
    """The access openings alone: full height (44 mm at h=80, 15 mm of wood
    above and below), not the subway opening; wider than a cable slot."""
    return [b for b in big(holes_) if b[3] - b[2] == pytest.approx(44, abs=0.5)
            and b[1] - b[0] > 25]


class TestHexagonAccess:

    def test_trapezoid_long_wall_two_openings(self) -> None:
        holes_ = hex_holes(HELIX_RING_N250["M2"], "long wall")
        openings = access(holes_)
        assert len(openings) == 2
        for y0, y1, x0, x1 in openings:
            assert y1 - y0 == pytest.approx(117.9, abs=0.5)
            assert x1 - x0 == pytest.approx(44, abs=0.5)
        # Either side of the middle, between the pilot pairs kept at each
        # end of each opening (end and centre pairs).
        assert sorted({a for a, _ in pilots(holes_)}) == pytest.approx(
            [45.0, 184.9, 308.2, 448.1], abs=0.1)
        # The openings, the pilots, and the subway opening (no cable slots:
        # no wiring crosses the ring's outside wall).
        assert len(holes_) == 2 + 8 + 1

    def test_trapezoid_short_walls(self) -> None:
        # Edge 4 joins the next trapezoid across: two openings round the
        # post, which carries the subway opening.
        holes_ = hex_holes(HELIX_RING_N250["M2"], "wall edge 4")
        assert len(access(holes_)) == 2
        assert len(big(holes_)) == 2 + 1

    def test_trapezoid_wall_lowered_all_along_unchanged(self) -> None:
        # The edge-4 wall under the lower plate is too low for an opening.
        args = HELIX_RING_N250_GROUND["M2"]
        assert hex_holes(args, "wall edge 4") == hex_holes(plain(args), "wall edge 4")

    def test_hexagon_walls(self) -> None:
        args = HELIX_RING_N250["M6"]           # all six walls by default
        for edge in (1, 2, 4, 6):
            holes_ = hex_holes(args, f"wall edge {edge}")
            openings = access(holes_)
            assert len(openings) == 2
            for y0, y1, x0, x1 in openings:
                # The pairs here are too close for the centre ones to stay,
                # so the end pairs stay and the openings run to the post.
                assert (y1 - y0, x1 - x0) == pytest.approx((37.3, 44), abs=0.5)
            # The middle post is as wide as the spoke, over its middle.
            assert openings[1][0] - openings[0][1] == pytest.approx(60, abs=0.1)
            assert sorted({a for a, _ in pilots(holes_)}) == pytest.approx([45.0, 201.5], abs=0.1)

    def test_openings_keep_clear_of_a_track_opening(self) -> None:
        # M6 edge 3: the return's notch (35 wide, 35 mm in from the centre)
        # takes the room of the opening on its side; the other stays.  A
        # post's width of wood (15 mm) is left between them.
        args = HELIX_RING_N250["M6"]
        openings = access(hex_holes(args, "wall edge 3"))
        assert len(openings) == 1
        box = HexmoHexagon()
        box.parseArgs(args)
        box.open()
        side, _ = box._wallSize()
        notch = (side / 2 - 35 - 17.5, side / 2 - 35 + 17.5)
        for y0, y1, _, _ in openings:
            assert y0 >= notch[1] + 15 - 0.1 or y1 <= notch[0] - 15 + 0.1
        # Edge 5's spur rests on the wall top, cutting nothing: both stay.
        assert len(access(hex_holes(args, "wall edge 5"))) == 2

    @pytest.mark.parametrize("module", ["M2", "M6"])
    def test_stepped_walls_are_access_walls(self, module) -> None:
        # A --lower_ground stepped wall gets access openings in its
        # full-height part, a post's width clear of the step; nothing cuts
        # through its lowered top.
        args = HELIX_RING_N250_GROUND[module]
        box = HexmoHexagon()
        box.parseArgs(args)
        box.open()
        side, _ = box._wallSize()
        lower = 23.8 - 3                         # the lowered wall's body
        for name in ("wall edge 3", "wall edge 5"):
            holes_ = hex_holes(args, name)
            openings = access(holes_)
            assert len(openings) == 1
            # The step is past the spur's inner side, 52.5 mm from the centre.
            y_in = side / 2 + (-52.5 if name.endswith("3") else 52.5)
            for y0, y1, _, _ in openings:
                assert y0 >= y_in + 15 - 0.1 or y1 <= y_in - 15 + 0.1
            low = [h for h in holes_ if (h[1] < y_in if name.endswith("3") else h[0] > y_in)]
            assert all(x1 <= lower - 5 + 0.1 for _, _, _, x1 in low)

    def test_stepped_walls_mirror_at_the_joint(self) -> None:
        # M2's edge 5 meets M3's edge 3: their holes mirror along the wall.
        box = HexmoHexagon()
        box.parseArgs(HELIX_RING_N250_GROUND["M2"])
        box.open()
        side, _ = box._wallSize()
        a = hex_holes(HELIX_RING_N250_GROUND["M2"], "wall edge 5")
        b = hex_holes(HELIX_RING_N250_GROUND["M3"], "wall edge 3")
        mirrored = sorted((round(side - y1, 1), round(side - y0, 1), x0, x1) for y0, y1, x0, x1 in b)
        assert len(a) == len(mirrored)
        for p, q in zip(a, mirrored):
            assert p == pytest.approx(q, abs=0.15)

    @pytest.mark.parametrize("edges, match", [("7", "edges 1–6"), ("x", "edges 1–6")])
    def test_bad_edges_refused(self, edges, match) -> None:
        box = HexmoHexagon()
        box.parseArgs(plain(HELIX_RING_N250["M6"])
                      + ["--access_openings=1", f"--access_edges={edges}"])
        with pytest.raises(ValueError, match=match):
            box.open()
            box.render()

    def test_on_all_walls_by_default(self) -> None:
        box = HexmoHexagon()
        box.parseArgs([])
        assert box.access_openings and box.access_edges == "1,2,3,4,5,6"
        # At the default h the wall body is 88 mm, so the openings are 58 tall.
        for edge in range(1, 7):
            assert len([b for b in big(hex_holes([], f"wall edge {edge}"))
                        if b[3] - b[2] == pytest.approx(58, abs=0.5) and b[1] - b[0] > 25]) == 2

    def test_too_small_for_a_hand_keeps_the_original_walls(self) -> None:
        args = ["--radius=120", "--h=80"]
        assert hex_holes(args, "wall edge 1") == hex_holes(plain(args), "wall edge 1")


class TestSupports:
    """Access walls give each hexagon support one large rounded-rectangle
    opening, centred on it, with the same wood all round, in place of its
    round holes."""

    @staticmethod
    def support_holes(args):
        box = HexmoHexagon()
        box.parseArgs(args)
        frame = next(f for f in _hexmo_step._render_frames(box) if f.name.startswith("support"))
        loops = sorted(_hexmo_step._frame_loops(frame), key=_area, reverse=True)
        out = [[p for seg in loop for p in seg[1:]] for loop in loops]
        return [(min(p[0] for p in q), max(p[0] for p in q), min(p[1] for p in q),
                 max(p[1] for p in q)) for q in out]

    @pytest.mark.parametrize("args, rim", [
        (HELIX_RING_N250["M6"], 15),           # 3 mm stock: 15 mm all round
        ([], 18),                              # 6 mm stock: three thicknesses
    ], ids=["n250", "default"])
    def test_one_centred_opening_with_an_even_rim(self, args, rim) -> None:
        outline, *holes = self.support_holes(args)
        (x0, x1, y0, y1), = holes
        box = HexmoHexagon()
        box.parseArgs(args)
        t = box.thickness
        # The outline's y runs over the finger tabs (t each end).
        body = (outline[2] + t, outline[3] - t)
        assert (x0 - outline[0], outline[1] - x1) == pytest.approx((rim, rim), abs=0.05)
        assert (y0 - body[0], body[1] - y1) == pytest.approx((rim, rim), abs=0.05)

    def test_off_keeps_the_round_holes(self) -> None:
        # A 55 mm support's usual hole is one 25 mm medium hole.
        _, *holes = self.support_holes(plain(HELIX_RING_N250["M6"]))
        assert holes
        for x0, x1, y0, y1 in holes:
            assert x1 - x0 < 30 and x1 - x0 == pytest.approx(y1 - y0, abs=0.5)


def test_ring_presets_have_access() -> None:
    assert "--access_openings=1" in HELIX_RING_N250["M3"]
    assert not any(a.startswith("--access_edges") for a in HELIX_RING_N250["M6"])
