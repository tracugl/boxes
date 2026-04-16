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

from boxes import Boxes, edges
from boxes.Color import Color


class _HorizDivSpokeEdge(edges.BaseEdge):
    """Horizontal divider top edge: crossing slots with 'f' finger tabs in the spoke region.

    The horizontal divider spans W−2t = 3·col_w + 2·t.  Its top edge is divided
    into three col_w sections by two slot notches (for the vertical-divider
    interlock at mid-height).  When the spoke is present, the MIDDLE section is
    itself split into three sub-parts:

        'e' (pre-spoke gap) | 'f' (spoke width sw) | 'e' (post-spoke gap)

    The outer two sections (1 and 3) remain plain 'e'.

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
    @param col_w      - Width of each column segment in mm.
    @param slot_depth - Depth of the crossing-slot notches (= h/2 − t when spoke present).
    @param sw         - Spoke width in mm (only this central span gets 'f' tabs).
    """

    def __init__(self, boxes, col_w, slot_depth, sw) -> None:
        super().__init__(boxes, None)
        self._col_w      = col_w
        self._slot_depth = slot_depth
        self._sw         = sw

        # Compute the plain-'e' sub-sections flanking the 'f' strip inside the
        # middle section.  The middle section spans [col_w+t, 2·col_w+t].
        # The spoke occupies [side_gap, side_gap+sw] where
        #   side_gap = ((3·col_w + 2·t) − sw) / 2.
        t           = boxes.thickness
        total_w     = 3 * col_w + 2 * t          # = W − 2t
        side_gap    = (total_w - sw) / 2
        mid_start   = col_w + t                   # x-start of middle section
        self._pre   = max(0.0, side_gap - mid_start)           # gap before 'f'
        self._post  = max(0.0, (2 * col_w + t) - (side_gap + sw))  # gap after 'f'

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

        Draws section-1 ('e'), crossing slot, the mixed middle section
        ('e'+'f'+'e'), crossing slot, then section-3 ('e').  The total
        length equals W−2t = 3·col_w + 2·t, which must equal ``length``.

        @param length - Total edge length (must equal W−2t).
        """
        t      = self.boxes.thickness
        e_edge = self.edges['e']
        f_edge = self.edges['f']
        slot   = edges.Slot(self.boxes, self._slot_depth)

        # Section 1: full col_w, plain 'e'
        e_edge(self._col_w)
        # First crossing slot (t wide, slot_depth deep)
        slot(t)
        # Section 2 (middle): 'e' gap + 'f' spoke tabs + 'e' gap.
        # 'f' tabs project upward into the spoke face's fingerHoles.  The panel
        # is drawn at height h−t so that tabs + body = h total bounding-box.
        if self._pre > 0:
            e_edge(self._pre)
        f_edge(self._sw)
        if self._post > 0:
            e_edge(self._post)
        # Second crossing slot
        slot(t)
        # Section 3: full col_w, plain 'e'
        e_edge(self._col_w)


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


class HexmoRectangle(Boxes):
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
    _R4     = 35    # radius of large weight-reduction through-holes (mm) — equals
                    # (h − 2·_SPACER) / 2 for the default h=100, matching the 70 mm
                    # diameter produced by HexmoHexagon at the same height.
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

    def _drawCornerGroup8Rect(self, s):
        """Draw the end-column alignment cluster for a rectangularWall panel.

        Places a 3-hole vertical column at each end of the wall: one small hole
        near the top edge, one medium hole at the vertical centre, and one small
        hole near the bottom edge.  Both columns sit at x = 3·_SPACER from their
        respective inner edges.

        The medium hole x-position (3·sp) sets the ``corner_inner`` boundary used
        by ``drawAlignmentHolesRect`` and ``long_wall_cb`` when computing the safe
        zone for big through-holes, so that value must not change.

        All y-positions are derived from ``l_eff = self.h − 2·t`` so they are
        invariant with respect to outside mode.

        @param s - Panel length along the wall (x-axis of the rectangularWall callback).
        """
        sp = self._SPACER
        t  = self.thickness
        l_eff    = self.h - 2 * t
        sp_y     = sp
        y_center = l_eff / 2
        r2 = self._R2
        r3 = self._R3

        # Right-end cluster: small pair at 2·sp, then small/medium/small at 3·sp.
        self.hole(s - 2 * sp, l_eff - sp,  r3)   # near top, 2nd column
        self.hole(s - 2 * sp, sp_y,        r3)   # near bottom, 2nd column
        self.hole(s - 3 * sp, l_eff - sp,  r3)   # near top, 3rd column
        self.hole(s - 3 * sp, y_center,    r2)   # centre medium, 3rd column
        self.hole(s - 3 * sp, sp_y,        r3)   # near bottom, 3rd column

        # Left-end cluster: small pair at 2·sp, then small/medium/small at 3·sp.
        self.hole(2 * sp,     l_eff - sp,  r3)   # near top, 2nd column
        self.hole(2 * sp,     sp_y,        r3)   # near bottom, 2nd column
        self.hole(3 * sp,     l_eff - sp,  r3)   # near top, 3rd column
        self.hole(3 * sp,     y_center,    r2)   # centre medium, 3rd column
        self.hole(3 * sp,     sp_y,        r3)   # near bottom, 3rd column

    def _drawSupportGapFeatures(self, x_lo, x_hi):
        """Fill the x-axis gap between two features with a symmetric hole sub-group.

        Copied verbatim from HexmoHexagon so that divider panels produced by
        this generator carry the same sub-hole pattern as HexmoHexagon support
        panels, keeping all hole types pin-compatible across the system.

        Attempts to place, symmetrically within [x_lo, x_hi]:
          - Full G6 equivalent (left-small + centre-medium + right-small,
            top + bottom = 6 holes) when half-gap ≥ r2 + 2·r3 + 2·MIN_CLEAR.
          - G2-medium pair (top + bottom, 2 holes) when half-gap ≥ r2 + MIN_CLEAR.
          - Nothing when the gap or panel height is too small.

        @param x_lo - Inner left boundary of the gap (outer edge of left neighbour).
        @param x_hi - Inner right boundary of the gap (outer edge of right neighbour).
        """
        r2 = self._R2
        r3 = self._R3
        sp = self._SPACER
        # sp_y: height-direction margin for bottom-edge holes.  Plain sp — both
        # callbacks place y=0 at the inner bottom face, so no thickness offset.
        sp_y = sp
        mc = self._MIN_CLEAR

        # l_eff: effective inner height used by HexmoHexagon for all hole y-positions.
        # The hex callback does moveTo(0, -t) before drawing holes, reducing the
        # usable height to self.h - 2·t regardless of outside mode.  All top-edge
        # hole y-positions must use l_eff so they match the hex panel physically.
        l_eff = self.h - 2 * self.thickness
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

        if half_gap >= half_for_G6:
            # Full G6 equivalent: three x-positions × two y-positions (top + bottom).
            self.hole(x_mid - sm_offset, y_bot_r3, r3)
            self.hole(x_mid - sm_offset, y_top_r3, r3)
            self.hole(x_mid,             y_bot_r2, r2)
            self.hole(x_mid,             y_top_r2, r2)
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
        panel, at the same x position.  The central big hole (radius _R4) is a
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
        r4 = self._R4
        sp = self._SPACER
        mc = self._MIN_CLEAR

        l_eff = self.h - 2 * self.thickness
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
        self.hole(x_mid, y_big, r4)
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
        the big holes on the outer walls.  The hole radius is ``_R4`` — the same
        constant used by ``drawAlignmentHolesRect`` for the outer-wall big holes —
        so all large apertures in the assembled box share the same diameter.

        The vertical centre is placed at ``l_eff / 2`` (effective inner panel
        height divided by two), identical to the outer-wall big-hole y-position,
        so the holes align across mating faces.

        A hole is skipped if it would not fit: the segment width must be at least
        ``2 · _R4`` and the effective panel height must be at least ``2 · _R4``.

        @param x_lo - Inner left boundary of the segment (mm, callback frame x).
        @param x_hi - Inner right boundary of the segment (mm, callback frame x).
        """
        r4 = self._R4
        l_eff = self.h - 2 * self.thickness
        # Guard: skip if the hole diameter exceeds the segment or panel height.
        if (x_hi - x_lo) < 2 * r4 or l_eff < 2 * r4:
            return
        x_mid = (x_lo + x_hi) / 2
        y_mid = l_eff / 2
        self.hole(x_mid, y_mid, r4)

    def drawAlignmentHolesRect(self, s, gap_features=True, draw_corners=True):
        """Cut alignment features into an outer wall drawn by rectangularWall.

        Transposed counterpart of HexmoHexagon.drawAlignmentHoles: the 'long'
        axis of the hole pattern runs along x (wall length = s) rather than
        along y, matching the ``rectangularWall`` callback coordinate frame where
        the turtle faces right along the wall.

        All height-direction (y) positions are derived from self.h via l_eff
        (= self.h − 2·t) so they are invariant with respect to outside mode —
        no panel height argument is needed.

        The layout algorithm is identical to drawAlignmentHoles:
          1. Corner group-of-8 clusters at both ends (via _drawCornerGroup8Rect),
             unless ``draw_corners=False`` (used when the caller draws them
             separately at pre-shift coordinates).
          2. Up to three large through-holes along the y = l_eff/2 centre line,
             spaced to avoid the corner clusters.
          3. Gap filling between adjacent features (via _drawGapBandFeatures),
             controlled by the ``gap_features`` flag.

        The big-hole radius uses the fixed class constant _R4, matching the radius
        produced by HexmoHexagon for the same h value (r4 = (h − 2·_SPACER) / 2
        for the default h=100, giving r4=35 = diameter 70 mm).  Using a constant
        rather than re-deriving from l ensures identical hole sizes regardless of
        outside mode.

        @param s            - Wall length (x-axis of rectangularWall callback).
        @param gap_features - When True (default) the gaps between big holes and
                              the corner clusters are filled with top/bottom hole
                              pairs via ``_drawSupportGapFeatures``.  Pass False
                              for the short outer walls, where those gap holes
                              fall directly on the vertical-divider finger-joint
                              slots cut by ``fingerHolesAt`` in ``short_wall_cb``,
                              causing physical material conflicts.
        """
        sp = self._SPACER
        r2 = self._R2
        mc = self._MIN_CLEAR

        # Large through-hole radius — fixed class constant matching HexmoHexagon's
        # (h − 2·_SPACER) / 2 formula at the default h=100, giving diameter 70 mm.
        r4 = self._R4

        # Minimum x-distance from either end where a big hole centre can sit
        # without its edge overlapping the corner cluster's medium hole.
        x_floor = 3 * sp + r2 + r4 + mc

        # Available length for the interior big-hole band.
        available = s - 2 * x_floor

        if available < 0:
            # Wall too short for any interior big holes — corner clusters only.
            big_xs = []
        else:
            n = min(3, max(1, 1 + int(available / (2 * r4 + mc))))
            # Force odd count so the distribution is symmetric and s/2 is always
            # included, providing a track pass-through aperture at mid-wall.
            if n % 2 == 0:
                n -= 1
            if n == 1:
                big_xs = [s / 2]
            else:
                step = available / (n - 1)
                big_xs = [x_floor + i * step for i in range(n)]

        # Large through-holes along the centre line.
        # y_big: vertical centre of big through-holes.  Uses l_eff (effective inner
        # height = self.h − 2·t) rather than a callback-frame offset, so the physical
        # hole centre matches the hex polygonWall's y_big = l_eff / 2 for both
        # outside=True and outside=False.
        l_eff = self.h - 2 * self.thickness
        y_big = l_eff / 2
        for x in big_xs:
            self.hole(x, y_big, r4)

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

        # --- Grid geometry ------------------------------------------------------
        # The 3-column × n_cols-row grid divides the inner cavity dimensions evenly.
        # 2 vertical dividers (each thickness t) occupy 2t of the W width.
        # n_div_h horizontal dividers (each thickness t) occupy n_div_h·t of H.
        # The short wall panel is drawn with inner dimension W − 2t (so the
        # laser-cut bounding box = (W−2t) + 2t = W, matching the HexmoHexagon
        # side-wall width).  The box inner cavity in the short direction is
        # therefore W − 2t, and 2 vertical dividers (each thickness t) leave
        # (W − 2t) − 2t = W − 4t for the 3 column interiors.
        col_w = (W - 4 * t) / 3              # inner width of each of the 3 columns
        row_h = (H - n_div_h * t) / n_cols   # inner height of each row cell

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
            e_horiz_top = _HorizDivSpokeEdge(self, col_w, h / 2 - t + tol, sw)
        else:
            e_horiz_top = edges.SlottedEdge(self, [col_w] * 3, 'e', slots=h / 2 + tol)

        # Horizontal divider bottom: 'f' sections connect to base plate at the
        # three col_w spans; crossing positions use plain 'e' (no tabs there since
        # vertical dividers occupy that material).
        e_horiz_bot = edges.SlottedEdge(self, [col_w] * 3, 'f')

        # --- Shared callback precomputations ------------------------------------
        # dx and x_floor are used identically in both short_wall_cb and long_wall_cb.
        # Precomputing them once here avoids duplication inside each closure.
        #
        # dx: origin shift so rect hole x-positions align with hex hole y-positions
        # after the hex moveTo(0, -t) has been applied.  Derived empirically:
        # dx = t*(2 - 1/√3).
        dx = t * (2 - 1 / math.sqrt(3))
        # x_floor: minimum x-distance from either end where a big hole centre can
        # sit without overlapping the corner-cluster medium hole edge.
        x_floor = 3 * self._SPACER + self._R2 + self._R4 + self._MIN_CLEAR
        # div_pos: H-axis position of horizontal divider i (i = 0..3).
        # Used in long_wall_cb, spoke_cb, and base_cb.
        div_pos = lambda i: (i + 1) * row_h + (2 * i + 1) * t / 2

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

            The x-band compression (``s_rect``) and origin shift (``dx``) replicate
            the affine transform that the hexagon's ``polygonWall`` miter geometry
            applies to its edge-wall callbacks, so that big holes on both panel types
            are co-located in physical space when the two box types are assembled
            side-by-side.

            Captures from enclosing scope: ``col_w``, ``t``, ``h``, ``W``, ``r``,
            ``dx``, ``x_floor``.
            """
            self.fingerHolesAt(col_w + t / 2,           0, h, 90)
            self.fingerHolesAt(2 * col_w + 3 * t / 2,   0, h, 90)
            # Compute s_rect so that big-hole spacing in x matches the HexmoHexagon
            # edge wall's y-spacing.  The hex's polygonWall fires the callback with an
            # effective x-scale of (radius - 2t) / radius due to the miter setup at
            # each hex vertex (moveTo(-t/√3, 0) in the callback frame).  We replicate
            # that same compressed distribution by shrinking the interior band while
            # keeping the corner cluster positions (x_floor) fixed.
            s_rect   = 2 * x_floor + (self.radius - 2 * x_floor) * (self.radius - 2 * t) / self.radius
            # NOTE: the spoke-to-short-wall connection is now handled by the 'F'
            # FingerJointEdgeCounterPart on the top edge of this panel (edge[2] in
            # rectangularWall).  The edge notches are drawn as part of the panel
            # outline — no rectangularHole callback needed here.
            self.moveTo(-dx, 0)
            # gap_features=False: the gap-fill medium holes at x_mid of the two
            # inter-big-hole gaps land directly on the vertical-divider finger
            # slots (fingerHolesAt above), so they must be suppressed here.
            self.drawAlignmentHolesRect(s_rect, gap_features=False)

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

            The corner shift (``dx = t * (2 − 1/√3)``) matches the origin shift used
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
            l_eff = self.h - 2 * t
            y_big = l_eff / 2
            if x_floor + self._R4 + self._MIN_CLEAR <= row_h:
                self.hole(x_floor,     y_big, self._R4)
                self.hole(H - x_floor, y_big, self._R4)
            # Interior segments 1 … n_cols−2: full gap band when the segment is wide
            # enough, otherwise a single centred big hole.
            # The _drawGapBandFeatures threshold duplicates the guard inside that
            # method (half_gap >= md_off + r2 + mc) so we can choose the fallback
            # without modifying the method's signature.
            sm_off = self._R4 + self._MIN_CLEAR + self._R3
            md_off = sm_off + self._R3 + self._MIN_CLEAR + self._R2
            half_gap = row_h / 2
            for j in range(1, n_cols - 1):
                x_lo = j * (row_h + t)
                x_hi = x_lo + row_h
                if half_gap >= md_off + self._R2 + self._MIN_CLEAR:
                    # Wide enough for the full band pattern.
                    self._drawGapBandFeatures(x_lo, x_hi)
                else:
                    # Too narrow for the full band; place one centred big hole.
                    # _drawSupportSegmentHole self-guards if r4 doesn't fit.
                    self._drawSupportSegmentHole(x_lo, x_hi)

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
                # One large hole per segment — matches the outer-wall big-hole
                # pattern and is simpler to cut than the multi-hole G6 cluster.
                self._drawSupportSegmentHole(x_lo, x_lo + step)

        # Vertical dividers (H × h): n_cols row segments, step = row_h.
        vert_div_cb  = lambda: _seg_hole_cb(n_cols, row_h)
        # Horizontal dividers (W−2t × h): 3 column segments, step = col_w.
        # NOTE: the spoke-to-divider connection is handled by the 'f' sections on
        # the top edge (via _HorizDivSpokeEdge) — no extra fingerHoles needed here.
        horiz_div_cb = lambda: _seg_hole_cb(3, col_w)

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
            for i in range(2):
                x_c = (i + 1) * col_w + (2 * i + 1) * t / 2
                for j in range(n_cols):
                    self.fingerHolesAt(j * (row_h + t), x_c, row_h, 0)
            # Horizontal divider fingerHoles (angle=90 → drawn along W direction, now y).
            # y_c is the divider's H-direction position, now the x-axis of the panel.
            for i in range(n_div_h):
                for j in range(3):
                    self.fingerHolesAt(div_pos(i), j * (col_w + t), col_w, 90)

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

        # Two vertical dividers (H × h), creating the 3-column grid split.
        # Bottom SlottedEdge: 5 'f' sections + 4 Slot notches (depth h/2).
        # Left/right 'f': end-tabs into short outer wall fingerHoles.
        for _ in range(2):
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

        # Step 4 — step DOWN by H1 so column 1 starts at y = H2-H1.
        # Both columns then end at the same turtle y = H2, which maps to the
        # same TOP position in the SVG — i.e. the two columns are top-aligned.
        #
        # Column 1 contains 2 short outer walls + n_div_h horizontal dividers.
        # Every col1 panel has overallHeight = h + t (due to _HorizDivSpokeEdge.margin()).
        # H1 = (2 + n_div_h)·(h+t) + (2 + n_div_h)·s  (panels × [oH + s]).
        #
        # move="down only" with y_param P advances the cursor by −(P+s).
        # To advance by −H1 set P = H1−s = (2+n_div_h)·(h+t) + (1+n_div_h)·s.
        col1_align_param = (2 + n_div_h) * (h + t) + (1 + n_div_h) * self.spacing
        if col1_align_param > 0:
            self.rectangularWall(W, col1_align_param, "eeee", move="down only")

        # --- Column 1 (left side): W-dimension panels top-aligned with column 2 -
        # Drawn at turtle y = H2-H1 → top of col1 maps to the same SVG y as the
        # top of col2.

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

        self.drawReferencePanel(move="right")
