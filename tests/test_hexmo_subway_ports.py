"""Tests for --subway_ports: every joining wall made subway-ready (BOX-69,
on by default since BOX-70).

Each wall that joins another module gets the under-deck opening in its middle
(where the spoke meets it) with a 30 × 14 mm cable slot under it, so a subway
can carry on through any joint; an access wall carries it in its middle post.
Walls whose middle can't take it (a track or spur opening there, a lowered
--lower_ground wall) are left as they are.

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

HEX = ["--radius=250", "--thickness=3", "--h=80", "--edge_width=22", "--spoke_width=60",
       "--bottom=spoke", "--support_length=55", "--track_lead_in=20", "--track_width=17",
       "--under_track_width=35", "--under_track_height=23.8", "--corner_holes=g2",
       "--gap_holes=g2", "--big_hole_shape=rounded_rect", "--support_edges=2,4,6"]


def ports(cls, args):
    """Part name → (cable slots, subway openings) found in it.

    A slot is a 30 × 14 hole; an opening one 35 wide and taller than 40.
    Each is ``(along, height above the floor)`` of its centre.
    """
    box = cls()
    box.parseArgs(args + ["--subway_ports=1"])
    found = {}
    for f in _hexmo_step._render_frames(box):
        loops = _hexmo_step._frame_loops(f)
        out = max(loops, key=len)
        slots, openings = [], []
        for loop in loops:
            if loop is out:
                continue
            pts = [p for seg in loop for p in seg[1:]]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if {round(w), round(h)} == {30, 14}:
                slots.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
            elif round(min(w, h)) == 35 and max(w, h) > 40:
                openings.append((min(xs), max(xs), min(ys), max(ys)))
        found[f.name] = (slots, openings)
    return found


def ported(found, prefix="wall edge"):
    return sorted(n for n, (slots, _) in found.items() if n.startswith(prefix) and slots)


class TestHexagon:

    def test_all_six_walls(self) -> None:
        found = ports(HexmoHexagon, HEX)
        assert ported(found) == [f"wall edge {e}" for e in range(1, 7)]

    def test_slot_centred_under_the_opening(self) -> None:
        # Hex wall frame: x up from the floor panel, y along the wall.
        slots, openings = ports(HexmoHexagon, HEX)["wall edge 2"]
        (x, y), = slots
        x0, x1, y0, y1 = openings[0]
        assert x0 == pytest.approx(23.8)                     # the track height
        assert x == pytest.approx(23.8 / 2)                  # midway to the floor
        assert y == pytest.approx((y0 + y1) / 2)             # under the middle

    def test_trapezoid_short_walls(self) -> None:
        found = ports(HexmoHexagon, HEX[:-1] + ["--trapezoid=1",
                                                "--support_edges=4@140,4@38/90"])
        assert ported(found) == ["wall edge 3", "wall edge 4", "wall edge 5"]
        # The long wall joins nothing, but its access openings' post takes one.
        assert found["long wall"][0] != []

    def test_walls_with_a_spur_in_the_middle_are_left(self) -> None:
        # The ring's M2 has its spur 35 mm in on walls 3 and 5.
        assert ported(ports(HexmoHexagon, HELIX_RING_N250["M2"])) == ["wall edge 4"]

    def test_lowered_walls_are_left(self) -> None:
        # M6 with scenery: 3 and 5 are stepped, so left; edge 1 (the lower
        # level's own opening) and the access walls 2, 4 and 6 get ports.
        assert ported(ports(HexmoHexagon, HELIX_RING_N250_GROUND["M6"])) == [
            "wall edge 1", "wall edge 2", "wall edge 4", "wall edge 6"]

    def test_access_walls_get_it_in_the_middle_post(self) -> None:
        # Between the two access openings, centred on the wall, with the
        # same 12.5 mm of wood either side (60 mm post, 35 mm opening).
        found = ports(HexmoHexagon, HEX + ["--access_openings=1", "--access_edges=2,4,6"])
        assert ported(found) == [f"wall edge {e}" for e in range(1, 7)]
        slots, openings = found["wall edge 2"]
        (x0, x1, y0, y1), = openings
        assert (y1 - y0) == pytest.approx(35)
        assert (y0 + y1) / 2 == pytest.approx(slots[0][1])

    def test_trapezoid_long_wall_with_access(self) -> None:
        found = ports(HexmoHexagon, HELIX_RING_N250["M2"] + ["--under_track_height=23.8"])
        assert found["long wall"][0] and found["long wall"][1]

    def test_middle_post_widens_for_the_opening(self) -> None:
        # A 40 mm spoke is narrower than the 35 mm opening plus 5 mm of wood
        # each side: the post widens to 45 and the openings give way.
        found = ports(HexmoHexagon, HEX + ["--spoke_width=40"])
        assert ported(found) == [f"wall edge {e}" for e in range(1, 7)]
        box = HexmoHexagon()
        box.parseArgs(HEX + ["--spoke_width=40"])
        wall = _hexmo_step._frame_loops(next(f for f in _hexmo_step._render_frames(box)
                                             if f.name == "wall edge 2"))
        spans = sorted((min(p[1] for seg in loop for p in seg[1:]),
                        max(p[1] for seg in loop for p in seg[1:])) for loop in wall
                       if max(p[0] for seg in loop for p in seg[1:])
                       - min(p[0] for seg in loop for p in seg[1:]) == pytest.approx(50, abs=0.5))
        assert len(spans) == 2
        assert spans[1][0] - spans[0][1] == pytest.approx(45, abs=0.1)

    def test_slot_left_out_without_room(self) -> None:
        # At 15 mm the opening leaves too little wall under it for the slot,
        # which goes; the opening stays.
        found = ports(HexmoHexagon, [a for a in HEX if not a.startswith("--under_track_height")]
                      + ["--under_track_height=15"])
        slots, openings = found["wall edge 2"]
        assert slots == [] and openings


class TestRectangle:

    def test_end_walls_and_dividers(self) -> None:
        found = ports(HexmoRectangle, HELIX_ENTRY_N250)
        assert sorted(n for n, (slots, _) in found.items() if slots) == [
            "divider 1", "end wall 1", "end wall 2"]

    def test_turns_on_the_openings(self) -> None:
        args = [a for a in HELIX_ENTRY_N250 if not a.startswith(("--subway=", "--under_track="))]
        found = ports(HexmoRectangle, args)
        assert all(found[n][1] for n in ("end wall 1", "end wall 2", "divider 1"))


def test_on_by_default() -> None:
    box = HexmoHexagon()
    box.parseArgs([])
    assert box.subway_ports
    assert HexmoRectangle().parseArgs([]) is None


@pytest.mark.parametrize("cls, args", [
    (HexmoHexagon, ["--h=50"]),                       # too low for the opening
    (HexmoRectangle, ["--h=50"]),
    (HexmoRectangle, ["--num_rows=2", "--spoke_width=0"]),  # a support on the centre line
])
def test_default_ports_never_refuse(cls, args) -> None:
    # On by default, so a module that can't take them renders without them.
    box = cls()
    box.parseArgs(args)
    box.open()
    box.render()
    box.close()
