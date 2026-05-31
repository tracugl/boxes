# Copyright (C) 2026
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

"""
BattletechCarryBox generator.

A FlexBook-style living-hinge book sized to carry BattleTech miniatures,
paper maps, and accessories. Subclasses :class:`FlexBook` to inherit the
book/cover/spine/latch panel drawing helpers, then bolts on three extra
part groups in :meth:`render`:

1. **Map sleeve** — a flat, glue-assembled pocket fixed to the inside of one
   cover that holds paper hex maps.
2. **Mech-tray rows** — up to three independently liftable finger-jointed
   open-top boxes, each with its own slot-in dividers, so different cell
   widths can coexist (e.g. 60 mm cells for assault mechs + 40 mm cells for
   lights).
3. **Utility tray** — a small open-top box for dice, tokens, and pens.

Every dimension is exposed as an argparser argument so the box can be
re-rendered for different mini sizes, paper sizes, or row counts.
"""

from boxes import *  # noqa: F401, F403 — boxes idiom: imports Boxes, edges, boolarg, math, etc.
from boxes.generators.flexbook import FlexBook


# Default BattleTech-themed cell layout for the three mech-tray rows.
# Row 1 holds four assault mechs (60 mm cells; King Crab fits at 60 mm).
# Row 2 holds four mediums plus one heavy (mixed 40/60 mm cells).
# Row 3 holds six lights (uniform 40 mm cells).
DEFAULT_ROW_CELLS = (
    "60+60+60+60",
    "40+40+40+40+60",
    "40+40+40+40+40+40",
)


def _parse_cells(s):
    """Parse a row's cell-width string into a list of floats.

    The input string is a human-friendly list of cell widths in mm.
    Three separator conventions are accepted so users can write whichever
    feels natural:

    * ``"60+40+40+40"`` — plus-separated (BattleTech card convention)
    * ``"60 40 40 40"`` — whitespace-separated (boxes-native sx convention)
    * ``"60:40:40:40"`` — colon-separated (also boxes-native)
    * ``"60*4"``         — repeat shorthand (boxes-native), expands to ``[60,60,60,60]``

    An empty string (or any all-whitespace input) returns ``None``, which
    signals the caller that the row should be skipped at render time —
    that's how users disable a row without having to write a separate
    boolean toggle per row.

    Args:
        s: User-supplied cells string (e.g. ``"60+40+40+40"``).

    Returns:
        A list of cell widths in mm, or ``None`` if the row is disabled.

    Raises:
        ValueError: If a token cannot be parsed as a float.
    """
    if s is None:
        return None
    stripped = s.strip()
    if not stripped:
        return None

    # Normalise: '+' is the most common user-facing separator but the boxes
    # library's argparseSections only knows whitespace and ':'. Convert '+'
    # to a space so we can lean on the same lexing pattern (split on either)
    # before parsing each token, which keeps the parse surface tiny.
    normalised = stripped.replace("+", " ").replace(":", " ")

    cells = []
    for token in normalised.split():
        # Repeat shorthand: "60*4" → four 60mm cells. Parse the multiplier
        # explicitly so we can reject malformed inputs (e.g. "60*x") with a
        # clear error rather than producing nonsense floats.
        if "*" in token:
            value_str, count_str = token.split("*", 1)
            cells.extend([float(value_str)] * int(count_str))
        else:
            cells.append(float(token))
    return cells


