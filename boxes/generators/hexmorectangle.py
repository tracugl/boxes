"""Rectangular box with a fixed 3×5 internal grid, compatible with the HexmoHexagon
modular stacking system.

The short wall length equals one hexagon side (``--radius``), so a HexmoHexagon can
join any of its edges flush against either short wall of this rectangle.  The long
wall equals the hexagon flat-to-flat distance (``radius × √3``).

Phase implementation:
  1. Core structure: 4 outer walls + base plate (done).
  2. Internal 3×5 grid with crossing dividers (this file — Phase 2).
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

    Internal 3×5 grid crossing-joint convention:
      - Vertical dividers (2, spanning H): slots cut from the **bottom** edge,
        depth h/2, allowing horizontal dividers to slide in from above.
      - Horizontal dividers (4, spanning W): slots cut from the **top** edge,
        depth h/2, meshing with the vertical dividers' bottom slots at the
        midpoint of the wall height.
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
        """Generate all panels for the HexmoRectangle box (Phase 2: outer shell + 3×5 grid).

        Draws eleven panels:
          - 2 × short outer wall  (W × h)  — span the short (radius) axis
          - 2 × long outer wall   (H × h)  — span the long (radius × √3) axis
          - 1 × base plate        ((W + 2t) × (H + 2t))
          - 2 × vertical divider  (H × h)  — split the box into 3 columns
          - 4 × horizontal divider (W × h) — split the box into 5 rows

        When ``--outside`` is set, ``radius`` is treated as the outer box width
        (including wall material) rather than the inner cavity.

        Crossing-joint convention (slot-and-tab):
          Vertical dividers carry ``SlottedEdge`` on their **bottom** edges:
          five 'f' sections (finger-tabs for the base plate) separated by four
          Slot notches of depth h/2.  Horizontal dividers carry ``SlottedEdge``
          on their **top** edges: three 'e' sections separated by two Slot
          notches of depth h/2.  The two sets of notches interlock at mid-height
          when the horizontal dividers are lowered over the vertical ones during
          assembly.

        All outer walls carry fingerHoles callbacks so the divider 'f' end-tabs
        seat against each outer wall's inner face at the correct grid positions.

        Base plate carries fingerHoles callbacks for all six dividers, covering
        only the 'f' sections of each divider's bottom edge (not the plain or
        slotted crossing positions, which float above the base at those spots).
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

        # --- Grid geometry ------------------------------------------------------
        # The 3-column × 5-row grid divides the inner cavity dimensions evenly.
        # 2 vertical dividers (each thickness t) occupy 2t of the W width.
        # 4 horizontal dividers (each thickness t) occupy 4t of the H height.
        col_w = (W - 2 * t) / 3   # inner width of each of the 3 columns
        row_h = (H - 4 * t) / 5   # inner height of each of the 5 rows

        # --- Crossing slot edges ------------------------------------------------
        # Vertical dividers span H and use 'f' sections (connecting to base plate)
        # separated by Slot notches of depth h/2 at the 4 horizontal crossing
        # positions.  The slot is cut from the BOTTOM of the flat panel, so when
        # the divider stands upright the notch opens upward from the base.
        e_vert_bot = edges.SlottedEdge(self, [row_h] * 5, 'f', slots=h / 2)

        # Horizontal dividers span W and use plain 'e' sections on their top edge
        # separated by Slot notches of depth h/2 at the 2 vertical crossing
        # positions.  The slot is cut from the TOP of the flat panel; when the
        # divider stands upright it opens downward from the top, meshing with the
        # vertical divider's bottom slot at the h/2 midpoint.
        e_horiz_top = edges.SlottedEdge(self, [col_w] * 3, 'e', slots=h / 2)

        # Horizontal divider bottom: 'f' sections connect to base plate at the
        # three col_w spans; crossing positions use plain 'e' (no tabs there since
        # vertical dividers occupy that material).
        e_horiz_bot = edges.SlottedEdge(self, [col_w] * 3, 'f')

        # --- fingerHoles callbacks ----------------------------------------------
        # Each outer wall's callback is called once (at edge-0, bottom) by cc().
        # Passing a single-element list [fn] means cc() fires fn only for i=0;
        # for i=1,2,3 the IndexError fallthrough leaves the wall face untouched.

        # Short outer walls (W × h): two vertical dividers pass through.
        # Vertical divider 1 is centred at col_w + t/2 along W.
        # Vertical divider 2 is centred at 2·col_w + 3t/2 along W.
        # fingerHolesAt(x, 0, h, 90): holes at x from inner-left, going up h.
        def short_wall_cb():
            self.fingerHolesAt(col_w + t / 2,           0, h, 90)
            self.fingerHolesAt(2 * col_w + 3 * t / 2,   0, h, 90)

        # Long outer walls (H × h): four horizontal dividers pass through.
        # Divider i is centred at (i+1)·row_h + (2i+1)·t/2 along H (i = 0..3).
        def long_wall_cb():
            for i in range(4):
                pos = (i + 1) * row_h + (2 * i + 1) * t / 2
                self.fingerHolesAt(pos, 0, h, 90)

        # Base plate ((W+2t) × (H+2t)): fingerHoles for all six dividers.
        # At callback-0 the turtle sits at the inner-bottom-left corner of the
        # base face; x is measured along W, y along H (angle 90 = turn upward).
        #
        # Vertical dividers: 5 'f' sections each of length row_h, spaced row_h+t
        # apart in the H direction; centred at col_w+t/2 and 2·col_w+3t/2 in W.
        #
        # Horizontal dividers: 3 'f' sections each of length col_w, spaced col_w+t
        # apart in the W direction; centred at (i+1)·row_h+(2i+1)·t/2 in H.
        def base_cb():
            # Vertical divider fingerHoles (angle=90 → drawn along H direction).
            for i in range(2):
                x_c = (i + 1) * col_w + (2 * i + 1) * t / 2
                for j in range(5):
                    self.fingerHolesAt(x_c, j * (row_h + t), row_h, 90)
            # Horizontal divider fingerHoles (angle=0 → drawn along W direction).
            for i in range(4):
                y_c = (i + 1) * row_h + (2 * i + 1) * t / 2
                for j in range(3):
                    self.fingerHolesAt(j * (col_w + t), y_c, col_w, 0)

        # --- Outer walls --------------------------------------------------------
        # Short walls (front/back, spanning W) provide tabs on their small
        # (height-direction) edges — 'f' on left and right.
        # Long walls (left/right, spanning H) receive those tabs via 'F' slots
        # on their small (height-direction) edges.
        #
        # Edge string breakdown:
        #   "ffef": [bottom='f', right='f', top='e', left='f']  ← short walls
        #   "fFeF": [bottom='f', right='F', top='e', left='F']  ← long walls
        #
        # The short wall side-tabs ('f') project into the long wall end-slots ('F'),
        # creating flush corners where both outer faces are coplanar.
        # Both wall types use bottom='f' so their base-edge tabs slot into the
        # base plate's perimeter 'F' counter-part slots.
        # Top is left open ('e') — a lid can be added in a later phase.

        # Two short outer walls spanning the W (radius) axis — with vertical-divider holes.
        for _ in range(2):
            self.rectangularWall(W, h, "ffef",
                                 callback=[short_wall_cb], move="right")

        # Two long outer walls spanning the H (radius × √3) axis — with horizontal-divider holes.
        for _ in range(2):
            self.rectangularWall(H, h, "fFeF",
                                 callback=[long_wall_cb], move="right")

        # Advance the layout cursor to a fresh row below the wall panels.
        self.rectangularWall(1, h, "eeee", move="up only")

        # --- Base plate ---------------------------------------------------------
        # The base plate spans the full outer footprint of the box.
        # Each outer wall's bottom 'f' tabs extend t inward into the base perimeter,
        # so the base plate must be (W + 2t) wide and (H + 2t) deep.
        # 'F' (counter-part finger joint) on all four edges receives the wall tabs.
        # The base_cb callback adds fingerHoles for all six inner dividers.
        self.rectangularWall(W + 2 * t, H + 2 * t, "FFFF",
                             callback=[base_cb], move="right")

        # Advance cursor past the base plate row before drawing dividers.
        self.rectangularWall(1, H + 2 * t, "eeee", move="up only")

        # --- Vertical dividers --------------------------------------------------
        # Two panels spanning H (the long axis), creating the 3-column split.
        # Bottom edge: SlottedEdge with 5 'f' sections for base plate connection,
        # separated by 4 Slot notches (depth h/2) at the horizontal crossing points.
        # Left / right edges ('f'): end-tabs that seat into fingerHoles on the
        # two short outer walls.
        # Top edge ('e'): open — flush with the outer wall tops.
        for _ in range(2):
            self.rectangularWall(H, h,
                                 [e_vert_bot, 'f', 'e', 'f'],
                                 move="right")

        # Advance cursor past the vertical divider row.
        self.rectangularWall(1, h, "eeee", move="up only")

        # --- Horizontal dividers ------------------------------------------------
        # Four panels spanning W (the short axis), creating the 5-row split.
        # Bottom edge: SlottedEdge with 3 'f' sections for base plate connection,
        # plain 'e' (no slot, no tabs) at the 2 vertical crossing positions.
        # Top edge: SlottedEdge with 3 'e' sections and 2 Slot notches (depth h/2)
        # at vertical crossing positions — these interlock with the vertical
        # dividers' bottom slots at mid-height during assembly.
        # Left / right edges ('f'): end-tabs seating into fingerHoles on the long
        # outer walls.
        for _ in range(4):
            self.rectangularWall(W, h,
                                 [e_horiz_bot, 'f', e_horiz_top, 'f'],
                                 move="right")
