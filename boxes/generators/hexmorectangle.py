"""Rectangular box with a fixed 3×5 internal grid, compatible with the HexmoHexagon
modular stacking system.

The short wall length equals one hexagon side (``--radius``), so a HexmoHexagon can
join any of its edges flush against either short wall of this rectangle.  The long
wall equals the hexagon flat-to-flat distance (``radius × √3``).

Phase implementation:
  1. Core structure: 4 outer walls + base plate (done).
  2. Internal 3×5 grid with crossing dividers (this file — Phase 2).
  3. HexmoHexagon-compatible alignment holes on all panels.
  4. Reference panel and JSDoc polish.
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

import math

from boxes import Boxes, edges


class HexmoRectangle(Boxes):
    """Rectangular tray with a fixed 3×5 internal grid, compatible with HexmoHexagon stacking."""
    
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

    def _drawCornerGroup8Rect(self, s):
        """Draw the four corner L-clusters for a rectangularWall panel.

        Exact transposed counterpart of HexmoHexagon._drawCornerGroup8: every
        ``hole(x, y, r)`` call has its x and y arguments swapped so the 18-hole
        pattern fits the ``rectangularWall`` callback coordinate frame, where
        x runs along the wall length (s) and y runs along the panel height.

        The visual layout is identical to the hexagon variant; only the axis
        assignment changes.  Calling this from a ``rectangularWall`` callback
        therefore produces alignment holes that are pin-compatible with holes on
        adjacent HexmoHexagon panels.

        All height-direction (y) positions are derived from self.h via l_eff so
        they are invariant with respect to outside mode — no panel height argument
        is needed.

        @param s - Panel length along the wall (x-axis of the rectangularWall callback).
        """
        sp = self._SPACER
        t  = self.thickness
        # l_eff: the effective inner height used by HexmoHexagon for all hole
        # y-positions.  The hex callback does `moveTo(0, -t)` before drawing holes,
        # which effectively reduces the usable height by t at both ends.  The result
        # is l_eff = self.h − 2·t regardless of outside mode, and all hole y-positions
        # must use l_eff as the reference so that physical hole positions match.
        l_eff    = self.h - 2 * t
        # sp_y: y-margin for bottom-edge holes from inner bottom face (y=0 in callback).
        sp_y     = sp
        # y_center: vertical midpoint of the corner-strip medium holes.  Equals
        # l_eff / 2, matching HexmoHexagon._drawCornerGroup8's hole(l/2, ...) placement.
        y_center = l_eff / 2
        r2 = self._R2
        r3 = self._R3

        # Right-end top corner L-cluster.  Top positions are measured from l_eff
        # (the effective usable height) rather than from the raw callback height l,
        # so that the physical hole locations match the hex panel's top-cluster holes.
        self.hole(s - sp,         l_eff - sp,           r3)
        self.hole(s - 2 * sp,     l_eff - sp,           r3)
        self.hole(s - sp,         l_eff - 2 * sp,       r3)

        # Centre-strip registration pins at 3·sp from both ends of the wall.
        self.hole(s - 3 * sp, l_eff - sp,  r3)   # right end, near top
        self.hole(s - 3 * sp, y_center,    r2)   # right-end centre medium
        self.hole(3 * sp,     l_eff - sp,  r3)   # left end, near top
        self.hole(3 * sp,     y_center,    r2)   # left-end centre medium
        self.hole(s - 3 * sp, sp_y,        r3)   # right end, near bottom
        self.hole(3 * sp,     sp_y,        r3)   # left end, near bottom

        # Right-end bottom corner L-cluster.
        self.hole(s - sp,         sp_y,         r3)
        self.hole(s - 2 * sp,     sp_y,         r3)
        self.hole(s - sp,         sp_y + sp,    r3)

        # Left-end top corner L-cluster.
        self.hole(sp,         l_eff - sp,           r3)
        self.hole(2 * sp,     l_eff - sp,           r3)
        self.hole(sp,         l_eff - 2 * sp,       r3)

        # Left-end bottom corner L-cluster.
        self.hole(sp,         sp_y,         r3)
        self.hole(2 * sp,     sp_y,         r3)
        self.hole(sp,         sp_y + sp,    r3)

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
        MIN_CLEAR = 5.0

        # l_eff: effective inner height used by HexmoHexagon for all hole y-positions.
        # The hex callback does moveTo(0, -t) before drawing holes, reducing the
        # usable height to self.h - 2·t regardless of outside mode.  All top-edge
        # hole y-positions must use l_eff so they match the hex panel physically.
        l_eff = self.h - 2 * self.thickness
        # Vertical guard: bottom-medium top edge (sp_y + 3·r2/2) must clear top-medium
        # bottom edge (l_eff − sp − 3·r2/2) by at least MIN_CLEAR.
        # Rearranged: l_eff ≥ 2·sp + 3·r2 + MIN_CLEAR.
        if l_eff < 2 * sp + 3 * r2 + MIN_CLEAR:
            return

        half_gap = (x_hi - x_lo) / 2
        x_mid    = (x_lo + x_hi) / 2

        half_for_G2m = r2 + MIN_CLEAR
        sm_offset    = r2 + r3 + MIN_CLEAR   # ensures MIN_CLEAR between small and medium edges
        half_for_G6  = sm_offset + r3 + MIN_CLEAR

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

    def drawAlignmentHolesRect(self, s):
        """Cut alignment features into an outer wall drawn by rectangularWall.

        Transposed counterpart of HexmoHexagon.drawAlignmentHoles: the 'long'
        axis of the hole pattern runs along x (wall length = s) rather than
        along y, matching the ``rectangularWall`` callback coordinate frame where
        the turtle faces right along the wall.

        All height-direction (y) positions are derived from self.h via l_eff
        (= self.h − 2·t) so they are invariant with respect to outside mode —
        no panel height argument is needed.

        The layout algorithm is identical to drawAlignmentHoles:
          1. Corner group-of-8 clusters at both ends (via _drawCornerGroup8Rect).
          2. Up to three large through-holes along the y = l_eff/2 centre line,
             spaced to avoid the corner clusters.
          3. Gap filling between adjacent features (via _drawSupportGapFeatures).

        The big-hole radius uses the fixed class constant _R4, matching the radius
        produced by HexmoHexagon for the same h value (r4 = (h − 2·_SPACER) / 2
        for the default h=100, giving r4=35 = diameter 70 mm).  Using a constant
        rather than re-deriving from l ensures identical hole sizes regardless of
        outside mode.

        @param s - Wall length (x-axis of rectangularWall callback).
        """
        sp = self._SPACER
        r2 = self._R2
        MIN_CLEAR = 5.0

        # Large through-hole radius — fixed class constant matching HexmoHexagon's
        # (h − 2·_SPACER) / 2 formula at the default h=100, giving diameter 70 mm.
        r4 = self._R4

        # Minimum x-distance from either end where a big hole centre can sit
        # without its edge overlapping the corner cluster's medium hole.
        x_floor = 3 * sp + r2 + r4 + MIN_CLEAR

        # Available length for the interior big-hole band.
        available = s - 2 * x_floor

        if available < 0:
            # Wall too short for any interior big holes — corner clusters only.
            big_xs = []
        else:
            n = min(3, max(1, 1 + int(available / (2 * r4 + MIN_CLEAR))))
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

        # Fill every gap between adjacent features with sub-hole pairs.
        corner_inner = 3 * sp + r2                        # inner x-edge of corner medium hole
        lo_bounds = [corner_inner]      + [x + r4 for x in big_xs]
        hi_bounds = [x - r4 for x in big_xs] + [s - corner_inner]
        for x_lo, x_hi in zip(lo_bounds, hi_bounds):
            self._drawSupportGapFeatures(x_lo, x_hi)

        # Corner clusters — drawn last so their fixed-offset holes are never
        # masked by the dynamic interior features.
        self._drawCornerGroup8Rect(s)

    def render(self) -> None:
        """Generate all panels for the HexmoRectangle box (Phase 2: outer shell + 3×5 grid).

        Draws eleven panels:
          - 2 × short outer wall  (W × h)  — span the short (radius) axis
          - 2 × long outer wall   (H × h)  — span the long (radius × √3) axis
          - 1 × base plate        (W × (H + 2t))
          - 2 × vertical divider  (H × h)  — split the box into 3 columns
          - 4 × horizontal divider ((W−2t) × h) — split the box into 5 rows

        ``--radius`` is always the inner corner-to-corner radius of the matching
        HexmoHexagon; W is derived from it without any outside-mode adjustment so
        that the short wall bbox = W regardless of outside mode.  When
        ``--outside`` is set, ``h`` and ``H`` are adjusted to inner dimensions
        (matching HexmoHexagon's outside-mode convention); W is unchanged.

        Crossing-joint convention (slot-and-tab):
          Vertical dividers carry ``SlottedEdge`` on their **bottom** edges:
          five 'f' sections (finger-tabs for the base plate) separated by four
          Slot notches of depth h/2.  Horizontal dividers carry ``SlottedEdge``
          on their **top** edges: three 'e' sections separated by two Slot
          notches of depth h/2.  The two sets of notches interlock at mid-height
          when the horizontal dividers are lowered over the vertical ones during
          assembly.

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

        # --- Grid geometry ------------------------------------------------------
        # The 3-column × 5-row grid divides the inner cavity dimensions evenly.
        # 2 vertical dividers (each thickness t) occupy 2t of the W width.
        # 4 horizontal dividers (each thickness t) occupy 4t of the H height.
        # The short wall panel is drawn with inner dimension W − 2t (so the
        # laser-cut bounding box = (W−2t) + 2t = W, matching the HexmoHexagon
        # side-wall width).  The box inner cavity in the short direction is
        # therefore W − 2t, and 2 vertical dividers (each thickness t) leave
        # (W − 2t) − 2t = W − 4t for the 3 column interiors.
        col_w = (W - 4 * t) / 3   # inner width of each of the 3 columns
        row_h = (H - 4 * t) / 5   # inner height of each of the 5 rows

        # --- Crossing slot edges ------------------------------------------------
        # Vertical dividers span H and use 'f' sections (connecting to base plate)
        # separated by Slot notches of depth h/2 at the 4 horizontal crossing
        # positions.  The slot is cut from the BOTTOM of the flat panel, so when
        # the divider stands upright the notch opens upward from the base.
        e_vert_bot = edges.SlottedEdge(self, [row_h] * 5, 'f', slots=h / 2)

        # Horizontal dividers span W and use plain 'e' sections on their top edge
        # separated by Slot notches of depth h/2 at the 2 vertical crossing
        # positions.  The slot is cut from the TOP of the flat panel; when the
        # divider stands upright it opens downward from the top, meshing with the
        # vertical divider's bottom slot at the h/2 midpoint.
        e_horiz_top = edges.SlottedEdge(self, [col_w] * 3, 'e', slots=h / 2)

        # Horizontal divider bottom: 'f' sections connect to base plate at the
        # three col_w spans; crossing positions use plain 'e' (no tabs there since
        # vertical dividers occupy that material).
        e_horiz_bot = edges.SlottedEdge(self, [col_w] * 3, 'f')

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

            Captures from enclosing scope: ``col_w``, ``t``, ``h``, ``W``, ``r``.
            """
            self.fingerHolesAt(col_w + t / 2,           0, h, 90)
            self.fingerHolesAt(2 * col_w + 3 * t / 2,   0, h, 90)
            # Compute s_rect so that big-hole spacing in x matches the HexmoHexagon
            # edge wall's y-spacing.  The hex's polygonWall fires the callback with an
            # effective x-scale of (radius - 2t) / radius due to the miter setup at
            # each hex vertex (moveTo(-t/√3, 0) in the callback frame).  We replicate
            # that same compressed distribution by shrinking the interior band while
            # keeping the corner cluster positions (x_floor) fixed.
            sp_loc   = self._SPACER
            r1_loc   = self._R4
            x_floor  = 3 * sp_loc + self._R2 + r1_loc + 5.0
            s_rect   = 2 * x_floor + (self.radius - 2 * x_floor) * (self.radius - 2 * t) / self.radius
            # dx: origin shift so that rect hole x-positions align with hex hole y-positions
            # after the hex moveTo(0, -t) has been applied.  Derived empirically:
            # dx = t*(2 - 1/√3).
            dx = t * (2 - 1 / math.sqrt(3))
            self.moveTo(-dx, 0)
            self.drawAlignmentHolesRect(s_rect)

        # Long outer walls (H × h): four horizontal dividers pass through.
        # Divider i is centred at (i+1)·row_h + (2i+1)·t/2 along H (i = 0..3).
        def long_wall_cb():
            """Place fingerHoles and alignment holes on a long outer wall panel.

            Registered as the edge-0 (bottom) callback for ``rectangularWall``; called
            once per long wall.  Draws four horizontal-divider fingerHole rows at their
            respective row-centre positions, then delegates to ``drawAlignmentHolesRect``
            to cut the full alignment-hole pattern spanning the long wall's inner width H.

            Captures from enclosing scope: ``row_h``, ``t``, ``h``, ``H``.
            """
            for i in range(4):
                pos = (i + 1) * row_h + (2 * i + 1) * t / 2
                self.fingerHolesAt(pos, 0, h, 90)
            self.drawAlignmentHolesRect(H)

        # Vertical dividers (H × h): alignment holes placed per row segment.
        # Each of the 5 row segments spans [j*(row_h+t), j*(row_h+t)+row_h] along
        # x (the H axis); crossing slots at the remaining t-wide positions hold no
        # holes.  _drawSupportGapFeatures fills each segment with top/bottom hole
        # pairs compatible with HexmoHexagon support panels.
        def vert_div_cb():
            """Place alignment holes in each row segment of a vertical divider.

            Registered as the edge-0 callback for the two vertical divider panels.
            For each of the 5 row segments along the long axis, calls
            ``_drawSupportGapFeatures`` to fill the segment with top/bottom hole pairs
            matching the HexmoHexagon support-panel pattern.  The crossing-slot regions
            (width ``t``) between segments receive no holes.

            Captures from enclosing scope: ``row_h``, ``t``, ``h``.
            """
            for j in range(5):
                x_lo = j * (row_h + t)
                self._drawSupportGapFeatures(x_lo, x_lo + row_h)

        # Horizontal dividers (W × h): alignment holes placed per column segment.
        # Each of the 3 column segments spans [j*(col_w+t), j*(col_w+t)+col_w].
        def horiz_div_cb():
            """Place alignment holes in each column segment of a horizontal divider.

            Registered as the edge-0 callback for the four horizontal divider panels.
            For each of the 3 column segments along the short axis, calls
            ``_drawSupportGapFeatures`` to fill the segment with top/bottom hole pairs
            matching the HexmoHexagon support-panel pattern.  The crossing-slot regions
            (width ``t``) between segments receive no holes.

            Captures from enclosing scope: ``col_w``, ``t``, ``h``.
            """
            for j in range(3):
                x_lo = j * (col_w + t)
                self._drawSupportGapFeatures(x_lo, x_lo + col_w)

        # Base plate ((W+2t) × (H+2t)): fingerHoles for all six dividers.
        # At callback-0 the turtle sits at the inner-bottom-left corner of the
        # base face; x is measured along W, y along H (angle 90 = turn upward).
        #
        # Vertical dividers: 5 'f' sections each of length row_h, spaced row_h+t
        # apart in the H direction; centred at col_w+t/2 and 2·col_w+3t/2 in W.
        #
        # Horizontal dividers: 3 'f' sections each of length col_w, spaced col_w+t
        # apart in the W direction; centred at (i+1)·row_h+(2i+1)·t/2 in H.
        def base_cb():
            """Draw fingerHoles for all six inner dividers on the base plate.

            Registered as the edge-0 callback for the base plate ``rectangularWall``.
            At callback-0 the turtle's origin is at the inner bottom-left corner of
            the base face, with x along the short (W) axis and y along the long (H)
            axis.

            Two vertical-divider rows are placed at column-centre x-positions
            (``col_w + t/2`` and ``2·col_w + 3t/2``); each row consists of 5
            finger-hole segments of length ``row_h``, separated by ``t``-wide gaps at
            the horizontal crossing positions.

            Four horizontal-divider rows are placed at row-centre y-positions; each
            row consists of 3 finger-hole segments of length ``col_w``, separated by
            ``t``-wide gaps at the vertical crossing positions.

            Captures from enclosing scope: ``col_w``, ``row_h``, ``t``.
            """
            # Vertical divider fingerHoles (angle=90 → drawn along H direction).
            for i in range(2):
                x_c = (i + 1) * col_w + (2 * i + 1) * t / 2
                for j in range(5):
                    self.fingerHolesAt(x_c, j * (row_h + t), row_h, 90)
            # Horizontal divider fingerHoles (angle=0 → drawn along W direction).
            for i in range(4):
                y_c = (i + 1) * row_h + (2 * i + 1) * t / 2
                for j in range(3):
                    self.fingerHolesAt(j * (col_w + t), y_c, col_w, 0)

        # --- Outer walls --------------------------------------------------------
        # Short walls (front/back, spanning W) provide tabs on their small
        # (height-direction) edges — 'f' on left and right.
        # Long walls (left/right, spanning H) receive those tabs via 'F' slots
        # on their small (height-direction) edges.
        #
        # Edge string breakdown:
        #   "ffef": [bottom='f', right='f', top='e', left='f']  ← short walls
        #   "fFeF": [bottom='f', right='F', top='e', left='F']  ← long walls
        #
        # The short wall side-tabs ('f') project into the long wall end-slots ('F'),
        # creating flush corners where both outer faces are coplanar.
        # Both wall types use bottom='f' so their base-edge tabs slot into the
        # base plate's perimeter 'F' counter-part slots.
        # Top is left open ('e') — a lid can be added in a later phase.

        # Two short outer walls spanning the W (radius) axis — with vertical-divider holes.
        # The panel is drawn with inner dimension W-2t so its laser-cut bounding box
        # equals W (= side-2t = HexmoHexagon edge-wall width), enabling flush assembly.
        for _ in range(2):
            self.rectangularWall(W - 2 * t, h, "ffef",
                                 callback=[short_wall_cb], move="right")

        # Two long outer walls spanning the H (radius × √3) axis — with horizontal-divider holes.
        for _ in range(2):
            self.rectangularWall(H, h, "fFeF",
                                 callback=[long_wall_cb], move="right")

        # Advance the layout cursor to a fresh row below the wall panels.
        self.rectangularWall(1, h, "eeee", move="up only")

        # --- Base plate ---------------------------------------------------------
        # The base plate spans the full outer footprint of the box.
        # Short walls have inner dimension W−2t and 'f' tabs on both vertical sides,
        # so their outer extent = (W−2t) + 2t = W.  Long walls have inner H and
        # 'F' (female) on their vertical sides (no outward protrusion there), but
        # because edgeCorner adds a step of t at each top/bottom corner for their
        # 'F' side edges, the long wall outer extent = H + 2t.
        # Base plate must therefore be W wide × (H + 2t) deep.
        # 'F' on all four edges receives the bottom 'f' tabs from every outer wall.
        # The base_cb callback adds fingerHoles for all six inner dividers.
        self.rectangularWall(W, H + 2 * t, "FFFF",
                             callback=[base_cb], move="right")

        # Advance cursor past the base plate row before drawing dividers.
        self.rectangularWall(1, H + 2 * t, "eeee", move="up only")

        # --- Vertical dividers --------------------------------------------------
        # Two panels spanning H (the long axis), creating the 3-column split.
        # Bottom edge: SlottedEdge with 5 'f' sections for base plate connection,
        # separated by 4 Slot notches (depth h/2) at the horizontal crossing points.
        # Left / right edges ('f'): end-tabs that seat into fingerHoles on the
        # two short outer walls.
        # Top edge ('e'): open — flush with the outer wall tops.
        for _ in range(2):
            self.rectangularWall(H, h,
                                 [e_vert_bot, 'f', 'e', 'f'],
                                 callback=[vert_div_cb], move="right")

        # Advance cursor past the vertical divider row.
        self.rectangularWall(1, h, "eeee", move="up only")

        # --- Horizontal dividers ------------------------------------------------
        # Four panels spanning W (the short axis), creating the 5-row split.
        # Bottom edge: SlottedEdge with 3 'f' sections for base plate connection,
        # plain 'e' (no slot, no tabs) at the 2 vertical crossing positions.
        # Top edge: SlottedEdge with 3 'e' sections and 2 Slot notches (depth h/2)
        # at vertical crossing positions — these interlock with the vertical
        # dividers' bottom slots at mid-height during assembly.
        # Left / right edges ('f'): end-tabs seating into fingerHoles on the long
        # outer walls.
        # Horizontal dividers span the inner short cavity (W−2t) between the two
        # long outer walls, with 'f' end-tabs on left and right seating into the
        # fingerHoles on those long walls.  Inner dimension = W−2t; bbox = W.
        for _ in range(4):
            self.rectangularWall(W - 2 * t, h,
                                 [e_horiz_bot, 'f', e_horiz_top, 'f'],
                                 callback=[horiz_div_cb], move="right")
