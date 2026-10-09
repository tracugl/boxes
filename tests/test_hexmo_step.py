"""Tests for the 3D (STEP) assembly export of a HexmoHexagon module.

The export builds simplified solids (no finger joints), each placed where it
sits once assembled: the floor panel and deck, the side walls with their track
openings and under-deck opening cut, the support walls, the riser beds and
supports, and the tracks as thin ribbons with a train-clearance box above
them.  z = 0 is the top of the floor panel, matching the generator's track
heights.

Needs the optional ``step`` dependency (build123d); skipped without it.
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

pytest.importorskip("build123d")

from hexmo_testutil import IGNORE_CORE_MATMUL, PLAIN_WALLS

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators._hexmo_step import export_step_file, hexmo_parts
from boxes.generators.hexmohexagon import HexmoHexagon

T = 3.0
L = 74.0                                  # wall body at h=80: floor top to deck underside
R_OUT = 220.0                             # --outside: radius is the outer corner radius
A_OUT = R_OUT * math.sqrt(3) / 2

# The helix ring's M6 (N, h=80), as in the N README.
M6 = ["--radius=220", "--thickness=3", "--h=80", "--edge_width=22", "--spoke_width=60",
      "--bottom=spoke", "--support_length=55", "--support_edges=2,4,6",
      "--track_lead_in=26", "--track_width=17",
      "--track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5",
      "--under_track_edges=1", "--under_track_height=27.8", "--under_track_width=35",
      "--track_openings=5:17.5:74:35,3:-35:35.6:35",
      "--deck_slots=1:0-5:17.5@169../35,3:35-1:0@..186/35",
      "--risers=1:0-5:17.5@169..~77..74/35,3:35-1:0@..186~35.6..31/35,"
      "3:35-1:0@186..~31..27.8/35"] + PLAIN_WALLS
# The helix ring's M1 (a trapezoid).
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--bottom=spoke",
      "--edge_width=22", "--spoke_width=60", "--support_length=55",
      "--support_edges=4@132,4@30/90", "--track_lead_in=26", "--track_width=17",
      "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
      "--track_openings=3:-17.5:74:35,5:35:66.1:35", "--deck_slots=3:-17.5-5:-35/35",
      "--risers=3:-17.5-5:-35~74..66.1/35"] + PLAIN_WALLS


def parts(args):
    """Parsed generator → {name: Part3D}."""
    box = HexmoHexagon()
    box.parseArgs(args)
    return {p.name: p for p in hexmo_parts(box)}


@pytest.fixture(scope="module")
def m6():
    return parts(M6)


def zrange(part):
    bb = part.solid.bounding_box()
    return bb.min.Z, bb.max.Z


class TestM6Parts:

    def test_panels_walls_and_supports(self, m6) -> None:
        assert {"floor", "deck"} <= set(m6)
        assert {f"wall edge {e}" for e in range(1, 7)} <= set(m6)
        assert {n for n in m6 if n.startswith("support ")} == {
            "support edge 2", "support edge 4", "support edge 6"}

    def test_heights(self, m6) -> None:
        assert zrange(m6["floor"]) == pytest.approx((-T, 0))
        assert zrange(m6["deck"]) == pytest.approx((L, L + T))
        assert zrange(m6["wall edge 1"]) == pytest.approx((0, L))
        assert zrange(m6["support edge 4"]) == pytest.approx((0, L))

    def test_deck_reaches_over_the_walls(self, m6) -> None:
        bb = m6["deck"].solid.bounding_box()
        assert (bb.min.X, bb.max.X) == pytest.approx((-R_OUT, R_OUT), abs=0.01)
        assert (bb.min.Y, bb.max.Y) == pytest.approx((-A_OUT, A_OUT), abs=0.01)

    def test_deck_slots_are_cut(self, m6) -> None:
        full = 3 * math.sqrt(3) / 2 * R_OUT ** 2 * T
        # Two 35 mm slots, roughly 190 + 190 mm long, come out of the deck.
        assert full - m6["deck"].solid.volume == pytest.approx(35 * 380 * T, rel=0.15)

    def test_wall_openings(self, m6) -> None:
        plain = m6["wall edge 2"].solid.volume
        # Edge 5: the spur crosses on the wall top (flush), so nothing is cut.
        assert m6["wall edge 5"].solid.volume == pytest.approx(plain)
        # Edge 3: the return's notch, 35 wide, from 35.6 up through the top.
        assert plain - m6["wall edge 3"].solid.volume == pytest.approx(35 * (L - 35.6) * T, rel=0.01)
        # Edge 1: the under-deck opening, 35 wide, 27.8 up to one thickness under the deck.
        assert plain - m6["wall edge 1"].solid.volume == pytest.approx(
            35 * (L - T - 27.8) * T, rel=0.01)

    def test_risers(self, m6) -> None:
        beds = sorted(n for n in m6 if n.startswith("riser bed"))
        assert len(beds) == 3
        supports = [n for n in m6 if n.startswith("riser support")]
        assert supports
        # The spur's bed slopes from deck level (77) down to the wall top (74).
        spur = next(m6[n] for n in beds if "1:0-5:17.5" in n)
        assert zrange(spur) == pytest.approx((74 - T, 77), abs=0.05)
        # Every riser support stands on the floor.
        assert all(zrange(m6[n])[0] == pytest.approx(0) for n in supports)

    def test_tracks(self, m6) -> None:
        tracks = [p for p in m6.values() if p.kind == "track"]
        # The deck tracks sit on the deck top; the lowest track is the return
        # leaving at edge 1, 27.8 above the floor panel.
        assert max(zrange(p)[1] for p in tracks) == pytest.approx(L + T + 3, abs=0.05)
        assert min(zrange(p)[0] for p in tracks) == pytest.approx(27.8, abs=0.05)

    def test_clearance_only_over_the_risers_by_default(self, m6) -> None:
        # The deck tracks can't hit anything, so only the three riser stretches
        # get a train-clearance box.
        clearances = [n for n, p in m6.items() if p.kind == "clearance"]
        assert len(clearances) == 3

    def test_smooth_sloping_bed(self, m6) -> None:
        # One smooth solid (top, bottom, two sides, two ends), not a mesh of
        # triangles, with the bed's true volume: 35 wide, 3 thick, 188 long.
        spur = next(p for n, p in m6.items() if n.startswith("riser bed 1:0-5:17.5"))
        assert len(spur.solid.faces()) <= 8
        assert spur.solid.volume == pytest.approx(35 * 3 * (357.0 - 169), rel=0.01)

    def test_return_clearance_fits_under_the_deck(self, m6) -> None:
        # Past its slot the return's train envelope must stay under the deck.
        under = [p for n, p in m6.items()
                 if p.kind == "clearance" and "3:35-1:0@186" in n]
        assert under and zrange(under[0])[1] <= L + 1e-6


class TestM1Trapezoid:

    def test_half_hexagon(self) -> None:
        m1 = parts(M1)
        assert {"wall edge 3", "wall edge 4", "wall edge 5", "long wall"} <= set(m1)
        assert "wall edge 1" not in m1
        bb = m1["deck"].solid.bounding_box()
        assert bb.max.Y == pytest.approx(0, abs=0.01)
        assert bb.min.Y == pytest.approx(-A_OUT, abs=0.01)


@pytest.mark.parametrize("mode, count", [("none", 0), ("all", None)])
def test_clearance_option(mode, count) -> None:
    box = HexmoHexagon()
    box.parseArgs(M6)
    built = hexmo_parts(box, clearance=mode)
    tracks = len([p for p in built if p.kind == "track"])
    clearances = len([p for p in built if p.kind == "clearance"])
    assert clearances == (tracks if count is None else count)


def test_bad_clearance_option() -> None:
    box = HexmoHexagon()
    box.parseArgs(M6)
    with pytest.raises(ValueError, match="clearance"):
        hexmo_parts(box, clearance="some")


def test_export_writes_an_assembly(tmp_path) -> None:
    box = HexmoHexagon()
    box.parseArgs(M6)
    path = tmp_path / "m6.step"
    export_step_file(box, path)
    text = path.read_text(errors="ignore")
    assert text.startswith("ISO-10303-21")
    # Part names survive into the file.
    assert "deck" in text and "wall edge 1" in text
