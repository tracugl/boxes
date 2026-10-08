"""Tests for --subway_ports: every joining wall made subway-ready (BOX-69,
on by default since BOX-70).

Each wall that joins another module gets the under-deck opening in its middle
(where the spoke meets it), so a subway can carry on through any joint; an
access wall carries it in its middle post.  Walls whose middle can't take it
(a track or spur opening there, a lowered --lower_ground wall) are left as
they are.  Each joining access wall also gets an upright 14 × 30 mm cable slot
at each end, between a pilot pair, clear of the subway's supports.

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

    A slot is a 30 × 14 hole, as ``(x, y, w, h)``: its centre and size in
    the part's frame; an opening one 35 wide and taller than 40, as its
    bounding box ``(x0, x1, y0, y1)``.
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
                slots.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, w, h))
            elif round(min(w, h)) == 35 and max(w, h) > 40:
                openings.append((min(xs), max(xs), min(ys), max(ys)))
        found[f.name] = (slots, openings)
    return found


def ported(found, prefix="wall edge"):
    """Parts with a subway opening."""
    return sorted(n for n, (_, openings) in found.items()
                  if n.startswith(prefix) and openings)


def pilled(found, prefix="wall edge"):
    """Parts with cable slots."""
    return sorted(n for n, (slots, _) in found.items() if n.startswith(prefix) and slots)


class TestHexagon:

    def test_all_six_walls(self) -> None:
        found = ports(HexmoHexagon, HEX)
        assert ported(found) == [f"wall edge {e}" for e in range(1, 7)]

    def test_upright_slots_at_the_wall_ends(self) -> None:
        # Hex wall frame: x up from the floor panel, y along the wall.  One
        # slot near each end, 30 tall and 14 wide, in the pilot column 45 mm
        # in (the g2 corner groups' pair), centred between its two pilots.
        box = HexmoHexagon()
        box.parseArgs(HEX)
        box.open()
        side, l = box._wallSize()
        slots, _ = ports(HexmoHexagon, HEX)["wall edge 2"]
        assert len(slots) == 2
        for x, y, w, h in slots:
            assert (w, h) == pytest.approx((30, 14))
            assert x == pytest.approx(l / 2)
        assert sorted(y for _, y, _, _ in slots) == pytest.approx([45, side - 45], abs=0.01)

    def test_slots_on_every_joining_wall(self) -> None:
        # Wiring crosses any joint, spur or not; the long wall joins nothing.
        found = ports(HexmoHexagon, HELIX_RING_N250["M2"])
        assert pilled(found) == ["wall edge 3", "wall edge 4", "wall edge 5"]
        assert found["long wall"][0] == []

    def test_slots_need_room_between_the_pilots(self) -> None:
        # At h=70 the pilot pair is 34 mm apart inside: too little for the
        # 30 mm slot with 4 mm of wood each side; the access openings stay.
        found = ports(HexmoHexagon, HEX + ["--h=70"])
        assert pilled(found) == []

    def test_trapezoid_short_walls(self) -> None:
        found = ports(HexmoHexagon, HEX[:-1] + ["--trapezoid=1",
                                                "--support_edges=4@140,4@38/90"])
        assert ported(found) == ["wall edge 3", "wall edge 4", "wall edge 5"]
        # The long wall joins nothing, but its access openings' post takes
        # the subway opening (no cable slots: no wiring crosses it).
        assert found["long wall"][1] != [] and found["long wall"][0] == []

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
        box = HexmoHexagon()
        box.parseArgs(HEX)
        box.open()
        side, _ = box._wallSize()
        _, openings = found["wall edge 2"]
        (x0, x1, y0, y1), = openings
        assert (y1 - y0) == pytest.approx(35)
        assert (y0 + y1) / 2 == pytest.approx(side / 2)

    def test_trapezoid_long_wall_with_access(self) -> None:
        found = ports(HexmoHexagon, HELIX_RING_N250["M2"] + ["--under_track_height=23.8"])
        assert found["long wall"][1] and not found["long wall"][0]

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

    def test_low_opening_keeps_the_slots(self) -> None:
        # The slots are at the wall ends, so a low subway opening (15 mm)
        # doesn't crowd them.
        found = ports(HexmoHexagon, [a for a in HEX if not a.startswith("--under_track_height")]
                      + ["--under_track_height=15"])
        slots, openings = found["wall edge 2"]
        assert len(slots) == 2 and openings


class TestRectangle:

    def test_end_walls_and_dividers(self) -> None:
        found = ports(HexmoRectangle, HELIX_ENTRY_N250)
        walls = {n: v for n, v in found.items() if n.startswith(("end wall", "divider"))}
        assert ported(walls, "") == ["divider 1", "end wall 1", "end wall 2"]
        # The end walls join a module; the dividers' lane openings pass a cable.
        assert pilled(walls, "") == ["end wall 1", "end wall 2"]

    def test_slots_line_up_with_the_hexagon(self) -> None:
        # The entry's end wall and the M6 wall it joins (edge 1) have their
        # slots in the same place, measured from the wall centre and the deck.
        rect = HexmoRectangle()
        rect.parseArgs(HELIX_ENTRY_N250)
        rect.open()
        half = (rect._rectLayout().W - 2 * rect.thickness) / 2
        end = sorted((round(x - half, 1), round(y, 1))
                     for x, y, _, _ in ports(HexmoRectangle, HELIX_ENTRY_N250)["end wall 1"][0])
        hexagon = HexmoHexagon()
        hexagon.parseArgs(HELIX_RING_N250["M6"])
        hexagon.open()
        side, l = hexagon._wallSize()
        m6 = sorted((round(y - side / 2, 1), round(l - x, 1))
                    for x, y, _, _ in ports(HexmoHexagon, HELIX_RING_N250["M6"])["wall edge 1"][0])
        assert len(end) == 2 and end == m6

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
