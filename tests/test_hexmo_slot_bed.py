"""Tests for a deck slot's cut-out doubling as the riser bed (BOX-55).

When a riser runs along exactly the same route, stretch and width as a deck
slot, the strip that falls out of the slot is the riser's bed: the bed's
support slots are cut in the deck inside the slot outline (before it), the
slot stops at the wall's inner face so the strip fits between the walls, and
no separate bed part is drawn.

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

from boxes.generators.hexmohexagon import HexmoHexagon

T = 3.0
R_IN = 220 - T / math.cos(math.radians(30))
APOTHEM = R_IN * math.sqrt(3) / 2

# Helix ring M1 at h=80, everything 35 mm wide.
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--track_lead_in=26",
      "--track_width=17", "--bottom=spoke", "--edge_width=22", "--spoke_width=60",
      "--support_length=55", "--support_edges=4@132,4@30/90",
      "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
      "--track_openings=3:-17.5:73.6:35,5:35:65.9:35"]
SLOT = "--deck_slots=3:-17.5-5:-35/35"
RISER = "--risers=3:-17.5-5:-35~73.6..65.9/35"


def render(args):
    """Render; return (separate beds drawn, support slots cut inside deck slots, slot plan)."""
    box = HexmoHexagon()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    beds, in_slot, plans = [0], [0], []
    orig_bed, orig_slots, orig_plan = box._drawRiserBed, box.drawDeckSlots, box._deckSlotPlan
    box._drawRiserBed = lambda *a, **kw: (beds.__setitem__(0, beds[0] + 1), orig_bed(*a, **kw))[1]

    def slots_spy(plan, isTrapezoid):
        in_slot[0] += sum(len(sl.get("stations") or []) for sl in plan)
        return orig_slots(plan, isTrapezoid)

    box.drawDeckSlots = slots_spy
    box._deckSlotPlan = lambda *a, **kw: (plans.append(orig_plan(*a, **kw)), plans[-1])[1]
    box.open()
    box.render()
    box.close()
    return beds[0], in_slot[0], plans[0]


def reach(point, edge_angle):
    n = (math.cos(math.radians(edge_angle)), math.sin(math.radians(edge_angle)))
    return point[0] * n[0] + point[1] * n[1]


class TestSlotAsBed:

    def test_matching_slot_is_the_bed(self) -> None:
        beds, in_slot, (slot,) = render(M1 + [SLOT, RISER])
        assert beds == 0                  # no separate bed part
        assert slot["bed"] and in_slot == len(slot["stations"]) > 0

    def test_bed_slot_stops_at_the_walls_inner_face(self) -> None:
        _, _, (slot,) = render(M1 + [SLOT, RISER])
        segments = slot["segments"]
        assert reach(segments[0].p0, 330) == pytest.approx(APOTHEM)
        assert reach(segments[-1].p1, 210) == pytest.approx(APOTHEM)

    def test_different_width_keeps_a_separate_bed(self) -> None:
        beds, in_slot, (slot,) = render(M1 + [SLOT, "--risers=3:-17.5-5:-35~73.6..65.9/30"])
        assert beds == 1 and in_slot == 0 and not slot["bed"]
        # An ordinary slot still runs 1 mm past the wall's inner face.
        assert reach(slot["segments"][0].p0, 330) == pytest.approx(APOTHEM + 1)

    def test_different_stretch_keeps_a_separate_bed(self) -> None:
        beds, in_slot, _ = render(M1 + [SLOT, "--risers=3:-17.5-5:-35@20..300~73.6..65.9/35"])
        assert beds == 1 and in_slot == 0

    def test_riser_without_a_slot_keeps_its_bed(self) -> None:
        beds, in_slot, plan = render(M1 + [RISER])
        assert beds == 1 and in_slot == 0 and plan == []
