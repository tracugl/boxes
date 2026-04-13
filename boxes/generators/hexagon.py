"""Hexagon box generator with optional 'spoke' bottom pattern.

The 'spoke' style draws a hexagonal frame (outer and inner hex cut) plus six
identical kite-shaped cutouts arranged symmetrically around the centre.
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
import copy
import datetime
import math

from boxes import Boxes, edges, boolarg
from boxes.generators.bayonetbox import BayonetBox
from boxes.Color import *


class HexagonBox(BayonetBox):
    """Box with a regular hexagon or half hexagon as the base. """

    ui_group = "Box"

    # Alignment-hole geometry constants shared by drawAlignmentHoles,
    # drawAlignmentHolesLong, and drawSupports.  Centralising them here
    # means a single change propagates to all three methods.
    _SPACER = 15    # minimum clearance from panel edge to hole edge (mm)
    _R2     = 12.5  # radius of medium alignment-pin receiver holes (mm)
    _R3     = 3     # radius of small registration dot / pilot holes (mm)

    def __init__(self) -> None:
        Boxes.__init__(self)

        # Override the default material thickness to suit typical hex box use.
        defaultgroup = self.argparser._action_groups[1]
        for action in defaultgroup._actions:
            if action.dest == 'thickness':
                action.default = 6.0

        self.addSettingsArgs(edges.FingerJointSettings, finger=5, space=5, surroundingspaces=2, play=0.2)

        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--radius", action="store", type=float, default=500.0,
            help="inner radius of the hexagon (at the corners)")
        self.argparser.add_argument(
            "--top", action="store", type=str, default="closed",
            choices=["closed"],
            help="style of the top")
        self.argparser.add_argument(
            "--bottom", action="store", type=str, default="spoke",
            choices=["spoke", "closed"],
            help="style of the bottom")
        self.argparser.add_argument(
            "--edge_width", action="store", type=float, default=60.0,
            help="Width of the outer hexagonal frame for spoke bottom.")
        self.argparser.add_argument(
            "--spoke_width", action="store", type=float, default=120.0,
            help="Width of the spokes for spoke bottom.")
        self.argparser.add_argument(
            "--support_length", action="store", type=float, default=150.0,
            help="length of the internal supports.")
        self.argparser.add_argument(
            "--supports", action="store", type=boolarg, default=True,
            help="add internal support walls and matching finger-joint slots in the top and bottom panels.")
        self.argparser.add_argument(
            "--trapezoid", action="store", type=boolarg, default=False,
            help="If true, only draw a half-hexagon.")

        self.lugs = 6
        self.n = 6

    def drawSupports(self, isTrapezoid=False):
        """Draw rectangular internal support walls, one per half-spoke.

        A hexagonal spoke bottom has six support walls — one for each of the
        six half-spokes radiating from the centre (two halves per axis across
        the three 60° axes).  In trapezoid mode only the three downward
        half-spokes are present, so only three support walls are needed.

        All walls are identical rectangles of size support_length × box_height,
        finger-jointed on both long edges ('fefe' pattern), so they can be
        laser-cut from the same template.

        A single large circular through-hole is cut in the centre of each
        support, using the same sizing formula as drawAlignmentHoles:
            r1 = (h - spacer - spacer) / 2
        where 'spacer' is the minimum clearance margin from the panel edges.
        If 'spacer' yields a non-positive radius the hole is omitted.

        @param isTrapezoid - When True, render 3 support walls instead of 6.
        """
        h = self.h
        if self.outside:
            h = self.adjustSize(h)
        sl = self.support_length

        # Mirror the hole-radius formula used by drawAlignmentHoles so that the
        # support hole is consistent with the rest of the geometry.  Use self.h
        # (raw box height, not adjustSize-shrunk) to keep diameters identical
        # regardless of whether --outside is set.
        r1 = (self.h - 2 * self._SPACER) / 2

        # Number of support walls: 6 for a full hexagon, 3 for a trapezoid.
        n_supports = 3 if isTrapezoid else 6

        if r1 > 0:
            # Callback fires at the bottom-left corner (edge 0) with the
            # x-axis pointing right and y-axis pointing into the panel.
            # From that origin, (sl/2, h/2) is the geometric centre of the
            # rectangle, which is exactly where the through-hole should sit.
            def draw_center_hole():
                self.hole(sl / 2, h / 2, r1)

            for _ in range(n_supports):
                self.rectangularWall(sl, h, "fefe", callback=[draw_center_hole], move="right")
        else:
            # Panel is too short for the hole to clear the edges — render
            # without a hole rather than producing invalid geometry.
            for _ in range(n_supports):
                self.rectangularWall(sl, h, "fefe", move="right")

    def drawSupportHoles(self, r, isTrapezoid=False):
        """Cut finger-joint slots into the bottom panel for all three spoke axes.

        A hexagonal spoke bottom has three internal support walls, one per spoke
        direction (0°, +60°, and -60° from the vertical axis).  Each spoke gets
        two finger-joint slots placed symmetrically around the hex centre so that
        the rectangular support wall can slot perpendicularly into the panel.

        This callback fires at the start of edge 0 (the bottom-left vertex of the
        flat-top hexagon), NOT at the panel centre.  In that coordinate system the
        panel centre lies at (r/2, H).  To rotate each spoke's slots correctly we
        must first translate the origin to the centre and THEN rotate; rotating
        around (0,0) would pivot around the bottom-left vertex and produce wildly
        misplaced slots.

        moveTo(r/2, H, spoke_angle) achieves the combined translate-then-rotate in
        one call (ctx.translate followed by ctx.rotate).  After that, the two
        fingerHolesAt positions are expressed in centre-relative coordinates:
        (0, ±H/2), so they sit symmetrically on each spoke axis regardless of
        the spoke angle.

        In trapezoid mode the hex centre sits on the long top edge, and only the
        three downward half-spokes fall inside the panel.  The "lower slot" (local
        y < 0, i.e. below centre toward the short bottom edge) is the one that
        stays; the upper slot would land outside the trapezoid and is omitted.
        The coordinate formula for the centre (r/2, H) is unchanged because V0
        (callback origin) is the same bottom-left vertex in both modes.

        @param r          - Inner corner radius of the hexagon bottom panel.
        @param isTrapezoid - When True, only cut the three lower (inward) slots
                             instead of all six.
        """
        sl = self.support_length

        H = r * math.sqrt(3) / 2.0  # apothem — also the y-distance from origin to centre

        # The three spoke axes are 60° apart.  For each one, shift the coordinate
        # origin to the hex centre and rotate to align with the spoke, then draw
        # the slot(s).  saved_context() keeps the transform local so the next
        # spoke starts from the original origin.
        #
        # Both regularPolygonWall (hex) and drawTrapezoidWall (trap) fire the
        # support-holes callback (callback[1]) at y = edges[0].startWidth() + burn
        # = thickness + burn above V0.  From that callback origin, moveTo(r/2, H)
        # places the centre at y = H + thickness + burn from V0 — identical in both
        # modes.  No special trapezoid correction is needed here.

        for spoke_angle in (0, 60, -60):
            with self.saved_context():
                # Translate to the hex centre then rotate to the spoke axis.
                self.moveTo(r / 2, H, spoke_angle)
                # Lower slot: midpoint at (0, -H/2) in centre-relative coords.
                # This slot falls in the trapezoid's half (below the hex centre)
                # and is always drawn.
                self.fingerHolesAt(0, -H / 2 - sl / 2, sl, angle=90)
                if not isTrapezoid:
                    # Upper slot: midpoint at (0, +H/2) — above the hex centre.
                    # Only present in full-hexagon mode; outside the trapezoid panel.
                    self.fingerHolesAt(0,  H / 2 - sl / 2, sl, angle=90)

    def _drawCornerGroup8(self, s, l):
        """Draw the corner registration clusters shared by all side-panel variants.

        Each end of a side panel (top and bottom edges) carries an L-shaped cluster
        of small pilot holes at its two corners, plus one medium hole centred on the
        panel's x-midpoint at 3 × _SPACER from the edge.  Together these form the
        'group-of-8' referenced in the alignment-hole pattern: 8 small holes total
        (3 per corner L × 2 corners, but the two inward L-legs share the centre-line
        column) surrounding the 2 centre-line medium holes.

        All positions use fixed _SPACER offsets so the clusters sit the same physical
        distance from the panel edges regardless of how wide or tall the panel is.
        This method is called by both drawAlignmentHoles and drawAlignmentHolesLong
        to eliminate 18 lines of verbatim duplication.

        @param s - Panel height (pre-shrink side0 value), used for y-axis positions.
        @param l - Panel width (slant length), used for x-axis positions.
        """
        sp = self._SPACER
        r2 = self._R2
        r3 = self._R3

        # Top-right corner L-cluster and top-left corner L-cluster.
        self.hole(l - sp,     s - sp,     r3)
        self.hole(l - sp,     s - 2 * sp, r3)
        self.hole(l - 2 * sp, s - sp,     r3)

        # Centre-line pins at 3·sp from both top and bottom edges.
        self.hole(l - sp, s - 3 * sp, r3)
        self.hole(l / 2,  s - 3 * sp, r2)  # top-centre medium hole
        self.hole(l - sp, 3 * sp,     r3)
        self.hole(l / 2,  3 * sp,     r2)  # bottom-centre medium hole

        self.hole(sp,     s - 3 * sp, r3)
        self.hole(sp,     3 * sp,     r3)

        self.hole(sp,         s - sp,     r3)
        self.hole(sp,         s - 2 * sp, r3)
        self.hole(2 * sp,     s - sp,     r3)

        # Bottom-right corner L-cluster and bottom-left corner L-cluster.
        self.hole(l - sp,     sp,         r3)
        self.hole(l - sp,     2 * sp,     r3)
        self.hole(l - 2 * sp, sp,         r3)

        self.hole(sp,         sp,         r3)
        self.hole(sp,         2 * sp,     r3)
        self.hole(2 * sp,     sp,         r3)

    def _drawGapFeatures(self, l, y_lo, y_hi):
        """Fill the space between two adjacent features with G6 sub-groups.

        Attempts to place, symmetrically within the inner gap [y_lo, y_hi]:
          - Full G6 equivalent (G2-small + G2-medium + G2-small, 6 holes)
            when half-gap ≥ r2 + 2·r3 + 2·MIN_CLEAR  (≈ 28.5 mm)
          - G2-medium pair only (2 holes)
            when half-gap ≥ r2 + MIN_CLEAR             (≈ 17.5 mm)
          - Nothing when the gap is too small

        y_lo and y_hi are **inner** boundaries — the outer edge of the lower
        adjacent feature and the inner edge of the upper adjacent feature
        respectively.  Callers compute them as: corner_inner = 3·sp + r2,
        big_hole top/bottom = centre ± r1.

        The small holes in the G6 are placed at y_mid ± sm_offset where
        sm_offset = r2 + r3 + MIN_CLEAR, guaranteeing MIN_CLEAR clearance
        to both the medium hole and the gap boundaries.

        @param l    - Panel width (for x-position calculations).
        @param y_lo - Inner lower boundary (top edge of the feature below this gap).
        @param y_hi - Inner upper boundary (bottom edge of the feature above this gap).
        """
        r2 = self._R2
        r3 = self._R3
        sp = self._SPACER
        MIN_CLEAR = 5.0

        half_gap = (y_hi - y_lo) / 2
        y_mid    = (y_lo + y_hi) / 2

        # Minimum half-gap for a G2-medium pair to clear both boundaries.
        half_for_G2m = r2 + MIN_CLEAR              # ≈ 17.5 mm

        # Small holes are placed at y_mid ± sm_offset.  The offset must satisfy:
        #   sm_offset ≥ r2 + r3 + MIN_CLEAR   (clear the medium hole edge)
        # And the small must also clear the gap boundary:
        #   sm_offset + r3 + MIN_CLEAR ≤ half_gap
        # Combined minimum half-gap for the full G6 equivalent:
        sm_offset   = r2 + r3 + MIN_CLEAR          # ≈ 20.5 mm
        half_for_G6 = sm_offset + r3 + MIN_CLEAR   # ≈ 28.5 mm

        if half_gap >= half_for_G6:
            # Full G6 equivalent: G2-small · G2-medium · G2-small (symmetric).
            self.hole(l - sp,        y_mid - sm_offset, r3)  # lower small, right side
            self.hole(sp,            y_mid - sm_offset, r3)  # lower small, left side
            self.hole(l - r2/2 - sp, y_mid,             r2)  # medium, right side
            self.hole(sp + r2/2,     y_mid,             r2)  # medium, left side
            self.hole(l - sp,        y_mid + sm_offset, r3)  # upper small, right side
            self.hole(sp,            y_mid + sm_offset, r3)  # upper small, left side

        elif half_gap >= half_for_G2m:
            # Gap too narrow for smalls — place medium pair only.
            self.hole(l - r2/2 - sp, y_mid, r2)
            self.hole(sp + r2/2,     y_mid, r2)

    def drawAlignmentHoles(self, s, l, text):
        """Cut and etch alignment features into a side panel for stacking hexagons.

        The corner group-of-8 clusters at both panel ends are always drawn at
        fixed absolute spacer offsets (invariant to panel height).  The interior
        layout has two layers:

        1. Big holes: up to three, always odd-counted so s/2 (the mandatory
           centre track-pass-through aperture) is included.  A single centred
           hole is used when the wall is too short for three.

        2. Gap filling: every space between adjacent features (corner → BIG,
           BIG → BIG, BIG → corner) is passed to _drawGapFeatures, which
           fills it with a G6-equivalent (G2-small + G2-medium + G2-small)
           or just a G2-medium pair depending on how much room is available.

        At radius=300 this produces corner-8 → G2s → G2m → BIG → G2m → G2s
        → corner-8, matching the intended pattern exactly.

        @param s    - Pre-shrink panel height (original side0, before subtracting 2*t).
        @param l    - Panel width (slant length l from render()).
        @param text - Unused; kept for API compatibility.
        """
        sp = self._SPACER
        r2 = self._R2

        # r1 is sized so the hole fills most of the wall width (l), leaving
        # _SPACER clearance top and bottom of the box height dimension.
        r1 = (self.h - 2 * sp) / 2

        # Minimum edge-to-edge clearance between any two circular features.
        MIN_CLEAR = 5.0

        # Lowest y where a big hole centre can sit without its edge overlapping
        # the corner group's medium hole (at 3·sp, radius r2).
        y_floor = 3 * sp + r2 + r1 + MIN_CLEAR

        # Vertical band available for interior holes, between the two safe floors.
        available = s - 2 * y_floor

        # Compute how many big holes fit without overlapping each other.
        # Each adjacent pair requires at least (2·r1 + MIN_CLEAR) centre-to-centre.
        if available < 0:
            # Wall too short — no interior holes; just the corner groups.
            big_ys = []
        else:
            n = min(3, max(1, 1 + int(available / (2 * r1 + MIN_CLEAR))))
            # Force an odd count so the distribution is always symmetric and
            # s/2 is guaranteed to be a big hole.  The centre hole must remain
            # present at every radius because it acts as a track pass-through
            # aperture for stacked board sections.
            if n % 2 == 0:
                n -= 1
            if n == 1:
                # Single hole centred vertically.
                big_ys = [s / 2]
            else:
                # For odd n ≥ 3, evenly spaced with the middle hole at s/2.
                step = available / (n - 1)
                big_ys = [y_floor + i * step for i in range(n)]

        # Draw the big through-holes along the vertical centre line.
        for y in big_ys:
            self.hole(l / 2, y, r1)

        # Fill every gap with sub-groups via _drawGapFeatures.
        # Boundaries: the corner group's inner edge is 3·sp + r2 (top of the
        # medium hole).  Each big hole contributes its outer edge at centre ± r1.
        corner_inner = 3 * sp + r2
        lo_bounds = [corner_inner]      + [y + r1 for y in big_ys]
        hi_bounds = [y - r1 for y in big_ys] + [s - corner_inner]
        for y_lo, y_hi in zip(lo_bounds, hi_bounds):
            self._drawGapFeatures(l, y_lo, y_hi)

        # Corner group-of-8 clusters (see _drawCornerGroup8 for layout details).
        self._drawCornerGroup8(s, l)

    def drawAlignmentHolesLong(self, s, l, text):
        """Cut and etch alignment features into the trapezoid long back wall.

        The long back wall spans two hex-side-lengths (s = 2 * side0_orig).
        Its hole layout is derived from the standard-wall algorithm (see
        drawAlignmentHoles) applied to s_half = s/2, then mirrored symmetrically
        about the centre so that positions near either edge of the long wall match
        exactly the positions on the adjacent standard walls.

        Pattern (bottom → top, n_big=3 case):
            group-of-8
            BIG  G6  BIG  G6  BIG          ← bottom half positions
            BIG  (centre, no G6 on either side — "transition zone")
            BIG  G6  BIG  G6  BIG          ← top half (mirrored)
            group-of-8

        When fewer big holes fit per half (small-radius boards), the pattern
        shrinks proportionally while preserving the corner groups.

        @param s    - Pre-shrink panel height (2 * side0_orig for the long wall).
        @param l    - Panel width (slant length l from render()).
        @param text - Unused; kept for API compatibility.
        """
        sp = self._SPACER
        r2 = self._R2
        r1 = (self.h - 2 * sp) / 2

        # Use the same dynamic algorithm as drawAlignmentHoles, applied to
        # s_half so the bottom-half y-positions match the adjacent standard wall.
        s_half = s / 2
        MIN_CLEAR = 5.0
        y_floor   = 3 * sp + r2 + r1 + MIN_CLEAR
        available = s_half - 2 * y_floor

        if available < 0:
            half_ys = []
        else:
            n = min(3, max(1, 1 + int(available / (2 * r1 + MIN_CLEAR))))
            # Force odd count — see drawAlignmentHoles for the reasoning.
            if n % 2 == 0:
                n -= 1
            if n == 1:
                half_ys = [s_half / 2]
            else:
                step = available / (n - 1)
                half_ys = [y_floor + i * step for i in range(n)]

        # Full list: bottom half + long-wall centre + top half mirrored.
        # The centre hole at s/2 is distinct from any half_ys value (half_ys
        # lives in [y_floor, s_half - y_floor] ⊂ [0, s_half], and y_floor > 0).
        big_ys = half_ys + [s / 2] + [s - y for y in reversed(half_ys)]

        # Draw the big through-holes along the vertical centre line.
        for y in big_ys:
            self.hole(l / 2, y, r1)

        # Fill every gap with sub-groups via _drawGapFeatures — same logic as
        # drawAlignmentHoles.  The "transition zone" gaps near s/2 are naturally
        # narrow and will produce only G2m or nothing, while the outer gaps
        # (matching the adjacent standard walls) receive the full G6 equivalent.
        corner_inner = 3 * sp + r2
        lo_bounds = [corner_inner]      + [y + r1 for y in big_ys]
        hi_bounds = [y - r1 for y in big_ys] + [s - corner_inner]
        for y_lo, y_hi in zip(lo_bounds, hi_bounds):
            self._drawGapFeatures(l, y_lo, y_hi)

        # Corner group-of-8 clusters — same layout as drawAlignmentHoles.
        self._drawCornerGroup8(s, l)

    def drawKites(self, r, joint_type, isTrapezoid):
        """Draw six kite-shaped cutouts inside the hexagonal spoke bottom panel.

        Each kite is derived from a master shape aligned with the flat-top
        orientation of the outer hexagon, then rotated in 60-degree increments.
        If the frame or spokes would degenerate (non-positive dimensions), the
        method falls back to a plain closed polygon with no cutouts.

        @param r           - Inner corner radius of the hexagon bottom panel.
        @param joint_type  - Two-character edge string (e.g. 'yY') passed
                             through to regularPolygonWall on fallback.
        @param isTrapezoid - When True, only the two kites in the flat half
                             are drawn (half-hexagon / trapezoid mode).
        """
        n = self.n
        edge_width = self.edge_width
        spoke_width = self.spoke_width

        sqrt3 = math.sqrt(3)
        cos30 = sqrt3 / 2.0
        A_outer = r * cos30             # outer apothem of the hex
        A_inner = A_outer - edge_width  # apothem inset by the frame width
        if A_inner <= 0:
            # Frame width consumes the entire panel — fall back to solid hex.
            self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
            return
        R_inner = A_inner / cos30                   # inner corner radius after frame
        # Half the chord length of the kite base (derived from spoke geometry).
        s = (A_inner / sqrt3) - (spoke_width / 2.0)
        if s <= 0:
            # Spokes are too wide to fit — fall back to solid hex.
            self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
            return

        # Define the master kite with its apex pointing upward (+y direction).
        P1 = (0.0, R_inner)                          # top vertex (120° angle)
        P2 = (s * sqrt3 / 2.0, R_inner - s / 2.0)   # right 90° vertex
        P3 = (0.0, R_inner - 2.0 * s)               # inner 60° vertex
        P4 = (-s * sqrt3 / 2.0, R_inner - s / 2.0)  # left 90° vertex

        def rotate_points(pts, angle_deg):
            """Rotate a list of (x, y) points around the origin by angle_deg."""
            ang = math.radians(angle_deg)
            ca, sa = math.cos(ang), math.sin(ang)
            return [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]

        # Rotate master kite 30° so its edges align with the flat-top hex orientation.
        kite_master = rotate_points([P1, P2, P3, P4], 30)

        # Produce one kite per hex face by rotating the master in 60° steps.
        kites = [rotate_points(kite_master, 60 * i) for i in range(6)]

        for kite_counter, kite in enumerate(kites):
            # In trapezoid mode only kites 2 and 3 are drawn.  The master kite
            # has its apex at +y (upward), so after the 30° alignment rotation:
            #   kite 0 apex → upper-left  (above centre, outside the trapezoid)
            #   kite 1 apex → left        (at centre height)
            #   kite 2 apex → lower-left  (below centre, inside the trapezoid) ✓
            #   kite 3 apex → lower-right (below centre, inside the trapezoid) ✓
            #   kite 4 apex → right       (at centre height)
            #   kite 5 apex → upper-right (above centre, outside the trapezoid)
            # The trapezoid is the bottom half of the hexagon, so only kites 2
            # and 3 fall within its boundary.
            if isTrapezoid and kite_counter not in (2, 3):
                continue

            self.ctx.move_to(kite[0][0], kite[0][1])
            for x_, y_ in kite[1:]:
                self.ctx.line_to(x_, y_)
            self.ctx.line_to(kite[0][0], kite[0][1])
            self.ctx.stroke()

    def drawTrapezoidWall(self, r, edges_char='e', hole=None, callback=None, move=None):
        """Draw a trapezoidal panel — the bottom (or top) half of a regular hexagon.

        The trapezoid is derived by slicing a flat-top hexagon horizontally through
        its centre.  Two trapezoids placed back-to-back on their long edge reform the
        original hexagon.  The four edges, traversed counter-clockwise from the
        bottom-left vertex (V0), are:

          Edge 0 — short bottom edge, length r  (hex side length)
          Edge 1 — right slanted side, length r
          Edge 2 — long top/join edge, length 2r
          Edge 3 — left slanted side, length r

        Exterior turn angles (same as regularPolygonWall convention):
          60° at V1 and V0 (interior angle 120°)
          120° at V2 and V5 (interior angle 60°)

        Callback convention (identical to regularPolygonWall):
          callback[0] — fired at the hexagon centre (r/2 from V0, H above V0)
          callback[1..4] — fired at the start of edges 0..3 respectively

        The bounding box width equals that of the full hexagon (both span 2r
        horizontally), so the layout cursor advances by the same x-amount as a
        corresponding regularPolygonWall call would.

        @param r          - Hexagon circumradius (= hex side length).
        @param edges_char - Edge type character or single-char string for all four
                            sides (default 'e').  One char is replicated to all four
                            edges; a 4-char string assigns each edge individually.
        @param hole       - Diameter of a central circular cutout, or None.
        @param callback   - List/tuple of callables; indexed per the convention above.
        @param move       - Layout direction string ('right', 'up only', etc.).
        """
        # H_geom = r*√3/2 is the apothem of the hexagon (= intended panel height).
        # H is a helper variable used only for the bounding box and callback positions;
        # it does NOT control the actual cut path height.
        #
        # Bounding box height = H + 2*thickness + spacing.  We want this to equal
        # H_geom + spacing, so H = H_geom - 2*thickness.
        #
        # The cut path height is determined by the edge/corner geometry.  A naive
        # edgeCorner(120° exterior) at V2 produces step1 = t*tan(60°) = t√3 in the
        # 60° direction, contributing y = t√3·sin(60°) = 3t/2.  Combined with V1's
        # +t/2 and the per-edge shortfall, the total comes out to H_geom + t — one
        # thickness too tall.
        #
        # The fix: at V2 and V5 the step that lies along the slant direction is drawn
        # as t/√3 (matching the miter used at 60°-exterior hex vertices) rather than
        # t√3.  This brings the join-edge outer face to exactly H_geom, so two
        # trapezoid panels placed back-to-back on their join edges reproduce the full
        # hexagon height.
        H = r * math.sqrt(3) / 2.0 - 2 * self.thickness

        # Resolve the edge character(s) to edge objects.  Replicate a single char
        # across all four sides; otherwise treat as a per-edge sequence.
        if not hasattr(edges_char, "__getitem__") or len(edges_char) == 1:
            edges = [self.edges.get(edges_char, edges_char)] * 4
        else:
            edges = [self.edges.get(e, e) for e in edges_char]
        edges = edges + edges   # duplicate for wrapping corner references

        # Bounding box.  The trapezoid has the same horizontal span as the full
        # hexagon (leftmost point x = -r/2, rightmost x = 3r/2), so we reuse the
        # hex tw formula from regularPolygonWall.  Height:
        #   path_height = H_geom (achieved via the custom V2/V5 corners below)
        #   th = path_height + edges[0].spacing() = H_geom + spacing
        sp = max(edges[i].spacing() for i in range(4))
        tw = 2 * r + 2 * sp / math.sin(math.radians(60))
        th = H + 2 * self.thickness + edges[0].spacing()

        if self.move(tw, th, move, before=True):
            return

        # Position the cursor at V0 — the left end of the short bottom edge.
        # Formula mirrors regularPolygonWall: 0.5*tw - 0.5*side, where side=r.
        self.moveTo(0.5 * tw - 0.5 * r, edges[0].margin())

        # Centre callback (callback[0] for kites) and optional central hole.
        # The hex centre sits at the join-edge outer face level (H_geom from V0).
        # We fire the callback at y = H + 2*thickness + burn = H_geom + burn so
        # that kite paths originate at the join-edge boundary and extend inward
        # (downward in panel coordinates).
        if hole:
            self.hole(r / 2., H + 2 * self.thickness + self.burn, hole / 2.)
        self.cc(callback, 0, r / 2., H + 2 * self.thickness + self.burn)

        # ── Edge 0: short bottom edge (length r) ─────────────────────────────
        self.cc(callback, 1, 0, edges[0].startWidth() + self.burn)
        edges[0](r)
        self.edgeCorner(edges[0], edges[1], 60)    # 60° exterior at V1 (interior 120°)

        # ── Edge 1: right slanted side (length r) ────────────────────────────
        self.cc(callback, 2, 0, edges[1].startWidth() + self.burn)
        edges[1](r)

        # V2 corner (120° exterior, interior 60°): use t/√3 for the slant-direction
        # step instead of the standard t·tan(60°) = t√3.  This is the same miter
        # size used at hexagon vertices (60° exterior) and places the join-edge outer
        # face at exactly H_geom — half the full hexagon path height.
        self.edge(self.thickness / math.sqrt(3.0))
        self.corner(120)
        # step3 at 180°: use 2t/√3 (= 2A) not t·tan(60°)=t√3 (= 3A).
        # The 3A value over-extends the path by A = t/√3 per side, producing a
        # trapezoid that is 2A = 2t/√3 wider than the hexagon.  2A matches the
        # miter geometry needed for the join-edge outer face to align with the
        # corresponding hexagon vertex.
        self.edge(2.0 * self.thickness / math.sqrt(3.0))

        # ── Edge 2: long top/join edge (length 2r) ───────────────────────────
        self.cc(callback, 3, 0, edges[2].startWidth() + self.burn)
        edges[2](2 * r)

        # V5 corner (120° exterior, interior 60°): symmetric reduction of the
        # return step3 (t/√3 instead of t√3) so the path closes correctly after
        # the modified V2 step1.
        # step1 at 180°: symmetric reduction matching the V2 step3 fix above.
        # 2t/√3 instead of t·tan(60°)=t√3 so both corners contribute equally to
        # closing the extra horizontal travel introduced by the modified V2 step1.
        self.edge(2.0 * self.thickness / math.sqrt(3.0))
        self.corner(120)
        self.edge(self.thickness / math.sqrt(3.0))

        # ── Edge 3: left slanted side (length r) ─────────────────────────────
        self.cc(callback, 4, 0, edges[3].startWidth() + self.burn)
        edges[3](r)
        self.edgeCorner(edges[3], edges[0], 60)    # 60° exterior at V0 (interior 120°)

        self.move(tw, th, move)

    def drawReferencePanel(self, move="right"):
        """Render a flat reference panel listing all generator parameters.

        The panel is sized to contain the full parameter list as engraved text
        and uses Color.ETCHING so that laser software routes it as an engrave
        pass rather than a cut pass.  A Color.OUTER_CUT rectangle provides the
        border so the panel can be cut from stock.

        The panel is positioned using the standard boxes ``move`` convention:
        call with ``move="right"`` (default) to advance the layout cursor to
        the right of the panel, or ``move="up only"`` to reserve space only.

        @param move - Direction string passed to self.move() for layout
                      control.  Defaults to "right".
        """
        fontsize = 6          # mm — small but legible on most laser systems
        margin = 5            # mm — clearance between border and text
        line_height = 1.4 * fontsize  # matches boxes text() inter-line spacing
        panel_width = 150     # mm — wide enough for longest expected param lines

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
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        header_lines = [f"{self.__class__.__name__}  {timestamp}", ""]
        param_lines = [f"{dest}: {val}" for dest, val in params]
        lines = header_lines + param_lines

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

    def render(self):
        """Generate all panels and walls that make up the hexagon box.

        Handles outside vs inside measurement modes and all supported
        top/bottom style variants.
        """
        r, h, n, isTrapezoid = self.radius, self.h, self.n, self.trapezoid

        if self.outside:
            # Convert outside measurements to inside by subtracting material thickness.
            r -= self.thickness / math.cos(math.radians(360 / (2 * n)))
            if self.top == "none":
                h = self.adjustSize(h, False)
            elif "lid" in self.top and self.top != "angled lid":
                h = self.adjustSize(h) - self.thickness
            else:
                h = self.adjustSize(h)

        t = self.thickness

        # Top and bottom radii are always equal, so a single regularPolygon call
        # suffices.  The taper scaffold (r0/r1, a, beta, d_top/d_bottom) from the
        # original starter-template geometry reduces to zero-taper constants and
        # has been removed.
        r, _, side = self.regularPolygon(n, radius=r)

        # Capture the original side length before shrinking — used for alignment-hole
        # position ratios and for computing the long trapezoid back-wall width.
        side_orig = side

        # Subtract two thicknesses from each side so finger joints fit flush.
        side -= 2 * t

        # Side-wall height equals box height (no taper — l simplifies from
        # sqrt((r0−r1)²+h²) to h when r0=r1).
        l = h
        # Dihedral correction angle between adjacent side panels (taper angle = 0).
        phi = 180 - 2 * math.degrees(math.asin(math.cos(math.pi / n)))

        # Register custom finger-joint edge objects.  Each call mutates self.edges
        # as a side effect; the returned settings object is not used afterwards,
        # so it is assigned to _ to make the write-only pattern explicit.
        _ = copy.deepcopy(self.edges["f"].settings)
        _.setValues(self.thickness, angle=phi)
        _.edgeObjects(self, chars="gGH")

        # Top and bottom panels are parallel (no taper), so both use angle=90.
        _ = copy.deepcopy(self.edges["f"].settings)
        _.setValues(self.thickness, angle=90)
        _.edgeObjects(self, chars="yYH")

        _ = copy.deepcopy(self.edges["f"].settings)
        _.setValues(self.thickness, angle=90)
        _.edgeObjects(self, chars="zZH")

        def drawTop(r, top_type, joint_type):
            """Render one face (top or bottom) as the appropriate panel style.

            Top is always 'closed'; bottom is 'spoke' or 'closed'.  In
            trapezoid mode the hexagonal panel is replaced by the equivalent
            trapezoidal panel produced by drawTrapezoidWall.

            When bottom='spoke' the support walls have finger joints ('fefe')
            on both ends, so the closed top panel must carry matching support-
            hole slots.  The support-hole callback is placed at index 1 (the
            edge-0-start / V0 position) so that drawSupportHoles can translate
            from V0 to the hex centre with its standard moveTo(r/2, H, angle)
            formula — the same position used by the spoke bottom panel.

            @param r          - Inner corner radius of this face.
            @param top_type   - 'closed' or 'spoke'.
            @param joint_type - Two-character edge string, e.g. 'yY' or 'zZ'.
            """
            # Build the support-hole callback for closed panels.  Fires at the
            # V0-start slot (index 1); index 0 is None so the kites/centre slot
            # is skipped.  Active whenever self.supports is True, regardless of
            # whether the opposite face is "spoke" or "closed".
            if self.supports:
                support_cb = [None, lambda: self.drawSupportHoles(r=r, isTrapezoid=isTrapezoid)]
            else:
                support_cb = None

            if isTrapezoid:
                if top_type == "spoke":
                    # Build spoke callbacks; only append drawSupportHoles when
                    # supports are enabled so the slot geometry matches the walls.
                    spoke_cbs = [lambda: self.drawKites(r=r, joint_type=joint_type, isTrapezoid=True)]
                    if self.supports:
                        spoke_cbs.append(lambda: self.drawSupportHoles(r=r, isTrapezoid=True))
                    self.drawTrapezoidWall(
                        r=r, edges_char=joint_type[1], move="right",
                        callback=spoke_cbs)
                else:  # "closed"
                    self.drawTrapezoidWall(r=r, edges_char=joint_type[1], move="right",
                                           callback=support_cb)
            else:
                if top_type == "spoke":
                    spoke_cbs = [lambda: self.drawKites(r=r, joint_type=joint_type, isTrapezoid=False)]
                    if self.supports:
                        spoke_cbs.append(lambda: self.drawSupportHoles(r=r))
                    self.regularPolygonWall(
                        corners=n, r=r, edges=joint_type[1], move="right",
                        callback=spoke_cbs)
                else:  # "closed"
                    self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right",
                                            callback=support_cb)

        with self.saved_context():
            # Draw bottom panel first, then top (order affects SVG layout).
            drawTop(r, self.bottom, "yY")
            drawTop(r, self.top, "zZ")
            # Support walls must be placed inside this saved_context block so
            # they land after the face panels in the layout stream.  Outside the
            # block the cursor reverts to its pre-block position, causing the
            # walls to overlap whatever is drawn next.
            if self.supports:
                self.drawSupports(isTrapezoid=isTrapezoid)

        # Invisible up-only move reserves vertical space for the panels above.
        # In trapezoid mode the panel is half-height, so use the trapezoid wall
        # for space reservation to avoid excess vertical whitespace in the layout.
        if isTrapezoid:
            self.drawTrapezoidWall(r=r, edges_char='F', move="up only")
        else:
            self.regularPolygonWall(corners=n, r=r, edges='F', move="up only")

        fingers_top = self.top in ("closed", "hole", "angled hole",
                                   "round lid", "angled lid2", "bayonet mount")
        fingers_bottom = self.bottom in ("closed", "hole", "angled hole",
                                         "round lid", "angled lid2", "spoke")

        t_ = self.edges["G"].startwidth()
        bottom_edge = ('y' if fingers_bottom else 'e')
        top_edge = ('z' if fingers_top else 'e')
        # No taper: d_top = d_bottom = 0, so l is unchanged after this point.

        # Alignment-hole callback shared by all hex side panels.
        # moveTo(0, -t) compensates for the 2*t trimming of side: the natural
        # callback origin sits t to the left of where it was before trimming,
        # so shifting t rightward (−y in local coords) restores centre alignment
        # when new and old panels are stacked and centred.
        def draw_aligned_holes():
            self.moveTo(0, -self.thickness)
            self.drawAlignmentHoles(side_orig, l, "A")

        # Alignment-hole callback for the trapezoid long back wall.
        # The long wall spans two hex-side-lengths, so its pre-shrink width is
        # 2*side_orig.  Passing that as the `s` parameter scales all fractional
        # hole positions proportionally to the wider panel.
        def draw_aligned_holes_long():
            self.moveTo(0, -self.thickness)
            self.drawAlignmentHolesLong(2 * side_orig, l, "A")

        # Standard stepped-tab side-panel border.  With no taper, d_top = d_bottom = 0
        # and angle a = 0, so the border reduces to right-angle turns and the two
        # inset steps are zero-length.  The shape is still defined explicitly (rather
        # than a plain rectangle) so that the E-edge finger-joint tabs are placed
        # correctly by polygonWall.
        borders0 = [side, 90,
                    0, -90, t_, 90, l, 90, t_, -90, 0,
                    90, side, 90,
                    0, -90, t_, 90, l, 90, t_, -90, 0, 90]
        e0 = bottom_edge + 'E' + top_edge + 'E'

        if isTrapezoid:
            # Trapezoid side walls: 4 panels instead of 6.
            #
            #   1 × long back wall  — spans the join edge (length 2r)
            #   3 × standard walls  — one each for right slant, short front, left slant
            #

            # Long back-wall border.  Width is 2*side_orig − 2*t because the panel
            # spans two hex-side-lengths with finger-joint notches only at the two
            # outer ends (no junction at the midpoint in a trapezoid box).
            side_long = 2 * side_orig - 2 * t
            borders_long = [side_long, 90,
                            0, -90, t_, 90, l, 90, t_, -90, 0,
                            90, side_long, 90,
                            0, -90, t_, 90, l, 90, t_, -90, 0, 90]

            # Long back wall (1 panel).  callback[1] fires at the first stepped-tab
            # segment where the alignment holes are drawn; callback[0] is None
            # (the former drawMarkers2 stub has been removed).
            self.polygonWall(borders_long, edge=e0, correct_corners=False, move="right",
                             callback=[None, draw_aligned_holes_long])

            # Three standard-width walls (right slant, front short, left slant).
            for _ in range(3):
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right",
                                 callback=[None, draw_aligned_holes])

        else:
            # Even number of sides (n=6): all panels use the stepped-tab profile.
            for _ in range(n):
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right",
                                 callback=[None, draw_aligned_holes])

        # Append a reference panel that engraves all parameter values onto a
        # flat piece of stock — useful for reproducing or identifying a cut job.
        self.drawReferencePanel(move="right")
