# Copyright (C) 2013-2014 Florian Festi
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
from boxes import Boxes, edges
from boxes.generators.bayonetbox import BayonetBox
from boxes.Color import *
from boxes.qrcode_factory import BoxesQrCodeFactory
from boxes.vectors import kerf
"""Hexagon generator with optional 'spoke' bottom pattern.

The 'spoke' style draws a hexagonal frame (outer and inner hex cut) plus six
identical kite shaped cutouts. This avoids boolean geometry libraries so it
works robustly with the existing drawing context (no shapely dependency).
"""

### Helpers

def dist(dx, dy):
    """distance function for sorting"""
    return (dx*dx + dy*dy)**0.5

class HexagonBox(BayonetBox):
    """Box with regular hexagon as base"""

    description = """For short side walls that don't fit a connecting finger reduce *surroundingspaces* and *finger* in the Finger Joint Settings.

The lids needs to be glued. For the bayonet lid all outside rings attach to the bottom, all inside rings to the top.
"""

    ui_group = "Box"

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings, surroundingspaces=1)
        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--radius_bottom",  action="store", type=float, default=50.0,
            help="inner radius of the box bottom (at the corners)")
        self.argparser.add_argument(
            "--radius_top",  action="store", type=float, default=50.0,
            help="inner radius of the box top (at the corners)")
        self.argparser.add_argument(
            "--top",  action="store", type=str, default="none",
            choices=["none", "hole", "angled hole", "angled lid", "angled lid2", "round lid", "bayonet mount", "closed"],
            help="style of the top and lid")
        self.argparser.add_argument(
            "--alignment_pins",  action="store", type=float, default=1.0,
            help="diameter of the alignment pins for bayonet lid")
        self.argparser.add_argument(
            "--bottom",  action="store", type=str, default="spoke",
            choices=["none", "closed", "hole", "angled hole", "angled lid", "angled lid2", "round lid", "spoke"],
            help="style of the bottom and bottom lid")
        self.argparser.add_argument(
            "--edge_width", action="store", type=float, default=5.0,
            help="Width of the outer hexagonal frame for spoke bottom.")
        self.argparser.add_argument(
            "--spoke_width", action="store", type=float, default=5.0,
            help="Width of the spokes for spoke bottom.")
        self.argparser.add_argument(
            "--angled_hole_rim", action="store", type=float, default=-1.0,
            help="Rim width for angled hole (use -1 to default to material thickness)")

        self.lugs=6
        self.n = 6

    def render(self):

        r0, r1, h, n = self.radius_bottom, self.radius_top, self.h, self.n

        if self.outside:
            r0 = r0 - self.thickness / math.cos(math.radians(360/(2*n)))
            r1 = r1 - self.thickness / math.cos(math.radians(360/(2*n)))
            if self.top == "none":
                h = self.adjustSize(h, False)
            elif "lid" in self.top and self.top != "angled lid":
                h = self.adjustSize(h) - self.thickness
            else:
                h = self.adjustSize(h)

        t = self.thickness


        r0, sh0, side0  = self.regularPolygon(n, radius=r0)
        r1, sh1, side1  = self.regularPolygon(n, radius=r1)

        # length of side edges
        #l = (((side0-side1)/2)**2 + (sh0-sh1)**2 + h**2)**0.5
        l = ((r0-r1)**2 + h**2)**.5
        # angles of sides -90° aka half of top angle of the full pyramid sides
        a = math.degrees(math.asin((side1-side0)/2/l))
        # angle between sides (in boxes style change of travel)
        phi = 180 - 2 * math.degrees(
            math.asin(math.cos(math.pi/n) / math.cos(math.radians(a))))

        fingerJointSettings = copy.deepcopy(self.edges["f"].settings)
        fingerJointSettings.setValues(self.thickness, angle=phi)
        fingerJointSettings.edgeObjects(self, chars="gGH")

        beta = math.degrees(math.atan((sh1-sh0)/h))
        angle_bottom = 90 + beta
        angle_top = 90 - beta

        fingerJointSettings = copy.deepcopy(self.edges["f"].settings)
        fingerJointSettings.setValues(self.thickness, angle=angle_bottom)
        fingerJointSettings.edgeObjects(self, chars="yYH")

        fingerJointSettings = copy.deepcopy(self.edges["f"].settings)
        fingerJointSettings.setValues(self.thickness, angle=angle_top)
        fingerJointSettings.edgeObjects(self, chars="zZH")


        def drawTop(r, sh, top_type, joint_type):
            if top_type == "spoke":
                outer_radius = r
                edge_width = self.edge_width
                spoke_width = self.spoke_width

                # Geometry translated from provided JavaScript sample.
                sqrt3 = math.sqrt(3)
                cos30 = sqrt3 / 2.0
                A_outer = outer_radius * cos30            # outer apothem
                A_inner = A_outer - edge_width            # inner apothem after frame
                if A_inner <= 0:
                    # Frame would vanish – fallback to closed polygon
                    self.regularPolygonWall(corners=n, r=outer_radius, edges=joint_type[1], move="right")
                    return
                R_inner = A_inner / cos30                 # inner radius at corners
                # Short side length helper (derived from JS logic)
                s = (A_inner / sqrt3) - (spoke_width / 2.0)
                if s <= 0:
                    # Spokes collapse – fallback
                    self.regularPolygonWall(corners=n, r=outer_radius, edges=joint_type[1], move="right")
                    return

                def hex_points(R):
                    # Keep orientation consistent with other parts (point to the right at angle 0)
                    return [(R*math.cos(math.radians(60*i)), R*math.sin(math.radians(60*i))) for i in range(6)]

                outer_hex = hex_points(outer_radius)

                # Master kite (pointing upward in our coordinate system, y positive)
                P1 = (0.0, R_inner)                               # top vertex (120°)
                P2 = (s*sqrt3/2.0, R_inner - s/2.0)               # right 90° vertex
                P3 = (0.0, R_inner - 2.0*s)                       # inner 60° vertex
                P4 = (-s*sqrt3/2.0, R_inner - s/2.0)              # left 90° vertex
                def rotate_points(pts, angle_deg):
                    ang = math.radians(angle_deg)
                    ca, sa = math.cos(ang), math.sin(ang)
                    return [(x*ca - y*sa, x*sa + y*ca) for x, y in pts]

                kite_master = [P1, P2, P3, P4]
                # Rotate master kite by 30° so that its edges align with the flat orientation of the outer hex
                kite_master = rotate_points(kite_master, 30)

                kites = [rotate_points(kite_master, 60*i) for i in range(6)]

                # Bounding box based on outer hex
                xs = [p[0] for p in outer_hex]
                ys = [p[1] for p in outer_hex]
                minx, maxx = min(xs), max(xs)
                miny, maxy = min(ys), max(ys)
                w = maxx - minx
                h = maxy - miny
                if self.move(w, h, "right", before=True):
                    return
                ox, oy = -minx, -miny

                def draw_polygon(points):
                    self.ctx.move_to(points[0][0] + ox, points[0][1] + oy)
                    for x_, y_ in points[1:]:
                        self.ctx.line_to(x_ + ox, y_ + oy)
                    self.ctx.line_to(points[0][0] + ox, points[0][1] + oy)
                    self.ctx.stroke()

                # Cut outer boundary
                draw_polygon(outer_hex)
                # Cut kite voids (leave spokes + inner hub material intact)
                for kite in kites:
                    draw_polygon(kite)
                self.move(w, h, "right")
                return
            if top_type == "closed":
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
            elif top_type == "angled lid":
                self.regularPolygonWall(corners=n, r=r, edges='e', move="right")
                self.regularPolygonWall(corners=n, r=r, edges='E', move="right")
            elif top_type in ("angled hole", "angled lid2"):
                rim_w = self.angled_hole_rim if self.angled_hole_rim > 0 else t
                inner_sh = sh - rim_w
                callbacks = []
                if inner_sh > 0:
                    callbacks.append(lambda: self.regularPolygonAt(0, 0, n, h=inner_sh))
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right", callback=callbacks if callbacks else None)
                if top_type == "angled lid2":
                    self.regularPolygonWall(corners=n, r=r, edges='E', move="right")
            elif top_type in ("hole", "round lid"):
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right",
                                        hole=(sh-t)*2)
            if top_type == "round lid":
                self.parts.disc(sh*2, move="right")
            if self.top == "bayonet mount":
                self.diameter = 2*sh
                self.parts.disc(sh*2-0.1*t, callback=self.lowerCB,
                                move="right")
                self.regularPolygonWall(corners=n, r=r, edges='F',
                                        callback=[self.upperCB], move="right")
                self.parts.disc(sh*2, move="right")


        with self.saved_context():
            # Draw bottom (may be 'spoke') then top
            drawTop(r0, sh0, self.bottom, "yY")
            drawTop(r1, sh1, self.top, "zZ")

        self.regularPolygonWall(corners=n, r=max(r0, r1), edges='F', move="up only")

        fingers_top = self.top in ("closed", "hole", "angled hole",
                                   "round lid", "angled lid2", "bayonet mount")
        fingers_bottom = self.bottom in ("closed", "hole", "angled hole",
                                         "round lid", "angled lid2")

        t_ = self.edges["G"].startwidth()
        bottom_edge = ('y' if fingers_bottom else 'e')
        top_edge = ('z' if fingers_top else 'e')
        d_top = max(0, -t_ * math.sin(math.radians(a)))
        d_bottom = max(0.0, t_ * math.sin(math.radians(a)))
        l -= (d_top + d_bottom)

        if n % 2:
            e = bottom_edge + 'ege' + top_edge + 'eeGee'
            borders = [side0, 90-a, d_bottom, 0, l, 0, d_top, 90+a, side1,
                       90+a, d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90-a]
            for i in range(n):
                self.polygonWall(borders, edge=e, correct_corners=False,
                                 move="right")
        else:
            borders0 = [side0, 90-a,
                        d_bottom, -90, t_, 90, l, 90, t_, -90, d_top,
                        90+a, side1, 90+a,
                        d_top, -90, t_, 90, l, 90, t_, -90, d_bottom, 90-a]
            e0 = bottom_edge + 'eeGee' + top_edge + 'eeGee'
            borders1 = [side0, 90-a, d_bottom, 0, l, 0, d_top, 90+a, side1,
                        90+a, d_top, 0, l, 0, d_bottom, 90-a]
            e1 = bottom_edge + 'ege' + top_edge + 'ege'
            for i in range(n//2):
                self.polygonWall(borders0, edge=e0, correct_corners=False,
                                 move="right")
                self.polygonWall(borders1, edge=e1, correct_corners=False,
                                 move="right")
