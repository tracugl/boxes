"""Settings for the N-scale helix ring, as used by the 3D (STEP) export.

The helix ring is six modules round a centre, M1–M5 trapezoids and M6 a full
hexagon, plus a HexmoRectangle at M6 edge 1 carrying the turnouts.  Trains
run edge 3 → edge 5 through every module, so M(n)'s edge 5 meets M(n+1)'s edge
3, and M6's edge 5 meets M1's edge 3.  The spur descends a full turn from M6's
deck to the lower level, which leaves under M6's deck at edge 1.  The README's
"Riser boards" section explains the numbers; these are the same settings, at
h=80.

The N ring is ``radius=250`` (spur curve about R300, main line R358, 22.5 mm
out from the centre line to leave room for scenery beside the spur), with a
20 mm straight where each track crosses a joint, built by :func:`helix_ring`.
The spur falls at a steady 2.28 %, leaving 3 mm spare headroom where it runs
under M6's deck and 4 mm under the entry.  (An earlier ``radius=220`` ring,
with the kite floor, has been retired.)

The few numbers that depend on the module size are worked out once and kept
here (see :class:`RingSize`), so the presets are plain data.

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
      lower ground's height in the scenery ring.

    @ivar radius     - Module outside radius (``--radius``).
    @ivar lead_in    - The straight where each track crosses a joint
                       (``--track_lead_in``); the curve between is
                       ``1.5 × inner radius − √3 × lead_in``.
    @ivar joints     - The spur's height at each joint: M6/M1, M1/M2 … M5/M6.
    @ivar spur_start - Where the spur's riser starts on M6 (mm along 1:0-5:17.5).
    @ivar return_end - Where the return's deck slot ends on M6 (mm along 3:35-1:0).
    @ivar slot_height - The spur's height where the return's slot ends on M6.
    @ivar exit       - The lower level's height leaving M6 at edge 1.
    @ivar subway     - Carry the lower level through the entry rectangle on a
                       level bed and supports (--subway), at the exit height.
    """

    radius: float
    lead_in: float
    joints: tuple
    spur_start: float
    return_end: float
    slot_height: float = 31
    exit: float = 27.8
    subway: bool = False


# One steady 2.28 % grade, leaving 45.5 mm headroom under M6's deck (2.5 more
# than a train needs) and 47.2 mm under the entry rectangle's.  The return's
# slot ends at 210 (not further), so the two slots on M6, cut wider than the
# track for long cars on curves, still leave a 10 mm web of deck between them.
SIZE_250 = RingSize(250, 20, (74, 65.6, 57.6, 49.5, 41.4, 33.3), 178, 210,
                    slot_height=28.5, exit=23.8, subway=True)

# Access walls (hand-access openings in every wall, with the subway opening
# and its cable slot in the middle post).
_WALLS = ["--access_openings=1", "--subway_ports=1"]


