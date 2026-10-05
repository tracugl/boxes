"""Tests for the exact 3D parts: the real cut outlines, extruded and placed.

With ``detail="exact"`` the 3D export renders the module (at burn 0, so parts
are their nominal size), takes each assembled part's cut outline off the sheet
(finger joints, holes, kites, notches …), maps it back to the part's own frame
and places it.  Riser beds stay smooth sloping solids, with their support
slots cut through; tracks and clearance boxes are added as before.

The key check is that joined parts mesh: a wall's tabs go into the floor's and
deck's slots, not through solid board.

Needs the optional ``step`` dependency (build123d); skipped without it.
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

pytest.importorskip("build123d")

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

import build123d as bd

from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N, HELIX_RING_N
from boxes.generators._hexmo_step import (
    exact_hexmo_parts, exact_rect_parts, hexmo_parts,
)
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

T = 3.0
L = 74.0


def hexagon(args):
    box = HexmoHexagon()
    box.parseArgs(args)
    return box


@pytest.fixture(scope="module")
def m6():
    return {p.name: p for p in exact_hexmo_parts(hexagon(HELIX_RING_N["M6"]))}


@pytest.fixture(scope="module")
def m6_simple():
    return {p.name: p for p in hexmo_parts(hexagon(HELIX_RING_N["M6"]))}


@pytest.fixture(scope="module")
def m1():
    return {p.name: p for p in exact_hexmo_parts(hexagon(HELIX_RING_N["M1"]))}


@pytest.fixture(scope="module")
def entry():
    box = HexmoRectangle()
    box.parseArgs(HELIX_ENTRY_N)
    return {p.name: p for p in exact_rect_parts(box)}


def bbox(part):
    return part.solid.bounding_box()


def overlap(a, b):
    """Volume shared by two parts' solids."""
    common = a.solid & b.solid
    return sum(s.volume for s in common.solids()) if common else 0.0


class TestHexagon:

    def test_same_parts_as_the_simple_model(self, m6, m6_simple) -> None:
        cut = {n for n, p in m6_simple.items() if p.kind not in ("track", "clearance")}
        assert cut <= set(m6)

    def test_every_part_is_a_valid_solid(self, m6) -> None:
        bad = [n for n, p in m6.items() if not p.solid.is_valid]
        assert bad == []

    def test_wall_tabs_reach_into_floor_and_deck(self, m6) -> None:
        bb = bbox(m6["wall edge 2"])
        assert (bb.min.Z, bb.max.Z) == pytest.approx((-T, L + T), abs=0.01)

    def test_panels_at_their_heights(self, m6) -> None:
        assert (bbox(m6["floor"]).min.Z, bbox(m6["floor"]).max.Z) == pytest.approx((-T, 0))
        assert (bbox(m6["deck"]).min.Z, bbox(m6["deck"]).max.Z) == pytest.approx((L, L + T))

    def test_exact_parts_are_close_to_the_simple_ones(self, m6, m6_simple) -> None:
        # Same parts, give or take finger joints and holes.
        for name in ("deck", "wall edge 4", "support edge 4"):
            assert m6[name].solid.volume == pytest.approx(m6_simple[name].solid.volume, rel=0.25)
            a, b = bbox(m6[name]), bbox(m6_simple[name])
            assert (a.center().X, a.center().Y) == pytest.approx((b.center().X, b.center().Y), abs=3)

    def test_notch_on_the_right_side_of_the_wall(self, m6) -> None:
        # Edge 3's notch for the return is 35 mm anticlockwise of the wall's
        # middle (−35 from the midpoint), from 35.6 up through the top.  A point
        # in it is empty; the mirror image of that point is solid board.
        import math
        th = math.radians(330)
        u, tan = (math.cos(th), math.sin(th)), (-math.sin(th), math.cos(th))
        a = 216.5 * math.sqrt(3) / 2 + T / 2          # mid-thickness of the wall
        wall = m6["wall edge 3"].solid

        def at(pos, z):
            return bd.Vector(a * u[0] + pos * tan[0], a * u[1] + pos * tan[1], z)

        # 70 mm up: inside the notch, above the wall's big holes (≤ 62 mm).
        assert not wall.is_inside(at(-35, 70))
        assert wall.is_inside(at(35, 70))

    @pytest.mark.parametrize("panel", ["floor", "deck"])
    @pytest.mark.parametrize("wall", ["wall edge 1", "wall edge 3", "wall edge 4"])
    def test_wall_tabs_mesh_with_the_panel_slots(self, m6, panel, wall) -> None:
        # Tabs sit in slots: the solids barely touch.
        assert overlap(m6[wall], m6[panel]) < 5.0

    @pytest.mark.parametrize("panel", ["floor", "deck"])
    def test_support_tabs_mesh_with_the_panel_slots(self, m6, panel) -> None:
        assert overlap(m6["support edge 4"], m6[panel]) < 5.0

    def test_riser_supports_mesh_with_the_floor(self, m6) -> None:
        name = next(n for n in m6 if n.startswith("riser support"))
        assert overlap(m6[name], m6["floor"]) < 5.0

    def test_beds_get_their_support_slots(self, m6, m6_simple) -> None:
        bed = next(n for n in m6 if n.startswith("riser bed 1:0-5:17.5"))
        assert m6[bed].solid.volume < m6_simple[bed].solid.volume - 50


class TestTrapezoid:

    def test_long_wall_and_half_panels(self, m1) -> None:
        assert {"long wall", "wall edge 3", "wall edge 4", "wall edge 5"} <= set(m1)
        assert bbox(m1["deck"]).max.Y == pytest.approx(0, abs=0.5)

    @pytest.mark.parametrize("wall", ["long wall", "wall edge 4"])
    def test_walls_mesh_with_the_floor(self, m1, wall) -> None:
        assert overlap(m1[wall], m1["floor"]) < 5.0


class TestExtraLength:
    """A trapezoid with FingerJoint_extra_length used to be drawn with its
    outline 0.52 mm short of closing (BOX-65, since fixed); the export still
    builds the whole panel, not its holes (kites) on their own."""

    def test_trapezoid_panels_keep_their_outline(self) -> None:
        box = hexagon(["--radius=220", "--thickness=3", "--h=100", "--trapezoid=1",
                       "--bottom=spoke", "--edge_width=22", "--spoke_width=60",
                       "--FingerJoint_extra_length=0.1"])
        parts = {p.name: p for p in exact_hexmo_parts(box)}
        for name in ("deck", "floor"):
            bb = bbox(parts[name])
            # The whole half-hexagon: the outer corners are 220 mm out, and
            # the fingers' 0.3 mm extra puts the join edge's corners √3 × 0.3
            # further out on each side.
            assert bb.max.X - bb.min.X == pytest.approx(440 + 2 * 0.3 * 3 ** 0.5, abs=0.01)


class TestRectangle:

    def test_parts(self, entry) -> None:
        assert {"deck", "long wall 1", "long wall 2", "end wall 1", "end wall 2",
                "long support 1", "long support 2", "divider 1", "spoke"} <= set(entry)

    def test_walls_hang_from_the_deck_to_the_ground(self, entry) -> None:
        bb = bbox(entry["long wall 1"])
        assert bb.min.Z == pytest.approx(-T, abs=0.01)
        assert bb.max.Z == pytest.approx(L + T, abs=0.01)

    @pytest.mark.parametrize("part", ["long wall 1", "end wall 2", "long support 1", "divider 1"])
    def test_tabs_mesh_with_the_deck(self, entry, part) -> None:
        assert overlap(entry[part], entry["deck"]) < 5.0
