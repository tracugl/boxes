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
* ``radius=250``: bigger curves (spur about R300, main line R353), for 14 %
  more floor, with a 20 mm straight at each joint.  Its longer run lets the
  spur end lower at a gentler grade (2.28 % rather than 2.47 %), leaving 3 mm
  spare headroom where it runs under M6's deck and 4 mm under the entry.

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
      joint) to ``slot_height`` where the return's deck slot ends on M6; at
      most 31.0 (the 74 mm deck underside less a 43 mm train), lower for spare
      headroom.  ``joints`` are where that grade meets each module joint;
    * on M6 the spur leaves the deck (``spur_start`` mm along its route) as
      soon as its riser supports are clear of the return's track below, and
      the return's slot ends (``return_end`` mm) where it still leaves a deck
      web between the two slots;
    * the return then runs down to ``exit`` at edge 1, at most 27.8 (the most
      that fits a train under the entry rectangle's deck).  It is also the
      lower ground's height in the scenery ring;
    * the trapezoids' supports (``supports``, the 220 ring's kite floor only;
      the access-wall rings' track-following floor places its own): one
      radial just past the spur's slot, and one turned across the half-spoke
      just inside the main line.

    @ivar radius     - Module outside radius (``--radius``).
    @ivar lead_in    - The straight where each track crosses a joint
                       (``--track_lead_in``); the curve between is
                       ``1.5 × inner radius − √3 × lead_in``.
    @ivar joints     - The spur's height at each joint: M6/M1, M1/M2 … M5/M6.
    @ivar spur_start - Where the spur's riser starts on M6 (mm along 1:0-5:17.5).
    @ivar return_end - Where the return's deck slot ends on M6 (mm along 3:35-1:0).
    @ivar supports   - The trapezoids' --support_edges.
    @ivar slot_height - The spur's height where the return's slot ends on M6.
    @ivar exit       - The lower level's height leaving M6 at edge 1.
    @ivar subway     - Carry the lower level through the entry rectangle on a
                       level bed and supports (--subway), at the exit height.
    @ivar access     - Access walls (--access_openings and --subway_ports,
                       both on by default): hand-access openings in every
                       wall, with the subway opening and its cable slot in
                       the middle post.  Off pins the original walls (the
                       220 ring, kept as it was built).
    """

    radius: float
    lead_in: float
    joints: tuple
    spur_start: float
    return_end: float
    supports: str
    slot_height: float = 31
    exit: float = 27.8
    subway: bool = False
    access: bool = False


SIZE_220 = RingSize(220, 26, (74, 66.1, 58.5, 50.8, 43.2, 35.6), 169, 186, "4@132,4@30/90")
# One steady 2.28 % grade, leaving 46 mm headroom under M6's deck (3 more than
# a train needs) and 47.2 mm under the entry rectangle's.
SIZE_250 = RingSize(250, 20, (74, 65.6, 57.6, 49.5, 41.4, 33.3), 178, 233, "4@140,4@38/90",
                    slot_height=28, exit=23.8, subway=True, access=True)


def _walls(size):
    """The wall options for a size.

    @param size - :class:`RingSize`.
    @returns Access walls with subway ports, or the original walls.
    """
    if size.access:
        return ["--access_openings=1", "--subway_ports=1"]
    return ["--access_openings=0", "--subway_ports=0"]


def helix_ring(size):
    """The six ring modules' settings for a module size.

    @param size - :class:`RingSize`.
    @returns ``{"M1": [...], …, "M6": [...]}``: HexmoHexagon options.
    """
    common = [f"--radius={size.radius:g}", "--thickness=3", "--h=80", "--edge_width=22",
              # The access-wall ring has the track-following floor, whose
              # supports place themselves; the 220 ring keeps the kite floor
              # and its half-spoke supports, as it was built.
              "--spoke_width=60", f"--bottom={'spoke' if size.access else 'kites'}",
              "--support_length=55",
              f"--track_lead_in={size.lead_in:g}",
              "--track_width=17", "--under_track_width=35",
              # Every subway opening at the lower level's exit height, so they
              # line up all round (M6's edge 1 is the lower level's own).
              f"--under_track_height={size.exit:g}",
              # A cutout in the middle of the hexagon saves next to nothing
              # at N's size.
              "--center_cutout=0"] + _CUT + _walls(size)
    trapezoid = common + ["--trapezoid=1"] + (
        [] if size.access else [f"--support_edges={size.supports}"])
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
    h, x = size.slot_height, size.exit
    ring["M6"] = common + ([] if size.access else ["--support_edges=2,4,6"]) + [
        "--track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5",
        "--under_track_edges=1",
        f"--track_openings=5:17.5:74:35,3:-35:{j[5]:g}:35",
        f"--deck_slots=1:0-5:17.5@{s:g}../35,3:35-1:0@..{e:g}/35",
        f"--risers=1:0-5:17.5@{s:g}..~77..74/35,3:35-1:0@..{e:g}~{j[5]:g}..{h:g}/35,"
        f"3:35-1:0@{e:g}..~{h:g}..{x:g}/35"]
    return ring


def helix_entry(size):
    """The entry rectangle at M6 edge 1, for a module size.

    Two Peco medium turnouts split the entry line into M6's three deck tracks;
    the lower level passes underneath (on its own bed and supports, a subway,
    when the size has one).

    @param size - :class:`RingSize`.
    @returns HexmoRectangle options.
    """
    return [f"--radius={size.radius:g}", "--thickness=3", "--h=80", "--num_rows=3",
            "--num_columns=2", "--track_width=17", f"--track_lead_in={size.lead_in:g}",
            "--under_track=1",
            f"--under_track_height={size.exit:g}", "--under_track_width=35",
            "--turnouts=10:0:-35,133.7:0:35"] + _CUT + (
        [f"--subway={size.exit:g}"] if size.subway else []) + _walls(size)


def with_ground(ring, size):
    """The same ring opened up for scenery (--lower_ground).

    Upper ground on the deck, lower ground at the lower level's exit height
    on the inner side of M1–M5, and M6's side walls stepped to meet them.  The trapezoids' decks stop 15 mm inside the main line's rail edge
    (--upper_edge_gap), so there is little to sand away; M6 takes the same
    gap, so its side walls' deck joints (and fingers) match its neighbours'.

    @param ring - From :func:`helix_ring`.
    @param size - Its :class:`RingSize` (for the exit height).
    @returns The ring with the scenery options added.
    """
    return {name: args + [f"--lower_ground={size.exit:g}", "--upper_edge_gap=15"]
            for name, args in ring.items()}


# ------------------------------------------------------------------ HO

# The HO ring: the HO README's design (radius 500, 6 mm stock, h=100, the
# main line 40 mm outside the centre line, the spur 80 mm inside, 60 mm notches,
# slots and beds), with the lower level taken all the way down to the floor.
# One steady 1.89 % grade from the M6/M1 joint (88, on the wall tops) to M6's
# edge 1 (6: the bed lying on the floor), over the routes' 4336 mm: M1 722.4,
# M2–M5 695.0 each, M6's return 833.6.  Under M6's deck (past the return's
# slot, @490) the track is at most 12.5, leaving the 70 mm train envelope
# room under the 88 mm deck underside.  The return's riser has supports down to
# 12 (2t); its bed then slopes the last ~330 mm onto the floor strip at edge 1.
# Every module after the helix carries the lower level on the floor (a flat
# bed on the floor strip, --subway 6), so needs no supports.
_HO_JOINTS = (88, 74.3, 61.2, 48.1, 34.9, 21.8)
_HO_UNDER_DECK = 12.5         # the return's height where its deck slot ends
_HO_FLOOR = 6                 # the lower level: one thickness, on the floor

# The HO README's cut settings, with every subway opening at the floor level.
_HO_COMMON = ["--radius=500", "--h=100", "--thickness=6", "--edge_width=60",
              "--spoke_width=120", "--bottom=spoke", "--top=closed",
              "--corner_holes=g2", "--gap_holes=g2", "--big_hole_shape=rounded_rect",
              "--FingerJoint_play=0.1", "--FingerJoint_extra_length=0.05",
              "--track_lines=1", "--draw_track=1", "--track_width=30",
              "--track_lead_in=23", "--support_length=110", "--train_envelope=70",
              "--under_track_width=60", f"--under_track_height={_HO_FLOOR}",
              "--access_openings=1", "--subway_ports=1", "--labels=0", "--reference=0"]


def helix_ring_ho():
    """The HO ring's six modules (see the HO notes above).

    @returns ``{"M1": [...], …, "M6": [...]}``: HexmoHexagon options.
    """
    j = _HO_JOINTS
    trapezoid = _HO_COMMON + ["--trapezoid=1"]
    ring = {"M1": trapezoid + [
        "--track_routes=3:40-5:40,3:-40-5:-80",
        f"--track_openings=3:-40:{j[0]:g}:60,5:80:{j[1]:g}:60",
        "--deck_slots=3:-40-5:-80/60",
        f"--risers=3:-40-5:-80~{j[0]:g}..{j[1]:g}/60"]}
    for k in range(2, 6):
        a, b = j[k - 1], j[k]
        ring[f"M{k}"] = trapezoid + [
            "--track_routes=3:40-5:40,3:-80-5:-80",
            f"--track_openings=3:-80:{a:g}:60,5:80:{b:g}:60",
            "--deck_slots=3:-80-5:-80/60",
            f"--risers=3:-80-5:-80~{a:g}..{b:g}/60"]
    u, f = _HO_UNDER_DECK, _HO_FLOOR
    ring["M6"] = _HO_COMMON + [
        "--track_routes=1:-80-5:-40,3:-40-1:-80,1:0-5:40",
        "--under_track_edges=1",
        f"--track_openings=5:40:88:60,3:-80:{j[5]:g}:60",
        "--deck_slots=1:0-5:40@327../60,3:80-1:0@..490/60",
        f"--risers=1:0-5:40@327..~94..88/60,3:80-1:0@..490~{j[5]:g}..{u:g}/60,"
        f"3:80-1:0@490..~{u:g}..{f:g}/60"]
    return ring


# The HO ring opened up for scenery (see with_ground): the lower ground at the
# spur's lowest trapezoid joint (M5/M6, 21.8), so it meets the track there and
# the spur climbs above it everywhere else; the decks stop 25 mm inside the main
# line (N's 15, scaled to HO's 30 mm track).  The track-following floor's
# supports keep wholly under the deck or the lower plate by themselves.
_HO_GROUND = 21.8
_HO_EDGE_GAP = 25


def helix_ring_ho_ground():
    """The HO ring with upper and lower ground (--lower_ground 21.8).

    @returns ``{"M1": [...], …, "M6": [...]}``: HexmoHexagon options.
    """
    return {name: args + [f"--lower_ground={_HO_GROUND:g}", f"--upper_edge_gap={_HO_EDGE_GAP:g}"]
            for name, args in helix_ring_ho().items()}


def helix_entry_ho():
    """The HO ring's entry rectangle at M6 edge 1.

    M6's three deck tracks (±80 and the centre line) run straight on, the
    lower level on the floor underneath.  No turnouts: --turnouts models
    Peco's N medium turnout only.

    @returns HexmoRectangle options.
    """
    return [a for a in _HO_COMMON
            if not a.startswith(("--edge_width", "--bottom", "--top", "--support_length",
                                 "--train_envelope"))] + [
        "--slot_tolerance=1", "--num_columns=3", "--num_rows=3",
        "--track_line_count=3", "--track_spacing=80",
        "--under_track=1", f"--subway={_HO_FLOOR}/60"]


HELIX_RING_N = helix_ring(SIZE_220)
HELIX_ENTRY_N = helix_entry(SIZE_220)
HELIX_RING_N_GROUND = with_ground(HELIX_RING_N, SIZE_220)

HELIX_RING_N250 = helix_ring(SIZE_250)
HELIX_ENTRY_N250 = helix_entry(SIZE_250)
HELIX_RING_N250_GROUND = with_ground(HELIX_RING_N250, SIZE_250)

RINGS = {"N": (HELIX_RING_N, HELIX_ENTRY_N),
         "N-ground": (HELIX_RING_N_GROUND, HELIX_ENTRY_N),
         "N250": (HELIX_RING_N250, HELIX_ENTRY_N250),
         "N250-ground": (HELIX_RING_N250_GROUND, HELIX_ENTRY_N250),
         "HO": (helix_ring_ho(), helix_entry_ho()),
         "HO-ground": (helix_ring_ho_ground(), helix_entry_ho())}