def helix_ring(size):
    """The six ring modules' settings for a module size.

    @param size - :class:`RingSize`.
    @returns ``{"M1": [...], …, "M6": [...]}``: HexmoHexagon options.
    """
    common = [f"--radius={size.radius:g}", "--thickness=3", "--h=80", "--edge_width=22",
              # The N finger fit in 3 mm (the generators' defaults are HO's,
              # for 6 mm): 0.6 mm clearance, flush fingers, and a 0.3 mm glue
              # gap at the bottom of every socket for paint and glue.
              "--FingerJoint_play=0.2", "--FingerJoint_extra_length=0",
              "--FingerJoint_glue_gap=0.1",
              # The track-following floor, whose supports place themselves.
              "--spoke_width=60", "--bottom=spoke",
              "--support_length=55",
              f"--track_lead_in={size.lead_in:g}",
              # N track, and the N double-track spacing (40 mm, the default
              # is HO's) for a module given more than one track line.
              "--track_width=17", "--track_spacing=40", "--under_track_width=35",
              # Every subway opening at the lower level's exit height, so they
              # line up all round (M6's edge 1 is the lower level's own).
              f"--under_track_height={size.exit:g}",
              # N track and a 40 mm train (the default is HO's).
              "--train_envelope=43",
              # A cutout in the middle of the hexagon saves next to nothing
              # at N's size.
              "--center_cutout=0"] + _CUT + _WALLS
    trapezoid = common + ["--trapezoid=1"]
    j = size.joints
    ring = {"M1": trapezoid + [
        "--track_routes=3:22.5-5:22.5,3:-17.5-5:-35",
        f"--track_openings=3:-17.5:{j[0]:g}:35,5:35:{j[1]:g}:35",
        "--deck_slots=3:-17.5-5:-35/35",
        f"--risers=3:-17.5-5:-35~{j[0]:g}..{j[1]:g}/35"]}
    for k in range(2, 6):
        # M2–M5: the spur 35 mm in throughout.
        a, b = j[k - 1], j[k]
        ring[f"M{k}"] = trapezoid + [
            "--track_routes=3:22.5-5:22.5,3:-35-5:-35",
            f"--track_openings=3:-35:{a:g}:35,5:35:{b:g}:35",
            "--deck_slots=3:-35-5:-35/35",
            f"--risers=3:-35-5:-35~{a:g}..{b:g}/35"]
    s, e = size.spur_start, size.return_end
    h, x = size.slot_height, size.exit
    ring["M6"] = common + [
        "--track_routes=1:-40-5:-22.5,3:-22.5-1:-40,1:0-5:17.5",
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
            # The N finger fit, as the ring's (see helix_ring).
            "--FingerJoint_play=0.2", "--FingerJoint_extra_length=0",
            "--FingerJoint_glue_gap=0.1",
            "--num_columns=2", "--track_width=17", "--track_spacing=40",
            f"--track_lead_in={size.lead_in:g}",
            "--under_track=1",
            f"--under_track_height={size.exit:g}", "--under_track_width=35",
            "--train_envelope=43",
            "--turnouts=10:0:-40,133.7:0:40",
            # Peco N Code 80 medium (SL-E395/396: 123.7 mm, R457, 12°); the
            # defaults are HO's.
            "--turnout_length=123.7", "--turnout_radius=457", "--turnout_angle=12",
            "--turnout_reverse_radius=300"] + _CUT + (
        [f"--subway={size.exit:g}"] if size.subway else []) + _WALLS


def with_ground(ring, size):
    """The same ring opened up for scenery (--lower_ground).

    Upper ground on the deck, lower ground at the lower level's exit height
    on the inner side of M1–M5, and M6's side walls stepped to meet them.  The
    trapezoids' decks stop 5 mm inside the main line's rail edge
    (--upper_edge_gap): a narrow shoulder, leaving about 23 mm between a long
    car on the spur and the deck edge for the scenery between the levels.  M6
    takes the same gap, so its side walls' deck joints (and fingers) match
    its neighbours'.

    @param ring - From :func:`helix_ring`.
    @param size - Its :class:`RingSize` (for the exit height).
    @returns The ring with the scenery options added.
    """
    return {name: args + [f"--lower_ground={size.exit:g}", "--upper_edge_gap=5"]
            for name, args in ring.items()}


# ------------------------------------------------------------------ HO

# The HO ring: the HO README's design (radius 500, 6 mm stock, h=100, the
# main line 40 mm outside the centre line, the spur 80 mm inside, 60 mm notches,
# slots and beds), with the lower level taken all the way down to the floor.
# One steady 1.89 % grade from the M6/M1 joint (88, on the wall tops) to M6's
# edge 1 (6: the bed lying on the floor), over the routes' 4336 mm: M1 722.4,
# M2–M5 695.0 each, M6's return 833.6.  Under M6's deck (past the return's
# slot, @450) the track is at most 13.3, leaving the 70 mm train envelope
# room under the 88 mm deck underside.  The slot ends there (not further) so the
# two slots on M6, cut wider than the track for long cars on curves, still
# leave a 10 mm web of deck between them.  The return's riser has supports down to
# 12 (2t); its bed then slopes the last ~330 mm onto the floor strip at edge 1.
# Every module after the helix carries the lower level on the floor (a flat
# bed on the floor strip, --subway 6), so needs no supports.
_HO_JOINTS = (88, 74.3, 61.2, 48.1, 34.9, 21.8)
_HO_UNDER_DECK = 13.3         # the return's height where its deck slot ends
_HO_FLOOR = 6                 # the lower level: one thickness, on the floor

