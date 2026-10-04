"""Rectangular box with a fixed 3×5 internal grid, compatible with the HexmoHexagon
modular stacking system.

The short wall length equals one hexagon side (``--radius``), so a HexmoHexagon can
join any of its edges flush against either short wall of this rectangle.  The long
wall equals the hexagon flat-to-flat distance (``radius × √3``).

"""

# Copyright (C) 2025 Travis Cugley
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import datetime
import math
from types import SimpleNamespace

from boxes import Boxes, edges, boolarg
from boxes.Color import Color
from boxes.generators._hexmo_big_holes import HexmoBigHoleMixin
from boxes.generators._hexmo_track_guide import HexmoTrackGuideMixin
from boxes.generators._hexmo_track_template import HexmoTrackTemplateMixin
from boxes.generators._hexmo_track_routes import Arc, Line, offset_segments, segments_polyline
from boxes.generators._hexmo_turnouts import parse_turnouts, turnout_leg
from boxes.generators._hexmo_under_track import HexmoUnderTrackMixin


def _shiftY(seg, dy):
    """A ``Line``/``Arc`` moved ``dy`` mm along y."""
    if isinstance(seg, Line):
        return Line((seg.p0[0], seg.p0[1] + dy), (seg.p1[0], seg.p1[1] + dy))
    return Arc((seg.centre[0], seg.centre[1] + dy), seg.radius, seg.start_angle, seg.sweep)


