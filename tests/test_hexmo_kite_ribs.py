"""Tests for kite ribs under riser supports on a spoke floor (BOX-52).

On a spoke floor the kite cut-outs would leave nothing for a riser support to
slot into.  Wherever a support stands over a kite, a solid rib (a bar along
the support's slot, the slot plus a margin each side wide) is left right
across that kite, and the kite is cut as the openings either side of it.

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

from boxes.generators._hexmo_risers import clip_half_plane, min_width, rib_kites
from boxes.generators.hexmohexagon import HexmoHexagon

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

# Helix ring M1 at h=80 on a spoke floor, with its riser.
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--track_lead_in=26",
      "--track_width=17", "--bottom=spoke", "--support_length=55",
      "--support_position=125", "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
      "--track_openings=3:-17.5:72.5:26,5:35:65.2:26", "--deck_slots=3:-17.5-5:-35/26"]
M1_RISER = "--risers=3:-17.5-5:-35~72.5..65.2"


def area(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2


def openings(args):
    """Render; return (kite openings, rib lines) from the spoke floor."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    cut, ribs = [], []
    orig_cut = box._cutKites

    def spy(kites, rib_list):
        ribs.extend(rib_list)
        if rib_list:
            cut.extend(rib_kites(kites, rib_list, box.thickness + 2 * box._RIB_MARGIN,
                                 box._KITE_MIN_PIECE))
        else:
            cut.extend(kites)
        return orig_cut(kites, rib_list)

    box._cutKites = spy
    box.open()
    box.render()
    box.close()
    return cut, ribs


class TestClipping:

    def test_half_plane(self) -> None:
        part = clip_half_plane(SQUARE, (50.0, 0.0), (1.0, 0.0), 10.0)
        assert area(part) == pytest.approx(40 * 100)

    def test_min_width(self) -> None:
        assert min_width([(0, 0), (80, 0), (80, 20), (0, 20)]) == pytest.approx(20)

    def test_rib_splits_a_kite_in_two(self) -> None:
        # A support across the middle of the square, footprint along x.
        pieces = rib_kites([SQUARE], [((50.0, 50.0), (1.0, 0.0), 20.0)], 15.0, 15.0)
        assert len(pieces) == 2
        assert sum(area(p) for p in pieces) == pytest.approx(100 * 100 - 15 * 100)

    def test_far_rib_leaves_the_kite_alone(self) -> None:
        pieces = rib_kites([SQUARE], [((300.0, 50.0), (1.0, 0.0), 20.0)], 15.0, 15.0)
        assert pieces == [SQUARE]

    def test_thin_pieces_are_left_solid(self) -> None:
        # Rib 8 mm from the edge: the piece beyond it is under 15 mm wide.
        pieces = rib_kites([SQUARE], [((50.0, 15.5), (1.0, 0.0), 20.0)], 15.0, 15.0)
        assert len(pieces) == 1


class TestSpokeFloor:

    def test_without_risers_the_kites_are_unchanged(self) -> None:
        cut, ribs = openings(M1)
        assert ribs == [] and len(cut) == 2

    def test_m1_kites_get_ribs_and_supports_stand_on_solid_floor(self) -> None:
        plain, _ = openings(M1)
        cut, ribs = openings(M1 + [M1_RISER])
        # The ribs change the openings (a rib near a kite's edge can leave a
        # single piece, so the count need not grow), and remove material.
        assert ribs and cut != plain
        assert sum(area(p) for p in cut) < sum(area(p) for p in plain)
        # No support footprint touches an opening.
        for (x, y), (ax, ay), length in ribs:
            for k in range(-10, 11):
                p = (x + ax * length / 2 * k / 10, y + ay * length / 2 * k / 10)
                for poly in cut:
                    inside = all(
                        (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) > 0
                        for a, b in zip(poly, poly[1:] + poly[:1])) or all(
                        (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < 0
                        for a, b in zip(poly, poly[1:] + poly[:1]))
                    assert not inside

    def test_closed_floor_still_works(self) -> None:
        args = [a for a in M1 if a != "--bottom=spoke"] + ["--bottom=closed"]
        cut, ribs = openings(args + [M1_RISER])
        assert cut == [] and ribs == []