# The HO README's cut settings, with every subway opening at the floor level.
_HO_COMMON = ["--radius=500", "--h=100", "--thickness=6", "--edge_width=50",
              "--spoke_width=100", "--bottom=spoke", "--top=closed",
              "--corner_holes=g2", "--gap_holes=g2", "--big_hole_shape=rounded_rect",
              "--FingerJoint_play=0.1", "--FingerJoint_extra_length=0",
              "--FingerJoint_glue_gap=0.05",
              "--track_lines=1", "--draw_track=1", "--track_width=30",
              "--track_lead_in=23", "--support_length=100", "--train_envelope=70",
              "--under_track_width=60", f"--under_track_height={_HO_FLOOR}",
              "--access_openings=1", "--subway_ports=1", "--track_guide=1",
              "--track_template=1", "--labels=0", "--reference=0"]


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
        "--deck_slots=1:0-5:40@327../60,3:80-1:0@..450/60",
        f"--risers=1:0-5:40@327..~94..88/60,3:80-1:0@..450~{j[5]:g}..{u:g}/60,"
        f"3:80-1:0@450..~{u:g}..{f:g}/60"]
    return ring


# The HO ring opened up for scenery (see with_ground): the lower ground at the
# spur's lowest trapezoid joint (M5/M6, 21.8), so it meets the track there and
# the spur climbs above it everywhere else; the decks stop 10 mm inside the main
# line (a narrow shoulder, as N's 5, leaving about 67 mm between a long car on
# the spur and the deck edge for scenery).  The track-following floor's
# supports keep wholly under the deck or the lower plate by themselves.
_HO_GROUND = 21.8
_HO_EDGE_GAP = 10


def helix_ring_ho_ground():
    """The HO ring with upper and lower ground (--lower_ground 21.8).

    @returns ``{"M1": [...], …, "M6": [...]}``: HexmoHexagon options.
    """
    return {name: args + [f"--lower_ground={_HO_GROUND:g}", f"--upper_edge_gap={_HO_EDGE_GAP:g}"]
            for name, args in helix_ring_ho().items()}


def helix_entry_ho():
    """The HO ring's entry rectangle at M6 edge 1.

    Two Peco HO medium turnouts (SL-E95/96, the --turnout defaults) split the
    entry line into M6's three deck tracks, as on the N ring: T1 (toe 10 mm
    in) sends one loop leg to −80, T2 (toe at T1's heel, 229) the other to
    +80, and the centre line runs on as the spur.  The lower level runs on the
    floor underneath.

    @returns HexmoRectangle options.
    """
    return [a for a in _HO_COMMON
            if not a.startswith(("--edge_width", "--bottom", "--top", "--support_length",
                                 "--train_envelope"))] + [
        "--slot_tolerance=1", "--num_columns=3", "--num_rows=3",
        "--turnouts=10:0:-80,229:0:80",
        "--under_track=1", f"--subway={_HO_FLOOR}/60"]


HELIX_RING_N250 = helix_ring(SIZE_250)
HELIX_ENTRY_N250 = helix_entry(SIZE_250)
HELIX_RING_N250_GROUND = with_ground(HELIX_RING_N250, SIZE_250)

RINGS = {"N250": (HELIX_RING_N250, HELIX_ENTRY_N250),
         "N250-ground": (HELIX_RING_N250_GROUND, HELIX_ENTRY_N250),
         "HO": (helix_ring_ho(), helix_entry_ho()),
         "HO-ground": (helix_ring_ho_ground(), helix_entry_ho())}
