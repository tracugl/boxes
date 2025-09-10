import math
import copy
from boxes import Boxes, edges


# Copyright (C) 2024 Florian Festi
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
class HalfHexagonBox2(Boxes):
    """Half Hexagon 2 (isosceles trapezoid) box – vertical walls.

    Geometry: derived from a regular hexagon with circum radius *r*.
    Long base = 2*r, short base = r, side legs = r, height = r*sqrt(3)/2.
    """

    ui_group = "Box"

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings, surroundingspaces=1)
        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--radius", action="store", type=float, default=50.0,
            help="Inner radius")
        self.argparser.add_argument(
            "--top", action="store", type=str, default="closed",
            choices=["none", "closed"], help="Top style")
        self.argparser.add_argument(
            "--bottom", action="store", type=str, default="spoke",
            choices=["none", "closed", "angled hole", "spoke"], help="Bottom style (angled hole creates rim + inner trapezoid hole; spoke adds 3 kite cutouts)")
        self.argparser.add_argument(
            "--edge_width", action="store", type=float, default=5.0,
            help="Frame width for spoke bottom")
        self.argparser.add_argument(
            "--spoke_width", action="store", type=float, default=5.0,
            help="Spoke width controlling kite shape for spoke bottom")
        self.n = 4  # number of edges of trapezoid

    # --- geometry helper -------------------------------------------------
    def trapezoidBorders(self, r):
        """Return polygonWall borders list for half-hexagon trapezoid.

        Format matches examples (heart, console, tetris): alternating length, angle.
        Angles are turning angles. We use 120,60,60,120 which closes with last implicit edge.
        """
        long_base = 2*r
        side = r
        short_base = r
        return [long_base, 120, side, 60, short_base, 60, side, 120], (long_base, side, short_base, side)

    # --- rendering -------------------------------------------------------
    def render(self):
        r0, h, t, n = self.radius, self.h, self.thickness, self.n
        if self.outside:
            # mimic hexagon: subtract thickness so outside size matches given *inner* radius
            #r0 = r0 - self.thickness / math.cos(math.radians(360/(2*n)))
            h = self.adjustSize(h)

        borders, (long_base, side_len, short_base, _) = self.trapezoidBorders(r0)

        # Ensure y/z finger edges exist with 90° angle for bottom/top joints
        fj_bottom = copy.deepcopy(self.edges["f"].settings)
        fj_bottom.setValues(t, angle=90)
        fj_bottom.edgeObjects(self, "yY")
        fj_top = copy.deepcopy(self.edges["f"].settings)
        fj_top.setValues(t, angle=90)
        fj_top.edgeObjects(self, "zZ")

        # Draw bottom/top plates first (like roundedregularbox pattern)
        with self.saved_context():
            if self.bottom != "none":
                if self.bottom == "closed":
                    # solid bottom
                    self.polygonWall(borders, edge="Y", move="right")
                elif self.bottom == "angled hole":
                    # Outer rim with centered inner trapezoid hole (scaled by thickness)
                    rim_w = self.edge_width if self.edge_width > 0 else t
                    r_inner = max(r0 - rim_w, 0)
                    inner_borders, _ = self.trapezoidBorders(r_inner)
                    if r_inner > 0:
                        h_outer = r0 * math.sqrt(3)/2.0
                        h_inner = r_inner * math.sqrt(3)/2.0
                        dx = (r0 - r_inner)  # centers horizontally
                        dy = (h_outer - h_inner)/2.0  # centers vertically
                        def _inner():
                            self.moveTo(dx, dy)
                            self.polygonWall(inner_borders, edge="eeee", turtle=True)
                        self.polygonWall(borders, edge="Y", move="right", callback=[_inner])
                    else:
                        self.polygonWall(borders, edge="Y", move="right")
                elif self.bottom == "spoke":
                    # Two kite cutouts inside half-hex/trapezoid
                    edge_w = self.edge_width
                    spoke_w = self.spoke_width
                    H = r0 * math.sqrt(3)/2.0  # trapezoid height (apothem of full hex)
                    A_inner = H - edge_w
                    if A_inner <= 0:
                        self.polygonWall(borders, edge="Y", move="right")
                    else:
                        sqrt3 = math.sqrt(3)
                        s = (A_inner / sqrt3) - (spoke_w / 2.0)
                        if s <= 0:
                            self.polygonWall(borders, edge="Y", move="right")
                        else:
                            # Center of trapezoid
                            cx = r0
                            # Equivalent inner radius along centerline
                            R_inner = A_inner * 2.0 / sqrt3
                            # Master kite oriented upward (angle 90°)
                            P1 = (0.0, R_inner)
                            P2 = (s*sqrt3/2.0, R_inner - s/2.0)
                            P3 = (0.0, R_inner - 2.0*s)
                            P4 = (-s*sqrt3/2.0, R_inner - s/2.0)
                            master = [P1, P2, P3, P4]
                            def rot(pts, ang_deg):
                                ang = math.radians(ang_deg)
                                ca, sa = math.cos(ang), math.sin(ang)
                                return [(x*ca - y*sa, x*sa + y*ca) for x,y in pts]
                            # Use two kites (omit center) symmetric about vertical axis
                            kite_angles = [120, 60]
                            kites = [rot(master, a) for a in kite_angles]
                            kites = [rot(kite, 90) for kite in kites]  # orient
                            kites = [[(x, -y) for (x, y) in kite] for kite in kites]  # flip vertical
                            # Reposition vertically: ensure nearest kite edge is edge_w from long base (y=0)
                            min_y = min(y for kite in kites for (_, y) in kite)
                            cy = edge_w - min_y
                            def draw_kites():
                                for kite in kites:
                                    # translate to center
                                    self.ctx.move_to(kite[0][0] + cx, kite[0][1] + cy)
                                    for x_, y_ in kite[1:]:
                                        self.ctx.line_to(x_ + cx, y_ + cy)
                                    self.ctx.line_to(kite[0][0] + cx, kite[0][1] + cy)
                                    self.ctx.stroke()
                            self.polygonWall(borders, edge="Y", move="right", callback=[draw_kites])
            if self.top == "closed":
                self.polygonWall(borders, edge="Z", move="right")

        # Place outline (for reference) and create walls; use y/z fingers for bottom/top like hexagon
        self.polygonWall(borders, move="up only")
        self.polygonWalls(borders, h, bottom="y", top="z")

