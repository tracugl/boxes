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
from collections import namedtuple

import rectpack
from rectpack import newPacker, PackingBin

from boxes import Boxes, edges, boolarg
from boxes.generators.bayonetbox import BayonetBox
from boxes.Color import *

# Lightweight record bundling a single cuttable component for sheet packing.
# label   — unique string identifier (e.g. 'hex_bottom', 'support_3')
# kind    — component category: 'hex_panel' | 'support' | 'side' | 'reference'
# w, h    — natural bounding-box dimensions in mm, *before* the framework adds
#           its own spacing (i.e. the values passed to self.move() by the draw
#           method, which adds self.spacing internally).
# draw_fn — zero-argument callable that draws this component using move=None
#           (no cursor advance); the caller is responsible for ctx.translate.
_ComponentSpec = namedtuple('_ComponentSpec', ['label', 'kind', 'w', 'h', 'draw_fn'])


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

        # ── Sheet-layout / nesting arguments ─────────────────────────────────
        # When sheet_width and sheet_height are both non-zero the generator
        # switches from its default left-to-right row layout to a two-pass
        # 2D bin-packing layout: first measure every component's bounding box,
        # then use rectpack to pack them onto sheets of the specified size, and
        # finally render each component at its packed position.  When either
        # dimension is 0 the legacy unbounded layout is used unchanged.

        self.argparser.add_argument(
            "--sheet_width", action="store", type=float, default=0.0,
            help="Width of one MDF sheet in mm. "
                 "When non-zero (with sheet_height), components are packed onto "
                 "sheets of this size. 0 = legacy unbounded layout.")
        self.argparser.add_argument(
            "--sheet_height", action="store", type=float, default=0.0,
            help="Height of one MDF sheet in mm. Required with sheet_width.")
        self.argparser.add_argument(
            "--sheet_margin", action="store", type=float, default=2.0,
            help="Minimum clearance added around every component before packing (mm).")
        self.argparser.add_argument(
            "--nest_algo", action="store", type=str, default="SkylineBlWm",
            help="rectpack 2D bin-packing algorithm name (see svgmerge.py "
                 "PACK_ALGO_CHOICES for valid values). Default: SkylineBlWm.")
        self.argparser.add_argument(
            "--nest_rotation", action="store", type=boolarg, default=False,
            help="Allow 90-degree rotation of components during packing. "
                 "Can improve sheet utilisation but rotation rendering is not "
                 "yet fully implemented; leave False for now.")
        self.argparser.add_argument(
            "--nest_in_waste", action="store", type=boolarg, default=True,
            help="Attempt to nest support walls inside kite cavities on hex "
                 "panel sheets. Only applies when bottom=spoke.")

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

    # ── Sheet-layout helpers ──────────────────────────────────────────────────

    def _measure_component(self, draw_call):
        """Measure one component's bounding box without drawing it.

        Temporarily replaces self.move with an intercepting wrapper that
        captures the (width, height) values on the first ``before=True`` call —
        these are the component's natural dimensions before the framework adds
        its own spacing internally.  The draw_call must use ``move='right only'``
        so that no ctx.save() is pushed and the canvas state is not disturbed.

        @param draw_call - Zero-argument callable that invokes one drawing
                           method with ``move='right only'``.
        @returns (w, h) tuple in mm — component natural dimensions (pre-spacing).
        """
        captured = {}
        _orig = self.move

        def _intercept(x, y, where, before=False, label=""):
            # Capture only the first before=True call — that belongs to the
            # top-level component.  Any nested calls (e.g. from callbacks that
            # invoke sub-components) are ignored via the 'not captured' guard.
            if before and not captured:
                captured['w'] = x
                captured['h'] = y
            return _orig(x, y, where, before=before, label=label)

        self.move = _intercept
        try:
            draw_call()
        finally:
            # Always restore the original method even if draw_call raises.
            self.move = _orig

        return captured.get('w', 0.0), captured.get('h', 0.0)

    def _kite_inscribed_rects(self, r):
        """Return the axis-aligned bounding box of each kite cavity.

        Replicates the kite geometry from drawKites() analytically using the
        same ``r``, ``edge_width``, and ``spoke_width`` parameters.  The
        returned positions are expressed in the hex-centre coordinate frame
        (origin at the centre of the hexagon), which is the same frame used
        by the kite vertex coordinates in drawKites().

        For each kite the method returns its centroid and its axis-aligned
        bounding-box dimensions.  A component centred at the kite centroid
        and smaller than ``bb_w * SAFETY × bb_h * SAFETY`` (where SAFETY ≈
        0.65 for diamond-shaped kites) will fit inside the kite polygon.

        Returns an empty list when the frame or spoke geometry degenerates
        (same conditions that cause drawKites to fall back to a solid panel).

        @param r - Inner corner radius of the hexagon bottom panel (mm).
        @returns List of (cx, cy, bb_w, bb_h) tuples — one per kite.
        """
        sqrt3 = math.sqrt(3)
        cos30 = sqrt3 / 2.0

        A_outer = r * cos30
        A_inner = A_outer - self.edge_width
        if A_inner <= 0:
            return []

        R_inner = A_inner / cos30
        s = (A_inner / sqrt3) - (self.spoke_width / 2.0)
        if s <= 0:
            return []

        # Master kite vertices — apex pointing upward (+y), before 30° rotation.
        # These match the P1..P4 definitions in drawKites() exactly.
        P1 = (0.0,             R_inner)
        P2 = (s * sqrt3 / 2.0, R_inner - s / 2.0)
        P3 = (0.0,             R_inner - 2.0 * s)
        P4 = (-s * sqrt3 / 2.0, R_inner - s / 2.0)

        def _rotate(pts, deg):
            """Rotate a list of (x, y) points CCW around the origin."""
            ang = math.radians(deg)
            ca, sa = math.cos(ang), math.sin(ang)
            return [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]

        # Apply the same 30° master alignment rotation used in drawKites.
        kite_master = _rotate([P1, P2, P3, P4], 30)

        result = []
        for i in range(6):
            verts = _rotate(kite_master, 60 * i)
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            bb_w = max_x - min_x
            bb_h = max_y - min_y
            result.append((cx, cy, bb_w, bb_h))

        return result

    # Safety factor applied to kite axis-aligned bounding boxes before
    # checking component fit.  Kites are diamond-shaped, so their actual
    # inscribed axis-aligned rectangle is roughly 65 % of the bounding box
    # in each dimension.
    _KITE_SAFETY = 0.65

    def _pack_and_render(self, cut_components, ref_fn, ref_w, ref_h, r, isTrapezoid):
        """Pack cut components onto MDF sheets and render them at packed positions.

        Two-phase packing strategy
        ──────────────────────────
        Phase A  — Pack hex panels and side walls (all non-support components)
                   using rectpack's SkylineBlWm algorithm (or the algorithm
                   chosen via --nest_algo).  Supports are excluded from this
                   phase so that kite cavities can be exploited first.

        Phase B  — When ``--nest_in_waste`` is enabled and ``bottom=spoke``,
                   compute the axis-aligned bounding box of every kite cavity
                   from the phase-A hex-panel placements.  Greedily assign
                   support walls to kite slots (first fit, no rotation).
                   Remaining supports (those that did not fit any kite) are
                   packed by a second rectpack pass that may open additional
                   sheet bins appended after the phase-A sheets.

        Sheet layout
        ────────────
        All cut-sheet zones are placed side-by-side horizontally in the single
        SVG canvas, each preceded by a Color.OUTER_CUT border rectangle at the
        exact sheet dimensions.  An info sheet (Color.ETCHING border + "DO NOT
        CUT" label) follows the cut sheets and contains the reference panel.

        Rendering
        ─────────
        Each component is drawn inside a saved_context() block: the context is
        translated to the component's packed position, then the component's
        draw_fn (which uses ``move=None``) is called.  ``move=None`` causes the
        framework's move() to call ctx.save() / moveTo(spacing/2, spacing/2) /
        ctx.restore() as usual, but without advancing the cursor — position
        control is fully delegated to the outer ctx.translate().

        @param cut_components - List of _ComponentSpec namedtuples (label, kind,
                                w, h, draw_fn) for all cuttable parts.
        @param ref_fn         - Zero-argument callable that draws the reference
                                panel with move=None.
        @param ref_w, ref_h   - Measured natural dimensions of the reference
                                panel (mm, pre-spacing).
        @param r              - Inner hex circumradius (mm), used to compute
                                kite positions when nest_in_waste is True.
        @param isTrapezoid    - Whether the box is in half-hexagon mode.
        """
        import math as _math   # local alias avoids shadowing outer scope math

        sw        = int(self.sheet_width)
        sh        = int(self.sheet_height)
        margin    = self.sheet_margin
        sp        = self.spacing
        GAP       = 20          # mm gap between adjacent sheet zones in the SVG
        # Fraction of kite bounding-box used as the available slot for nesting.
        KITE_SF   = self._KITE_SAFETY

        # ── Resolve packing algorithm ────────────────────────────────────────
        try:
            pack_algo = getattr(rectpack, self.nest_algo)
        except AttributeError:
            raise ValueError(
                f"Unknown nest_algo '{self.nest_algo}'. "
                "Check PACK_ALGO_CHOICES in boxes/svgmerge.py for valid names."
            )

        def _make_packer():
            """Return a fresh newPacker configured with the user's algorithm."""
            return newPacker(
                rotation=False,   # rotation rendering not yet fully supported
                pack_algo=pack_algo,
                bin_algo=PackingBin.Global,
            )

        def _packed_rect_size(w, h):
            """Round component dims up to integers including spacing and margin."""
            return (
                int(_math.ceil(w + sp + 2 * margin)),
                int(_math.ceil(h + sp + 2 * margin)),
            )

        # ── Separate supports from primary components ────────────────────────
        # Supports are held back so they can be tried in kite cavities first
        # (Phase B).  All other components go into the primary rectpack run
        # (Phase A).
        primary   = [c for c in cut_components if c.kind != 'support']
        supports  = [c for c in cut_components if c.kind == 'support']

        # Sort primary components largest-area-first so the packer has the
        # best chance of placing large hex panels before filling gaps.
        primary = sorted(primary, key=lambda c: -(c.w * c.h))

        # ── Phase A: pack hex panels + side walls ────────────────────────────
        packer_a = _make_packer()
        packer_a.add_bin(sw, sh, float("inf"))

        for idx, comp in enumerate(primary):
            pw, ph = _packed_rect_size(comp.w, comp.h)
            if pw > sw or ph > sh:
                raise ValueError(
                    f"Component '{comp.label}' ({pw}×{ph} mm) is larger than "
                    f"the sheet ({sw}×{sh} mm). Increase sheet dimensions or "
                    f"reduce the box radius."
                )
            packer_a.add_rect(pw, ph, idx)

        packer_a.pack()

        # Build placement dict: primary-list-index → (bin_id, rx, ry)
        placements_a = {}
        for bid, abin in enumerate(packer_a):
            for rect in abin:
                placements_a[rect.rid] = (bid, rect.x, rect.y)

        # Verify all primary components were placed.
        for idx, comp in enumerate(primary):
            if idx not in placements_a:
                raise ValueError(
                    f"Could not fit component '{comp.label}' onto any sheet. "
                    "Check that its dimensions fit within the sheet size."
                )

        n_phase_a_bins = max(bid for bid, _, _ in placements_a.values()) + 1

        # ── Phase B: kite-cavity nesting for support walls ───────────────────
        # Compute the absolute position of every kite centroid on every sheet
        # from the Phase-A hex-panel placements.
        kite_nested_placements = {}   # support list index → (bin_id, abs_x, abs_y)
        remaining_supports     = list(range(len(supports)))

        do_kite_nesting = (
            self.nest_in_waste
            and self.bottom == "spoke"
            and not isTrapezoid   # trapezoid has only 2 kites; skip for simplicity
        )

        if do_kite_nesting and supports:
            kite_info = self._kite_inscribed_rects(r)

            # Build a list of available kite slots from all Phase-A hex panels.
            # Each slot carries the bin it belongs to and its absolute canvas
            # position (bin-relative x/y + component translate offset).
            # 'available' is a mutable list; we pop slots as they are consumed.
            available_slots = []
            for idx, comp in enumerate(primary):
                if comp.kind != 'hex_panel':
                    continue
                bid, rx, ry = placements_a[idx]
                # The framework's move(before=True, where=None) adds spacing/2
                # then draws the component centred in its bounding box.
                # Hex centre in canvas coords (approximate — symmetric polygon):
                hex_cx = rx + sp / 2.0 + comp.w / 2.0
                hex_cy = ry + sp / 2.0 + comp.h / 2.0
                for kite_cx, kite_cy, bb_w, bb_h in kite_info:
                    available_slots.append({
                        'bid':     bid,
                        'abs_x':   hex_cx + kite_cx,   # kite centroid, canvas
                        'abs_y':   hex_cy + kite_cy,
                        'slot_w':  bb_w * KITE_SF,     # conservative inscribed
                        'slot_h':  bb_h * KITE_SF,
                    })

            # Greedy first-fit: for each support wall, try every available slot.
            unassigned = []
            for s_idx, comp in enumerate(supports):
                # Support wall natural size including framework spacing.
                needed_w = comp.w + sp
                needed_h = comp.h + sp
                placed = False
                for slot_i, slot in enumerate(available_slots):
                    fits = (
                        needed_w <= slot['slot_w']
                        and needed_h <= slot['slot_h']
                    )
                    if fits:
                        # Centre the support wall at the kite centroid.
                        draw_x = slot['abs_x'] - (comp.w + sp) / 2.0
                        draw_y = slot['abs_y'] - (comp.h + sp) / 2.0
                        kite_nested_placements[s_idx] = (slot['bid'], draw_x, draw_y)
                        available_slots.pop(slot_i)
                        placed = True
                        break
                if not placed:
                    unassigned.append(s_idx)
            remaining_supports = unassigned

        # ── Phase C: pack remaining support walls ────────────────────────────
        placements_c = {}    # support list index → (bin_id_offset_adjusted, rx, ry)

        if remaining_supports:
            supports_to_pack = [supports[i] for i in remaining_supports]
            packer_c = _make_packer()
            packer_c.add_bin(sw, sh, float("inf"))

            for local_idx, comp in enumerate(supports_to_pack):
                pw, ph = _packed_rect_size(comp.w, comp.h)
                if pw > sw or ph > sh:
                    raise ValueError(
                        f"Support wall ({pw}×{ph} mm) is larger than the sheet "
                        f"({sw}×{sh} mm)."
                    )
                packer_c.add_rect(pw, ph, local_idx)

            packer_c.pack()

            for bid, abin in enumerate(packer_c):
                for rect in abin:
                    orig_s_idx = remaining_supports[rect.rid]
                    # Store the *local* bin ID (0-based within Phase C).  The
                    # Phase-A offset is added during rendering so that this dict
                    # can be used directly for n_total_cut_bins computation below.
                    placements_c[orig_s_idx] = (bid, rect.x, rect.y)

            for local_idx, comp in enumerate(supports_to_pack):
                orig_s_idx = remaining_supports[local_idx]
                if orig_s_idx not in placements_c:
                    raise ValueError(
                        f"Could not fit support wall '{comp.label}' onto any sheet."
                    )

        # n_total_cut_bins = Phase-A bins + Phase-C bins.
        # placements_c holds *local* bin IDs (0-based within Phase C), so
        # adding 1 to the max gives the Phase-C bin count directly.
        n_total_cut_bins = n_phase_a_bins + (
            max((bid for bid, _, _ in placements_c.values()), default=-1) + 1
        )

        # ── Rendering ────────────────────────────────────────────────────────
        # All rendering happens in a single saved_context so that the cursor
        # returns to its pre-render position after we finish.  Components are
        # positioned by ctx.translate() before each draw_fn() call.
        with self.saved_context():
            # Shift to the drawing area origin (same offset that move() would
            # apply to the first component in the normal layout path).
            self.moveTo(sp / 2.0, sp / 2.0)

            # ── Draw cut-sheet border rectangles ─────────────────────────────
            # Border drawn first (behind components) at each bin's x-offset.
            # Color.OUTER_CUT is the standard cut-line colour used everywhere.
            self.set_source_color(Color.OUTER_CUT)
            for bin_id in range(n_total_cut_bins):
                x_off = bin_id * (sw + GAP)
                with self.saved_context():
                    self.moveTo(x_off, 0)
                    self.ctx.rectangle(0, 0, sw, sh)
                    self.ctx.stroke()

            # ── Draw primary (non-support) components ─────────────────────────
            for p_idx, comp in enumerate(primary):
                bid, rx, ry = placements_a[p_idx]
                x_off = bid * (sw + GAP)
                with self.saved_context():
                    self.moveTo(x_off + rx, ry)
                    comp.draw_fn()

            # ── Draw kite-nested support walls ───────────────────────────────
            for s_idx, comp in enumerate(supports):
                if s_idx not in kite_nested_placements:
                    continue
                bid, abs_x, abs_y = kite_nested_placements[s_idx]
                x_off = bid * (sw + GAP)
                with self.saved_context():
                    # abs_x/abs_y are already in bin-local coords (not offset).
                    self.moveTo(x_off + abs_x, abs_y)
                    comp.draw_fn()

            # ── Draw remaining (non-kite) support walls ───────────────────────
            for s_idx, comp in enumerate(supports):
                if s_idx not in placements_c:
                    continue
                local_bid, rx, ry = placements_c[s_idx]
                # Phase-C local bin IDs are 0-based within Phase C; add the
                # Phase-A count to get the absolute sheet index.
                bid = n_phase_a_bins + local_bid
                x_off = bid * (sw + GAP)
                with self.saved_context():
                    self.moveTo(x_off + rx, ry)
                    comp.draw_fn()

            # ── Info sheet: border + reference panel + "DO NOT CUT" label ────
            info_x_off = n_total_cut_bins * (sw + GAP)
            # Bounding box of the info sheet content.
            info_w = int(_math.ceil(ref_w + sp + 2 * margin))
            info_h = int(_math.ceil(ref_h + sp + 2 * margin))

            # Etching-colour border signals "not a cut sheet" to laser software.
            self.set_source_color(Color.ETCHING)
            with self.saved_context():
                self.moveTo(info_x_off, 0)
                self.ctx.rectangle(0, 0, info_w, info_h)
                self.ctx.stroke()

            # "DO NOT CUT" label etched at the top-centre of the info sheet.
            self.text(
                "DO NOT CUT — REFERENCE ONLY",
                info_x_off + info_w / 2.0,
                info_h + 4,
                align="middle center",
                fontsize=6,
                color=Color.ETCHING,
            )
            # Flush the text "T" entry from Part.path into Part.pathes so that
            # the subsequent ctx.new_part() call inside ref_fn() → move(before=True)
            # does not create a new Part while the old one still has an open path,
            # which would trigger the assert(not self.path) in Part.transform().
            self.ctx.stroke()

            # Reference panel content drawn at margin offset inside info sheet.
            with self.saved_context():
                self.moveTo(info_x_off + margin, margin)
                ref_fn()

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

        def drawTop(r, top_type, joint_type, move="right"):
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
            @param move       - Layout direction string passed to the underlying
                                wall method.  Use 'right' for the normal layout,
                                'right only' for dry-run measurement, or None
                                when the caller manages position via ctx.translate.
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
                        r=r, edges_char=joint_type[1], move=move,
                        callback=spoke_cbs)
                else:  # "closed"
                    self.drawTrapezoidWall(r=r, edges_char=joint_type[1], move=move,
                                           callback=support_cb)
            else:
                if top_type == "spoke":
                    spoke_cbs = [lambda: self.drawKites(r=r, joint_type=joint_type, isTrapezoid=False)]
                    if self.supports:
                        spoke_cbs.append(lambda: self.drawSupportHoles(r=r))
                    self.regularPolygonWall(
                        corners=n, r=r, edges=joint_type[1], move=move,
                        callback=spoke_cbs)
                else:  # "closed"
                    self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move=move,
                                            callback=support_cb)

        # ── Variables shared by both the original and sheet-layout paths ─────
        # Computed once here so the sheet-layout path can build component
        # closures without duplicating these calculations.

        fingers_top = self.top in ("closed", "hole", "angled hole",
                                   "round lid", "angled lid2", "bayonet mount")
        fingers_bottom = self.bottom in ("closed", "hole", "angled hole",
                                         "round lid", "angled lid2", "spoke")

        t_ = self.edges["G"].startwidth()
        bottom_edge = ('y' if fingers_bottom else 'e')
        top_edge    = ('z' if fingers_top    else 'e')

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

        # Trapezoid-specific: long back wall border (2 hex-side-lengths wide).
        side_long    = 2 * side_orig - 2 * t
        borders_long = [side_long, 90,
                        0, -90, t_, 90, l, 90, t_, -90, 0,
                        90, side_long, 90,
                        0, -90, t_, 90, l, 90, t_, -90, 0, 90]

        # ── Branch: sheet-layout vs. legacy row layout ────────────────────────
        if self.sheet_width > 0 and self.sheet_height > 0:
            # ── SHEET-LAYOUT PATH ────────────────────────────────────────────
            # Collect all cuttable components as _ComponentSpec records by doing
            # a dry-run measurement pass (move='right only') inside a
            # saved_context so the cursor movements are discarded.  Each
            # component also gets a draw_fn closure (move=None) for the actual
            # rendering phase driven by _pack_and_render.
            cut_components = []

            with self.saved_context():
                # ── Hex bottom panel ─────────────────────────────────────────
                w, h = self._measure_component(
                    lambda: drawTop(r, self.bottom, "yY", move="right only"))
                cut_components.append(_ComponentSpec(
                    label='hex_bottom', kind='hex_panel', w=w, h=h,
                    draw_fn=lambda: drawTop(r, self.bottom, "yY", move=None)))

                # ── Hex top panel ────────────────────────────────────────────
                w, h = self._measure_component(
                    lambda: drawTop(r, self.top, "zZ", move="right only"))
                cut_components.append(_ComponentSpec(
                    label='hex_top', kind='hex_panel', w=w, h=h,
                    draw_fn=lambda: drawTop(r, self.top, "zZ", move=None)))

                # ── Support walls (all identical) ────────────────────────────
                if self.supports:
                    h_supp = self.h
                    if self.outside:
                        h_supp = self.adjustSize(h_supp)
                    sl   = self.support_length
                    r1   = (self.h - 2 * self._SPACER) / 2
                    n_supp = 3 if isTrapezoid else 6

                    # Closure for the centre-hole callback — shared by all walls.
                    if r1 > 0:
                        def _draw_hole(sl=sl, h_supp=h_supp, r1=r1):
                            self.hole(sl / 2, h_supp / 2, r1)
                        def _draw_supp(sl=sl, h_supp=h_supp, r1=r1, _dh=_draw_hole):
                            self.rectangularWall(sl, h_supp, "fefe",
                                                 callback=[_dh], move=None)
                        _supp_meas = lambda sl=sl, h_supp=h_supp, r1=r1, _dh=_draw_hole: \
                            self.rectangularWall(sl, h_supp, "fefe",
                                                 callback=[_dh], move="right only")
                    else:
                        def _draw_supp(sl=sl, h_supp=h_supp):
                            self.rectangularWall(sl, h_supp, "fefe", move=None)
                        _supp_meas = lambda sl=sl, h_supp=h_supp: \
                            self.rectangularWall(sl, h_supp, "fefe", move="right only")

                    sw_w, sw_h = self._measure_component(_supp_meas)
                    for i in range(n_supp):
                        cut_components.append(_ComponentSpec(
                            label=f'support_{i}', kind='support',
                            w=sw_w, h=sw_h, draw_fn=_draw_supp))

                # ── Side walls ───────────────────────────────────────────────
                if isTrapezoid:
                    # 1 long back wall + 3 standard walls.
                    lw_w, lw_h = self._measure_component(
                        lambda: self.polygonWall(
                            borders_long, edge=e0, correct_corners=False,
                            move="right only",
                            callback=[None, draw_aligned_holes_long]))
                    cut_components.append(_ComponentSpec(
                        label='side_long', kind='side', w=lw_w, h=lw_h,
                        draw_fn=lambda: self.polygonWall(
                            borders_long, edge=e0, correct_corners=False,
                            move=None,
                            callback=[None, draw_aligned_holes_long])))

                    std_w, std_h = self._measure_component(
                        lambda: self.polygonWall(
                            borders0, edge=e0, correct_corners=False,
                            move="right only",
                            callback=[None, draw_aligned_holes]))
                    for i in range(3):
                        cut_components.append(_ComponentSpec(
                            label=f'side_{i}', kind='side', w=std_w, h=std_h,
                            draw_fn=lambda: self.polygonWall(
                                borders0, edge=e0, correct_corners=False,
                                move=None,
                                callback=[None, draw_aligned_holes])))
                else:
                    # 6 identical standard side walls.
                    std_w, std_h = self._measure_component(
                        lambda: self.polygonWall(
                            borders0, edge=e0, correct_corners=False,
                            move="right only",
                            callback=[None, draw_aligned_holes]))
                    for i in range(n):
                        cut_components.append(_ComponentSpec(
                            label=f'side_{i}', kind='side', w=std_w, h=std_h,
                            draw_fn=lambda: self.polygonWall(
                                borders0, edge=e0, correct_corners=False,
                                move=None,
                                callback=[None, draw_aligned_holes])))

            # Measure reference panel outside the discarded context so its
            # draw_fn fires from a stable cursor position inside _pack_and_render.
            ref_w, ref_h = self._measure_component(
                lambda: self.drawReferencePanel(move="right only"))
            ref_fn = lambda: self.drawReferencePanel(move=None)

            # Hand off to the packer — all drawing happens inside _pack_and_render.
            self._pack_and_render(cut_components, ref_fn, ref_w, ref_h,
                                  r, isTrapezoid)
            return  # skip the legacy layout path below

        # ── LEGACY ROW LAYOUT PATH (original behaviour, unchanged) ───────────
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

        if isTrapezoid:
            # Trapezoid side walls: 4 panels instead of 6.
            #
            #   1 × long back wall  — spans the join edge (length 2r)
            #   3 × standard walls  — one each for right slant, short front, left slant
            #

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
