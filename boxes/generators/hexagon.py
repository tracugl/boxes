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

import math
import copy
from boxes import Boxes, edges, boolarg
from boxes.generators.bayonetbox import BayonetBox


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
            "--support_length", action="store", type=float, default=120.0,
            help="length of the internal supports.")
        self.argparser.add_argument(
            "--trapezoid", action="store", type=boolarg, default=False,
            help="If true, only draw a half-hexagon.")

        self.lugs = 6
        self.n = 6

    def drawSupports(self):
        """Draw rectangular internal support walls, one per spoke bottom.

        The support is a simple rectangular wall whose height matches the box
        body height, finger-jointed on both long edges ('fefe' pattern).
        """
        h = self.h
        if self.outside:
            h = self.adjustSize(h)
        sl = self.support_length
        self.rectangularWall(sl, h, "fefe", move="right")

    def drawSupportHoles(self, r):
        """Cut finger-joint slots into the bottom panel for the internal supports.

        Two slots are placed symmetrically along the apothem axis so that the
        rectangular support walls slot perpendicularly into the bottom panel.

        @param r - Inner corner radius of the hexagon bottom panel.
        """
        sl = self.support_length

        H = r * math.sqrt(3) / 2.0  # apothem of the full hexagon
        H1 = H / 2
        H2 = H + H / 2

        self.fingerHolesAt(r / 2, H1 - sl / 2, sl, angle=90)
        self.fingerHolesAt(r / 2, H2 - sl / 2, sl, angle=90)

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
            for i in range(n):
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
            for i in range(n // 2):
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right")
                self.polygonWall(borders0, edge=e0, correct_corners=False, move="right")
