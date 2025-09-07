import math
import copy
from boxes import Boxes, edges


# Copyright (C) 2024 Florian Festi
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
class HalfHexagonBox(Boxes):
    """Half Hexagon (isosceles trapezoid) box – vertical walls.

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
            "--bottom", action="store", type=str, default="closed",
            choices=["none", "closed", "angled hole"], help="Bottom style (angled hole creates rim + inner trapezoid hole)")
        self.argparser.add_argument(
            "--angled_hole_rim", action="store", type=float, default=-1.0,
            help="Rim width for angled hole (use -1 to default to material thickness)")
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
        r0, h, t = self.radius, self.h, self.thickness

        
        if self.outside:
            # mimic hexagon: subtract thickness so outside size matches given *inner* radius
            r0 -= t
            h = self.adjustSize(h)

        borders, (long_base, side_len, short_base, _) = self.trapezoidBorders(r0)

        # Finger joint edge objects (90° only needed for vertical walls)
        base_top_fj = copy.deepcopy(self.edges["f"].settings)
        base_top_fj.setValues(t, angle=90)
        base_top_fj.edgeObjects(self, "fF")  # lower/upper variants

        # Draw bottom/top plates first (like roundedregularbox pattern)
        with self.saved_context():
            if self.bottom != "none":
                if self.bottom == "closed":
                    # solid bottom
                    self.polygonWall(borders, edge="ffff", move="right")
                elif self.bottom == "angled hole":
                    # Outer rim with centered inner trapezoid hole (scaled by thickness)
                    rim_w = self.angled_hole_rim if self.angled_hole_rim > 0 else t
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
                        self.polygonWall(borders, edge="ffff", move="right", callback=[_inner])
                    else:
                        self.polygonWall(borders, edge="ffff", move="right")
            if self.top == "closed":
                self.polygonWall(borders, edge="ffff", move="right")

        # Place outline (for reference) and create walls using polygonWalls
        self.polygonWall(borders, move="up only")
        self.polygonWalls(borders, h)

        # Provide top plate again as lid if requested (not interlocking)
        if self.top == "hole":
            self.rectangularWall(0, h, edges="eeee", move="up only")  # spacer / alignment artifact

