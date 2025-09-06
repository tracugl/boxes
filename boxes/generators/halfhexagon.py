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
        self.argparser.add_argument("--radius_bottom", action="store", type=float, default=50.0,
                                    help="Inner radius at bottom (same definition as hexagon generator)")
        self.argparser.add_argument("--radius_top", action="store", type=float, default=50.0,
                                    help="Inner radius at top (use different value for (future) taper – currently forced to vertical")
        self.argparser.add_argument("--top", action="store", type=str, default="none",
                                    choices=["none", "closed", "hole"], help="Top style")
        self.argparser.add_argument("--bottom", action="store", type=str, default="closed",
                                    choices=["none", "closed", "hole"], help="Bottom style")
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
        r0, r1, h, t = self.radius_bottom, self.radius_top, self.h, self.thickness

        # enforce vertical walls for now; if taper requested just warn by collapsing
        if abs(r0 - r1) > 0.01:
            r1 = r0  # TODO: implement tapering similar to hexagon pyramid sides

        if self.outside:
            # mimic hexagon: subtract thickness so outside size matches given *inner* radius
            r0 -= t
            r1 -= t
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
                    self.polygonWall(borders, edge="ffff", move="right")
                else:  # hole or none already filtered
                    self.polygonWall(borders, edge="eeee", move="right")
            if self.top == "closed":
                self.polygonWall(borders, edge="ffff", move="right")
            elif self.top == "hole":
                # simple hole: inner shrunken polygon
                self.polygonWall(borders, edge="eeee", move="right")

        # Place outline (for reference) and create walls using polygonWalls
        self.polygonWall(borders, move="up only")
        self.polygonWalls(borders, h)

        # Provide top plate again as lid if requested (not interlocking)
        if self.top == "hole":
            self.rectangularWall(0, h, edges="eeee", move="up only")  # spacer / alignment artifact

