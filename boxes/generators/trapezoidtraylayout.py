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
from boxes import edges
import boxes

class TrapezoidTrayLayout(boxes.Boxes):
    """Trapezoid shaped type tray with sloped sides"""

    ui_group = "Tray"

    def __init__(self) -> None:
        boxes.Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings)
        # Remove x, y as we'll use back_length and side_length instead
        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--back_length", action="store", type=float, default=650.0,
            help="length of the back edge (longer base) in mm")
        self.argparser.add_argument(
            "--side_length", action="store", type=float, default=400.0,
            help="length of the side edges (legs) in mm")
        self.argparser.add_argument(
            "--angle", action="store", type=float, default=67.5,
            help="interior angle between back and side in degrees")
        self.argparser.add_argument(
            "--support_wing_length", action="store", type=float, default=75.0,
            help="length of the support wings perpendicular to side walls in mm")
        self.argparser.add_argument(
            "--support_wings_per_side", action="store", type=int, default=2,
            help="number of support wings per side")

    def render(self):
        """Renders an isosceles trapezoid tray with:
        - back_length: Length of longer parallel side
        - side_length: Length of angled sides (legs)
        - angle: Interior angle between back and legs
        """
        # Handle size adjustments if outside dimensions are specified
        h = self.adjustSize(self.h) if self.outside else self.h
        back_length = self.adjustSize(self.back_length) if self.outside else self.back_length
        side_length = self.adjustSize(self.side_length) if self.outside else self.side_length

        # Calculate front edge length using interior angle
        angle_rad = math.radians(self.angle)
        inward_distance = side_length * math.cos(angle_rad)
        front_length = back_length - (2 * inward_distance)

        # Begin the box rendering
        
        # Draw base plate as a separate object
        self.moveTo(0, 10)  # Add 10mm spacing to avoid burn guide overlap
        
        self.edges["f"](back_length)           # Back edge (slots)
        self.corner(180 - self.angle)          # Back right corner
        self.edges["f"](side_length)           # Right side (slots)
        self.corner(self.angle)                # Front right corner
        self.edges["f"](front_length)          # Front edge (slots)
        self.corner(self.angle)                # Front left corner
        self.edges["f"](side_length)           # Left side (slots)
        self.corner(180 - self.angle)          # Back left corner
        self.ctx.stroke()                      # End base plate path as separate object
        
        # Move down for walls
        self.moveTo(0, side_length + 20)
        
        # Calculate wing parameters
        wing_length = self.adjustSize(self.support_wing_length) if self.outside else self.support_wing_length
        wings_per_side = self.support_wings_per_side
        
        # Calculate positions for wing slots
        spacing = side_length / (wings_per_side + 1)
        
        def wing_hole_callback():
            """Create holes in the side walls for support wings.
            Wings are evenly distributed along the wall length (e.g., at 1/3 and 2/3 for 2 wings)
            and aligned with the nearest finger joint."""
            # Calculate ideal positions for wings
            target_positions = [
                side_length * ((i + 1) / (wings_per_side + 1))
                for i in range(wings_per_side)
            ]
            
            # Calculate all valid finger positions
            pattern_width = 2 * self.thickness  # finger + space width
            usable_length = side_length - 2 * self.thickness  # exclude edge spaces
            num_patterns = int(usable_length // pattern_width)
            finger_positions = [
                self.thickness + i * pattern_width + self.thickness/2  # start after first space
                for i in range(num_patterns)
                if self.thickness < (self.thickness + i * pattern_width) < (side_length - self.thickness)
            ]
            
            # Create holes at nearest valid finger positions
            for target in target_positions:
                pos = min(finger_positions, key=lambda x: abs(x - target))
                self.fingerHolesAt(pos - self.thickness/2, self.thickness/2, h - self.thickness, 90)
        
        # Generate walls in sequence
        self.rectangularWall(front_length, h, edges="FfFF", move="right")  # Front wall
        self.rectangularWall(side_length, h, edges="FfFF", callback=[wing_hole_callback], move="right")   # Right wall with wing holes
        self.rectangularWall(back_length, h, edges="FfFF", move="right")   # Back wall
        self.rectangularWall(side_length, h, edges="FfFF", callback=[wing_hole_callback], move="right")   # Left wall with wing holes
        
        # Move down and back for the support wings
        self.moveTo(0 - front_length - side_length - back_length - side_length - wing_length, h + 30)
        
        # Draw all wings in sequence
        for _ in range(wings_per_side * 2):  # Total number of wings (2 per side)
            # Use F edge on the long edges that slot into the walls
            # Use f edges on all corners to accept fingers rather than protrude them
            self.rectangularWall(wing_length, h, edges="ffff", move="right")
