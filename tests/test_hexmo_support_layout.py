"""Tests for choosing and placing HexmoHexagon supports.

``--support_edges`` picks which half-spokes get a support wall (by the edge
each points to) and ``--support_position`` moves every support along its
half-spoke.  The support walls, the deck's support slots and the bottom
panel's support slots must stay consistent, the defaults must not change, and
the deck-slot check must use the chosen supports.

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

from hexmo_testutil import IGNORE_CORE_MATMUL, apply

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_track_routes import EDGE_ANGLES
from boxes.generators.hexmohexagon import HexmoHexagon

N = ["--radius=220", "--thickness=3", "--h=80", "--track_lead_in=26", "--track_width=17",
     "--support_length=55", "--bottom=spoke"]
R_IN = 220 - 3 / math.cos(math.radians(30))
APOTHEM = R_IN * math.sqrt(3) / 2

# The helix ring's M6 and M1 (h=80), as in the N-scale README.
M6 = N + ["--track_routes=1:-17.5-5:-17.5,3:-17.5-1:-17.5,1:-17.5-5:17.5",
          "--under_track_edges=1", "--under_track_height=28.5", "--under_track_width=26",
          "--track_openings=5:17.5:72.5:26,3:-35:36.9:26",
          "--deck_slots=1:-17.5-5:17.5@157../26,3:35-1:0@..262/26"]
M1 = N + ["--trapezoid=1", "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
          "--track_openings=3:-17.5:72.5:26,5:35:65.2:26",
          "--deck_slots=3:-17.5-5:-35/26"]


def support_parts(args):
    """Render; return (deck slots, bottom slots, support wall count).

    Each slot is ``(direction°, mid-distance)`` in its panel's centre frame
    (y up), from the support-hole callback's fingerHolesAt calls mapped through
    that panel's centre transform.
    """
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    slots, centres, walls = [], [], [0]
    orig_holes, orig_fh, orig_wall = box.drawSupportHoles, None, box.rectangularWall

    def holes_spy(r, isTrapezoid=False):
        # The panel's centre frame: the callback origin moved to (r/2, H),
        # as drawSupportHoles does (then lifted for the trapezoid's frame).
        with box.saved_context():
            box.moveTo(r / 2, r * math.sqrt(3) / 2)
            centres.append(~box.ctx._m)
        found = []

        def fh(x, y, length, angle=90, **kw):
            mid = apply(box.ctx._m, (x, y + length / 2))
            found.append(mid)
            return orig_fh(x, y, length, angle=angle, **kw)

        nonlocal_fh[0], box.fingerHolesAt = box.fingerHolesAt, fh
        try:
            return orig_holes(r, isTrapezoid=isTrapezoid)
        finally:
            box.fingerHolesAt = nonlocal_fh[0]
            inv = centres[-1]
            panel = []
            for p in found:
                x, y = apply(inv, p)
                panel.append((round(math.degrees(math.atan2(y, x))) % 360,
                              round(math.hypot(x, y), 3)))
            slots.append(sorted(panel))

    nonlocal_fh = [None]

    def wall_spy(x, y, edges="eeee", *a, **kw):
        if edges == "fefe":
            walls[0] += 1
        return orig_wall(x, y, edges, *a, **kw)

    box.drawSupportHoles, box.rectangularWall = holes_spy, wall_spy
    box.open()
    orig_fh = box.fingerHolesAt
    box.render()
    box.close()
    bottom, deck = slots          # bottom panel is drawn first
    return deck, bottom, walls[0]


class TestDefaults:

    def test_full_hexagon_unchanged(self) -> None:
        deck, bottom, walls = support_parts(N)
        assert walls == 6
        assert deck == bottom
        assert [a for a, _ in deck] == sorted(EDGE_ANGLES[e] % 360 for e in range(1, 7))
        assert all(d == pytest.approx(APOTHEM / 2, abs=0.01) for _, d in deck)

    def test_listing_every_edge_is_the_default(self) -> None:
        assert support_parts(N + ["--support_edges=1,2,3,4,5,6"]) == support_parts(N)

    def test_trapezoid_unchanged(self) -> None:
        deck, bottom, walls = support_parts(N + ["--trapezoid=1"])
        assert walls == 1
        assert deck == bottom == [(270, pytest.approx(APOTHEM / 2, abs=0.01))]


class TestSupportEdges:

    @pytest.mark.parametrize("edge", [1, 2, 3, 4, 5, 6])
    def test_each_edge_maps_to_its_half_spoke(self, edge) -> None:
        deck, bottom, walls = support_parts(N + [f"--support_edges={edge}"])
        assert walls == 1
        assert deck == bottom == [(round(EDGE_ANGLES[edge]) % 360, pytest.approx(APOTHEM / 2, abs=0.01))]

    def test_every_other_spoke(self) -> None:
        deck, bottom, walls = support_parts(N + ["--support_edges=2,4,6"])
        assert walls == 3
        assert deck == bottom
        assert [a for a, _ in deck] == [30, 150, 270]

    def test_trapezoid_side_supports(self) -> None:
        deck, _, walls = support_parts(N + ["--trapezoid=1", "--support_edges=3,4,5"])
        assert walls == 3
        assert [a for a, _ in deck] == [210, 270, 330]


class TestSupportPosition:

    def test_moves_every_support(self) -> None:
        deck, bottom, _ = support_parts(N + ["--support_position=125"])
        assert deck == bottom
        assert all(d == pytest.approx(125, abs=0.01) for _, d in deck)

    @pytest.mark.parametrize("pos, match", [(20, "centre"), (170, "side wall")])
    def test_refused(self, pos, match) -> None:
        with pytest.raises(ValueError, match=match):
            support_parts(N + [f"--support_position={pos}"])


class TestRefusedEdges:

    @pytest.mark.parametrize("value, match", [("7", "1–6"), ("x", "1–6")])
    def test_bad(self, value, match) -> None:
        with pytest.raises(ValueError, match=match):
            support_parts(N + [f"--support_edges={value}"])

    def test_trapezoid_has_no_edge_1(self) -> None:
        with pytest.raises(ValueError, match="trapezoid"):
            support_parts(N + ["--trapezoid=1", "--support_edges=1"])


class TestHelixRing:

    def test_m6_with_every_other_support(self) -> None:
        deck, _, walls = support_parts(M6 + ["--support_edges=2,4,6"])
        assert walls == 3 and len(deck) == 3

    def test_m6_with_all_supports_is_refused(self) -> None:
        with pytest.raises(ValueError, match="support towards edge"):
            support_parts(M6)

    def test_m1_with_the_support_moved_out(self) -> None:
        deck, _, walls = support_parts(M1 + ["--support_position=125"])
        assert walls == 1 and deck == [(270, pytest.approx(125, abs=0.01))]

    def test_m1_with_the_default_support_is_refused(self) -> None:
        with pytest.raises(ValueError, match="support towards edge 4"):
            support_parts(M1)
