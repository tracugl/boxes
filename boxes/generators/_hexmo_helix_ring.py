"""Settings for the N-scale helix ring, as used by the 3D (STEP) export.

The helix ring is six modules round a centre, M1–M5 trapezoids and M6 a full
hexagon, plus a HexmoRectangle at M6 edge 1 carrying the turnouts.  Trains
run edge 3 → edge 5 through every module, so M(n)'s edge 5 meets M(n+1)'s edge
3, and M6's edge 5 meets M1's edge 3.  The spur descends a full turn from M6's
deck to the lower level, which leaves under M6's deck at edge 1.  The README's
"Riser boards" section explains the numbers; these are the same settings, at
h=80.

The ring comes in two module sizes, each built by :func:`helix_ring`:

* ``radius=220``: the original ring (its spur curve is about R245), with a
  26 mm straight where each track crosses a joint;
* ``radius=250``: bigger curves (spur about R300, main line R353) and a
  gentler grade (2.13 % rather than 2.47 %), for 14 % more floor, with a
  20 mm straight at each joint.

Only a few numbers depend on the size; they are worked out once per size and
kept here (see :class:`RingSize`), so the presets are plain data.

Each entry is the generator's own command-line options.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

from dataclasses import dataclass

# The cut-sheet choices for this ring: fewer pierces (g2 hole groups),
# rounded-rectangle big holes, the track-laying guide and template, no part
# labels or reference rectangle.
_CUT = ["--corner_holes=g2", "--gap_holes=g2", "--big_hole_shape=rounded_rect",
        "--track_guide=1", "--track_template=1", "--labels=0", "--reference=0"]


@dataclass(frozen=True)
class RingSize:
    """The numbers that depend on the module size.

    Worked out by these rules (heights in mm above the floor panel, at h=80):

    * the spur falls at one steady grade from 74 (the wall tops, at the M6/M1
      joint) to 31.0 (the 74 mm deck underside less a 43 mm train) where the
      return's deck slot ends on M6, so ``joints`` are where that grade meets
      each module joint;
    * on M6 the spur leaves the deck (``spur_start`` mm along its route) as
      soon as its riser supports are clear of the return's track below, and
      the return's slot ends (``return_end`` mm) where it still leaves a deck
      web between the two slots;
    * the return then runs down to 27.8 at edge 1, the most that fits a train
      under the entry rectangle's deck, whatever the size;
    * the trapezoids' supports (``supports``): one radial just past the spur's
      slot, and one turned across the half-spoke just inside the main line.

    @ivar radius     - Module outside radius (``--radius``).
    @ivar lead_in    - The straight where each track crosses a joint
                       (``--track_lead_in``); the curve between is
                       ``1.5 × inner radius − √3 × lead_in``.
    @ivar joints     - The spur's height at each joint: M6/M1, M1/M2 … M5/M6.
    @ivar spur_start - Where the spur's riser starts on M6 (mm along 1:0-5:17.5).
    @ivar return_end - Where the return's deck slot ends on M6 (mm along 3:35-1:0).
    @ivar supports   - The trapezoids' --support_edges.
    """

    radius: float
    lead_in: float
    joints: tuple
    spur_start: float
    return_end: float
    supports: str


SIZE_220 = RingSize(220, 26, (74, 66.1, 58.5, 50.8, 43.2, 35.6), 169, 186, "4@132,4@30/90")
SIZE_250 = RingSize(250, 20, (74, 66.2, 58.6, 51.1, 43.5, 36), 178, 233, "4@140,4@38/90")


def helix_ring(size):
    """The six ring modules' settings for a module size.

    @param size - :class:`RingSize`.
    @returns ``{"M1": [...], …, "M6": [...]}``: HexmoHexagon options.
    """
    common = [f"--radius={size.radius:g}", "--thickness=3", "--h=80", "--edge_width=22",
              "--spoke_width=60", "--bottom=spoke", "--support_length=55",
              f"--track_lead_in={size.lead_in:g}",
              "--track_width=17", "--under_track_width=35"] + _CUT
    trapezoid = common + ["--trapezoid=1", f"--support_edges={size.supports}"]
    j = size.joints
    ring = {"M1": trapezoid + [
        "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
        f"--track_openings=3:-17.5:{j[0]:g}:35,5:35:{j[1]:g}:35",
        "--deck_slots=3:-17.5-5:-35/35",
        f"--risers=3:-17.5-5:-35~{j[0]:g}..{j[1]:g}/35"]}
    for k in range(2, 6):
        # M2–M5: the spur 35 mm in throughout.
        a, b = j[k - 1], j[k]
        ring[f"M{k}"] = trapezoid + [
            "--track_routes=3:17.5-5:17.5,3:-35-5:-35",
            f"--track_openings=3:-35:{a:g}:35,5:35:{b:g}:35",
            "--deck_slots=3:-35-5:-35/35",
            f"--risers=3:-35-5:-35~{a:g}..{b:g}/35"]
    s, e = size.spur_start, size.return_end
    ring["M6"] = common + [
        "--support_edges=2,4,6",
        "--track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5",
        "--under_track_edges=1", "--under_track_height=27.8",
        f"--track_openings=5:17.5:74:35,3:-35:{j[5]:g}:35",
        f"--deck_slots=1:0-5:17.5@{s:g}../35,3:35-1:0@..{e:g}/35",
        f"--risers=1:0-5:17.5@{s:g}..~77..74/35,3:35-1:0@..{e:g}~{j[5]:g}..31/35,"
        f"3:35-1:0@{e:g}..~31..27.8/35"]
    return ring


def helix_entry(size):
    """The entry rectangle at M6 edge 1, for a module size.

    Two Peco medium turnouts split the entry line into M6's three deck tracks;
    the lower level passes underneath.

    @param size - :class:`RingSize`.
    @returns HexmoRectangle options.
    """
    return [f"--radius={size.radius:g}", "--thickness=3", "--h=80", "--num_rows=3",
            "--num_columns=2", "--track_width=17", f"--track_lead_in={size.lead_in:g}",
            "--under_track=1",
            "--under_track_height=27.8", "--under_track_width=35",
            "--turnouts=10:0:-35,133.7:0:35"] + _CUT


def with_ground(ring):
    """The same ring opened up for scenery (--lower_ground).

    Upper ground on the deck, lower ground at 27.8 (the lower level's exit
    height) on the inner side of M1–M5, and M6's side walls stepped to meet
    them.  The trapezoids' decks stop 15 mm inside the main line's rail edge
    (--upper_edge_gap), so there is little to sand away; M6 takes the same
    gap, so its side walls' deck joints (and fingers) match its neighbours'.

    @param ring - From :func:`helix_ring`.
    @returns The ring with the scenery options added.
    """
    return {name: args + ["--lower_ground=27.8", "--upper_edge_gap=15"]
            for name, args in ring.items()}


HELIX_RING_N = helix_ring(SIZE_220)
HELIX_ENTRY_N = helix_entry(SIZE_220)
HELIX_RING_N_GROUND = with_ground(HELIX_RING_N)

HELIX_RING_N250 = helix_ring(SIZE_250)
HELIX_ENTRY_N250 = helix_entry(SIZE_250)
HELIX_RING_N250_GROUND = with_ground(HELIX_RING_N250)

RINGS = {"N": (HELIX_RING_N, HELIX_ENTRY_N),
         "N-ground": (HELIX_RING_N_GROUND, HELIX_ENTRY_N),
         "N250": (HELIX_RING_N250, HELIX_ENTRY_N250),
         "N250-ground": (HELIX_RING_N250_GROUND, HELIX_ENTRY_N250)}
