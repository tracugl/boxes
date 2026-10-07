"""Tests for HexmoRectangle --access_openings (BOX-69).

Hand access under the deck, e.g. to re-rail a train on the subway: each long
wall and long support gets one large rounded-rectangle opening per cell, all
lined up, in place of their weight and registration holes.

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
from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N250
from boxes.generators.hexmorectangle import HexmoRectangle

BASE = [a for a in HELIX_ENTRY_N250 if not a.startswith("--access_openings")]


def holes(args, name):
    """Hole bounding boxes ``(x0, x1, y0, y1)`` of a part, in its own frame."""
    box = HexmoRectangle()
    box.parseArgs(args)
    frame = next(f for f in _hexmo_step._render_frames(box) if f.name == name)
    loops = _hexmo_step._frame_loops(frame)
    out = max(loops, key=len)
    boxes_ = []
    for loop in loops:
        if loop is out:
            continue
        pts = [p for seg in loop for p in seg[1:]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        boxes_.append((round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1)))
    return sorted(boxes_)


def big(boxes_):
    return [b for b in boxes_ if b[1] - b[0] > 30]


def pilots(boxes_):
    """The Ø6 holes' centres, (along, across)."""
    return sorted((round((b[0] + b[1]) / 2, 1), round((b[2] + b[3]) / 2, 1))
                  for b in boxes_ if abs((b[1] - b[0]) - 6) < 0.5 and abs((b[3] - b[2]) - 6) < 0.5)


class TestAccessOpenings:

    def test_one_opening_per_cell(self) -> None:
        # Each cell's opening shrinks to keep the Ø6 pilot pairs nearest its
        # ends: about 132 × 50 mm at radius 250.
        openings = big(holes(BASE + ["--access_openings=1"], "long wall 1"))
        assert len(openings) == 2
        for x0, x1, y0, y1 in openings:
            assert x1 - x0 == pytest.approx(131.7, abs=0.5)
            assert y1 - y0 == pytest.approx(50, abs=0.5)

    def test_keeps_the_end_pilot_pairs_where_they_were(self) -> None:
        # The pairs at each end of each opening stay at their usual places
        # (a subset of the normal wall's Ø6 holes); the rest go.
        normal = pilots(holes(BASE, "long wall 1"))
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

    def test_off_by_default(self) -> None:
        # Only the usual holes (the biggest the 50 mm weight holes).
        assert max(b[1] - b[0] for b in holes(BASE, "long wall 1")) < 60

    def test_refused_when_too_small_for_a_hand(self) -> None:
        box = HexmoRectangle()
        box.parseArgs(BASE + ["--access_openings=1", "--num_columns=5"])
        with pytest.raises(ValueError, match="access_openings"):
            box.open()
            box.render()


def test_helix_entry_has_access_openings() -> None:
    assert "--access_openings=1" in HELIX_ENTRY_N250


# ---------------------------------------------------------------- HexmoHexagon

from boxes.generators._hexmo_helix_ring import HELIX_RING_N250, HELIX_RING_N250_GROUND
from boxes.generators.hexmohexagon import HexmoHexagon


def hex_holes(args, name):
    """As :func:`holes`, for a HexmoHexagon part (wall frame: x up, y along)."""
    box = HexmoHexagon()
    box.parseArgs(args)
    frame = next(f for f in _hexmo_step._render_frames(box) if f.name == name)
    loops = _hexmo_step._frame_loops(frame)
    out = max(loops, key=len)
    found = []
    for loop in loops:
        if loop is out:
            continue
        pts = [p for seg in loop for p in seg[1:]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        found.append((round(min(ys), 1), round(max(ys), 1), round(min(xs), 1), round(max(xs), 1)))
    return sorted(found)


def plain(args):
    return [a for a in args if not a.startswith("--access")]


class TestHexagonAccess:

    def test_trapezoid_long_wall_two_openings(self) -> None:
        holes_ = hex_holes(HELIX_RING_N250["M2"], "long wall")
        openings = big(holes_)
        assert len(openings) == 2
        for y0, y1, x0, x1 in openings:
            assert y1 - y0 == pytest.approx(123.9, abs=0.5)
            assert x1 - x0 == pytest.approx(50, abs=0.5)
        # Either side of the middle, between the pilot pairs kept at each
        # end of each opening (end and centre pairs).
        assert sorted({a for a, _ in pilots(holes_)}) == pytest.approx(
            [45.0, 184.9, 308.2, 448.1], abs=0.1)
        assert len(holes_) == 2 + 8

    def test_trapezoid_other_walls_unchanged(self) -> None:
        for name in ("wall edge 3", "wall edge 4", "wall edge 5"):
            assert (hex_holes(HELIX_RING_N250_GROUND["M2"], name)
                    == hex_holes(plain(HELIX_RING_N250_GROUND["M2"]), name))

    def test_hexagon_chosen_walls(self) -> None:
        args = HELIX_RING_N250["M6"]           # --access_edges 2,4,6
        for edge in (2, 4, 6):
            holes_ = hex_holes(args, f"wall edge {edge}")
            openings = big(holes_)
            assert len(openings) == 2
            for y0, y1, x0, x1 in openings:
                # The pairs here are too close for the centre ones to stay,
                # so the end pairs stay and the openings run to the post.
                assert (y1 - y0, x1 - x0) == pytest.approx((40.3, 50), abs=0.5)
            # The middle post is as wide as the spoke, over its middle.
            assert openings[1][0] - openings[0][1] == pytest.approx(60, abs=0.1)
            assert sorted({a for a, _ in pilots(holes_)}) == pytest.approx([45.0, 201.5], abs=0.1)
        # The walls that join the entry, M5 and M1 keep their holes.
        assert len(hex_holes(args, "wall edge 1")) > 5

    @pytest.mark.parametrize("edges, match", [("1,3,5", "track or under-deck"),
                                              ("7", "edges 1–6"), ("x", "edges 1–6")])
    def test_bad_edges_refused(self, edges, match) -> None:
        box = HexmoHexagon()
        box.parseArgs(plain(HELIX_RING_N250["M6"])
                      + ["--access_openings=1", f"--access_edges={edges}"])
        with pytest.raises(ValueError, match=match):
            box.open()
            box.render()

    def test_off_by_default(self) -> None:
        box = HexmoHexagon()
        box.parseArgs([])
        assert not box.access_openings


def test_ring_presets_have_access() -> None:
    assert "--access_openings=1" in HELIX_RING_N250["M3"]
    assert "--access_edges=2,4,6" in HELIX_RING_N250["M6"]
