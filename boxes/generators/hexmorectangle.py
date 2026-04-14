"""Rectangular box with a fixed 3×5 internal grid, compatible with the HexmoHexagon
modular stacking system.

The short wall length equals one hexagon side (``--radius``), so a HexmoHexagon can
join any of its edges flush against either short wall of this rectangle.  The long
wall equals the hexagon flat-to-flat distance (``radius × √3``).

Phase implementation:
  1. Core structure: 4 outer walls + base plate (this file — Phase 1).
  2. Internal 3×5 grid with crossing dividers.
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
    """Rectangular tray with a fixed 3×5 internal grid, compatible with HexmoHexagon stacking.

    The ``--radius`` parameter controls the overall dimensions and must match the
    ``--radius`` used on HexmoHexagon boxes you want to connect to this tray:

    - Short wall length  = ``radius``      (equals one hexagon side)
    - Long wall length   = ``radius × √3`` (equals the hexagon flat-to-flat distance)
    - Column inner width = ``radius / 3``  (3 equal columns across the short axis)
    - Row inner height   = ``radius × √3 / 5`` (5 equal rows along the long axis)

    FingerJoint settings are set to match HexmoHexagon (finger=5, space=5,
    surroundingspaces=2, play=0.2) so that joints between the two box types are
    compatible.
    """

    ui_group = "Box"

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
            help="Hexagon-compatibility radius (mm).  The short wall of the rectangle "
                 "will be exactly this length, matching one edge of a HexmoHexagon box "
                 "with the same radius.  Short dimension W = radius; "
                 "long dimension H = radius × √3.",
        )

    def render(self) -> None:
        """Generate all panels for the HexmoRectangle box (Phase 1: outer shell only).

        Draws five panels:
          - 2 × short outer wall  (W × h)  — span the short (radius) axis
          - 2 × long outer wall   (H × h)  — span the long (radius × √3) axis
          - 1 × base plate        ((W + 2t) × (H + 2t))

        When ``--outside`` is set, ``radius`` is treated as the outer box width
        (including wall material) rather than the inner cavity.

        All outer walls use the TrayLayout edge convention:
          bottom = 'f'  (finger tabs connecting to base plate 'F' slots)
          sides  = 'f'  (interlocking finger tabs at each corner)
          top    = 'e'  (open — no lid in Phase 1)
        """
        t = self.thickness
        r = self.radius
        h = self.h

        # --- Geometry -----------------------------------------------------------
        # W is the inner cavity short dimension (= one hexagon side for compatibility).
        # H is the inner cavity long dimension (= hexagon flat-to-flat distance).
        W = r
        H = r * math.sqrt(3)

        if self.outside:
            # When the user specifies outside dimensions, convert to inner cavity
            # by subtracting the wall material thickness from both ends of each axis.
            # W and H both have outer walls on two sides → subtract 2 × t.
            W = self.adjustSize(W)
            H = self.adjustSize(H)
            # Box height: only the base contributes (open top) → subtract 1 × t.
            h = self.adjustSize(h, e2=False)

        # --- Outer walls --------------------------------------------------------
        # Edge string "ffef": [bottom='f', right='f', top='e', left='f']
        # This matches TrayLayout's outer-wall convention:
        #   bottom 'f' tabs slot into the base plate's perimeter 'F' slots.
        #   side 'f' tabs interlock with the perpendicular wall's 'f' tabs at each corner.
        #   top is left open ('e') — a lid can be added in a later phase.

        # Two short outer walls spanning the W (radius) axis.
        for _ in range(2):
            self.rectangularWall(W, h, "ffef", move="right")

        # Two long outer walls spanning the H (radius × √3) axis.
        for _ in range(2):
            self.rectangularWall(H, h, "ffef", move="right")

        # Advance the layout cursor to a fresh row below the wall panels.
        # "up only" moves without drawing — the width argument is irrelevant.
        self.rectangularWall(1, h, "eeee", move="up only")

        # --- Base plate ---------------------------------------------------------
        # The base plate spans the full outer footprint of the box.
        # Each outer wall's bottom 'f' tabs extend t inward into the base perimeter,
        # so the base plate must be (W + 2t) wide and (H + 2t) deep.
        # 'F' (counter-part finger joint) on all four edges receives the wall tabs.
        self.rectangularWall(W + 2 * t, H + 2 * t, "FFFF", move="right")