class BattletechCarryBox(FlexBook):
    """BattleTech-themed flex-spine carry book with map sleeve, mech rows, and utility tray."""

    ui_group = "FlexBox"

    description = """
A FlexBook sized for a BattleTech kit: paper hex maps slide into a glued sleeve
on the inside of one cover, up to three independent mech-tray rows hold the
miniatures (each row gets its own cell layout), and a small removable utility
tray rides along for dice and pens.

Override `inner depth in mm` (the `y` parameter) if your tallest mech is taller
than the default 70 mm row height — the closed-book cavity must satisfy
`y - 2*thickness >= row_height + map_sleeve_depth`.
"""

    def __init__(self) -> None:
        # We deliberately skip FlexBook.__init__ and call Boxes.__init__
        # directly. FlexBook's __init__ calls buildArgParser with its own
        # defaults (x=75, y=35, h=125), and buildArgParser can only run
        # once per generator. Re-doing the setup here lets us register the
        # same FingerJoint + Flex edge settings, supply BattleTech-sized
        # defaults, and add our own arguments — all in one pass.
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings)
        self.addSettingsArgs(edges.FlexSettings)

        # Cover face = 245 × 295 mm (fits a 230×280 mm map sleeve with bezel).
        # Spine depth = 90 mm so the closed cavity (84 mm interior) holds a
        # 70 mm mech row + 10 mm map sleeve + ~4 mm clearance.
        self.buildArgParser(x=245.0, y=90.0, h=295.0)

        # FlexBook's own per-instance args — duplicated here because we
        # bypassed its __init__. Keep the help strings identical so the UI
        # form reads the same as the parent FlexBook page.
        self.argparser.add_argument(
            "--latchsize", action="store", type=float, default=8,
            help="size of latch in multiples of thickness")
        self.argparser.add_argument(
            "--recess_wall", action="store", type=boolarg, default=False,
            help="Whether to recess the inner wall for easier object removal")

        # ---- Map sleeve --------------------------------------------------
        # Sized for one of the standard BattleTech hex map sheets (~22×28cm)
        # with a few mm of tolerance. Sleeve internal depth defaults to 10mm
        # which comfortably holds ~50 sheets of paper.
        self.argparser.add_argument(
            "--include_map_sleeve", action="store", type=boolarg, default=True,
            help="Emit map sleeve parts (1 inner face + 3 glue strips)")
        self.argparser.add_argument(
            "--map_sleeve_w", action="store", type=float, default=230.0,
            help="Internal width of the map sleeve in mm")
        self.argparser.add_argument(
            "--map_sleeve_h", action="store", type=float, default=280.0,
            help="Internal height of the map sleeve in mm")
        self.argparser.add_argument(
            "--map_sleeve_depth", action="store", type=float, default=10.0,
            help="Internal depth of the map sleeve in mm (paper-stack thickness)")

        # ---- Mech-tray rows ---------------------------------------------
        # Three independent rows, each with its own depth + cell-width
        # layout. Leave a cells string empty to skip that row entirely.
        # row_height is shared because the cavity has a single depth budget.
        self.argparser.add_argument(
            "--row_height", action="store", type=float, default=70.0,
            help="Shared interior height (mm) of every mech-tray row")
        for i in range(1, 4):
            self.argparser.add_argument(
                f"--row{i}_depth", action="store", type=float, default=80.0,
                help=f"Depth of mech-tray row {i} in mm "
                     f"(along the long cavity axis); rows are laid end-to-end")
            self.argparser.add_argument(
                f"--row{i}_cells", action="store", type=str,
                default=DEFAULT_ROW_CELLS[i - 1],
                help=f"Cell widths for row {i}, e.g. '60+40+40+40' or '60*1 40*3'. "
                     f"Leave empty to skip this row.")

        # ---- Utility tray -----------------------------------------------
        # A separate open-top finger-jointed box for dice/pens/tokens.
        # Default size is sized to sit at one end of the cavity floor
        # alongside ~3 rows × 80 mm depth (240 + 45 ≤ 295 - 6 = 289).
        self.argparser.add_argument(
            "--include_utility_tray", action="store", type=boolarg, default=True,
            help="Emit utility-tray parts (floor + 4 finger-jointed walls)")
        self.argparser.add_argument(
            "--utility_tray_w", action="store", type=float, default=240.0,
            help="Internal width of the utility tray in mm")
        self.argparser.add_argument(
            "--utility_tray_d", action="store", type=float, default=45.0,
            help="Internal depth of the utility tray in mm")
        self.argparser.add_argument(
            "--utility_tray_h", action="store", type=float, default=30.0,
            help="Internal height of the utility tray in mm")

    # -----------------------------------------------------------------
    # Part-emission helpers
    # -----------------------------------------------------------------

    def _emit_map_sleeve(self):
        """Emit the four flat pieces that glue into the map sleeve.

        The sleeve is a thin pocket: one inner face (sits flush against
        the inside of a cover) plus three narrow strip walls (top, bottom,
        and the spine-side end). The opposite short edge is intentionally
        left open so maps slide in and out when the book opens.

        All pieces use plain butt edges (``"eeee"``) because they are
        glue-assembled — no finger joints would survive the strip's narrow
        depth. The user is expected to clamp + glue the strips between the
        cover and the inner face.

        Outer dimensions:
        * Inner face: ``(map_sleeve_w + 2t)`` × ``(map_sleeve_h + 2t)`` —
          the +2t accounts for the surrounding strip walls so the maps
          fit the *internal* width/height the user specified.
        * Long strips (top, bottom): ``map_sleeve_depth`` × ``map_sleeve_h``
        * Short strip (spine-side end): ``map_sleeve_depth`` × ``map_sleeve_w``
        """
        t = self.thickness
        w = self.map_sleeve_w
        h = self.map_sleeve_h
        d = self.map_sleeve_depth

        # Inner face that sits against the cover.
        self.rectangularWall(w + 2 * t, h + 2 * t, "eeee", move="up",
                             label="map sleeve face")

        # Two long strips (top + bottom of the sleeve, parallel to the cover height).
        self.rectangularWall(d, h, "eeee", move="up", label="map sleeve strip (long)")
        self.rectangularWall(d, h, "eeee", move="up", label="map sleeve strip (long)")

        # One short strip on the spine side — the opposite short side is left open.
        self.rectangularWall(d, w, "eeee", move="up", label="map sleeve strip (short)")

    def _row_finger_holes_callback(self, cells):
        """Build a callback that drills finger holes for slot-in dividers.

        For a row of N cells we need N-1 internal dividers. Each divider
        slots into both long walls (the front and back of the row), which
        means each long wall needs N-1 vertical rows of finger-hole slots
        cut into its inner face.

        The callback walks along the long wall left-to-right, advancing by
        ``cell_width + thickness`` after each cell (the +t accounts for the
        space the divider itself occupies). The first ``-0.5t`` offset
        centres the first hole row in the gap between the outer wall and
        the first divider — without it the holes would sit on the divider
        edge instead of beside it.

        Args:
            cells: List of cell widths in mm for this row.

        Returns:
            A callable suitable for the ``callback=[...]`` parameter of
            :meth:`rectangularWall`, or ``None`` if the row has no internal
            dividers (single cell ⇒ no holes needed).
        """
        if len(cells) <= 1:
            return None

        t = self.thickness
        height = self.row_height

        def cb():
            pos = -0.5 * t
            # cells[:-1] because there are len(cells)-1 dividers — the last
            # cell has no divider to its right (the outer wall closes the row).
            for cell_w in cells[:-1]:
                pos += cell_w + t
                self.fingerHolesAt(pos, 0, height)

        return cb

    def _emit_mech_row(self, cells, depth):
        """Emit one mech-tray row as a freestanding open-top finger-jointed box.

        Each row consists of:

        * **Floor**: a single ``ffff`` plate that mates with the four walls.
        * **Two long walls** (front + back, span the full cell-width axis):
          finger-jointed on three sides (floor + both ends), open on top.
          Internal finger-hole rows are drilled via a callback so the
          divider tabs slot into the walls' inner face.
        * **Two short walls** (left + right, span the row depth axis):
          finger-jointed on three sides, open on top. No callback —
          dividers don't reach the short walls.
        * **N-1 dividers**: ``efef`` flat plates that drop vertically into
          the long-wall holes from above. Their bottom edge rests on the
          floor; their top edge is open.

        Edge convention matches ABox (see :mod:`boxes.generators.abox`) so
        the joints align with the rest of the library's geometry — long
        walls use ``F`` on their side edges, short walls use ``f``.

        Args:
            cells: List of cell widths in mm (from :func:`_parse_cells`).
            depth: Depth of the row in mm (the dimension perpendicular to
                the cells, i.e. how far back a miniature can stand).
        """
        t = self.thickness
        h = self.row_height
        # Total outer width = sum of cell widths + (N+1) wall/divider
        # thicknesses. There are N-1 internal dividers plus 2 outer side
        # walls = N+1 thicknesses of material along the width axis. But the
        # standard finger-joint geometry absorbs the outer walls' thickness
        # into the floor's mating fingers, so the floor itself is just
        # sum(cells) + (N-1)*t wide. We use that everywhere here.
        n = len(cells)
        floor_w = sum(cells) + (n - 1) * t

        holes_cb = self._row_finger_holes_callback(cells)
        cb_list = [holes_cb] if holes_cb is not None else None

        with self.saved_context():
            # Long walls (front + back of the row). Both get the divider
            # hole callback so dividers can slot into either side.
            self.rectangularWall(
                floor_w, h, "FFeF", callback=cb_list,
                ignore_widths=[1, 6], move="up", label="row long wall")
            self.rectangularWall(
                floor_w, h, "FFeF", callback=cb_list,
                ignore_widths=[1, 6], move="up", label="row long wall")

            # Floor — mates with all four walls.
            self.rectangularWall(floor_w, depth, "ffff", move="up", label="row floor")

        # Park the cursor to the right of the long-wall column so the next
        # parts don't overlap.
        self.rectangularWall(floor_w, h, "FFeF", move="right only")

        # Short walls (left + right of the row).
        self.rectangularWall(
            depth, h, "FfeF", ignore_widths=[1, 6], move="up", label="row short wall")
        self.rectangularWall(
            depth, h, "FfeF", ignore_widths=[1, 6], move="up", label="row short wall")

        # Internal dividers. Each has finger tabs on its left/right edges
        # that key into the long-wall holes drilled by the callback above.
        for _ in range(n - 1):
            self.rectangularWall(
                depth, h, "efef", move="up", label="row divider")

    def _emit_utility_tray(self):
        """Emit a simple open-top finger-jointed box for dice/pens/tokens.

        Same edge convention as :meth:`_emit_mech_row` but without any
        dividers. Five pieces total: one floor + two long walls + two
        short walls. Like a tiny ABox.
        """
        w = self.utility_tray_w
        d = self.utility_tray_d
        h = self.utility_tray_h

        with self.saved_context():
            self.rectangularWall(
                w, h, "FFeF", ignore_widths=[1, 6], move="up",
                label="utility tray long wall")
            self.rectangularWall(
                w, h, "FFeF", ignore_widths=[1, 6], move="up",
                label="utility tray long wall")
            self.rectangularWall(w, d, "ffff", move="up", label="utility tray floor")

        self.rectangularWall(w, h, "FFeF", move="right only")

        self.rectangularWall(
            d, h, "FfeF", ignore_widths=[1, 6], move="up",
            label="utility tray short wall")
        self.rectangularWall(
            d, h, "FfeF", ignore_widths=[1, 6], move="up",
            label="utility tray short wall")

    # -----------------------------------------------------------------
    # Render entry point
    # -----------------------------------------------------------------

    def render(self):
        """Render the book and all configured inserts to the SVG canvas.

        Order matters here: FlexBook.render() ends by mutating ``self.y``
        and ``self.h`` (the y↔h swap at flexbook.py:278-281) and by
        scaling ``self.latchsize`` by ``self.thickness``. We delegate to
        the parent first so that side-effect is contained, then read the
        post-swap dimensions to do our own sanity checks before emitting
        the insert parts.
        """
        # Stash the pre-swap values for the cavity sanity check below —
        # super().render() will swap y and h on self, so we need to capture
        # the user's input "y" (spine depth) before it gets renamed to h.
        spine_depth = self.y
        t = self.thickness

        # Closed-book cavity depth = spine_depth - 2*thickness. The map
        # sleeve eats `map_sleeve_depth` of that, leaving the rest for the
        # mech rows. Warn (don't fail) if the user's settings can't physically
        # close the book — they may be deliberately over-stuffing for a
        # test print.
        cavity_depth = spine_depth - 2 * t
        sleeve_d = self.map_sleeve_depth if self.include_map_sleeve else 0.0
        budget = cavity_depth - sleeve_d - self.row_height
        if budget < 0:
            print(
                f"[BattletechCarryBox] WARNING: closed-book cavity is "
                f"{cavity_depth:.1f}mm but row_height ({self.row_height}) + "
                f"map_sleeve_depth ({sleeve_d}) = {self.row_height + sleeve_d:.1f}mm. "
                f"Book will not close cleanly (over budget by {-budget:.1f}mm)."
            )

        # 1. Emit the book itself (cover + spine + sides + latch hardware).
        super().render()

        # 2. Map sleeve (4 glue-assembled pieces).
        if self.include_map_sleeve:
            self._emit_map_sleeve()

        # 3. Mech-tray rows. Each rowN_cells param is a string — parse it,
        #    and only emit a row if the cells list is non-empty. This lets
        #    users disable rows by clearing the cells field instead of
        #    needing a separate boolean per row.
        for i in range(1, 4):
            cells_str = getattr(self, f"row{i}_cells")
            depth = getattr(self, f"row{i}_depth")
            cells = _parse_cells(cells_str)
            if cells:
                self._emit_mech_row(cells, depth)

        # 4. Utility tray.
        if self.include_utility_tray:
            self._emit_utility_tray()