class _HorizDivSpokeEdge(edges.BaseEdge):
    """Horizontal divider top edge: crossing slots with 'f' finger tabs in the spoke region.

    The horizontal divider spans W−2t = n·col_w + (n−1)·t for n = --num_rows
    lanes.  Its top edge is divided into n col_w sections by n−1 slot notches
    (for the long-support interlock at mid-height; none when n = 1).  When the
    spoke is present, the MIDDLE section (n is odd, so there is one) is itself
    split into three sub-parts:

        'e' (pre-spoke gap) | 'f' (spoke width sw) | 'e' (post-spoke gap)

    All other sections remain plain 'e'.

    The central 'f' (FingerJointEdge) section projects finger tabs UPWARD from the
    divider top edge.  These tabs slot into ``fingerHolesAt`` cuts in the spoke
    panel's face, locking the dividers and spoke together at the top of the box.

    **Height management:** 'f' tabs add ``t`` to the panel bounding-box height.
    To keep the assembled height at exactly ``h``, horizontal dividers are drawn
    with panel height ``h − t`` (see ``render()``).  The tabs then bring the total
    to ``(h − t) + t = h``.  The crossing-slot depth is also reduced from ``h/2``
    to ``h/2 − t`` so the interlock with vertical dividers still meets at y=``h/2``
    in the assembled box.

    Each segment is drawn by calling the edge object directly (no CompoundEdge
    step-adjustments), so all sections share the same baseline at y = panel-height.

    @param boxes      - Parent Boxes instance providing the drawing context.
    @param col_w      - Width of each lane section in mm.
    @param slot_depth - Depth of the crossing-slot notches (= h/2 − t when spoke present).
    @param sw         - Spoke width in mm (only this central span gets 'f' tabs).
    @param n_lanes    - Number of lanes (--num_rows); must be odd.
    """

    def __init__(self, boxes, col_w, slot_depth, sw, n_lanes=3) -> None:
        super().__init__(boxes, None)
        self._col_w      = col_w
        self._slot_depth = slot_depth
        self._sw         = sw
        self._n          = n_lanes

        # Compute the plain-'e' sub-sections flanking the 'f' strip inside the
        # middle section.  Lane k spans [k·(col_w+t), k·(col_w+t)+col_w]; the
        # middle lane is k = n//2.  The spoke is centred on the whole width:
        #   side_gap = (total_w − sw) / 2.
        t           = boxes.thickness
        total_w     = n_lanes * col_w + (n_lanes - 1) * t   # = W − 2t
        side_gap    = (total_w - sw) / 2
        mid_start   = (n_lanes // 2) * (col_w + t)          # x-start of middle lane
        self._pre   = max(0.0, side_gap - mid_start)                    # gap before 'f'
        self._post  = max(0.0, (mid_start + col_w) - (side_gap + sw))  # gap after 'f'

    def startWidth(self) -> float:
        """Return 0; the edge starts flush with the panel boundary."""
        return 0.0

    def endWidth(self) -> float:
        """Return 0; the edge ends flush with the panel boundary."""
        return 0.0

    def margin(self) -> float:
        """Return the tab protrusion height so move='up' allocates correct space.

        The central 'f' section draws finger tabs that protrude ``thickness`` mm
        above the panel face.  Returning ``thickness`` here lets ``spacing()``
        (= startWidth + margin = 0 + t = t) correctly account for this protrusion
        in the ``overallheight`` calculation inside ``rectangularWall``, preventing
        column-1 panels from overlapping in the SVG layout.
        """
        return self.boxes.thickness

    def __call__(self, length, **kw):
        """Draw the composite edge for ``length`` mm.

        Draws the lanes left to right with a crossing slot between each pair:
        plain 'e' lanes, except the middle lane, which is 'e'+'f'+'e'.  The
        total length equals W−2t = n·col_w + (n−1)·t, which must equal
        ``length``.

        @param length - Total edge length (must equal W−2t).
        """
        t      = self.boxes.thickness
        e_edge = self.edges['e']
        f_edge = self.edges['f']
        slot   = edges.Slot(self.boxes, self._slot_depth)

        for k in range(self._n):
            if k:
                # Crossing slot (t wide, slot_depth deep) for long support k.
                slot(t)
            if k != self._n // 2:
                e_edge(self._col_w)
                continue
            # Middle lane: 'e' gap + 'f' spoke tabs + 'e' gap.  'f' tabs
            # project upward into the spoke face's fingerHoles.  The panel is
            # drawn at height h−t so that tabs + body = h total bounding-box.
            if self._pre > 0:
                e_edge(self._pre)
            f_edge(self._sw)
            if self._post > 0:
                e_edge(self._post)


class _ShortWallTopEdge(edges.BaseEdge):
    """Short outer wall top edge: plain 'e' flanking a central 'F' counterpart slot.

    Draws the top edge of a short outer wall as three segments in sequence:
        'e' (side_gap mm) | 'F' (sw mm) | 'e' (side_gap mm)

    where ``side_gap = (W − 2t − sw) / 2``.  The central ``'F'`` section cuts
    FingerJointEdgeCounterPart notches into the wall's top EDGE (open at the edge,
    not a closed rectangle on the face), exactly matching the spoke panel's ``'f'``
    end tabs (both spanning ``sw`` mm).

    **Why not CompoundEdge?**
    ``CompoundEdge`` calls ``self.step(e.startWidth() - lastwidth)`` between each
    pair of segments.  When transitioning from ``'e'`` (endWidth=0) to ``'F'``
    (startWidth=t), it calls ``step(t)``, which moves the turtle t mm outward
    (perpendicular to the edge), growing the panel bounding-box height from h to
    h+t.  This class avoids that by calling each segment's ``__call__`` directly
    with no step adjustments, keeping all sections at the same baseline y=h and
    the wall bounding box exactly ``h`` mm tall.

    @param boxes    - Parent Boxes instance providing the drawing context.
    @param side_gap - Plain 'e' length on each side of the counterpart slot (mm).
    @param sw       - Spoke width in mm; also the length of the central 'F' section.
    """

    def __init__(self, boxes, side_gap, sw) -> None:
        super().__init__(boxes, None)
        self._side_gap = side_gap
        self._sw       = sw

    def startWidth(self) -> float:
        """Return 0; the edge starts flush with the panel boundary."""
        return 0.0

    def endWidth(self) -> float:
        """Return 0; the edge ends flush with the panel boundary."""
        return 0.0

    def __call__(self, length, **kw):
        """Draw the short outer wall top edge.

        Sequence: plain 'e' for ``side_gap`` mm, then 'F' counterpart notches for
        ``sw`` mm, then plain 'e' for ``side_gap`` mm.  All three segments are
        called directly (no ``step()`` between them), so the total bounding-box
        height stays exactly h.

        @param length - Total edge length (= W−2t = 2·side_gap + sw).
        """
        e_edge = self.edges['e']
        F_edge = self.edges['F']
        # Left plain section — no joint, open top edge
        e_edge(self._side_gap)
        # Central 'F' counterpart notches — cut INTO the edge, open at the top,
        # matching the spoke panel's 'f' end tabs (sw mm long on both panels).
        F_edge(self._sw)
        # Right plain section — no joint, open top edge
        e_edge(self._side_gap)


class HexmoRectangle(HexmoBigHoleMixin, HexmoTrackGuideMixin, HexmoTrackTemplateMixin,
                     HexmoUnderTrackMixin, Boxes):
    """Rectangular tray with a 3×N internal grid, compatible with HexmoHexagon stacking.

    The number of column compartments N is controlled by ``--num_columns`` (default 0 = auto).
    When auto, N is chosen based on ``--radius`` so that the compartment cells remain a
    useful size: large boxes (radius ≥ 400) use 5 columns; medium boxes
    (300 ≤ radius < 400) use 3 columns; small boxes (radius < 300) use 2 columns
    (a single central divider).
    """

    # The ``--radius`` parameter is the **inner corner-to-corner radius** of a regular
    # hexagon and must be set to the same value used on the HexmoHexagon boxes you want
    # to connect to this tray.  All dimensions are derived from it using the same
    # formulas as HexmoHexagon so that edges and faces mate flush:

    # - Short wall panel width  W = ``radius − 2 × thickness``
    #   (matches the laser-cut panel width of one HexmoHexagon side-wall, ensuring
    #   flush edge-to-edge alignment when the two box types are placed side by side)
    # - Short wall inner cavity = ``W − 2t`` (after subtracting the two long-wall
    #   thicknesses on either end of the short dimension)
    # - Long wall inner width   H = ``radius × √3``
    #   (matches the HexmoHexagon flat-to-flat inner cavity distance)
    # - Column inner width      = ``(W − 4t) / 3`` (3 equal columns across the short axis)
    # - Row inner height        = ``(H − 4t) / 5`` (5 equal rows along the long axis)

    # FingerJoint settings are set to match HexmoHexagon (finger=5, space=5,
    # surroundingspaces=2, play=0.2) so that joints between the two box types are
    # compatible.

    # Internal 3×5 grid crossing-joint convention:
    #   - Vertical dividers (2, spanning H): slots cut from the **bottom** edge,
    #     depth h/2, allowing horizontal dividers to slide in from above.
    #   - Horizontal dividers (4, spanning W): slots cut from the **top** edge,
    #     depth h/2, meshing with the vertical dividers' bottom slots at the
    #     midpoint of the wall height.
    # 

    ui_group = "Box"

    # Alignment-hole geometry constants — identical values to HexmoHexagon so
    # that pins and holes from both box types are interchangeable during assembly.
    _SPACER = 15    # minimum edge-to-hole-centre clearance (mm)
    _R2     = 12.5  # radius of medium alignment-pin receiver holes (mm)
    _R3     = 3     # radius of small registration pilot holes (mm)
    _MIN_CLEAR = 5.0  # minimum clearance between adjacent hole edges (mm)

    def __init__(self) -> None:
        """Initialise argument parser with FingerJoint settings and the ``--radius`` parameter."""
        Boxes.__init__(self)

        # Default thickness to 6 mm — typical for laser-cut board-game storage boxes
        # and matches HexmoHexagon's default.
        defaultgroup = self.argparser._action_groups[1]
        for action in defaultgroup._actions:
            if action.dest == 'thickness':
                action.default = 6.0

        # Finger-joint settings match HexmoHexagon so joints are interchangeable
        # when the two box types are physically connected during assembly.
        self.addSettingsArgs(
            edges.FingerJointSettings,
            finger=5, space=5, surroundingspaces=2, play=0.2,
        )

        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--radius", action="store", type=float, default=500.0,
            help="Inner corner-to-corner radius of the matching HexmoHexagon (mm). "
                 "Use the same value as the HexmoHexagon --radius to ensure edges "
                 "mate flush.  Short wall W = radius − 2×thickness; "
                 "long wall H = radius × √3.",
        )
        self.argparser.add_argument(
            "--spoke_width", action="store", type=float, default=120.0,
            help="Pass any non-zero value to include the centre support spoke; pass 0 "
                 "to omit it.  The spoke is a flat panel spanning the full inner short "
                 "axis (W − 2×thickness) and the full long axis (H = radius × √3).  "
                 "Its short ends carry finger tabs ('f') that slot into "
                 "FingerJointEdgeCounterPart notches on the top edge of each short "
                 "outer wall, and its face carries fingerHoles so that the four "
                 "horizontal dividers can lock in from below.  The numeric value of "
                 "this parameter is no longer used as a width — the span is always "
                 "W − 2t.  Default 120 (non-zero → spoke included).",
        )
        self.argparser.add_argument(
            "--slot_tolerance", action="store", type=float, default=1.0,
            help="Extra depth added to both the vertical-divider bottom slots and the "
                 "horizontal-divider top slots (mm).  The two slot sets meet exactly at "
                 "mid-height with tolerance=0; adding a positive value gives each slot "
                 "that many extra mm of depth so the panels seat fully despite laser "
                 "kerf and material-thickness variation.  1–2 mm is typical.  "
                 "Default 1.0.",
        )
        self.argparser.add_argument(
            "--num_columns", action="store", type=int, default=0,
            help="Number of column compartments along the long (H = radius × √3) axis "
                 "(they appear as columns in the SVG output).  "
                 "Determines how many horizontal dividers are cut: N columns require N−1 "
                 "dividers.  0 (default) auto-selects based on --radius: "
                 "radius ≥ 400 → 5 columns, 300 ≤ radius < 400 → 3 columns, "
                 "radius < 300 → 2 columns (one central divider).  "
                 "Minimum value is 1 (no horizontal dividers); maximum is 5.",
        )
        self.argparser.add_argument(
            "--num_rows", action="store", type=int, default=3,
            help="Number of lanes across the short (W) axis.  N lanes need N−1 "
                 "long internal supports (the dividers that run the full length "
                 "and slot into both end walls).  3 (default) gives two long "
                 "supports.  1 gives none: one open lane with no long-support "
                 "slots in the end walls or base, which suits small (e.g. N-scale) "
                 "modules where those slots would clash with the end-wall big hole.  "
                 "The centre spoke runs down the middle lane, so an even value "
                 "needs --spoke_width 0.",
        )

        # --- Track-guide markings (base plate) ---------------------------------
        # A HexmoRectangle is a straight module: track runs straight down its long
        # (H = radius × √3) axis, entering/leaving through the two short walls.
        # These options etch that straight track onto the base plate as a laying
        # guide.  They mirror the HexmoHexagon track parameters (same names) minus
        # the curve-only ones (no route selection, no radius label — a straight has
        # no finite radius).
        self.argparser.add_argument(
            "--track_lines", action="store", type=boolarg, default=True,
            help="Etch a straight track guide down the long axis of the base "
                 "plate (an engrave pass, not a cut).  Master switch for all the "
                 "track_* options below.")
        self.argparser.add_argument(
            "--track_line_count", action="store", type=int, default=1,
            help="Number of parallel track centrelines.  1 draws a single "
                 "centreline; higher counts add parallel tracks offset across the "
                 "short axis, spaced by --track_spacing (odd counts keep one on "
                 "the centre, even counts straddle it).")
        self.argparser.add_argument(
            "--track_spacing", action="store", type=float, default=80.0,
            help="Lateral spacing (mm) between adjacent track centrelines when "
                 "--track_line_count > 1.  Defaults to 80 mm.")
        self.argparser.add_argument(
            "--track_offset", action="store", type=str, default="centred",
            choices=["centred", "outer", "inner"],
            help="How multiple track lines (--track_line_count > 1) are placed "
                 "relative to the centreline.  'centred' (default) straddles the "
                 "centreline symmetrically.  'outer' keeps the centreline as the "
                 "base line and steps every additional line to one side only (+y), "
                 "the counterpart of the HexmoHexagon 'outer' (larger-radius) "
                 "side, so parallel tracks line up across a hex↔straight joint "
                 "when modules share the same track settings.  'inner' is the "
                 "mirror: extra lines step to −y, the counterpart of the "
                 "HexmoHexagon 'inner' (tighter-radius) side.  No effect when "
                 "--track_line_count is 1.")
        self.argparser.add_argument(
            "--track_center_offset", action="store", type=float, default=0.0,
            help="Signed lateral shift (mm) applied to the reference centreline "
                 "itself before the per-track --track_offset spacing is added.  "
                 "0 (default) is the true panel centre.  Positive moves it toward "
                 "+y (the counterpart of the HexmoHexagon 'outer'/larger-radius "
                 "side, so a shifted straight still matches a shifted hex curve "
                 "across a joint); negative moves it toward -y.  The whole track "
                 "family (and its --track_offset spacing) shifts with it.  With "
                 "--track_line_count 1 this simply relocates the single "
                 "centreline off the panel centre.")
        self.argparser.add_argument(
            "--draw_center", action="store", type=boolarg, default=False,
            help="Etch the track centreline(s) themselves.  Off by default.")
        self.argparser.add_argument(
            "--draw_track", action="store", type=boolarg, default=True,
            help="Etch the two track-footprint edges at ± track_width/2 either "
                 "side of each centreline, showing where the laid track sits.")
        self.argparser.add_argument(
            "--track_width", action="store", type=float, default=30.0,
            help="Physical width (mm) of the laid track/roadbed, used by "
                 "--draw_track for the footprint edges.  30 mm HO, 17 mm N.")
        self.argparser.add_argument(
            "--track_lead_in", action="store", type=float, default=30.0,
            help="Distance (mm) in from each short-wall end at which the "
                 "entry/exit crossing tick is drawn (see --track_crossing).")
        self.argparser.add_argument(
            "--track_crossing", action="store", type=boolarg, default=True,
            help="Etch a crossing tick perpendicular to the track at each end "
                 "(offset inward by --track_lead_in) marking where the track "
                 "enters/leaves the module.  Only drawn when --track_lead_in > 0.")
        self.argparser.add_argument(
            "--turnouts", action="store", type=str, default="",
            help="Turnouts etched on the deck, comma-separated 'toe:from:to': the "
                 "toe this many mm along the deck, on the straight track at lateral "
                 "offset 'from' (as for the track lines, + is +y); its diverging leg "
                 "curves off and settles at offset 'to', whose sign gives the hand, "
                 "by the end of the deck.  Every turnout faces the same end.  E.g. "
                 "the helix ring's entry: '10:0:-35,133.7:0:35'.  Blank (default): "
                 "none.")
        self.argparser.add_argument(
            "--turnout_length", action="store", type=float, default=123.7,
            help="Turnout length, toe to heel (mm).  Default: Peco N medium "
                 "(SL-E395/396).")
        self.argparser.add_argument(
            "--turnout_radius", action="store", type=float, default=457.0,
            help="Radius (mm) of the turnout's diverging road.  Default: Peco N "
                 "medium.")
        self.argparser.add_argument(
            "--turnout_angle", action="store", type=float, default=14.0,
            help="Turnout crossing angle (degrees).  Default: Peco N medium.")
        self.argparser.add_argument(
            "--turnout_reverse_radius", action="store", type=float, default=300.0,
            help="Radius (mm) of the flexible-track curve that brings a "
                 "diverging leg back parallel at its offset.")
        # --track_guide / --track_guide_clearance, shared with HexmoHexagon so
        # both generators cut the same guide plate.
        self._addTrackGuideArgs()
        # --track_template, --track_gauge, …, shared with HexmoHexagon.
        self._addTrackTemplateArgs()
        self.argparser.add_argument(
            "--corner_holes", action="store", type=str, default="g6",
            choices=["g6", "g2"],
            help="Small-hole cluster around each end registration medium hole.  "
                 "'g6' (default) draws the medium plus the surrounding Ø6 pilot "
                 "holes.  'g2' keeps only the medium and the two pilot holes "
                 "directly above and below it, dropping the offset side pair per "
                 "end — fewer laser pierces and a shorter cut time.  Matches the "
                 "HexmoHexagon option of the same name.")
        self.argparser.add_argument(
            "--gap_holes", action="store", type=str, default="g4",
            choices=["g4", "g2"],
            help="Registration cluster filling each gap between the big holes on "
                 "the divider/support panels.  'g4' (default) draws two mediums "
                 "with two Ø6 pilot holes each (2 medium + 4 small).  'g2' draws "
                 "a single centred medium with one pilot above and below it "
                 "(1 medium + 2 small) — fewer laser pierces.  Matches the "
                 "HexmoHexagon option of the same name.")
        self.argparser.add_argument(
            "--big_hole_shape", action="store", type=str, default="circle",
            choices=["circle", "rounded_rect"],
            help="Shape of the large weight-reduction through-holes.  'circle' "
                 "(default) draws them as circles (unchanged behaviour).  "
                 "'rounded_rect' draws each as a square with rounded corners "
                 "occupying the same bounding box as the circle (side = the "
                 "circle diameter), so all fit/clearance checks are unaffected.  "
                 "The small registration and medium holes are never changed by "
                 "this option.  Matches the HexmoHexagon option of the same name.")
        self.argparser.add_argument(
            "--big_hole_roundness", action="store", type=float, default=0.3,
            help="Corner rounding for --big_hole_shape=rounded_rect, as a "
                 "fraction of the hole's half-width (0 = square corners, "
                 "1 = fully round, i.e. back to a circle).  Default 0.3 — on the "
                 "Ø70 mm big holes of the default h=100 that is a 10.5 mm corner radius.  Values are "
                 "clamped by rectangularHole, so out-of-range numbers are safe.")
        # --big_hole_width / --big_hole_height, shared with HexmoHexagon.
        self._addBigHoleSizeArgs()
        self.argparser.add_argument(
            "--under_track", action="store", type=boolarg, default=False,
            help="Under-deck track opening: cut it through both end walls and "
                 "every short divider, in place of their centre big hole, so a "
                 "lower track can run under the deck from end to end.  It "
                 "matches HexmoHexagon's --under_track_edges opening.")
        # --under_track_height / --under_track_width, shared with HexmoHexagon.
        self._addUnderTrackArgs()

    def _hexWallLength(self):
        """Hole-pattern length of the matching HexmoHexagon side wall.

        The rect's short (end) wall joins a hex side wall face to face, so its
        registration holes must sit where the hex wall's do.  The hex lays
        its wall pattern over its hexagon side length ``side_orig``, centred
        on the wall.  That length is the circumradius, reduced by
        ``t / cos 30°`` in --outside mode, which is the same conversion
        HexmoHexagon.render applies.  Laying the rect pattern over this
        length, centred on the rect wall, reproduces the hex positions
        exactly, instead of approximating them.

        @returns Pattern length in mm.
        """
        r = self.radius
        if self.outside:
            r -= self.thickness / math.cos(math.radians(30))
        _, _, side = self.regularPolygon(6, radius=r)
        return side

    def _hexWallHeight(self):
        """Wall-body height of the matching HexmoHexagon side wall.

        Every height-direction hole position on the rect is measured over
        this height from the deck-side body edge, as the hex does.  The hex
        (closed top) wall body is ``h − 2t`` in --outside mode and ``h``
        otherwise.  Using the hex's height, rather than a fixed ``h − 2t``,
        keeps the medium and far-side pins level with the hex's in both modes.

        @returns Height in mm.
        """
        if self.outside:
            return self.h - 2 * self.thickness
        return self.h

    def _bigHoleRadius(self):
        """Radius of the big weight-reduction / pass-through holes.

        Uses the same formula as HexmoHexagon, ``(h − 2·_SPACER) / 2`` on the raw
        ``--h``, so the big holes are the same size as the hex's at every height
        (35 mm at the default h = 100), not only at h = 100.  Because the
        registration layout (_alignmentBigXs) spaces its holes by this radius
        exactly as the hex does, the end-wall big holes also sit where the hex
        wall's do.  Raw ``--h`` (not the outside-adjusted height) matches the hex.

        @returns Radius in mm; ≤ 0 on very short boxes, meaning no big holes.
        """
        return (self.h - 2 * self._SPACER) / 2

    def _bigPitch(self):
        """Target centre-to-centre spacing of packed big holes (mm): 2·r + _BIG_GAP."""
        return 2 * self._bigHoleRadius() + self._BIG_GAP

    def _drawCornerGroup8Rect(self, s):
        """Draw the end-column alignment cluster for a rectangularWall panel.

        Places a 3-hole vertical column at each end of the wall: one small hole
        near the top edge, one medium hole at the vertical centre, and one small
        hole near the bottom edge.  Both columns sit at x = 3·_SPACER from their
        respective inner edges.

        The medium hole x-position (3·sp) sets the ``corner_inner`` boundary used
        by ``drawAlignmentHolesRect`` and ``long_wall_cb`` when computing the safe
        zone for big through-holes, so that value must not change.

        All y-positions are measured over ``l_eff = _hexWallHeight()``, the
        matching hex wall's body height, so they line up with the hex in both
        --outside modes.

        @param s - Panel length along the wall (x-axis of the rectangularWall callback).
        """
        sp = self._SPACER
        t  = self.thickness
        l_eff    = self._hexWallHeight()
        sp_y     = sp
        y_center = l_eff / 2
        r2 = self._R2
        r3 = self._R3

        # Always drawn: the medium at each end (x = 3·sp) plus the pilot holes
        # directly above and below it (the 3rd-column pair, same x as the medium).
        self.hole(s - 3 * sp, l_eff - sp,  r3)   # right medium: pin above
        self.hole(s - 3 * sp, y_center,    r2)   # right centre medium
        self.hole(s - 3 * sp, sp_y,        r3)   # right medium: pin below
        self.hole(3 * sp,     l_eff - sp,  r3)   # left medium: pin above
        self.hole(3 * sp,     y_center,    r2)   # left centre medium
        self.hole(3 * sp,     sp_y,        r3)   # left medium: pin below

        # The offset side pair (2nd column at 2·sp) is only drawn in the full
        # 'g6' pattern; 'g2' omits it to save pierces.
        if self.corner_holes != "g6":
            return
        self.hole(s - 2 * sp, l_eff - sp,  r3)   # right, near top, 2nd column
        self.hole(s - 2 * sp, sp_y,        r3)   # right, near bottom, 2nd column
        self.hole(2 * sp,     l_eff - sp,  r3)   # left, near top, 2nd column
        self.hole(2 * sp,     sp_y,        r3)   # left, near bottom, 2nd column

    def _drawSupportGapFeatures(self, x_lo, x_hi, pilots=True):
        """Fill the x-axis gap between two features with a symmetric hole sub-group.

        Copied from HexmoHexagon so that outer-wall panels carry the same
        sub-hole pattern as HexmoHexagon panels, keeping all hole types
        pin-compatible across the modular system.

        Attempts to place, symmetrically within [x_lo, x_hi]:
          - Full G6 equivalent (left-small + centre-medium + right-small,
            top + bottom = 6 holes) when half-gap ≥ r2 + 2·r3 + 2·MIN_CLEAR.
          - G2-medium pair (top + bottom, 2 holes) when half-gap ≥ r2 + MIN_CLEAR.
          - Nothing when the gap or panel height is too small.

        @param x_lo - Inner left boundary of the gap (outer edge of left neighbour).
        @param x_hi - Inner right boundary of the gap (outer edge of right neighbour).
        @param pilots - When False, omit the small Ø6 pilot holes and keep only
            the medium holes.  Used on the internal divider panels, which register
            to nothing, so their pilots are pure laser overhead.
        """
        r2 = self._R2
        r3 = self._R3
        sp = self._SPACER
        # sp_y: height-direction margin for bottom-edge holes.  Plain sp — both
        # callbacks place y=0 at the inner bottom face, so no thickness offset.
        sp_y = sp
        mc = self._MIN_CLEAR

        # l_eff: the matching hex wall's body height (see _hexWallHeight).  All
        # top-edge hole y-positions use it so they match the hex panel.
        l_eff = self._hexWallHeight()
        # Vertical guard: bottom-medium top edge (sp_y + 3·r2/2) must clear top-medium
        # bottom edge (l_eff − sp − 3·r2/2) by at least _MIN_CLEAR.
        # Rearranged: l_eff ≥ 2·sp + 3·r2 + _MIN_CLEAR.
        if l_eff < 2 * sp + 3 * r2 + mc:
            return

        half_gap = (x_hi - x_lo) / 2
        x_mid    = (x_lo + x_hi) / 2

        half_for_G2m = r2 + mc
        sm_offset    = r2 + r3 + mc   # ensures _MIN_CLEAR between small and medium edges
        half_for_G6  = sm_offset + r3 + mc

        # Precompute y-positions for the top/bottom hole pairs.
        # Bottom: sp_y = sp (inner bottom face + clearance).
        # Top: measured from l_eff (effective inner height), leaving _SPACER
        # clearance at the top edge — matches the hex polygonWall's hole positions.
        y_bot_r3 = sp_y
        y_top_r3 = l_eff - sp
        y_bot_r2 = sp_y + r2 / 2
        y_top_r2 = l_eff - sp - r2 / 2

        if self.gap_holes == "g2":
            # G2: single centred medium with one pilot toward each edge
            # (1 medium + 2 small), matching the reduced HexmoHexagon pattern.
            if half_gap >= half_for_G2m:
                self.hole(x_mid, l_eff / 2, r2)      # centred medium
                if pilots:
                    self.hole(x_mid, y_bot_r3, r3)   # pilot near bottom edge
                    self.hole(x_mid, y_top_r3, r3)   # pilot near top edge
            return

        if half_gap >= half_for_G6:
            # Full G4 pattern: two mediums (top + bottom) flanked by small pilots.
            self.hole(x_mid, y_bot_r2, r2)
            self.hole(x_mid, y_top_r2, r2)
            if pilots:
                self.hole(x_mid - sm_offset, y_bot_r3, r3)
                self.hole(x_mid - sm_offset, y_top_r3, r3)
                self.hole(x_mid + sm_offset, y_bot_r3, r3)
                self.hole(x_mid + sm_offset, y_top_r3, r3)

        elif half_gap >= half_for_G2m:
            # Gap too narrow for small flanking holes — medium pair only.
            self.hole(x_mid, y_bot_r2, r2)
            self.hole(x_mid, y_top_r2, r2)

    def _drawGapBandFeatures(self, x_lo, x_hi):
        """Draw a centred big hole flanked by small and medium top/bottom pairs.

        Produces the following symmetric arrangement within the gap [x_lo, x_hi]:

            medium pair  |  small pair  |  BIG  |  small pair  |  medium pair

        Each "pair" is one hole at the top edge and one at the bottom edge of the
        panel, at the same x position.  The central big hole (radius _bigHoleRadius()) is a
        single vertically-centred hole, matching the outer-wall big-hole style.

        Spacings are computed so that every adjacent pair of hole edges is exactly
        MIN_CLEAR (5 mm) apart:
          - big→small  offset = r4 + MIN_CLEAR + r3
          - small→med  offset += r3 + MIN_CLEAR + r2

        The method silently returns if the gap is too narrow to fit the outermost
        medium holes with MIN_CLEAR clearance from the gap boundaries, or if the
        effective panel height is too small for vertical hole placement.

        @param x_lo - Inner left boundary of the gap (mm, callback frame x).
        @param x_hi - Inner right boundary of the gap (mm, callback frame x).
        """
        r2 = self._R2
        r3 = self._R3
        r4 = self._bigHoleRadius()
        sp = self._SPACER
        mc = self._MIN_CLEAR

        l_eff = self._hexWallHeight()
        # Vertical guard: bottom-medium top edge must clear top-medium bottom edge.
        if l_eff < 2 * sp + 3 * r2 + mc:
            return

        half_gap = (x_hi - x_lo) / 2
        x_mid    = (x_lo + x_hi) / 2

        # Lateral offsets from x_mid, each edge-to-edge clearance = _MIN_CLEAR.
        sm_off = r4 + mc + r3          # big edge → small centre
        md_off = sm_off + r3 + mc + r2  # small edge → medium centre

        # Horizontal guard: outermost medium edge must not overlap gap boundary.
        if half_gap < md_off + r2 + mc:
            return

        # y-positions for top/bottom pairs — match _drawSupportGapFeatures convention.
        y_bot_r3 = sp
        y_top_r3 = l_eff - sp
        y_bot_r2 = sp + r2 / 2
        y_top_r2 = l_eff - sp - r2 / 2
        y_big    = l_eff / 2

        # Central big hole (single vertically-centred, matching outer-wall big holes).
        self._drawBigHole(x_mid, y_big, r4)
        # Small flanking pairs (top + bottom at ±sm_off from centre).
        for off in (-sm_off, sm_off):
            self.hole(x_mid + off, y_bot_r3, r3)
            self.hole(x_mid + off, y_top_r3, r3)
        # Medium outer pairs (top + bottom at ±md_off from centre).
        for off in (-md_off, md_off):
            self.hole(x_mid + off, y_bot_r2, r2)
            self.hole(x_mid + off, y_top_r2, r2)

    def _drawSupportSegmentHole(self, x_lo, x_hi):
        """Draw a single large through-hole centred in the grid-cell segment [x_lo, x_hi].

        Used on internal divider panels (vertical and horizontal) to provide one
        large weight-reduction aperture per cell, matching the visual language of
        the big holes on the outer walls.  The hole radius is ``_bigHoleRadius()``,
        the same radius ``drawAlignmentHolesRect`` uses for the outer-wall big
        holes, so all large apertures in the assembled box share one diameter.

        The vertical centre is placed at ``l_eff / 2`` (half the matching hex
        wall height, see _hexWallHeight), identical to the outer-wall big-hole
        y-position,
        so the holes align across mating faces.

        A hole is skipped if it would not fit: the segment width must be at least
        twice the big-hole radius, and so must the effective panel height.

        @param x_lo - Inner left boundary of the segment (mm, callback frame x).
        @param x_hi - Inner right boundary of the segment (mm, callback frame x).
        """
        r4 = self._bigHoleRadius()
        l_eff = self._hexWallHeight()
        # Guard: skip if the hole diameter exceeds the segment or panel height.
        if (x_hi - x_lo) < 2 * r4 or l_eff < 2 * r4:
            return
        x_mid = (x_lo + x_hi) / 2
        y_mid = l_eff / 2
        self._drawBigHole(x_mid, y_mid, r4)

    # Edge-to-edge gap targeted between packed big weight-reduction holes (mm):
    # just above the minimum that still fits one full G4 cluster (2 medium +
    # 4 small), so big holes are preferred and packed fairly densely.  The
    # centre-to-centre pitch is 2·r + this (see _bigPitch), so the gap stays
    # the same whatever size --h makes the big holes; 140 mm at the default h=100.
    _BIG_GAP = 70.0

    # Minimum clearance from a big hole's *edge* to a span boundary — a divider
    # finger slot or a corner cluster.  Deliberately larger than _MIN_CLEAR so
    # big weight-reduction holes never crowd those structural edge fittings; a
    # slot-side gap this size holds a small/medium cluster instead.
    _BIG_EDGE = 30.0

    def _fillWeightSpan(self, x_lo, x_hi, edge_lo=None, edge_hi=None, pilots=True,
                        clusters=True, y_centre=None):
        """Weight-reduction fill for one panel span, mirroring HexmoHexagon.

        Big weight-reduction holes come **first**: as many as fit are packed
        (one per :meth:`_bigPitch`, shaped by ``--big_hole_shape``) along the
        span centre line, then every leftover gap — including the two end gaps —
        is filled with **one** small/medium cluster via
        :meth:`_drawSupportGapFeatures` (copied verbatim from HexmoHexagon:
        ``--gap_holes=g4`` → 2 medium + 4 small, ``g2`` → 1 medium + 2 small).
        The big-hole packing is identical for g4 and g2.

        ``edge_lo`` / ``edge_hi`` are the clearances a big-hole *centre* must keep
        from each boundary.  Default (``None``) is big-hole radius + ``_BIG_EDGE``, used for
        a divider finger slot, where a big must stay well clear.  Pass ``0`` when
        the boundary is already a safe big-centre position (a corner-cluster
        ``x_floor``), so a big hole is placed there instead of a cluster.

        @param x_lo - Inner left boundary of the span (mm, callback frame x).
        @param x_hi - Inner right boundary of the span (mm, callback frame x).
        """
        r4, mc = self._bigHoleRadius(), self._MIN_CLEAR
        slot_edge = r4 + self._BIG_EDGE
        if edge_lo is None:
            edge_lo = slot_edge
        if edge_hi is None:
            edge_hi = slot_edge
        span = x_hi - x_lo
        if span <= 0:
            return
        # y-centre of the big holes; defaults to the wall's inner mid-height, but
        # callers on a differently-proportioned panel (e.g. the spoke, which is
        # sw wide) pass their own centre.  ``clusters=False`` packs big holes only
        # and draws no small/medium gap features at all.
        y_big = self._hexWallHeight() / 2.0 if y_centre is None else y_centre
        # Range in which a big-hole *centre* may sit, given the per-side edge
        # clearances (divider slots inset by r4 + _BIG_EDGE, corner sides by 0).
        c_lo, c_hi = x_lo + edge_lo, x_hi - edge_hi
        if c_hi <= c_lo:
            # The per-side edge clearances can't both be met (a short end cell).
            # If a single big hole still fits the raw span, centre it so its
            # clearance is *balanced* between the two boundaries — better than
            # crowding one — and cluster-fill any room left on each side.
            # Otherwise the span is genuinely too small: use one cluster.
            if span >= 2 * r4 + 2 * mc:
                xc = (x_lo + x_hi) / 2.0
                self._drawBigHole(xc, y_big, r4)
                if clusters:
                    self._drawSupportGapFeatures(x_lo, xc - r4 - mc, pilots=pilots)
                    self._drawSupportGapFeatures(xc + r4 + mc, x_hi, pilots=pilots)
            elif clusters:
                self._drawSupportGapFeatures(x_lo, x_hi, pilots=pilots)
            return
        c_span = c_hi - c_lo
        # Big holes ~_bigPitch() apart, spread across the centre range (endpoints
        # included for n ≥ 2 so the outermost bigs hug the boundaries).
        n_big = max(1, round(1 + c_span / self._bigPitch()))
        if n_big == 1:
            centres = [(c_lo + c_hi) / 2.0]
        else:
            centres = [c_lo + c_span * i / (n_big - 1) for i in range(n_big)]
        for xc in centres:
            self._drawBigHole(xc, y_big, r4)
        # Gaps: span start → first big, between adjacent bigs, last big → end.
        los = [x_lo] + [c + r4 + mc for c in centres]
        his = [c - r4 - mc for c in centres] + [x_hi]
        if clusters:
            for g_lo, g_hi in zip(los, his):
                self._drawSupportGapFeatures(g_lo, g_hi, pilots=pilots)

    def _alignmentBigXs(self, s):
        """Big-hole x-positions of the alignment pattern over a wall of length ``s``.

        This is the same layout HexmoHexagon.drawAlignmentHoles uses for its big
        holes, so over the hex wall length (``_hexWallLength``) these positions
        co-locate with the hex wall's.  Up to three holes, always an odd count,
        so ``s/2`` (the track pass-through aperture) is included.

        @param s - Pattern length (mm), in the alignment-pattern frame.
        @returns Big-hole centre x-positions (mm) in that frame.
        """
        sp, r2, r4, mc = self._SPACER, self._R2, self._bigHoleRadius(), self._MIN_CLEAR
        # Minimum x-distance from either end where a big hole centre can sit
        # without its edge overlapping the corner cluster's medium hole.  This is
        # registration-critical: it co-locates the outer-wall big holes with the
        # HexmoHexagon edge-wall big holes, so it must NOT change.  The tight
        # ~MIN_CLEAR gap to the corner cluster is the alignment, not a defect —
        # do not "centre" these big holes.
        x_floor = 3 * sp + r2 + r4 + mc
        # Available length for the interior big-hole band.
        available = s - 2 * x_floor
        if available < 0:
            # Wall too short for any interior big holes — corner clusters only.
            return []
        n = min(3, max(1, 1 + int(available / (2 * r4 + mc))))
        # Force odd count so the distribution is symmetric and s/2 is always
        # included, providing a track pass-through aperture at mid-wall.
        if n % 2 == 0:
            n -= 1
        if n == 1:
            return [s / 2]
        step = available / (n - 1)
        return [x_floor + i * step for i in range(n)]

    def drawAlignmentHolesRect(self, s, gap_features=True, draw_corners=True,
                               big_xs=None):
        """Cut alignment features into an outer wall drawn by rectangularWall.

        Transposed counterpart of HexmoHexagon.drawAlignmentHoles: the 'long'
        axis of the hole pattern runs along x (wall length = s) rather than
        along y, matching the ``rectangularWall`` callback coordinate frame where
        the turtle faces right along the wall.

        All height-direction (y) positions are measured over l_eff, the
        matching hex wall's body height (see _hexWallHeight), so no panel
        height argument is needed.

        The layout algorithm is identical to drawAlignmentHoles:
          1. Corner group-of-8 clusters at both ends (via _drawCornerGroup8Rect),
             unless ``draw_corners=False`` (used when the caller draws them
             separately at pre-shift coordinates).
          2. Up to three large through-holes along the y = l_eff/2 centre line,
             spaced to avoid the corner clusters.
          3. Gap filling between adjacent features (via _drawGapBandFeatures),
             controlled by the ``gap_features`` flag.

        The big-hole radius is ``_bigHoleRadius()``, HexmoHexagon's
        ``(h − 2·_SPACER) / 2`` on the raw ``--h``, so the sizes match the hex at
        every height and in both --outside modes (35 mm at the default h = 100).

        @param s            - Wall length (x-axis of rectangularWall callback).
        @param gap_features - When True (default) the gaps between big holes and
                              the corner clusters are filled with top/bottom hole
                              pairs via ``_drawSupportGapFeatures``.  Pass False
                              for the short outer walls, where those gap holes
                              fall directly on the vertical-divider finger-joint
                              slots cut by ``fingerHolesAt`` in ``short_wall_cb``,
                              causing physical material conflicts.
        @param big_xs       - Big-hole x-positions to draw instead of the default
                              registration layout (same frame).  The short walls
                              pass a filtered set that keeps clear of the
                              long-support slots and is shared with the short
                              dividers.
        """
        sp = self._SPACER
        r2 = self._R2

        # Large through-hole radius, the same as HexmoHexagon's at this --h.
        r4 = self._bigHoleRadius()

        # Big-hole x-positions: the registration layout (see _alignmentBigXs),
        # unless the caller supplies a filtered set in this same frame.
        if big_xs is None:
            big_xs = self._alignmentBigXs(s)

        # Large through-holes along the centre line.
        # y_big: vertical centre of big through-holes, half the matching hex wall
        # height, so the physical hole centre matches the hex wall's in both
        # --outside modes.
        l_eff = self._hexWallHeight()
        y_big = l_eff / 2
        for x in big_xs:
            self._drawBigHole(x, y_big, r4)

        # Fill every gap between adjacent features with the band pattern.
        # Skipped when gap_features=False (e.g. short outer walls), where the
        # gap x-centres coincide with vertical-divider finger-joint slots.
        corner_inner = 3 * sp + r2                        # inner x-edge of corner medium hole
        if gap_features:
            lo_bounds = [corner_inner]      + [x + r4 for x in big_xs]
            hi_bounds = [x - r4 for x in big_xs] + [s - corner_inner]
            for x_lo, x_hi in zip(lo_bounds, hi_bounds):
                self._drawGapBandFeatures(x_lo, x_hi)

        # Corner clusters — drawn last so their fixed-offset holes are never
        # masked by the dynamic interior features.  Suppressed when the caller
        # has already drawn them at pre-shift coordinates (draw_corners=False).
        if draw_corners:
            self._drawCornerGroup8Rect(s)

    def drawReferencePanel(self, move="right") -> None:
        """Render a flat reference panel listing all generator parameters.

        The panel is sized to contain the full parameter list as engraved text
        and uses ``Color.ETCHING`` so that laser software routes it as an
        engrave pass rather than a cut pass.  A ``Color.OUTER_CUT`` rectangle
        provides the border so the panel can be cut from stock.

        The panel is positioned using the standard boxes ``move`` convention:
        call with ``move="right"`` (default) to advance the layout cursor to
        the right of the panel, or ``move="up only"`` to reserve space only.

        @param move - Direction string passed to ``self.move()`` for layout
                      control.  Defaults to ``"right"``.
        """
        fontsize    = 6                      # mm — small but legible on most laser systems
        margin      = 5                      # mm — clearance between border and text
        line_height = 1.4 * fontsize         # matches boxes text() inter-line spacing
        panel_width = 150                    # mm — wide enough for longest expected param lines

        # Gather current parameter values by walking all argparser actions and
        # reading the corresponding attribute off self.  Edge-setting args
        # (e.g. FingerJoint_finger) are also stored on self via setattr after
        # parse_args, so getattr covers them without special-casing.
        # Actions whose dest is SUPPRESS (e.g. --help) have no corresponding
        # attribute and are skipped by the getattr guard.
        params = []
        seen_dests: set[str] = set()
        for action in self.argparser._actions:
            dest = action.dest
            if dest in seen_dests or dest == argparse.SUPPRESS:
                continue
            seen_dests.add(dest)
            val = getattr(self, dest, None)
            if val is None:
                continue
            params.append((dest, val))
        params.sort(key=lambda p: p[0])

        # Build text: generator name + ISO timestamp header, then one param per line.
        timestamp   = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        header_lines = [f"{self.__class__.__name__}  {timestamp}", ""]
        param_lines  = [f"{dest}: {val}" for dest, val in params]
        lines        = header_lines + param_lines

        panel_height = 2 * margin + len(lines) * line_height

        # First call with before=True: reserve layout space; return early if
        # the caller only wants space reservation (e.g. move="up only").
        if self.move(panel_width, panel_height, move, True):
            return

        # Outer cut border so the panel can be laser-separated from stock.
        self.set_source_color(Color.OUTER_CUT)
        self.ctx.rectangle(0, 0, panel_width, panel_height)
        self.ctx.stroke()

        # Render the parameter list as a single multi-line etching block.
        # boxes' text() iterates lines in reverse and moves upward per line,
        # so lines[0] ends up at the top and lines[-1] sits at y=margin.
        self.text(
            "\n".join(lines),
            x=margin,
            y=margin,
            fontsize=fontsize,
            color=Color.ETCHING,
        )

        # Second call: advance the layout cursor past the rendered panel.
        self.move(panel_width, panel_height, move)

    def drawRectTrackLines(self, length, width):
        """Etch the straight track guide onto the base plate.

        The rectangle is a straight module: track runs straight down its long
        (H) axis and crosses the two short walls, so the guide is a set of
        straight lines running the full ``length`` (H) at the centre of the
        short ``width`` (W − 2t) dimension.  This mirrors the HexmoHexagon
        ``--track_middle`` straight (there is no curve, hence no radius label).

        Called from the base-plate ``rectangularWall`` callback, whose frame has
        x running 0…length along the long axis and y running 0…width across the
        short axis.  For each of ``--track_line_count`` parallel tracks (offset
        laterally by ``--track_spacing``) it optionally draws the centreline
        (``--draw_center``), the two footprint edges at ± track_width/2
        (``--draw_track``), and a perpendicular crossing tick at each end
        (``--track_crossing``), offset inward by ``--track_lead_in`` to mark
        where the track enters/leaves the module.

        Lines whose lateral position would fall outside the panel are skipped.

        @param length - Long-axis extent of the base plate (H), in mm.
        @param width  - Short-axis extent of the base plate (W − 2t), in mm.
        """
        n_lines = self.track_line_count
        if n_lines < 1:
            return

        half_width = self.track_width / 2.0
        lead_in = self.track_lead_in
        # Tick half-length: spans the track (rail to rail) when the footprint
        # edges are drawn, plus a small overhang; a bare centreline gets just the
        # overhang each side.  Matches the HexmoHexagon crossing-tick sizing.
        cross_half = (half_width if self.draw_track else 0.0) + 6.0

        y_centre = width / 2.0
        # Lateral offsets, from the helper shared with HexmoHexagon and the guide
        # plate (see HexmoTrackGuideMixin._trackOffsets).  Positive = +y, which
        # matches the hexagon's 'outer' (larger-radius) direction, so tracks line
        # up across a hex↔straight joint.  The hline guard clips anything the
        # offsets push past 0/width.
        offsets = self._trackOffsets()

        def hline(y):
            """Draw one full-length line at lateral position y (skip if off-panel)."""
            if y < 0.0 or y > width:
                return
            self.ctx.move_to(0.0, y)
            self.ctx.line_to(length, y)
            self.ctx.stroke()

        with self.saved_context():
            self.set_source_color(Color.ETCHING)
            for off in offsets:
                cy = y_centre + off
                if self.draw_center:
                    hline(cy)
                if self.draw_track:
                    hline(cy - half_width)
                    hline(cy + half_width)
                # End crossing ticks (perpendicular = vertical), offset inward by
                # lead_in from each short-wall end, spanning the track width.
                if (self.track_crossing and lead_in > 0
                        and (self.draw_center or self.draw_track)):
                    for xt in (lead_in, length - lead_in):
                        self.ctx.move_to(xt, cy - cross_half)
                        self.ctx.line_to(xt, cy + cross_half)
                        self.ctx.stroke()

    def _turnoutLegs(self, length, width):
        """Solve every --turnouts diverging leg on the deck.

        @param length - Deck length along the track (H).
        @param width  - Deck width across it (W − 2t); offsets are measured
                        from its centre, + towards +y as for the track lines.
        @returns One tuple of ``Line``/``Arc`` pieces per leg, in the deck
                 callback's frame (x along the deck, y from its −y edge).
        @throws ValueError - From the turnout geometry, or if a leg's track
                             footprint runs off the deck.
        """
        legs = []
        half = self.track_width / 2.0
        for spec in parse_turnouts(self.turnouts):
            leg = turnout_leg(spec, length, self.turnout_length, self.turnout_radius,
                              self.turnout_angle, self.turnout_reverse_radius)
            # Move from offsets about the centre line into the deck frame.
            shifted = tuple(_shiftY(seg, width / 2.0) for seg in leg.segments)
            ys = [y for _, y in segments_polyline(shifted, 16)]
            if min(ys) - half < 0 or max(ys) + half > width:
                raise ValueError(
                    f"--turnouts: the leg from {spec.toe:g} mm to offset {spec.end:g} "
                    f"runs off the {width:.0f} mm deck (track {self.track_width:g} mm "
                    "wide).")
            legs.append(shifted)
        return legs

    def _etchTurnoutLeg(self, segments):
        """Etch one turnout's diverging leg, styled like the straight track lines.

        Draws its centreline (--draw_center) and/or footprint edges
        (--draw_track), a tick across the through road at the toe (where the
        switch blades start), and with --track_crossing a tick --track_lead_in
        from the end of the deck, matching the straight lines' end ticks.

        @param segments - The leg's pieces in the deck frame (see _turnoutLegs).
        """
        half = self.track_width / 2.0
        lines = []
        if self.draw_center:
            lines.append(segments)
        if self.draw_track:
            for d in (-half, half):
                moved = offset_segments(segments, d)
                if moved is not None:
                    lines.append(moved)
        cross_half = (half if self.draw_track else 0.0) + 6.0
        toe = segments[0].p0
        end = segments[-1].p1
        with self.saved_context():
            self.set_source_color(Color.ETCHING)
            for line in lines:
                points = segments_polyline(line, 32)
                self.ctx.move_to(*points[0])
                for p in points[1:]:
                    self.ctx.line_to(*p)
                self.ctx.stroke()
            if lines:
                ticks = [toe[0]]
                if self.track_crossing and self.track_lead_in > 0:
                    ticks.append(end[0] - self.track_lead_in)
                for x, y in zip(ticks, (toe[1], end[1])):
                    self.ctx.move_to(x, y - cross_half)
                    self.ctx.line_to(x, y + cross_half)
                    self.ctx.stroke()

    def _rectLayout(self):
        """The rectangle's sizes and internal grid, shared by render and the 3D export.

        @returns SimpleNamespace with ``t``; ``r`` (inner circumradius of the
                 matching hexagon) and ``apothem``; ``W`` (short-wall panel
                 width), ``H`` (inner long length), ``h`` (inner height);
                 ``n_cols``/``n_div_h`` (cells along H and the short dividers
                 between them), ``n_rows``/``n_div_v`` (lanes across W and the
                 long supports between them), ``col_w``/``row_h`` (lane and cell
                 inner sizes), ``sw`` (spoke width, clamped), and ``lane_pos``/
                 ``div_pos`` (lists: long-support positions across the inner
                 width, short-divider positions along H, both to their centres).
        @throws ValueError - On an impossible --num_rows.
        """
        t = self.thickness
        r = self.radius
        h = self.h

        # W: the --radius parameter is *always* interpreted as the inner
        # corner-to-corner radius of the matching HexmoHexagon, regardless of
        # whether --outside is set.  This ensures the short wall bounding box
        # W = radius − 2t matches the HexmoHexagon side-wall panel width computed
        # with the same raw radius.  The outside flag must NOT be applied to r
        # before this step; doing so would reduce W by t/cos(30°) relative to the
        # hexagon panel, preventing flush assembly.
        _, _, side_raw = self.regularPolygon(6, radius=self.radius)
        W = side_raw - 2 * t

        # H and h: if --outside is set the user has given the OUTER height/radius;
        # convert to inner using the same formula HexmoHexagon uses.  This keeps
        # the box interior depth and the long-axis cavity correct for outside mode
        # while leaving W unaffected (see above).
        if self.outside:
            r -= self.thickness / math.cos(math.radians(360 / (2 * 6)))
            h = self.adjustSize(h, e2=False)

        _, apothem, _ = self.regularPolygon(6, radius=r)

        # H: inner long dimension = hexagon flat-to-flat inner cavity distance.
        # For a regular hexagon, flat-to-flat = 2 × apothem = r × √3.
        H = 2 * apothem


        # --- Column-count selection ---------------------------------------------
        # n_cols controls how many compartments the long axis is divided into
        # (they appear as columns in the SVG output); n_div_h = n_cols − 1
        # horizontal dividers are required.
        #
        # When --num_columns is 0 (auto), the count is chosen to keep cell sizes
        # practical: a large box (radius ≥ 400) gets 5 columns, a medium box
        # (300 ≤ radius < 400) gets 3 columns, and a small box (radius < 300)
        # gets 2 columns (a single central divider).  The threshold at 300 matches
        # the observation that 4 dividers are unnecessary at that scale.
        if self.num_columns == 0:
            if self.radius >= 400:
                n_cols = 5
            elif self.radius >= 300:
                n_cols = 3
            else:
                n_cols = 2
        else:
            n_cols = max(1, self.num_columns)

        # Number of horizontal dividers = one fewer than the number of column cells.
        n_div_h = n_cols - 1

        # --- Lanes across the short axis (--num_rows) ----------------------------
        # N lanes need N−1 long internal supports (vertical dividers spanning H).
        # An even N puts a support on the centreline, exactly where the spoke
        # runs and where the horizontal dividers' spoke tabs sit, so that
        # combination is refused rather than drawn with a clash.
        n_rows = self.num_rows
        if n_rows < 1:
            raise ValueError(f"--num_rows must be at least 1 (got {n_rows}).")
        if n_rows % 2 == 0 and self.spoke_width > 0:
            raise ValueError(
                f"--num_rows {n_rows} puts a long support on the centreline, "
                "where the spoke runs; use an odd --num_rows or --spoke_width 0.")
        # Number of long internal supports (vertical dividers).
        n_div_v = n_rows - 1

        # --- Grid geometry ------------------------------------------------------
        # The n_rows-lane × n_cols-cell grid divides the inner cavity evenly.
        # (In the code the lanes across W are "columns" (col_w) and the cells
        # along H are "rows" (row_h); the CLI names count the other way round:
        # --num_rows counts lanes and --num_columns counts cells.)
        # n_div_v vertical dividers (each thickness t) occupy n_div_v·t of W.
        # n_div_h horizontal dividers (each thickness t) occupy n_div_h·t of H.
        # The short wall panel is drawn with inner dimension W − 2t (so the
        # laser-cut bounding box = (W−2t) + 2t = W, matching the HexmoHexagon
        # side-wall width).  The box inner cavity in the short direction is
        # therefore W − 2t, and the vertical dividers leave
        # (W − 2t) − n_div_v·t for the lane interiors.
        col_w = (W - 2 * t - n_div_v * t) / n_rows   # inner width of each lane
        if col_w <= 0:
            raise ValueError(
                f"--num_rows {n_rows} leaves no room between the long supports.")
        row_h = (H - n_div_h * t) / n_cols   # inner height of each row cell
        # lane_pos: W-axis centre of long support i (i = 0..n_div_v−1), measured
        # from the inner face of a long wall.  Used by short_wall_cb and base_cb.
        lane_pos = lambda i: (i + 1) * col_w + (2 * i + 1) * t / 2

        # Support spoke geometry.  sw=0 suppresses the spoke and all its cutouts.
        sw  = self.spoke_width
        # Clamp sw to the middle-column interior width.  The 'f' strip drawn by
        # _HorizDivSpokeEdge spans exactly sw mm inside the middle section
        # (between the two crossing slots).  If sw > col_w the edge overdraws
        # by (sw − col_w) mm, producing an unclosed panel outline on the left
        # and shifting the second crossing slot into the segment-2 weight-
        # reduction hole.  Clamping to col_w ensures the total drawn length
        # equals W − 2t regardless of the user-supplied --spoke_width value.
        if sw > 0:
            sw = min(sw, col_w)
        div_pos = lambda i: (i + 1) * row_h + (2 * i + 1) * t / 2
        return SimpleNamespace(
            t=t, r=r, apothem=apothem, W=W, H=H, h=h,
            n_cols=n_cols, n_div_h=n_div_h, n_rows=n_rows, n_div_v=n_div_v,
            col_w=col_w, row_h=row_h, sw=sw,
            lane_pos=[lane_pos(i) for i in range(n_div_v)],
            div_pos=[div_pos(i) for i in range(n_div_h)])

    def render(self) -> None:
        """Generate all panels for the HexmoRectangle box (outer shell + 3×N grid).

        Draws ``5 + 2 + n_div_h`` panels, where ``n_div_h = n_cols − 1``:
          - 2 × short outer wall  (W × h)  — span the short (radius) axis
          - 2 × long outer wall   (H × h)  — span the long (radius × √3) axis
          - 1 × base plate        ((H + 2t) × W)  — rotated so H is horizontal
          - 2 × vertical divider  (H × h)  — split the box into 3 columns
          - n_div_h × horizontal divider ((W−2t) × h) — split the box into n_cols columns

        ``n_cols`` is determined by ``--num_columns`` (0 = auto-select from radius):
          radius ≥ 400 → 5 columns (4 dividers); 300 ≤ radius < 400 → 3 columns (2 dividers);
          radius < 300 → 2 columns (1 central divider).

        ``--radius`` is always the inner corner-to-corner radius of the matching
        HexmoHexagon; W is derived from it without any outside-mode adjustment so
        that the short wall bbox = W regardless of outside mode.  When
        ``--outside`` is set, ``h`` and ``H`` are adjusted to inner dimensions
        (matching HexmoHexagon's outside-mode convention); W is unchanged.

        Crossing-joint convention (slot-and-tab):
          Vertical dividers carry ``SlottedEdge`` on their **bottom** edges:
          n_cols 'f' sections (finger-tabs for the base plate) separated by
          n_div_h Slot notches of depth h/2.  Horizontal dividers carry
          ``SlottedEdge`` on their **top** edges: three 'e' sections separated
          by two Slot notches of depth h/2.  The two sets of notches interlock
          at mid-height when the horizontal dividers are lowered over the
          vertical ones during assembly.

        All outer walls carry fingerHoles callbacks so the divider 'f' end-tabs
        seat against each outer wall's inner face at the correct grid positions.

        Base plate carries fingerHoles callbacks for all six dividers, covering
        only the 'f' sections of each divider's bottom edge (not the plain or
        slotted crossing positions, which float above the base at those spots).
        """
        t = self.thickness
        r = self.radius
        h = self.h

        # --- Geometry -----------------------------------------------------------
        # Derive inner cavity dimensions from the hexagon circumradius r using the
        # same formulas as HexmoHexagon so that edges mate flush.
        #
        # regularPolygon(6, radius=r) returns (r, apothem, side) where:
        #   side   = r              (for a regular hexagon, side == circumradius)
        #   apothem = r × cos(30°) = r × √3 / 2  (centre-to-flat-face distance)

        # Sizes and the internal grid (see _rectLayout, shared with the 3D export).
        lay = self._rectLayout()
        r, h, apothem, W, H = lay.r, lay.h, lay.apothem, lay.W, lay.H
        n_cols, n_div_h, n_rows, n_div_v = lay.n_cols, lay.n_div_h, lay.n_rows, lay.n_div_v
        col_w, row_h, sw = lay.col_w, lay.row_h, lay.sw
        lane_pos = lambda i: lay.lane_pos[i]

        # Turnout legs (--turnouts), solved and checked before anything is
        # drawn; etched on the deck by base_cb.
        turnout_legs = self._turnoutLegs(H, W - 2 * t)
        # Extra slot depth added to both crossing-slot sets so panels seat fully
        # despite laser kerf and material-thickness variation.
        tol = self.slot_tolerance

        # --- Crossing slot edges ------------------------------------------------
        # Vertical dividers span H and use 'f' sections (connecting to base plate)
        # separated by Slot notches of depth h/2 at the n_div_h horizontal crossing
        # positions.  The slot is cut from the BOTTOM of the flat panel, so when
        # the divider stands upright the notch opens upward from the base.
        # n_cols segments of row_h, separated by n_div_h crossing slots.
        e_vert_bot = edges.SlottedEdge(self, [row_h] * n_cols, 'f', slots=h / 2 + tol)

        # Horizontal dividers span W−2t and use a composite top edge:
        #   - When the spoke is present: _HorizDivSpokeEdge, which draws the
        #     outer two col_w sections as plain 'e' and the middle col_w section
        #     as 'e'+'f'+'e'.  The 'f' tabs (sw wide) project upward into the
        #     spoke's fingerHoles.  To keep the assembled height at h, the
        #     horizontal dividers are drawn at height h−t (body only); the tabs
        #     add t back → total bounding-box = h.  The crossing-slot depth is
        #     reduced from h/2 to h/2−t so the interlock with vertical dividers
        #     (whose slots go upward h/2 from the bottom) still meets at y=h/2
        #     in the assembled box: (h−t) − (h/2−t) = h/2 ✓
        #   - When the spoke is omitted: plain SlottedEdge('e') as before.
        if sw > 0:
            e_horiz_top = _HorizDivSpokeEdge(self, col_w, h / 2 - t + tol, sw, n_rows)
        else:
            e_horiz_top = edges.SlottedEdge(self, [col_w] * n_rows, 'e', slots=h / 2 + tol)

        # Horizontal divider bottom: 'f' sections connect to base plate at the
        # three col_w spans; crossing positions use plain 'e' (no tabs there since
        # vertical dividers occupy that material).
        e_horiz_bot = edges.SlottedEdge(self, [col_w] * n_rows, 'f')

        # --- Shared callback precomputations ------------------------------------
        # dx is used identically in both short_wall_cb and long_wall_cb.
        # Precomputing it once here avoids duplication inside each closure.
        #
        # s_hex: length of the matching hex wall's hole pattern (see
        # _hexWallLength).  The hex centres that pattern on its wall, so the rect
        # short wall centres the same pattern on its inner span W − 2t.
        # dx: the origin shift that achieves that centring:
        #   dx = (s_hex − (W − 2t)) / 2.
        # In --outside mode this equals t·(2 − 1/√3), the value that used to be
        # hard-coded as "empirical".  Deriving it keeps outside=0 correct as well.
        s_hex = self._hexWallLength()
        dx = (s_hex - (W - 2 * t)) / 2
        # end_big_xs: big-hole centres shared by the end walls and the short
        # dividers, in their common frame (x from the inner face of a long wall,
        # 0 … W − 2t).  They start from the hex-registration layout over s_hex,
        # shifted by dx into this frame.  Any hole that would cross a long-support
        # slot is dropped: the slots sit at lane_pos(i) on both panels (finger
        # slots in the end walls, crossing notches in the dividers), and a hole
        # through a joint weakens it.  The survivors are still a subset of the
        # hex wall's big holes, so registration is unaffected.  Both panels cut
        # exactly this list, so their big holes line up along the module.
        # Keep-out uses the hole's real half-width, so a narrower
        # --big_hole_width can fit between the supports where the full size
        # can't.  The centres themselves never move.
        big_keepout = (self._bigHoleHalfExtent(self._bigHoleRadius())[0]
                       + t / 2 + self._MIN_CLEAR)
        end_big_xs = [x - dx for x in self._alignmentBigXs(s_hex)
                      if all(abs(x - dx - lane_pos(i)) >= big_keepout
                             for i in range(n_div_v))]

        # Under-deck track opening (see _hexmo_under_track): on the end walls
        # and short dividers it replaces the centre big hole, at the wall
        # centre ``under_x`` in the same frame as end_big_xs.  Their y runs
        # down from the deck underside (the base plate is the deck), so the
        # opening's span above the floor maps to ``l_eff − height``.
        under_x = s_hex / 2 - dx
        under_y = None
        if self.under_track:
            # Validate everything before any panel is drawn.
            self._checkUnderTrackClearsCorners(s_hex)
            l_eff = self._hexWallHeight()
            bottom, top = self._underTrackSpan(l_eff)
            under_y = (l_eff - top, l_eff - bottom)
            half = self.under_track_width / 2
            for i in range(n_div_v):
                if abs(under_x - lane_pos(i)) < half + t / 2 + self._MIN_CLEAR:
                    raise ValueError(
                        "--under_track: a long support (--num_rows "
                        f"{n_rows}) crosses the end walls within the "
                        f"{self.under_track_width:g} mm opening; use an odd "
                        "--num_rows or a narrower --under_track_width.")
            big_half = self._bigHoleHalfExtent(self._bigHoleRadius())[0]
            end_big_xs = [x for x in end_big_xs
                          if abs(x - under_x) >= half + big_half + self._MIN_CLEAR]
        # div_pos: H-axis position of horizontal divider i (i = 0..3).
        # Used in long_wall_cb, spoke_cb, and base_cb.
        div_pos = lambda i: lay.div_pos[i]

        # --- fingerHoles callbacks ----------------------------------------------
        # Each outer wall's callback is called once (at edge-0, bottom) by cc().
        # Passing a single-element list [fn] means cc() fires fn only for i=0;
        # for i=1,2,3 the IndexError fallthrough leaves the wall face untouched.

        # Short outer walls (W × h): two vertical dividers pass through.
        # Vertical divider 1 is centred at col_w + t/2 along W.
        # Vertical divider 2 is centred at 2·col_w + 3t/2 along W.
        # fingerHolesAt(x, 0, h, 90): holes at x from inner-left, going up h.
        # drawAlignmentHolesRect(W-2t, h): alignment holes span the short wall's
        # inner dimension (W-2t) so that hole positions are compatible with the
        # matching HexmoHexagon side-wall holes (both panels are W = side-2t wide).
        def short_wall_cb():
            """Place fingerHoles and alignment holes on a short outer wall panel.

            Registered as the edge-0 (bottom) callback for ``rectangularWall``; called
            once per short wall during SVG generation.  Draws two vertical-divider
            fingerHole rows then delegates to ``drawAlignmentHolesRect`` to cut the
            full alignment-hole pattern across a compressed x-band whose spacing
            matches the HexmoHexagon edge-wall hole spacing.

            The alignment pattern is laid over the hex wall's own pattern length
            (``s_hex``) and centred on this wall by the origin shift ``dx``.  That
            puts every pin, medium and big hole at the same offset from the wall
            centre as on the mating HexmoHexagon side wall, so dowels pass
            straight through both.  The wall centre is also the track centreline.
            An earlier "compressed" length (s_rect) matched only the near end, and
            put the far end up to s_rect − s_hex out (3.6 mm at radius 190).

            Captures from enclosing scope: ``col_w``, ``t``, ``h``,
            ``s_hex``, ``dx``.
            """
            for i in range(n_div_v):
                self.fingerHolesAt(lane_pos(i), 0, h, 90)
            # NOTE: the spoke-to-short-wall connection is now handled by the 'F'
            # FingerJointEdgeCounterPart on the top edge of this panel (edge[2] in
            # rectangularWall).  The edge notches are drawn as part of the panel
            # outline — no rectangularHole callback needed here.
            self.moveTo(-dx, 0)
            # gap_features=False: the gap-fill medium holes at x_mid of the two
            # inter-big-hole gaps land directly on the vertical-divider finger
            # slots (fingerHolesAt above), so they must be suppressed here.
            #
            # The big-hole x-positions are NOT adjusted here: on this outer
            # (short) wall they are a registration surface, placed via s_hex so
            # they co-locate with the HexmoHexagon edge-wall big holes when the
            # two box types are assembled side by side.  Moving them (e.g. to
            # add corner clearance) breaks that alignment, so drawAlignmentHolesRect
            # keeps its default registration x_floor.
            self.drawAlignmentHolesRect(s_hex, gap_features=False,
                                        big_xs=[x + dx for x in end_big_xs])
            if under_y is not None:
                self._drawUnderTrackOpening(under_x + dx, *under_y, along_x=True)

        # Long outer walls (H × h): four horizontal dividers pass through.
        # Divider i is centred at (i+1)·row_h + (2i+1)·t/2 along H (i = 0..3).
        #
        # Corner cluster x-offset: the short wall's drawAlignmentHolesRect call is
        # preceded by moveTo(-dx, 0), which places its corner clusters at sp-dx from
        # each inner edge (aligned to the HexmoHexagon face geometry).  To keep the
        # two wall types pin-compatible, the long wall corner clusters must also sit
        # at sp-dx from each inner edge.  This is achieved by:
        #   1. moveTo(-dx, 0) — shift origin left by dx.
        #   2. _drawCornerGroup8Rect(H + 2*dx) — corners at sp (shifted) = sp-dx
        #      (absolute) from each end.  Right cluster: (H+2*dx−sp) shifted =
        #      H+dx−sp absolute → sp−dx from the right inner edge. ✓
        #   3. moveTo(dx, 0)  — restore origin for the big-hole band.
        #   4. Two big holes placed directly at x_floor and H−x_floor (segments 0
        #      and 4).  drawAlignmentHolesRect is NOT used on the long wall because
        #      we need full control over which segments carry a gap band.
        #
        # Gap band placement: segments 1, 2, and 3 each receive a full gap band
        # (big + small pair + medium pair) via _drawGapBandFeatures when the
        # segment is wide enough (half_gap ≥ 81 mm, i.e. radius ≳ 482 mm).
        # When the segment is too narrow for the full band but still fits a single
        # big hole (half_gap ≥ r4 + MIN_CLEAR = 40 mm), a single centred big hole
        # is placed via _drawSupportSegmentHole.
        # Segments 0 and 4 carry only the single big hole at x_floor / H-x_floor
        # when x_floor + r4 clears the first/last divider slot (row_h guard).
        #
        # Row segment j occupies x ∈ [j·(row_h+t), j·(row_h+t)+row_h].
        # Centering the gap band in that range gives ~8.2 mm clearance to the
        # adjacent finger-joint slots on both sides at default radius.
        def long_wall_cb():
            """Place fingerHoles and alignment holes on a long outer wall panel.

            Registered as the edge-0 (bottom) callback for ``rectangularWall``; called
            once per long wall.  Draws four horizontal-divider fingerHole rows, then:
              1. Corner clusters shifted by ``dx`` to match the short wall edge distance.
              2. Single big holes at ``x_floor`` and ``H − x_floor`` for segments 0
                 and 4 — only when x_floor + r4 clears the adjacent divider slot.
              3. Segments 1, 2, and 3: full gap band (big + small pair + medium pair)
                 via ``_drawGapBandFeatures`` when half_gap ≥ 81 mm (radius ≳ 482 mm);
                 otherwise a single centred big hole via ``_drawSupportSegmentHole``
                 when half_gap ≥ r4 + MIN_CLEAR = 40 mm.

            Segments 0 and 4 do not receive a full gap band because placing a big
            hole at their segment midpoints would overlap the corner cluster.

            The corner shift (``dx``, derived from the hex wall length) matches the origin shift used
            in ``short_wall_cb`` so that corner cluster holes are at the same distance
            from the panel edge on both wall types, keeping them pin-compatible.

            Captures from enclosing scope: ``row_h``, ``t``, ``h``, ``H``,
            ``dx``, ``x_floor``, ``div_pos``.
            """
            for i in range(n_div_h):
                # Horizontal dividers are h−t tall (body); 'f' top tabs are not
                # part of the end tab that slots into this wall, so fingerHoles
                # span only the body height h−t.
                self.fingerHolesAt(div_pos(i), 0, h - t, 90)
            # Shift the corner clusters by dx so they land at sp-dx from each inner
            # edge — the same distance as the short wall's hex-aligned corner clusters.
            self.moveTo(-dx, 0)
            self._drawCornerGroup8Rect(H + 2 * dx)
            self.moveTo(dx, 0)
            # Segments 0 and n_cols−1 (the two end segments): single big hole at
            # x_floor / H−x_floor.  The segment midpoints are too close to the corner
            # clusters for a full gap band; x_floor is the minimum safe distance from
            # the corner cluster.  Guard: the right edge of the hole (x_floor + r4)
            # must also clear the left edge of the first horizontal-divider finger
            # slot at x = row_h, otherwise the big circle punches into the interlock
            # joint.  When row_h is small (small --radius) there is simply no room
            # and the hole is suppressed rather than overlapping the joint.
            # Weight-reduction fill (see _fillWeightSpan): pack big holes and
            # fill the gaps between them with small/medium column clusters.  The
            # wall is divided into n_cols cells by the horizontal-divider slots;
            # the two end cells are inset by x_floor so the fill clears the
            # corner clusters, and interior cells span slot-to-slot.
            # An end cell runs from the corner cluster's outer edge (the medium
            # hole at 3·SPACER, right edge 3·SPACER + r2) to the first divider
            # slot.  Passing that true boundary lets _fillWeightSpan give the big
            # hole proper, balanced clearance from the corner cluster (rather
            # than pinning it a single MIN_CLEAR away).  Interior cells run
            # slot-to-slot with the default clearance on both sides.
            corner_edge = 3 * self._SPACER + self._R2
            if n_cols == 1:
                self._fillWeightSpan(corner_edge, H - corner_edge)
            else:
                self._fillWeightSpan(corner_edge, row_h)
                self._fillWeightSpan(H - row_h, H - corner_edge)
                for j in range(1, n_cols - 1):
                    x_lo = j * (row_h + t)
                    self._fillWeightSpan(x_lo, x_lo + row_h)

        # Segment-hole helper used by both divider types.
        # n: number of segments; step: inner length of each segment (row_h or col_w).
        # Each segment spans [j*(step+t), j*(step+t)+step]; crossing slots get no holes.
        def _seg_hole_cb(n, step):
            """Place one large centred hole per grid segment along the panel's x-axis.

            Called by ``vert_div_cb`` (5 row segments, step=row_h) and
            ``horiz_div_cb`` (3 column segments, step=col_w).  Each segment spans
            ``[j*(step+t), j*(step+t)+step]``; the ``t``-wide crossing slots between
            segments receive no holes.

            @param n    - Number of segments to fill.
            @param step - Inner length of each segment (mm).
            """
            for j in range(n):
                x_lo = j * (step + t)
                # Divider panels: packed big holes with medium gap features, but
                # pilots=False drops the Ø6 registration pilots — internal support
                # walls register to nothing, so those pilots are pure overhead.
                self._fillWeightSpan(x_lo, x_lo + step, pilots=False)

        # Vertical dividers (H × h): n_cols row segments, step = row_h.
        vert_div_cb  = lambda: _seg_hole_cb(n_cols, row_h)
        # Horizontal dividers (W−2t × h): n_rows lane segments, step = col_w.
        # NOTE: the spoke-to-divider connection is handled by the 'f' sections on
        # the top edge (via _HorizDivSpokeEdge) — no extra fingerHoles needed here.
        def _horiz_div_holes():
            """Weight-reduction holes on a short internal divider.

            The big holes are exactly the end walls' (``end_big_xs``), at the
            same height, so they line up along the module, for example as a
            wiring run.  Every other gap in each lane (between the lane's
            crossing notches and those big holes) gets the usual small/medium
            cluster, without pilots, because internal dividers register to
            nothing.  No extra big holes are packed in, because they wouldn't
            line up with anything.

            Captures from enclosing scope: ``n_rows``, ``col_w``, ``t``,
            ``end_big_xs``.
            """
            r4, mc = self._bigHoleRadius(), self._MIN_CLEAR
            y_big = self._hexWallHeight() / 2.0
            for j in range(n_rows):
                x_lo = j * (col_w + t)
                x_hi = x_lo + col_w
                bigs = [x for x in end_big_xs if x_lo <= x <= x_hi]
                for x in bigs:
                    self._drawBigHole(x, y_big, r4)
                # Spans the gap filling must stay clear of: each big hole and,
                # in its lane, the under-deck track opening.
                spans = [(x - r4 - mc, x + r4 + mc) for x in bigs]
                if under_y is not None and x_lo <= under_x <= x_hi:
                    self._drawUnderTrackOpening(under_x, *under_y, along_x=True)
                    half = self.under_track_width / 2
                    spans = sorted(spans + [(under_x - half - mc, under_x + half + mc)])
                los = [x_lo] + [hi for _, hi in spans]
                his = [lo for lo, _ in spans] + [x_hi]
                for g_lo, g_hi in zip(los, his):
                    self._drawSupportGapFeatures(g_lo, g_hi, pilots=False)

        horiz_div_cb = lambda: _horiz_div_holes()

        # Base plate ((W−2t) × H inner, W × (H+2t) outer): fingerHoles for all
        # six dividers.  At callback-0 the turtle sits at the inner-bottom-left
        # corner of the base face; x is measured along W−2t, y along H.
        #
        # Vertical dividers: n_cols 'f' sections each of length row_h, spaced row_h+t
        # apart in the H direction; centred at col_w+t/2 and 2·col_w+3t/2 in W.
        #
        # Horizontal dividers: 3 'f' sections each of length col_w, spaced col_w+t
        # apart in the W direction; centred at div_pos(i) in H for i in [0, n_div_h).
        def base_cb():
            """Draw fingerHoles for all six inner dividers on the base plate.

            Registered as the edge-0 callback for the base plate ``rectangularWall``.
            The base plate is drawn as ``rectangularWall(H, W−2t, …)`` so that the
            longer H edge runs horizontally in the SVG (left-to-right), matching the
            laser cutter's preferred orientation.  At callback-0 the turtle's origin
            is at the inner bottom-left corner of the base face, with x along the
            long (H) axis and y along the short (W−2t) axis.

            Two vertical-divider rows are placed at column-centre y-positions
            (``col_w + t/2`` and ``2·col_w + 3t/2`` along W); each row consists of
            n_cols finger-hole segments of length ``row_h`` drawn along x (H
            direction, angle=0), separated by ``t``-wide gaps at the horizontal
            crossing positions.

            n_div_h horizontal-divider rows are placed at row-centre x-positions
            (along H); each row consists of 3 finger-hole segments of length
            ``col_w`` drawn along y (W direction, angle=90), separated by ``t``-wide
            gaps at the vertical crossing positions.

            Captures from enclosing scope: ``col_w``, ``row_h``, ``t``,
            ``n_cols``, ``n_div_h``.
            """
            # Vertical divider fingerHoles (angle=0 → drawn along H direction, now x).
            # x_c is the divider's W-direction position, now the y-axis of the panel.
            # n_cols segments of row_h at positions j*(row_h+t) for j in [0, n_cols).
            for i in range(n_div_v):
                x_c = lane_pos(i)
                for j in range(n_cols):
                    self.fingerHolesAt(j * (row_h + t), x_c, row_h, 0)
            # Horizontal divider fingerHoles (angle=90 → drawn along W direction, now y).
            # y_c is the divider's H-direction position, now the x-axis of the panel.
            for i in range(n_div_h):
                for j in range(n_rows):
                    self.fingerHolesAt(div_pos(i), j * (col_w + t), col_w, 90)
            # Straight track guide down the long (H) axis, centred across the short
            # (W − 2t) axis.  The callback frame has x along H and y along W − 2t.
            if self.track_lines:
                self.drawRectTrackLines(H, W - 2 * t)
                for leg in turnout_legs:
                    self._etchTurnoutLeg(leg)

        # --- Outer walls --------------------------------------------------------
        # Long walls (left/right, spanning H) provide tabs on their small
        # (height-direction) edges — 'f' on left and right.
        # Short walls (front/back, spanning W) receive those tabs via 'F' slots
        # on their small (height-direction) edges.
        #
        # Edge string breakdown:
        #   "fFeF": [bottom='f', right='F', top='e', left='F']  ← short walls
        #   "ffef": [bottom='f', right='f', top='e', left='f']  ← long walls
        #
        # The long wall side-tabs ('f') project into the short wall end-slots ('F'),
        # creating flush corners where both outer faces are coplanar.  This
        # arrangement is preferred over the reverse because the short wall alignment-
        # hole clusters sit ~t mm from the panel edge; removing the protruding 'f'
        # tab from the short wall ends gives those clusters a clean flat edge rather
        # than having small pilot holes directly adjacent to a finger-joint tab tip.
        # Both wall types use bottom='f' so their base-edge tabs slot into the
        # base plate's perimeter 'F' counter-part slots.
        # Top is left open ('e') — a lid can be added in a later phase.

        # Two short outer walls spanning the W (radius) axis — with vertical-divider holes.
        # The panel is drawn with inner dimension W-2t so its laser-cut bounding box
        # equals W (= side-2t = HexmoHexagon edge-wall width), enabling flush assembly.
        #
        # Short wall edge list when the spoke is present:
        #   [bottom='f', right='F', top=CompoundEdge, left='F']
        #
        # The top edge uses a CompoundEdge(['e', 'F', 'e'], [gap, sw, gap]):
        #   - Plain 'e' for (W-2t-sw)/2 on each side — no joint, open edge
        #   - FingerJointEdgeCounterPart ('F') for the central sw mm only
        #     → notches cut into the top EDGE (open at edge, not as a face
        #     rectangle), matching the spoke's 'f' end tabs exactly.
        #   The spoke's end tab length (sw) equals the 'F' centre section length,
        #   so the tab pattern aligns perfectly.
        #
        # When the spoke is omitted the top reverts to plain 'e': "fFeF".
        if sw > 0:
            side_gap    = (W - 2 * t - sw) / 2
            # _ShortWallTopEdge draws 'e'+'F'+'e' without step() adjustments.
            # CompoundEdge cannot be used here: it calls step(t) when transitioning
            # from 'e' (endWidth=0) to 'F' (startWidth=t), which grows the panel
            # bounding-box from h to h+t — exactly the 106.4 mm symptom the user
            # reported.  _ShortWallTopEdge calls each segment directly, keeping the
            # wall at exactly h mm.
            e_short_top = _ShortWallTopEdge(self, side_gap, sw)
            short_wall_edges = ['f', 'F', e_short_top, 'F']
        else:
            short_wall_edges = "fFeF"
        # =======================================================================
        # SVG layout — two-column vertical stack
        #
        # In the boxes framework, move="up" advances the turtle y-coordinate
        # upward and maps to LOWER SVG y values (top of the image).  Panels
        # drawn later (at higher turtle y) therefore appear HIGHER in the SVG.
        #
        # To place column 1 (narrow, short panels) at the TOP of the SVG while
        # keeping it on the LEFT, we use the following trick:
        #
        #   1. move="right only" by W — pre-advance the cursor to column 2's
        #      x-position without drawing anything.  Column 2 will sit to the
        #      right of column 1 in the SVG.
        #   2. Draw all column 2 panels with move="up" — they start at turtle
        #      y=0 and stack upward, occupying the LOWER portion of the SVG.
        #   3. move="left only" by W — step the cursor back to x=0 while
        #      keeping the accumulated y (= col2 total height).
        #   4. Draw all column 1 panels with move="up" — they start above
        #      column 2's top (higher turtle y = UPPER portion of the SVG).
        #
        # Column 1 (width ≈ W = 488 mm at default radius):
        #   2 × short outer wall   (W−2t × h)
        #   4 × horizontal divider (W−2t × h−t, bbox h)
        #
        # Column 2 (width ≈ H+2t = 878 mm at default radius):
        #   2 × long outer wall    (H × h)
        #   2 × vertical divider   (H × h)
        #   1 × spoke              (H × sw)  [if sw > 0]
        #   1 × base plate         (H × W−2t)
        #
        # With default parameters this yields ≈ 1377 × 1652 mm (≈ 1:1 aspect).
        # =======================================================================

        # Step 1 — pre-advance to column 2's x-position.
        # W (= W−2t + 2t) is the max bbox width of column 1 panels: horizontal
        # dividers have 'f' on their side edges, adding t on each side beyond the
        # W−2t inner dimension, so using W ensures no overlap with column 2.
        self.rectangularWall(W, h, "eeee", move="right only")

        # --- Column 2 (right side): H-dimension panels stacked at low turtle y --
        # These will appear in the LOWER portion of the SVG.

        # Two long outer walls (H × h).
        # Bottom 'f': base plate connection.  Left/right 'f': into short wall 'F'.
        for _ in range(2):
            self.rectangularWall(H, h, "ffef",
                                 callback=[long_wall_cb], move="up")

        # n_div_v vertical dividers / long supports (H × h), splitting the width
        # into --num_rows lanes (none when --num_rows is 1).
        # Bottom SlottedEdge: n_cols 'f' sections + n_div_h Slot notches (depth h/2).
        # Left/right 'f': end-tabs into short outer wall fingerHoles.
        for _ in range(n_div_v):
            self.rectangularWall(H, h,
                                 [e_vert_bot, 'f', 'e', 'f'],
                                 callback=[vert_div_cb], move="up")

        # Centre support spoke (H × sw), stacked above the vertical dividers.
        # Short ends 'f': tab into _ShortWallTopEdge central 'F' section.
        # Face fingerHoles receive the 4 horizontal-divider 'f' top strips.

        def spoke_cb():
            """Draw fingerHoles for all four horizontal dividers on the spoke face.

            For each horizontal divider (4 positions along H), draws a single
            sw-length run of fingerHoles in the W direction (angle=90).  This
            matches the sw-wide 'f' strip produced by ``_HorizDivSpokeEdge`` on the
            divider's top edge — the 'f' tabs project upward into these slots.

            The spoke panel spans y = 0 to y = sw in its callback frame, which
            corresponds to the spoke's full W footprint (side_gap to side_gap+sw
            in the assembled box).  The divider's 'f' strip falls exactly in this
            range, so a single ``fingerHolesAt(x_div, 0, sw, 90)`` per divider
            produces the complete matching slot set.

            Captures from enclosing scope: ``row_h``, ``t``, ``sw``.
            """
            for i in range(n_div_h):
                # One sw-length fingerHoles run per divider: receives the sw-wide
                # 'f' strip from _HorizDivSpokeEdge.
                self.fingerHolesAt(div_pos(i), 0, sw, 90)
            # Large weight-reduction / access holes in the row gaps between the
            # divider finger slots.  Big holes only (clusters=False) — the spoke
            # registers to nothing, so it needs no medium/small holes — centred
            # across the spoke's sw width and packed clear of the finger slots and
            # the finger-tabbed ends (_fillWeightSpan keeps _BIG_EDGE clearance).
            if sw >= 2 * self._bigHoleRadius() + 2 * self._MIN_CLEAR:
                bounds = [0.0] + [div_pos(i) for i in range(n_div_h)] + [H]
                for g_lo, g_hi in zip(bounds[:-1], bounds[1:]):
                    self._fillWeightSpan(g_lo, g_hi, clusters=False, y_centre=sw / 2)

        if sw > 0:
            self.rectangularWall(H, sw, "efef",
                                 callback=[spoke_cb], move="up")

        # Base plate (H × W−2t) — topmost panel in column 2.
        # Drawn H-wide so the long axis is horizontal (laser left-to-right).
        # All four edges 'F': accept the outer-wall 'f' bottom tabs.
        self.rectangularWall(H, W - 2 * t, "FFFF",
                             callback=[base_cb], move="up")

        # Step 3 — step cursor back to x=0, keeping the accumulated y.
        # After column 2's move="up" calls the cursor sits at
        # (W+spacing, H2).  Stepping left by W lands at (0, H2).
        self.rectangularWall(W, h, "eeee", move="left only")

        # Step 4 — step DOWN so the two columns are top-aligned: column 1 starts
        # at y = H2 − H1 and both end at the same turtle y, which maps to the
        # same TOP position in the SVG.
        #
        # But when column 1 is the taller one (H1 > H2; e.g. --num_rows 1 drops
        # the long supports from column 2 while --num_columns 5 adds dividers to
        # column 1), H2 − H1 is below the starting line.  Column 1 would then
        # drop onto the --reference bar that open() draws at the origin.  So
        # the step is min(H1, H2): top-aligned when column 2 is taller (the
        # usual case), and bottom-aligned on the starting line otherwise.
        #
        # Heights are measured exactly as rectangularWall + move advance the
        # cursor: y + edges[0].spacing() + edges[2].spacing() + self.spacing.
        def stack(panels):
            return sum(y + self.edges.get(e[0], e[0]).spacing()
                       + self.edges.get(e[2], e[2]).spacing() + self.spacing
                       for y, e in panels)
        H2 = stack([(h, "ffef")] * 2
                   + [(h, [e_vert_bot, 'f', 'e', 'f'])] * n_div_v
                   + ([(sw, "efef")] if sw > 0 else [])
                   + [(W - 2 * t, "FFFF")])
        H1 = stack([(h, short_wall_edges)] * 2
                   + [(h - t, [e_horiz_bot, 'f', e_horiz_top, 'f'])] * n_div_h)
        # move="down only" with y_param P advances the cursor by −(P + s).
        col1_align_param = min(H1, H2) - self.spacing
        if col1_align_param > 0:
            self.rectangularWall(W, col1_align_param, "eeee", move="down only")

        # --- Column 1 (left side): W-dimension panels top-aligned with column 2 -
        # Drawn at turtle y = max(H2 − H1, 0) → top of col1 maps to the same SVG y
        # as the top of col2 whenever col2 is the taller column.

        # Two short outer walls (W−2t × h).
        for _ in range(2):
            self.rectangularWall(W - 2 * t, h, short_wall_edges,
                                 callback=[short_wall_cb], move="up")

        # n_div_h horizontal dividers (W−2t × h−t body; 'f' top tabs → bbox h).
        # Bottom SlottedEdge 'f': base plate connection.
        # Top _HorizDivSpokeEdge (or SlottedEdge 'e' without spoke).
        # Left/right 'f': end-tabs into long outer wall fingerHoles.
        for _ in range(n_div_h):
            self.rectangularWall(W - 2 * t, h - t,
                                 [e_horiz_bot, 'f', e_horiz_top, 'f'],
                                 callback=[horiz_div_cb], move="up")

        # Optional track-laying jig for the end walls.  It is drawn in the
        # frame of the hex wall these end walls mate with, so it is the same
        # plate HexmoHexagon cuts and fits either module.
        if self.track_guide:
            self.drawTrackGuide(self._hexWallLength(), self._hexWallHeight(),
                                move="right")

        # Optional Tracksetta-style template: a straight the full length of the
        # etched track (H, end wall to end wall).  Every track's straight is the
        # same, so one template covers them all.
        if self.track_template:
            self.drawTrackTemplate([("line", H)], f"straight {self.track_gauge:g}mm",
                                   move="right")

        self.drawReferencePanel(move="right")
