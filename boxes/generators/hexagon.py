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


### Helpers

def dist(dx, dy):
    """Return the Euclidean distance for a 2-D offset vector.

    @param dx - Horizontal component of the offset.
    @param dy - Vertical component of the offset.
    @returns  Float distance, always non-negative.
    """
    return (dx * dx + dy * dy) ** 0.5


class HexagonBox(BayonetBox):
    """Box with a regular hexagon or half hexagon as the base. """

    ui_group = "Box"

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

        # Mirror the spacer and hole-radius formula used by drawAlignmentHoles
        # so that the support hole is consistent with the rest of the geometry.
        # Crucially, drawAlignmentHoles uses self.h (the raw box height), not the
        # adjustSize()-shrunk value, so we do the same here to keep the diameters
        # identical regardless of whether --outside is set.
        spacer = 15  # minimum clearance from panel edge to hole edge, in mm
        r1 = (self.h - spacer - spacer) / 2

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

    def drawMarkers2(self, s, l, text):
        """Placeholder for optional marker geometry on side panels.

        Currently a stub; retained so the callback signature stays stable and
        individual markers can be re-enabled by uncommenting the relevant lines.

        @param s    - Panel height (the pre-shrink side0 value), used for y-scaling.
        @param l    - Panel width (slant length), used for x-scaling.
        @param text - Label string (unused in the active code path).
        """
        # Unused reference variables kept for potential future use.
        h = self.h
        r = self.radius

        # self.hole(l-10, s-10, 12)
        # self.rectangularHole(r/2, h/2, 5, 5, r=0, center_x=True, center_y=True)

    def drawAlignmentHoles(self, s, l, text):
        """Cut and etch alignment features into a side panel for stacking hexagons.

        The coordinate system inside a polygonWall callback has the slant length
        (l) along the x-axis and side0 (s) along the y-axis.  All hole positions
        are derived from those two dimensions so they scale correctly with box
        size.

        The caller should pass the **pre-shrink** side0 value (side0_orig) paired
        with a moveTo(0, -t) shift in the wrapper.  Together, this produces a
        uniform t-inward offset on every hole so that new panels (trimmed by 2*t)
        align centre-to-centre with old panels when the two are stacked and centred.

        @param s    - Pre-shrink panel height (original side0, before subtracting 2*t).
        @param l    - Panel width (slant length l from render()).
        @param text - Unused; kept for API compatibility.
        """
        h = self.h
        spacer = 15  # minimum clearance from panel edges, in mm

        # Three large round through-holes along the vertical centre line.
        # r1 is sized to leave 'spacer' clearance above and below.
        r1 = (h - spacer - spacer) / 2
        self.hole(l / 2, s / 2,     r1)  # vertical centre
        self.hole(l / 2, s / 5,     r1)  # lower fifth
        self.hole(l / 2, 4 * s / 5, r1)  # upper fifth

        # Medium round holes used as alignment-pin receivers, mirrored left/right.
        r2 = 12.5
        self.hole(l - r2 / 2 - spacer, 7 * s / 20,  r2)  # right, lower band
        self.hole(l - r2 / 2 - spacer, 13 * s / 20, r2)  # right, upper band
        self.hole(spacer + r2 / 2,     7 * s / 20,  r2)  # left,  lower band
        self.hole(spacer + r2 / 2,     13 * s / 20, r2)  # left,  upper band

        # Small registration dots flanking each medium hole (r3 = 3 mm pilot holes).
        r3 = 3
        # Four dots around the lower-band medium holes.
        self.hole(l - spacer, 7 * s / 20 + 2 * spacer, r3)
        self.hole(l - spacer, 7 * s / 20 - 2 * spacer, r3)
        self.hole(spacer,     7 * s / 20 + 2 * spacer, r3)
        self.hole(spacer,     7 * s / 20 - 2 * spacer, r3)

        # Four dots around the upper-band medium holes.
        self.hole(l - spacer, 13 * s / 20 + 2 * spacer, r3)
        self.hole(l - spacer, 13 * s / 20 - 2 * spacer, r3)
        self.hole(spacer,     13 * s / 20 + 2 * spacer, r3)
        self.hole(spacer,     13 * s / 20 - 2 * spacer, r3)

        # Corner registration clusters (top-right, top-left, bottom-right, bottom-left).
        self.hole(l - spacer,     s - spacer,     r3)
        self.hole(l - spacer,     s - 2 * spacer, r3)
        self.hole(l - 2 * spacer, s - spacer,     r3)

        self.hole(l - spacer, s - 3 * spacer, r3)
        self.hole(l / 2,      s - 3 * spacer, r2)  # top-centre medium hole
        self.hole(l - spacer, 3 * spacer,     r3)
        self.hole(l / 2,      3 * spacer,     r2)  # bottom-centre medium hole

        self.hole(spacer,         s - 3 * spacer, r3)
        self.hole(spacer,         3 * spacer,     r3)

        self.hole(spacer,         s - spacer,     r3)
        self.hole(spacer,         s - 2 * spacer, r3)
        self.hole(2 * spacer,     s - spacer,     r3)

        self.hole(l - spacer,     spacer,         r3)
        self.hole(l - spacer,     2 * spacer,     r3)
        self.hole(l - 2 * spacer, spacer,         r3)

        self.hole(spacer,         spacer,         r3)
        self.hole(spacer,         2 * spacer,     r3)
        self.hole(2 * spacer,     spacer,         r3)

    def drawAlignmentHolesLong(self, s, l, text):
        """Cut and etch alignment features into the trapezoid long back wall.

        The long back wall spans two hex-side-lengths (s = 2*side0_orig).
        Hole positions are derived by applying the standard wall's fractional
        positions (s/5, 7s/20, s/2, 13s/20, 4s/5) from **both ends**, using
        s_half = s/2 as the reference length so positions line up exactly with
        the corresponding holes on the adjacent standard walls.

        Pattern along the s-axis (bottom → top):
            group-of-8
            BIG(s/5)  G6(7s/20)  BIG(s/2)  G6(13s/20)  BIG(4s/5)
            BIG(centre = s/2 of the long wall)
            BIG(s - 4s/5)  G6(s - 13s/20)  BIG(s - s/2)  G6(s - 7s/20)  BIG(s - s/5)
            group-of-8

        The three consecutive BIG holes in the middle (4s/5, s/2, and 6s/5 of
        s_half) are the expected "transition zone" where the two mirrored halves
        meet with no G6 between them.

        The corner group-of-8 clusters are copied verbatim from drawAlignmentHoles
        and use fixed spacer offsets, so they sit the same physical distance from
        each edge regardless of how wide the panel is.

        @param s    - Pre-shrink panel height (2*side0_orig for the long wall).
        @param l    - Panel width (slant length l from render()).
        @param text - Unused; kept for API compatibility.
        """
        h = self.h
        spacer = 15  # minimum clearance from panel edges, in mm

        r1 = (h - spacer - spacer) / 2
        r2 = 12.5
        r3 = 3

        # s_half is one standard-wall side length.  Applying the standard wall's
        # fractional positions to s_half (rather than s) makes every hole on the
        # long wall land at the same absolute distance from its nearest edge as the
        # corresponding hole on a standard wall — so they line up when panels are
        # stacked or compared side by side.
        s_half = s / 2

        # Seven large through-holes along the vertical centre line (x = l/2).
        # Outer six mirror the standard wall's three positions from each end;
        # the seventh sits at the true centre of the long wall (s/2).
        for frac in (1/5, 1/2, 4/5):
            self.hole(l / 2, frac * s_half,     r1)  # bottom half
            self.hole(l / 2, s - frac * s_half, r1)  # top half (mirrored)
        self.hole(l / 2, s / 2, r1)  # centre

        # Four groups-of-6 (2 medium + 4 small dots), mirrored from both ends.
        # Fractions 7/20 and 13/20 match the standard wall's G6 positions exactly.
        for frac in (7/20, 13/20):
            for y in (frac * s_half, s - frac * s_half):
                # Medium alignment-pin receivers, mirrored left/right.
                self.hole(l - r2 / 2 - spacer, y, r2)  # right medium
                self.hole(spacer + r2 / 2,     y, r2)  # left medium
                # Small registration dots flanking each medium hole.
                self.hole(l - spacer, y + 2 * spacer, r3)
                self.hole(l - spacer, y - 2 * spacer, r3)
                self.hole(spacer,     y + 2 * spacer, r3)
                self.hole(spacer,     y - 2 * spacer, r3)

        # Corner registration clusters — identical to drawAlignmentHoles.
        # These are the "group-of-8": 8 small holes per end (4 per corner, forming
        # an L-shape), each pair of corners surrounding one central medium hole.
        # All positions use fixed spacer offsets so the clusters sit the same
        # physical distance from the panel edges regardless of panel width.
        self.hole(l - spacer,     s - spacer,     r3)
        self.hole(l - spacer,     s - 2 * spacer, r3)
        self.hole(l - 2 * spacer, s - spacer,     r3)

        self.hole(l - spacer, s - 3 * spacer, r3)
        self.hole(l / 2,      s - 3 * spacer, r2)  # top-centre medium hole
        self.hole(l - spacer, 3 * spacer,     r3)
        self.hole(l / 2,      3 * spacer,     r2)  # bottom-centre medium hole

        self.hole(spacer,         s - 3 * spacer, r3)
        self.hole(spacer,         3 * spacer,     r3)

        self.hole(spacer,         s - spacer,     r3)
        self.hole(spacer,         s - 2 * spacer, r3)
        self.hole(2 * spacer,     s - spacer,     r3)

        self.hole(l - spacer,     spacer,         r3)
        self.hole(l - spacer,     2 * spacer,     r3)
        self.hole(l - 2 * spacer, spacer,         r3)

        self.hole(spacer,         spacer,         r3)
        self.hole(spacer,         2 * spacer,     r3)
        self.hole(2 * spacer,     spacer,         r3)

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
        r0, r1, h, n, isTrapezoid = self.radius, self.radius, self.h, self.n, self.trapezoid

        if self.outside:
            # Convert outside measurements to inside by subtracting material thickness.
            r0 = r0 - self.thickness / math.cos(math.radians(360 / (2 * n)))
            r1 = r1 - self.thickness / math.cos(math.radians(360 / (2 * n)))
            if self.top == "none":
                h = self.adjustSize(h, False)
            elif "lid" in self.top and self.top != "angled lid":
                h = self.adjustSize(h) - self.thickness
            else:
                h = self.adjustSize(h)

        t = self.thickness

        r0, sh0, side0 = self.regularPolygon(n, radius=r0)
        r1, sh1, side1 = self.regularPolygon(n, radius=r1)

        # Capture the original side lengths before shrinking.  side0_orig is used
        # for alignment-hole position ratios; side1_orig is needed to compute the
        # correct width of the long back wall in trapezoid mode (that wall spans
        # two side-lengths so its trimmed width = 2*side_orig - 2*t, not 2*side).
        side0_orig = side0
        side1_orig = side1

        # Subtract two thicknesses from each side so finger joints fit flush.
        side0 = side0 - 2 * t
        side1 = side1 - 2 * t

        # Slant length of the tapered side walls.
        l = ((r0 - r1) ** 2 + h ** 2) ** 0.5
        # Taper angle (degrees): how much the side panels lean inward.
        a = math.degrees(math.asin((side1 - side0) / 2 / l))
        # Dihedral correction angle between adjacent side panels.
        phi = 180 - 2 * math.degrees(
            math.asin(math.cos(math.pi / n) / math.cos(math.radians(a))))

        # Finger-joint settings for side-to-side joints (accounts for dihedral angle phi).
        fingerJointSettings = copy.deepcopy(self.edges["f"].settings)
        fingerJointSettings.setValues(self.thickness, angle=phi)
        fingerJointSettings.edgeObjects(self, chars="gGH")

        beta = math.degrees(math.atan((sh1 - sh0) / h))
        angle_bottom = 90 + beta
        angle_top = 90 - beta

        # Finger-joint settings for the bottom panel (angled to match taper).
        fingerJointSettings = copy.deepcopy(self.edges["f"].settings)
        fingerJointSettings.setValues(self.thickness, angle=angle_bottom)
        fingerJointSettings.edgeObjects(self, chars="yYH")

        # Finger-joint settings for the top panel (mirror of the bottom angle).
        fingerJointSettings = copy.deepcopy(self.edges["f"].settings)
        fingerJointSettings.setValues(self.thickness, angle=angle_top)
        fingerJointSettings.edgeObjects(self, chars="zZH")

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
            drawTop(r0, self.bottom, "yY")
            drawTop(r1, self.top, "zZ")
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
            self.drawTrapezoidWall(r=max(r0, r1), edges_char='F', move="up only")
        else:
            self.regularPolygonWall(corners=n, r=max(r0, r1), edges='F', move="up only")

        fingers_top = self.top in ("closed", "hole", "angled hole",
                                   "round lid", "angled lid2", "bayonet mount")
        fingers_bottom = self.bottom in ("closed", "hole", "angled hole",
                                         "round lid", "angled lid2", "spoke")

        t_ = self.edges["G"].startwidth()
        bottom_edge = ('y' if fingers_bottom else 'e')
        top_edge = ('z' if fingers_top else 'e')
        d_top = max(0, -t_ * math.sin(math.radians(a)))
        d_bottom = max(0.0, t_ * math.sin(math.radians(a)))
        l -= (d_top + d_bottom)

        # Alignment-hole callback shared by all hex side panels.
        # moveTo(0, -t) compensates for the 2*t trimming of side0: the natural
        # callback origin sits t to the left of where it was before trimming,
        # so shifting t rightward (−y in local coords) restores centre alignment
        # when new and old panels are stacked and centred.
        def draw_aligned_holes():
            self.moveTo(0, -self.thickness)
            self.drawAlignmentHoles(side0_orig, l, "A")

        # Alignment-hole callback for the trapezoid long back wall.
        # The long wall spans two hex-side-lengths, so its pre-shrink width is
        # 2*side0_orig.  Passing that as the `s` parameter to drawAlignmentHoles
        # scales all fractional hole positions (corner clusters, centre-line
        # through-holes, mid-band pin holes) proportionally to the wider panel.
        def draw_aligned_holes_long():
            self.moveTo(0, -self.thickness)
            self.drawAlignmentHolesLong(2 * side0_orig, l, "A")

        if isTrapezoid:
            # Trapezoid side walls: 4 panels instead of 6.
            #
            #   1 × long back wall  — spans the join edge (length 2r)
            #   3 × standard walls  — one each for right slant, short front, left slant
            #                         (all width = side0, same geometry as hex panels)
            #
            # The long back wall uses the same stepped-tab border profile as the
            # hex panels (borders0) but with a width of 2*side_orig − 2*t.  This
            # wider panel connects to the two slant walls via the same E-edge tabs.
            e0 = bottom_edge + 'E' + top_edge + 'E'

            # Standard hex side-panel border (width = side0 / side1).
            borders0 = [side0, 90 - a,
                        d_bottom, -90, t_, 90, l, 90, t_, -90, d_top,
                        90 + a, side1, 90 + a,
                        d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90 - a]

            # Long back-wall border.  The bottom/top widths are 2*side_orig − 2*t
            # because the panel spans two hex-side-lengths and has only one finger-
            # joint notch at each end (not at the midpoint — there is no wall
            # junction there in a trapezoid box).
            side0_long = 2 * side0_orig - 2 * t
            side1_long = 2 * side1_orig - 2 * t
            borders_long = [side0_long, 90 - a,
                            d_bottom, -90, t_, 90, l, 90, t_, -90, d_top,
                            90 + a, side1_long, 90 + a,
                            d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90 - a]

            # Long back wall (1 panel).  The callback list mirrors the standard
            # walls: index 0 fires at the bottom edge (drawMarkers2 label),
            # index 1 fires at the first stepped-tab segment where the alignment
            # holes are drawn relative to the full panel dimensions.
            self.polygonWall(borders_long, edge=e0, correct_corners=False, move="right",
                             callback=[lambda: self.drawMarkers2(2 * side0_orig, l, "A"),
                                       draw_aligned_holes_long])

            # Three standard-width walls (right slant, front short, left slant).
            for _ in range(3):
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right",
                                 callback=[lambda: self.drawMarkers2(side0_orig, l, "A"),
                                           draw_aligned_holes])

        elif n % 2:
            # Odd number of sides: all side panels are identical.
            e = bottom_edge + 'ege' + top_edge + 'eeGee'
            borders = [side0, 90 - a, d_bottom, 0, l, 0, d_top, 90 + a, side1,
                       90 + a, d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90 - a]
            for _ in range(n):
                self.polygonWall(borders, edge=e, correct_corners=False, move="right")
        else:
            # Even number of sides: all panels use the stepped-tab profile.
            # (borders1 / e1 were a planned alternating-panel variant that was
            # never activated; the single borders0 / e0 pattern is correct here.)
            borders0 = [side0, 90 - a,
                        d_bottom, -90, t_, 90, l, 90, t_, -90, d_top,
                        90 + a, side1, 90 + a,
                        d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90 - a]
            e0 = bottom_edge + 'E' + top_edge + 'E'

            for _ in range(n // 2):
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right",
                                 callback=[lambda: self.drawMarkers2(side0_orig, l, "A"),
                                           draw_aligned_holes])
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right",
                                 callback=[lambda: self.drawMarkers2(side0_orig, l, "A"),
                                           draw_aligned_holes])

        # Append a reference panel that engraves all parameter values onto a
        # flat piece of stock — useful for reproducing or identifying a cut job.
        self.drawReferencePanel(move="right")
