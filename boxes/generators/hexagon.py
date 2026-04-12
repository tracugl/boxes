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
    """Box with a regular hexagon as the base.

    Supports tapered (top radius != bottom radius) geometry, several lid
    styles inherited from BayonetBox, and an optional decorative 'spoke'
    pattern on the bottom panel.
    """

    ui_group = "Box"

    def __init__(self) -> None:
        Boxes.__init__(self)

        # Override the default material thickness to suit typical hex box use.
        defaultgroup = self.argparser._action_groups[1]
        for action in defaultgroup._actions:
            if action.dest == 'thickness':
                action.default = 6.0

        self.addSettingsArgs(edges.FingerJointSettings, finger=5, space=5, surroundingspaces=2, play=0.15)

        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--radius_bottom", action="store", type=float, default=500.0,
            help="inner radius of the box bottom (at the corners)")
        self.argparser.add_argument(
            "--radius_top", action="store", type=float, default=500.0,
            help="inner radius of the box top (at the corners)")
        self.argparser.add_argument(
            "--top", action="store", type=str, default="closed",
            choices=["none", "hole", "angled hole", "angled lid", "angled lid2", "round lid", "bayonet mount", "closed"],
            help="style of the top and lid")
        self.argparser.add_argument(
            "--alignment_pins", action="store", type=float, default=1.0,
            help="diameter of the alignment pins for bayonet lid")
        self.argparser.add_argument(
            "--bottom", action="store", type=str, default="spoke",
            choices=["none", "closed", "hole", "angled hole", "angled lid", "angled lid2", "round lid", "spoke"],
            help="style of the bottom and bottom lid")
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
            "--trapezoid", action="store", type=boolarg, default=False,
            help="If true, only draw a half-hexagon.")

        self.lugs = 6
        self.n = 6

    def drawSupports(self):
        """Draw rectangular internal support walls, one per spoke axis.

        A hexagonal spoke bottom has three support walls (one per 60° spoke
        direction).  All three are identical rectangles of size
        support_length × box_height, finger-jointed on both long edges
        ('fefe' pattern), so they can be laser-cut from the same template.

        A single large circular through-hole is cut in the centre of each
        support, using the same sizing formula as drawAlignmentHoles:
            r1 = (h - spacer - spacer) / 2
        where 'spacer' is the minimum clearance margin from the panel edges.
        If 'spacer' yields a non-positive radius the hole is omitted.
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

        # Three identical support walls, one per spoke direction (0°, +60°, -60°).
        # Drawing all three ensures the correct quantity is indicated on the sheet
        # so the operator knows to cut 3 copies.
        if r1 > 0:
            # Callback fires at the bottom-left corner (edge 0) with the
            # x-axis pointing right and y-axis pointing into the panel.
            # From that origin, (sl/2, h/2) is the geometric centre of the
            # rectangle, which is exactly where the through-hole should sit.
            def draw_center_hole():
                self.hole(sl / 2, h / 2, r1)

            for _ in range(3):
                self.rectangularWall(sl, h, "fefe", callback=[draw_center_hole], move="right")
        else:
            # Panel is too short for the hole to clear the edges — render
            # without a hole rather than producing invalid geometry.
            for _ in range(3):
                self.rectangularWall(sl, h, "fefe", move="right")

    def drawSupportHoles(self, r):
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

        @param r - Inner corner radius of the hexagon bottom panel.
        """
        sl = self.support_length

        H = r * math.sqrt(3) / 2.0  # apothem — also the y-distance from origin to centre

        # The three spoke axes are 60° apart.  For each one, shift the coordinate
        # origin to the hex centre and rotate to align with the spoke, then draw
        # the two slots at ±H/2 along the local y-axis.  saved_context() keeps the
        # transform local so the next spoke starts from the original origin.
        for spoke_angle in (0, 60, -60):
            with self.saved_context():
                # Translate to centre (r/2, H) then rotate by spoke_angle.
                self.moveTo(r / 2, H, spoke_angle)
                # Lower slot: midpoint at (0, -H/2) in centre-relative coords.
                self.fingerHolesAt(0, -H / 2 - sl / 2, sl, angle=90)
                # Upper slot: midpoint at (0, +H/2) in centre-relative coords.
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
        r = self.radius_bottom

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
            # In trapezoid mode only kites 0 and 5 (the two front-facing ones) are drawn.
            if isTrapezoid and kite_counter not in (0, 5):
                continue

            self.ctx.move_to(kite[0][0], kite[0][1])
            for x_, y_ in kite[1:]:
                self.ctx.line_to(x_, y_)
            self.ctx.line_to(kite[0][0], kite[0][1])
            self.ctx.stroke()

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

        Handles tapered geometry (different top and bottom radii), outside vs
        inside measurement modes, and all supported top/bottom style variants.
        """
        r0, r1, h, n, isTrapezoid = self.radius_bottom, self.radius_top, self.h, self.n, self.trapezoid

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

        # Capture the original side length before shrinking.  Alignment-hole
        # positions are computed from side0_orig (not the trimmed side0) so that
        # the proportional layout stays consistent.  A moveTo(0, -t) shift in
        # draw_aligned_holes() then nudges every hole t inward, achieving
        # centre-to-centre alignment when new and old panels are stacked centred.
        side0_orig = side0

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

        def drawTop(r, sh, top_type, joint_type):
            """Render one hexagonal face (top or bottom) in the requested style.

            @param r          - Inner corner radius of this face.
            @param sh         - Apothem (short radius) of this face.
            @param top_type   - Style string from the --top / --bottom argument.
            @param joint_type - Two-character edge string, e.g. 'yY' or 'zZ'.
            """
            if top_type == "closed":
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
            elif top_type == "spoke":
                self.regularPolygonWall(
                    corners=n, r=r, edges=joint_type[1], move="right",
                    callback=[
                        lambda: self.drawKites(r=r, joint_type=joint_type, isTrapezoid=isTrapezoid),
                        lambda: self.drawSupportHoles(r=r),
                    ])
                self.drawSupports()
            elif top_type == "angled lid":
                self.regularPolygonWall(corners=n, r=r, edges='e', move="right")
                self.regularPolygonWall(corners=n, r=r, edges='E', move="right")
            elif top_type in ("angled hole", "angled lid2"):
                rim_w = self.edge_width if self.edge_width > 0 else t
                inner_sh = sh - rim_w
                callbacks = []
                if inner_sh > 0:
                    callbacks.append(lambda: self.regularPolygonAt(0, 0, n, h=inner_sh))
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right",
                                        callback=callbacks if callbacks else None)
                if top_type == "angled lid2":
                    self.regularPolygonWall(corners=n, r=r, edges='E', move="right")
            elif top_type in ("hole", "round lid"):
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right",
                                        hole=(sh - t) * 2)
            if top_type == "round lid":
                self.parts.disc(sh * 2, move="right")
            if top_type == "bayonet mount":
                # Bayonet lid requires three additional pieces: lower disc with
                # lugs, upper ring with receiving slots, and a plain top disc.
                self.diameter = 2 * sh
                self.parts.disc(sh * 2 - 0.1 * t, callback=self.lowerCB, move="right")
                self.regularPolygonWall(corners=n, r=r, edges='F',
                                        callback=[self.upperCB], move="right")
                self.parts.disc(sh * 2, move="right")

        with self.saved_context():
            # Draw bottom panel first, then top (order affects SVG layout).
            drawTop(r0, sh0, self.bottom, "yY")
            drawTop(r1, sh1, self.top, "zZ")

        # Invisible up-only move reserves vertical space for the panels above.
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

        if n % 2:
            # Odd number of sides: all side panels are identical.
            e = bottom_edge + 'ege' + top_edge + 'eeGee'
            borders = [side0, 90 - a, d_bottom, 0, l, 0, d_top, 90 + a, side1,
                       90 + a, d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90 - a]
            for _ in range(n):
                self.polygonWall(borders, edge=e, correct_corners=False, move="right")
        else:
            # Even number of sides: alternating panel types share opposite faces.
            borders0 = [side0, 90 - a,
                        d_bottom, -90, t_, 90, l, 90, t_, -90, d_top,
                        90 + a, side1, 90 + a,
                        d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90 - a]
            e0 = bottom_edge + 'E' + top_edge + 'E'
            borders1 = [side0, 90 - a, d_bottom, 0, l, 0, d_top, 90 + a, side1,
                        90 + a, d_top, 0, l, 0, d_bottom, 90 - a]
            e1 = bottom_edge + 'e' + top_edge + 'e'
            # The polygonWall callback at index 1 fires at the RIGHT end of the
            # side0 edge.  Because side0 was trimmed by 2*t, this natural origin
            # sits 2*t to the LEFT (in SVG x) of where it sat in old builds.
            #
            # We want holes to align centre-to-centre: when a new panel (shorter
            # by 2*t) is laid on top of an old panel and centred, each panel edge
            # recedes by t.  So every hole must shift t towards the panel centre
            # relative to a right-edge-aligned reference.
            #
            # moveTo(0, -t) compensates: local y points leftward (−SVG x), so
            # a negative dy moves the origin rightward (+SVG x) by t, placing
            # holes t closer to the right edge than the natural origin would give.
            # Combined with using side0_orig for position ratios, this produces a
            # uniform t-inward shift on every hole, which cancels the t-outward
            # shift of the panel edge when the two panels are centred.
            def draw_aligned_holes():
                self.moveTo(0, -self.thickness)
                self.drawAlignmentHoles(side0_orig, l, "A")

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
