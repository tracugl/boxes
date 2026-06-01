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
from boxes.Color import Color
from boxes.generators.flexbook import FlexBook


# Named cell-width aliases matching standard BattleTech miniature base sizes.
# Heavy/Assault mechs (King Crab, Atlas) typically sit on 60 mm bases; Medium
# and most Light mechs use 40 mm bases. Users can mix names with numeric
# widths in any row's cells string, e.g. ``"Heavy+Heavy+Medium+45"``.
NAMED_CELL_WIDTHS = {
    "heavy": 60.0,
    "assault": 60.0,   # alias — assault mechs share the heavy 60 mm base
    "medium": 40.0,
    "light": 30.0,
}


# Default BattleTech-themed cell layout for the three mech-tray rows. All
# three rows are padded out to a uniform outer width by the row's filler
# strip (see :meth:`_emit_mech_row` and the ``row_target_outer_width``
# parameter), so the assembled trays look matched inside the box even
# though each row holds a different mix of mech sizes.
DEFAULT_ROW_CELLS = (
    "Heavy+Heavy+Heavy+Heavy",                          # 4 heavies — a heavy lance
    "Heavy+Medium+Medium+Medium+Medium",                # 1 heavy + 4 mediums
    "Medium+Medium+Medium+Medium+Medium+Medium",        # 6 mediums
)


def _parse_cell_value(token):
    """Resolve a single token to a cell width in mm.

    Named aliases (``"Heavy"``, ``"Medium"``, ``"Light"``, ``"Assault"``)
    are matched case-insensitively against :data:`NAMED_CELL_WIDTHS`.
    Anything else is parsed as a float in millimetres, which lets users
    drop in non-standard widths (e.g. for custom-base minis) by writing
    a literal number.

    Args:
        token: Single cell specifier — a name or a numeric string.

    Returns:
        Cell width in mm.

    Raises:
        ValueError: If the token is neither a known name nor a float.
    """
    lower = token.lower()
    if lower in NAMED_CELL_WIDTHS:
        return NAMED_CELL_WIDTHS[lower]
    return float(token)


def _parse_cells(s):
    """Parse a row's cell-width string into a list of floats.

    The input string is a human-friendly list of cell widths. Both
    numeric values (in mm) and named mech-class aliases (``Heavy``,
    ``Medium``, ``Light``, ``Assault``) are accepted, and can be mixed.
    Four separator conventions are accepted so users can write whichever
    feels natural:

    * ``"Heavy+Medium+Medium"`` — plus-separated (BattleTech card convention)
    * ``"Heavy Medium Medium"`` — whitespace-separated (boxes-native sx convention)
    * ``"Heavy:Medium:Medium"`` — colon-separated (also boxes-native)
    * ``"Heavy*4"`` / ``"60*4"`` — repeat shorthand, expands to four copies

    An empty string (or any all-whitespace input) returns ``None``, which
    signals the caller that the row should be skipped at render time —
    that's how users disable a row without having to write a separate
    boolean toggle per row.

    Args:
        s: User-supplied cells string (e.g. ``"Heavy+Medium+Medium+40"``).

    Returns:
        A list of cell widths in mm, or ``None`` if the row is disabled.

    Raises:
        ValueError: If a token cannot be resolved to a width.
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
        # Repeat shorthand: "Heavy*4" or "60*4" → four copies of the value.
        # Parse the multiplier explicitly so we can reject malformed inputs
        # (e.g. "Heavy*x") with a clear error rather than nonsense output.
        if "*" in token:
            value_str, count_str = token.split("*", 1)
            cells.extend([_parse_cell_value(value_str)] * int(count_str))
        else:
            cells.append(_parse_cell_value(token))
    return cells


class _NotchedTopEdge(edges.BaseEdge):
    """A plain straight edge with a rectangular notch cut into one end.

    Used for the TOP edges of mech-row dividers and short walls. The
    notch is the size of the cross-row label strip (``notch_width`` x
    ``notch_depth``), and when the row is assembled, the strip drops
    into the notches of all the dividers + both short walls, sitting
    flush with the wall tops on its top face.

    The notch is at the START of the edge (= the corner where this
    edge begins, drawn in the rectangularWall path order), but
    OFFSET inward by ``notch_inset`` mm so there's a strip of wood
    between the notch's outer wall and the panel's adjacent edge.
    Without the inset, the notch's right wall would land exactly on
    the panel's right edge — two cut lines on top of each other,
    which doesn't laser-cut cleanly.

    For rectangularWall's TOP edge, the start corner is the panel's
    top-right when viewed in panel-local coords — the user installs
    all panels with this corner at the FRONT of the row so the
    notches align.
    """

    char = "_"
    description = "Top edge with rectangular notch for label-strip"

    def __init__(self, boxes_, settings, notch_width, notch_depth,
                 notch_inset=0.0):
        # `settings` is unused for this edge type (no finger geometry to
        # configure) but BaseEdge expects an argument so callers can pass
        # None and it just becomes a no-op slot.
        super().__init__(boxes_, settings)
        self.notch_width = notch_width
        self.notch_depth = notch_depth
        self.notch_inset = notch_inset

    def __call__(self, length, **kw):
        w = self.notch_width
        n = self.notch_depth
        d = self.notch_inset
        if w <= 0 or n <= 0 or length < d + w:
            # Degenerate inputs — fall back to a plain straight edge so the
            # panel still closes cleanly.
            self.edge(length)
            return
        # Polyline trace from the edge's start corner, heading along the
        # edge (in rectangularWall's TOP edge that's local -x world).
        # Sequence: walk `d` mm along the edge (the protective lip),
        # turn into panel (+90 CCW = down for top edge), walk `n` mm
        # INTO the panel, turn back along the edge direction (-90 CW),
        # walk `w` mm along the notch bottom, turn back UP OUT of the
        # panel (-90 CW), walk `n` mm back to edge level, turn to
        # resume along the edge (+90 CCW), walk the remaining
        # `length - d - w` mm to the other corner.
        self.polyline(d, 90, n, -90, w, -90, n, 90, length - d - w)


class BattletechCarryBox(FlexBook):
    """BattleTech-themed flex-spine carry book with map sleeve, mech rows, and utility tray."""

    ui_group = "FlexBox"

    description = """
A FlexBook sized for a BattleTech kit: paper hex maps slide into a glued sleeve
on the inside of one cover, up to three independent mech-tray rows hold the
miniatures (each row gets its own cell layout), and a small removable utility
tray rides along for dice and pens.

**Closure:** FlexBook's 7-piece sliding-pin latch hardware is suppressed. Apply
4× 8 mm × 3 mm neodymium disc magnets when assembling: glue one pair onto the
inside face of the front cover and one matching pair onto the inside face of
the latch wall. The generator etches alignment circles (faint blue ETCHING
strokes that the laser cutter engraves rather than cuts) on both panels at
the correct positions — centre a magnet on each etched circle, glue with
epoxy or CA, and the four magnets will line up across the closing seam.

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

        # Cover face = 266 × 311 mm. Sized so the default tray layout
        # fits in the back cover's usable rectangular area (= the area
        # inside the corner curves of the cover panel, where the trays
        # actually rest) with ~2 mm of total play in each direction.
        # The empirically-correct "available tray space" formula is
        # approximately:
        #     available_width  ≈ x − thickness     = 263 mm at default
        #     available_length ≈ h                 = 308 mm at default
        # — which is what a user sees when measuring the cover SVG with
        # the wall positions and corner radii subtracted, not the
        # cavity-between-wall-inner-faces I had been computing earlier.
        # With x=266 and h=311 the available space becomes 263 × 311 mm
        # vs the 261 × 309 mm tray stack, giving ~2 mm × ~2 mm play.
        # Map sleeve (230 × 280 mm internal) gets ~18 mm bezel along the
        # cover-width axis and ~15 mm along the cover-height axis.
        # Spine depth = 90 mm so the closed cavity (84 mm interior) holds a
        # 70 mm mech row + 10 mm map sleeve + ~4 mm clearance.
        self.buildArgParser(x=266.0, y=90.0, h=311.0)

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
        # Three independent rows, each with its own depth + cell layout.
        # Leave a cells string empty to skip that row entirely. row_height
        # is shared because the cavity has a single depth budget.
        #
        # Cells can be specified as named mech classes (Heavy=60 mm,
        # Medium=40 mm, Light=30 mm) or as numeric widths in mm, mixed
        # in any combination. By default every row is padded out to the
        # same outer width (``row_target_outer_width`` below) so the
        # trays look uniform inside the box even when one row holds 4
        # heavies (240 mm of cells) and another holds 6 mediums (also
        # 240 mm of cells but with 2 more dividers).
        self.argparser.add_argument(
            "--row_height", action="store", type=float, default=70.0,
            help="Shared interior height (mm) of every mech-tray row — the "
                 "vertical space inside each cell for the mech itself. "
                 "Internal dividers stop at this height.")
        self.argparser.add_argument(
            "--label_strip_depth", action="store", type=float, default=12.0,
            help="Depth (mm) of a name-plate strip recessed into the row "
                 "across the short walls and the internal dividers. Both "
                 "short walls and every divider get a rectangular notch "
                 "cut into their top edge (`label_strip_depth` wide x "
                 "`thickness` deep); the strip is a flat piece sized "
                 "floor_w x this depth x thickness that drops into these "
                 "notches from above. The strip's TOP face sits flush "
                 "with the wall tops — assembled row total height is "
                 "still exactly row_height, no protrusion above. The "
                 "front portion of each cell's open top is covered by "
                 "the strip; the BACK portion stays open for mech "
                 "insertion. Set to 0 to disable (no notches, no strip).")
        self.argparser.add_argument(
            "--row_target_outer_width", action="store", type=float, default=0.0,
            help="Target outer width (mm) for ALL mech-tray rows. Each row "
                 "with cells totalling LESS than this gets a filler strip "
                 "of empty floor at one end so all rows are the same "
                 "external size. The default (0) auto-computes this as the "
                 "widest enabled row's natural outer width — that way the "
                 "padding rescales automatically when you change thickness "
                 "or cell sizes. Set to a negative value to disable padding "
                 "entirely and let each row use its natural width.")
        for i in range(1, 4):
            self.argparser.add_argument(
                f"--row{i}_depth", action="store", type=float, default=80.0,
                help=f"Depth of mech-tray row {i} in mm "
                     f"(along the long cavity axis); rows are laid end-to-end")
            self.argparser.add_argument(
                f"--row{i}_cells", action="store", type=str,
                default=DEFAULT_ROW_CELLS[i - 1],
                help=f"Cell layout for row {i}. Mix named classes "
                     f"(Heavy=60mm, Medium=40mm, Light=30mm, Assault=60mm) "
                     f"with numeric widths, e.g. 'Heavy+Medium+Medium+40' "
                     f"or 'Heavy*4'. Leave empty to skip this row.")

        # ---- Magnet placement guides -----------------------------------
        # FlexBook's sliding-pin latch is suppressed (see the panel overrides
        # below). In its place we etch alignment marks for user-supplied disc
        # magnets: two pairs near the latch end of the book — one pair on the
        # inside of the front cover, one pair on the inside of the latch wall.
        # The marks are drawn in Color.ETCHING (a non-cutting blue stroke that
        # laser-cutter software interprets as engrave-only), so they appear as
        # surface engravings rather than holes through the wood.
        self.argparser.add_argument(
            "--magnet_diameter", action="store", type=float, default=8.0,
            help="Diameter (mm) of the disc magnets the user will glue at "
                 "assembly time — etched alignment circles are sized to match")
        self.argparser.add_argument(
            "--magnet_pair_spacing", action="store", type=float, default=120.0,
            help="Distance (mm) between the two magnet pairs along the latch "
                 "edge of the cover — larger = more grip across a heavier book")
        self.argparser.add_argument(
            "--magnet_edge_inset", action="store", type=float, default=10.0,
            help="Distance (mm) from the panel's outer edge to the magnet "
                 "centre. Should be at least magnet_diameter/2 + 2 mm so the "
                 "magnet body sits clear of the edge")

        # ---- Latch tabs / slots -----------------------------------------
        # Magnets alone resist vertical separation when the book is closed,
        # but they don't stop the cover from sliding laterally (e.g. in a
        # bag). Adding small mechanical tabs on the latch wall's top edge
        # that poke through matching slots in the cover locks the cover in
        # place: lift straight up to open, drop straight down (with magnetic
        # snap) to close. Tab height = thickness so each tab sits flush
        # with the cover's outer face — magnets still do all the holding.
        self.argparser.add_argument(
            "--latch_tab_count", action="store", type=int, default=2,
            help="Number of mechanical latch tabs along the lid-side edge "
                 "of the latch wall. 2 is enough to prevent rotation; 1 "
                 "allows the cover to pivot. 0 disables tabs entirely.")
        self.argparser.add_argument(
            "--latch_tab_width", action="store", type=float, default=10.0,
            help="Width (mm) of each latch tab along the closing seam. "
                 "Wider tabs are easier to align but more visible from "
                 "outside the cover.")
        self.argparser.add_argument(
            "--latch_tab_spacing", action="store", type=float, default=60.0,
            help="Distance (mm) between adjacent latch tab centres. "
                 "Pick a value smaller than magnet_pair_spacing so the tab "
                 "slots and magnet etchings don't collide on the cover.")
        self.argparser.add_argument(
            "--latch_tab_clearance", action="store", type=float, default=0.3,
            help="Per-side clearance (mm) between the latch tab and the "
                 "matching cover slot — accounts for laser kerf and "
                 "assembly tolerance. Total slot oversize is 2× this.")

        # ---- Utility tray -----------------------------------------------
        # A separate open-top finger-jointed box for dice/pens/tokens.
        # Default size is sized to sit at one end of the cavity floor
        # alongside ~3 rows × 80 mm depth (240 + 45 ≤ 295 - 6 = 289).
        self.argparser.add_argument(
            "--include_utility_tray", action="store", type=boolarg, default=True,
            help="Emit utility-tray parts: floor + lid + 1 long wall + "
                 "2 short walls. The OTHER long side is intentionally "
                 "open (drawer-style); items are accessed by pulling the "
                 "tray out and tipping it through the open long side.")
        self.argparser.add_argument(
            "--utility_tray_w", action="store", type=float, default=255.0,
            help="Internal width of the utility tray in mm. Default 255 "
                 "matches the mech row's interior so utility outer "
                 "width (= w + 2t) equals the row outer width, giving a "
                 "uniform side-to-side fit in the cavity.")
        self.argparser.add_argument(
            "--utility_tray_d", action="store", type=float, default=45.0,
            help="Internal depth of the utility tray in mm — also the "
                 "width of the drawer-style opening on one long side.")
        self.argparser.add_argument(
            "--utility_tray_h", action="store", type=float, default=30.0,
            help="Internal height (top-to-bottom) of the utility tray "
                 "in mm. Same axis as row_height for the mech rows.")

        # ---- Dice tower (in the spine) ---------------------------------
        # Turn the otherwise-wasted spine cavity into a small dice tower.
        # The spine forms a half-cylindrical pocket when the cover folds;
        # dice dropped through a hole in the TOP side-wall bulge fall down
        # the spine, bounce off finger-jointed ramps that slot through the
        # recess wall, and exit through a hole in the BOTTOM side-wall
        # bulge.
        self.argparser.add_argument(
            "--include_dice_tower", action="store", type=boolarg, default=True,
            help="Add dice entry/exit holes in the side walls and "
                 "finger-jointed deflector ramps that slot through the "
                 "recess wall, turning the spine into a small dice tower. "
                 "Disable to leave the side walls + recess wall as plain "
                 "panels.")
        self.argparser.add_argument(
            "--dice_hole_radius", action="store", type=float, default=20.0,
            help="Radius (mm) of the semicircular dice entry/exit hole "
                 "cut into each side-wall bulge. The semicircle's flat "
                 "side is the DIAMETER (= 2 * this value) and its curve "
                 "extends toward the bulge's outer edge. Default 20 mm "
                 "gives a 40 mm flat side — two 16 mm d6 dice exit "
                 "side by side with plenty of clearance. The wider "
                 "single opening lets dice fall out without having to "
                 "align with a small fixed hole. Set to 0 to disable "
                 "just the side-wall holes (ramps still emitted).")
        self.argparser.add_argument(
            "--dice_tower_ramp_count", action="store", type=int, default=2,
            help="Number of deflector ramps slotting through the recess "
                 "wall into the spine cavity. Each ramp angles inward off "
                 "the recess wall; consecutive ramps alternate slope so "
                 "dice zig-zag down. 0 disables the ramps (and the recess "
                 "wall stays as plain finger-jointed panel).")
        self.argparser.add_argument(
            "--dice_tower_ramp_angle", action="store", type=float, default=30.0,
            help="Angle (degrees from horizontal) of each ramp when "
                 "installed. 30 deg matches the default in boxes' built-in "
                 "DiceTower generator.")
        self.argparser.add_argument(
            "--dice_tower_ramp_length", action="store", type=float, default=50.0,
            help="Length (mm) of each ramp's TAB EDGE — the edge whose "
                 "finger tabs slot into the recess wall. Determines the "
                 "ramp's extent along the spine direction.")
        self.argparser.add_argument(
            "--dice_tower_ramp_width", action="store", type=float, default=30.0,
            help="Width (mm) of each ramp perpendicular to the tab edge — "
                 "how far the ramp protrudes into the spine cavity from "
                 "the recess wall. Should be less than spine radius "
                 "(y_spine / 2 = 45 mm by default) so the ramp doesn't "
                 "touch the flex.")

    # -----------------------------------------------------------------
    # Recess wall override (add floor-side finger teeth)
    # -----------------------------------------------------------------
    #
    # FlexBook's recess wall has plain `e` edges on both of its long
    # sides, leaving the wall floating between the side walls — held only
    # by its short edges into the side-wall surface holes. That's fine
    # for an empty box but too wobbly under three rows of mech-tray
    # weight at the spine end. We add finger teeth on the FLOOR-side
    # long edge so the wall is anchored to the back cover surface as
    # well (matching the latch wall, which already mates to the back
    # cover via the cover's left h-edge). The LID-side long edge stays
    # plain or, when ``--recess_wall`` is enabled, keeps the FlexBook
    # U-recess feature for easier in-box access.

    def flexBookRecessedWall(self, h, y, include_recess, callback=None, move=None):
        """Emit the spine-end wall with a finger-jointed floor-side edge.

        The FLOOR-side long edge (edge 2 in the path; the SVG-right side
        of this portrait panel) is upgraded from ``e`` to ``f`` so the
        wall's teeth slot into matching finger holes drilled in the back
        cover by :meth:`flexBookCover`. Everything else is verbatim from
        :meth:`FlexBook.flexBookRecessedWall`.
        """
        t = self.thickness
        tw, th = h, y + 2 * t

        if self.move(tw, th, move, True):
            return

        # Recess polyline parameters (preserved verbatim from FlexBook).
        cutout_radius = min(h / 4, y / 8)
        cutout_angle = 90
        cutout_predist = y * 0.2
        cutout_angle_dist = h / 2 - 2 * cutout_radius
        cutout_base_dist = y - (y * 0.4) - 4 * cutout_radius

        # If a dice tower is enabled, drill angled finger holes in the
        # recess wall's surface so the deflector ramps can slot through.
        # Each ramp's tab edge mates with one row of finger holes — the
        # angle of the row determines the ramp's tilt when installed.
        # Consecutive ramps alternate angle direction so dice zig-zag
        # down the spine cavity.
        if self.include_dice_tower and self.dice_tower_ramp_count > 0:
            self._drill_recess_ramp_holes(h, y, t)

        self.moveTo(0, t)

        self.edges["f"](h)
        self.corner(90)
        self.edges["f"](y)  # CHANGED: floor-side, was `e`, now `f` for back-cover mating
        self.corner(90)
        self.edges["f"](h)
        self.corner(90)
        if include_recess:
            self.polyline(
                cutout_predist,
                (cutout_angle, cutout_radius),
                cutout_angle_dist,
                (-cutout_angle, cutout_radius),
                cutout_base_dist,
                (-cutout_angle, cutout_radius),
                cutout_angle_dist,
                (cutout_angle, cutout_radius),
                cutout_predist)
        else:
            self.edges["e"](y)
        self.corner(90)

        self.move(tw, th, move)

    def _drill_recess_ramp_holes(self, wall_h, wall_y, t):
        """Drill angled finger-hole rows on the recess wall for dice-tower ramps.

        ``wall_h`` is the recess wall's short dimension (= spine depth,
        90 mm by default). ``wall_y`` is the wall's long dimension (=
        cover-height direction, 311 mm by default). Ramps are positioned
        along the long axis at evenly-spaced intervals; their tab rows are
        drilled at ``±dice_tower_ramp_angle`` degrees, alternating, so
        consecutive ramps slope opposite ways for the zig-zag.

        Called from :meth:`flexBookRecessedWall` BEFORE the panel outline
        is drawn — at that point the cursor is at the panel's natural
        origin (0, 0), so all hole coordinates are in panel-local frame
        with the panel rectangle spanning (0, t) to (h, t + y).
        """
        n = self.dice_tower_ramp_count
        ramp_len = self.dice_tower_ramp_length
        angle = self.dice_tower_ramp_angle

        # Evenly space the ramps along the wall's long axis, leaving a
        # ~10 mm clearance at each end of the wall so dice can enter and
        # exit the spine cavity without immediately hitting a ramp.
        end_clearance = 10.0
        usable = wall_y - 2 * end_clearance
        if n == 1:
            positions_y = [t + end_clearance + usable / 2]
        else:
            step = usable / (n - 1)
            positions_y = [t + end_clearance + i * step for i in range(n)]

        # X position: centre the ramp's tab line on the wall's short
        # axis. Each ramp is `ramp_len` long along its angle; the tab
        # line spans roughly the wall's middle so the ramp sticks out
        # toward the flex roughly perpendicular to the wall surface.
        centre_x = wall_h / 2.0

        for i, py in enumerate(positions_y):
            # Alternate angle sign so ramps zig-zag.
            tilt = angle if i % 2 == 0 else -angle
            # The fingerHolesAt start position is the LEFT end of the tab
            # row. Walk back by half the projected x/y to centre the row
            # on (centre_x, py).
            start_x = centre_x - (ramp_len / 2.0) * math.cos(math.radians(tilt))
            start_y = py - (ramp_len / 2.0) * math.sin(math.radians(tilt))
            self.fingerHolesAt(start_x, start_y, ramp_len, tilt)

    def flexBookSide(self, h, x, r, callback=None, move=None):
        """Emit the curved side wall, optionally with dice-tower holes.

        Copied verbatim from :meth:`FlexBook.flexBookSide` and extended
        with two circular through-holes in the half-disc bulge area. The
        bulge wraps over the spine cavity when the book is assembled; the
        two holes let the user drop dice into the spine from outside,
        with each hole sized to a single d6 (default 18 mm, fits a 16 mm
        die with 1 mm clearance per side). The same drilling runs on
        BOTH side walls — the user installs one as the top of the book
        (entry) and the other as the bottom (exit) when storing the
        book upright on a shelf.
        """
        t = self.thickness

        tw, th = h + t, x + 2 * t + r
        if self.move(tw, th, move, True):
            return

        # Inherited finger holes for end-wall mating (recess + latch walls).
        self.fingerHolesAt(0, x + 1.5 * t, h, 0)

        # Dice entry/exit hole — a single SEMICIRCLE cut into the bulge.
        # The bulge is centred at panel-local (h/2, x + 2t) with radius
        # r (= spine_radius); the semicircle is placed with its FLAT
        # side toward the main side-wall body and its CURVE extending
        # toward the bulge's outer edge. Compared with two separate
        # circular holes, the wider continuous opening means dice don't
        # need to align with a fixed centre to fall through — they can
        # exit anywhere along the flat side, making the bottom-of-spine
        # exit feel less restrictive.
        if self.include_dice_tower and self.dice_hole_radius > 0:
            cx_mid = h / 2.0
            hr = self.dice_hole_radius
            # Leave ~4 mm of bulge wood between the semicircle's apex
            # and the bulge's outer curve so the curved edge stays
            # structurally sound. The bulge apex is at panel-y =
            # (x + 2t) + r; the semicircle apex is `flat_y + hr` so:
            apex_clearance = 4.0
            flat_y = (x + 2 * t) + r - apex_clearance - hr
            self._semicircle_hole(cx_mid, flat_y, hr)

        self.edges["F"](h)
        self.corner(90, 0)
        self.edges["e"](t)
        self.edges["f"](x + t)
        self.corner(180, r)
        self.edges["e"](x + 2 * t)
        self.corner(90)

        self.move(tw, th, move)

    # -----------------------------------------------------------------
    # FlexBook panel overrides (suppress latch cuts)
    # -----------------------------------------------------------------
    #
    # FlexBook's stock latch is a 7-piece sliding-bolt assembly (4 brackets
    # + 1 stopper + 1 pin, plus the slot/anchor cuts in the cover and the
    # slot/U-notch cuts in the latch wall). For a carry-book this size and
    # weight it's both fiddly and out of proportion: the brackets are
    # 15 × 17 mm at t=3 mm and the pin slides parallel to the cover (easy
    # to dislodge in a bag). We swap the whole thing for two pairs of
    # user-supplied self-adhesive disc magnets glued to the inner faces at
    # assembly time — see this class's docstring/description.
    #
    # That requires:
    #   * skipping the 4 brackets + stopper + pin parts at render time
    #     (see the overridden :meth:`render` below);
    #   * omitting the 3 ``rectangularHole`` cuts that FlexBook places on
    #     the front cover for the pin slot + 2 bracket anchors
    #     (overridden :meth:`flexBookCover`);
    #   * omitting the pin-slot hole and bottom U-notch on the latch wall,
    #     leaving a plain finger-jointed rectangle (overridden
    #     :meth:`flexBookLatchWall`).
    #
    # The structural geometry — cover outline, wall sizes, finger joints —
    # is unchanged. We just remove subtractive cuts that no longer
    # correspond to any hardware in the new design.

    def _build_tabbed_edge_polyline(self, edge_length):
        """Return polyline args for an edge with outward tab protrusions.

        The polyline replaces a single :meth:`edges["e"]` call along the
        lid-side edge of the latch wall. It draws plain edge segments
        interspersed with rectangular tab extensions that stick OUT of the
        panel by ``thickness`` mm (so each tab sits flush with the cover's
        outer face when threaded through a matching slot in the cover at
        closing time).

        The caller is responsible for positioning the cursor at one end of
        the edge with its heading along the edge direction. The returned
        polyline list ends with a ``90`` corner that closes the panel
        outline, matching the convention used by the original FlexBook
        polyline replacement (see :mod:`boxes.generators.flexbook`).

        Args:
            edge_length: Total length of the lid-side edge in mm. Tabs are
                spaced evenly and centred on this edge.

        Returns:
            A flat list of alternating length/angle arguments suitable for
            passing to :meth:`polyline` via ``self.polyline(*args)``.
        """
        n = self.latch_tab_count
        tab_w = self.latch_tab_width
        tab_spacing = self.latch_tab_spacing
        t = self.thickness

        # Degenerate cases — draw a plain edge with no tabs.
        if n <= 0 or tab_w <= 0:
            return [edge_length, 90]

        # Compute tab centre positions along the edge, evenly spaced and
        # symmetric around the midpoint. With n=2 and spacing=60, this gives
        # centres at (length/2 - 30) and (length/2 + 30).
        tab_centres = [
            edge_length / 2 + (k - (n - 1) / 2) * tab_spacing
            for k in range(n)
        ]

        # Between-tab segments: leading segment, gaps between consecutive
        # tabs, and the trailing segment. Each tab consumes `tab_w` of edge
        # length itself (drawn during the tab's outer-edge segment).
        segments = []
        cursor_pos = 0
        for tc in tab_centres:
            tab_start = tc - tab_w / 2
            segments.append(tab_start - cursor_pos)
            cursor_pos = tc + tab_w / 2
        segments.append(edge_length - cursor_pos)

        # Tab excursion sequence — turn out of the panel, walk along the
        # tab's outer edge, turn back in. For a cursor walking along the
        # edge in its forward direction with the panel interior on its
        # LEFT, this sequence is: -90 (right turn out), t (out), +90 (turn
        # parallel to edge), tab_w (along tab top), +90 (turn back toward
        # panel), t (in), -90 (back to original heading).
        tab_excursion = [-90, t, 90, tab_w, 90, t, -90]

        # Build the full polyline: leading segment, then for each tab the
        # excursion followed by the next segment. Finish with the closing
        # 90° corner to bring the path back to its starting heading.
        args = [segments[0]]
        for i in range(n):
            args.extend(tab_excursion)
            args.append(segments[i + 1])
        args.append(90)
        return args

    def flexBookCover(self, move=None):
        """Emit the cover panel without FlexBook's latch slot or anchor holes.

        This is a verbatim copy of :meth:`FlexBook.flexBookCover` with the
        three ``rectangularHole`` calls removed — those holes were the pin
        slot and the two square anchor holes for the under-cover latch
        brackets. With the magnet-based closure they have no purpose.
        """
        x, y = self.x, self.y
        c4 = self.c4
        t = self.thickness

        tw = 2 * x + 6 * t + 2 * c4 + t
        th = y + 4 * t

        if self.move(tw, th, move, True):
            return

        # Drill finger holes in the back cover for the recess wall's teeth.
        # The recess wall stands at the spine end of the back cover (just
        # before the flex hinge); its newly-finger-jointed FLOOR-side edge
        # (see :meth:`flexBookRecessedWall` override) slots into these
        # holes. The position uses the same inset convention as the
        # standard h-edge — burn + edge_width + thickness/2 inward from
        # the wood edge — so the joint geometry matches the cover's other
        # finger-hole edges exactly. We read ``edge_width`` from the live
        # FingerJoint settings instead of hardcoding the library default
        # (1.0 mm) so users who customise --FingerJoint_edge_width get
        # correctly-positioned holes too. Length y matches the wall's
        # long edge. We do this BEFORE moveTo because the cursor is still
        # at the panel's natural origin (0, 0); fingerHolesAt is wrapped
        # in saved_context so it won't disturb the cursor for the
        # subsequent path drawing.
        edge_width = self.edges["f"].settings.edge_width
        recess_wall_inset = self.burn + edge_width + t / 2
        back_cover_spine_x = 2 * t + (x + t)  # right edge of the back cover area
        self.fingerHolesAt(back_cover_spine_x - recess_wall_inset, 2 * t, y, 90)

        self.moveTo(2 * t, 0)

        self.edges["h"](x + t)
        self.edges["X"](2 * c4 + t, y + 4 * t)  # flex spine
        self.edges["e"](x + t)
        self.corner(90, 2 * t)
        self.edges["e"](y / 2)
        # FlexBook drills three rectangular holes here for the latch hardware
        # (pin slot + 2 anchor holes). We replace them with:
        #   * Etched alignment circles for user-applied disc magnets, and
        #   * Through-cut rectangular slots that receive the latch tabs on
        #     the latch wall's lid-side edge.
        #
        # Coordinate frame: the cursor is at the midpoint of the cover's
        # latch-end edge, facing along the edge (heading is +y world UP).
        # Local +x is the cursor's heading; local +y is 90° CCW from
        # heading (boxes convention — the arc-centre of a +90 corner lies
        # in local +y direction, which is LEFT of motion). For this cursor
        # that puts local +y at -x world — i.e. INTO the cover panel,
        # away from the latch edge. So positive LY values move INTO the
        # panel; that's where we want both the magnet etchings and the
        # through-slots that receive the latch wall's tabs.
        half_span = self.magnet_pair_spacing / 2
        # Magnets: ±magnet_pair_spacing/2 along the edge, magnet_edge_inset
        # INTO the panel.
        self.regularPolygonHole(
            +half_span, self.magnet_edge_inset,
            d=self.magnet_diameter, n=24, color=Color.ETCHING)
        self.regularPolygonHole(
            -half_span, self.magnet_edge_inset,
            d=self.magnet_diameter, n=24, color=Color.ETCHING)
        # Latch slots: ±latch_tab_spacing/2 along the edge, centred 1.5×t
        # INTO the panel so each slot sits over the centre of the latch
        # wall's thickness when closed (the wall is t mm thick; its outer
        # face aligns with the cover's latch-end edge, so its mid-thickness
        # is at +1.5×t INTO the cover). Slot dimensions match the tab plus
        # `latch_tab_clearance` per side for kerf and assembly tolerance.
        # Tab offsets here match the offsets computed inside
        # :meth:`_build_tabbed_edge_polyline` so the slots and tabs always
        # align exactly when the book closes.
        if self.latch_tab_count > 0:
            slot_dx = self.latch_tab_width + 2 * self.latch_tab_clearance
            slot_dy = t + 2 * self.latch_tab_clearance
            for k in range(self.latch_tab_count):
                offset = (k - (self.latch_tab_count - 1) / 2) * self.latch_tab_spacing
                self.rectangularHole(offset, 1.5 * t, slot_dx, slot_dy)
        self.edges["e"](y / 2)
        self.corner(90, 2 * t)
        self.edges["e"](x + t + 2 * c4 + t)
        self.edges["h"](x + t)
        self.corner(90, 2 * t)
        self.edges["h"](y)
        self.corner(90, 2 * t)

        self.move(tw, th, move)

    def flexBookLatchWall(self, h, y, latchSize, callback=None, move=None):
        """Emit the latch-end wall with magnet markers and tab protrusions.

        FlexBook's version of this method drew a horizontal pin slot in the
        wall's surface and a U-shaped notch in the bottom edge — the
        sliding-bolt closure mechanism. We replace both with:

        * A FLAT plain-edge lid-side long edge so the closed cover lies
          flush against the wall's top (the wall is positioned with its
          lid-side edge facing up at assembly; the cover sits down on top).
        * Two (configurable) rectangular tab extensions protruding ``t``
          mm out of the panel on the lid-side edge. Each tab pokes through
          a matching slot in the cover, locking the cover laterally so it
          can't slide off in transit. Tab height == cover thickness so
          each tab sits flush with the cover's outer face when latched.
        * Two etched alignment circles inside the panel near the lid-side
          edge, indicating where the user glues disc magnets at assembly.

        Magnets handle the vertical hold-down; the tabs handle lateral
        location. ``latchSize`` is accepted for FlexBook signature parity
        but is unused.
        """
        del latchSize  # accepted for signature compatibility but unused
        t = self.thickness

        # FlexBook adjusts the panel's left margin by 3t when the opposite
        # wall isn't recessed (so the latch- and recess-side panels line
        # up in the SVG). The tab protrusions on the lid-side edge stick
        # OUT of the panel rectangle by ``t`` mm, so we widen the move
        # envelope by ``t`` to reserve space for them.
        tab_extent = t if self.latch_tab_count > 0 else 0
        if self.recess_wall:
            x_adjust = 0
        else:
            x_adjust = 3 * t

        tw, th = h + t + x_adjust + tab_extent, y + 2 * t

        if self.move(tw, th, move, True):
            return

        # Shift the panel's local origin right by ``tab_extent`` so tabs
        # extending leftward (in -x_world) still fall within the reserved
        # move envelope rather than overlapping the previous SVG panel.
        self.moveTo(x_adjust + tab_extent, t)

        # The four edges of the wall in the order they're drawn:
        #   1. bottom edge (length h):  short, mates with one side wall
        #   2. right edge  (length y):  long, the FLOOR-side of the wall
        #                               (`f` kept for parity with FlexBook;
        #                               vestigial under the magnet design)
        #   3. top edge    (length h):  short, mates with the other side wall
        #   4. left edge   (length y):  long, the LID-side of the wall
        #                               — drawn as a polyline with two tab
        #                               extensions sticking out (-x world)
        self.edges["f"](h)
        self.corner(90)
        self.edges["f"](y)
        self.corner(90)
        self.edges["f"](h)
        self.corner(90)
        # Magnet alignment circles, placed on the lid-side face just inside
        # the panel from the lid-side edge (the 4th edge, drawn next).
        # Cursor is at (x_adjust + tab_extent, t + y), heading -y world
        # (about to draw the left edge going DOWN). Local +x = heading
        # (-y world); local +y is 90° CCW from heading (boxes convention,
        # = +x world from this cursor), which points INTO the wall panel
        # from the lid-side edge. Positive LY therefore moves the marker
        # INTO the panel. The midpoint of the lid-side edge sits at +y/2
        # along the cursor's heading direction, so markers go at
        # local (y/2 ± half_span, +inset).
        half_span = self.magnet_pair_spacing / 2
        self.regularPolygonHole(
            y / 2 - half_span, self.magnet_edge_inset,
            d=self.magnet_diameter, n=24, color=Color.ETCHING)
        self.regularPolygonHole(
            y / 2 + half_span, self.magnet_edge_inset,
            d=self.magnet_diameter, n=24, color=Color.ETCHING)
        # Lid-side edge: a polyline with tab protrusions (or a plain edge
        # if `latch_tab_count == 0`). The polyline INCLUDES the final 90°
        # corner that closes the panel outline, so we don't add another
        # `self.corner(90)` after it.
        self.polyline(*self._build_tabbed_edge_polyline(y))

        self.move(tw, th, move)

    # -----------------------------------------------------------------
    # Part-emission helpers
    # -----------------------------------------------------------------

    def _semicircle_hole(self, x, y, r):
        """Cut a semicircular hole in the current panel.

        The semicircle's flat side is horizontal, with its midpoint at
        ``(x, y)`` in panel-local coordinates. The curve extends UPWARD
        by ``r`` mm — apex at ``(x, y + r)``, endpoints of the flat
        side at ``(x - r, y)`` and ``(x + r, y)``.

        Implementation uses cairo's arc primitive directly (the same
        approach :meth:`boxes.Boxes.hole` takes for full circles).
        boxes' ``polyline`` with a ``(180, r)`` corner-with-radius does
        NOT close back to the diameter's start — corner arcs are
        centred perpendicular to the heading, so a 180° turn lands the
        cursor offset by 2r in both directions rather than returning to
        the start. Using ``ctx.arc`` lets us put the arc centre at the
        midpoint of the diameter, which is what closes the half-disc.
        """
        # Finish any open path so this hole starts a fresh subpath.
        self.ctx.stroke()
        with self.saved_context():
            self.set_source_color(Color.INNER_CUT)
            # Translate the local frame so the centre of the diameter
            # is at the local origin. No rotation — boxes' internal
            # math convention (y-up) means a CCW arc from angle 0 to π
            # traces the UPPER half of the unit circle, which is the
            # half we want above the flat side.
            self.moveTo(x, y)
            # Right end of the diameter at (r, 0); arc CCW from there
            # through (0, r) up top to (-r, 0); then a straight
            # line_to back to (r, 0) forms the flat side of the
            # semicircle. boxes' Context wrapper has no close_path,
            # so we explicitly draw the closing segment.
            self.ctx.move_to(r, 0)
            self.ctx.arc(0, 0, r, 0, math.pi)
            self.ctx.line_to(r, 0)
            self.ctx.stroke()

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

    def _row_finger_holes_callback(self, cells, height):
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
            height: Length of each finger-hole row in mm. Pass the divider
                height (NOT the wall height) so the holes stop short of
                the wall top when called with a shorter height, leaving the
                label strip band unbroken.

        Returns:
            A callable suitable for the ``callback=[...]`` parameter of
            :meth:`rectangularWall`, or ``None`` if the row has no internal
            dividers (single cell ⇒ no holes needed).
        """
        if len(cells) <= 1:
            return None

        t = self.thickness

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

        Uniform width via filler strip
        ------------------------------
        If ``row_target_outer_width`` is set (default 261 mm) and the row's
        natural outer width is LESS than the target, the row's floor is
        extended at the trailing edge to make the outer dimensions match.
        The trailing extension is just empty floor — no extra divider —
        so a 4-heavy row (240 mm of cells + 5 walls = 255 mm natural) gets
        a 6 mm strip of unused floor at one end, ending up the same outer
        size as a 6-medium row (240 + 7 walls = 261 mm natural, no filler).
        This keeps the tray system visually uniform regardless of the cell
        mix.

        Args:
            cells: List of cell widths in mm (from :func:`_parse_cells`).
            depth: Depth of the row in mm (the dimension perpendicular to
                the cells, i.e. how far back a miniature can stand).
        """
        t = self.thickness
        # Wall and divider heights are both row_height. The label strip
        # (if any) is emitted as a SEPARATE flat piece below — it sits
        # on top of the assembled row's walls, not inside the cells,
        # so the cell interior keeps the user's full row_height.
        h = self.row_height
        # Each row's natural floor width = sum of cell widths + (N-1)
        # divider thicknesses. The outer dimensions add 2*t for the two
        # short walls flanking the floor along the cell-width axis.
        n = len(cells)
        natural_floor_w = sum(cells) + (n - 1) * t
        natural_outer_w = natural_floor_w + 2 * t

        # If a target outer width is set and the row's natural outer width
        # is narrower, extend the floor with an empty filler strip at the
        # trailing edge so all rows share the same external dimensions.
        # A target of <= 0 disables this behaviour and falls back to natural
        # widths per row (render() resolves the default 0 to the widest
        # row's natural outer before reaching here, so by this point the
        # value is either positive or explicitly negative). If the row is
        # wider than the target, we keep the natural width and warn —
        # clipping cells would be surprising.
        target_outer_w = getattr(self, "row_target_outer_width", 0.0) or 0.0
        if target_outer_w > 0 and target_outer_w >= natural_outer_w:
            floor_w = target_outer_w - 2 * t
        else:
            if target_outer_w > 0 and target_outer_w < natural_outer_w:
                print(
                    f"[BattletechCarryBox] WARNING: row natural outer width "
                    f"{natural_outer_w:.1f}mm exceeds row_target_outer_width "
                    f"{target_outer_w:.1f}mm; rendering at natural width."
                )
            floor_w = natural_floor_w

        # Finger hole callback drills divider mating holes in the long
        # walls, spanning the divider's full height.
        holes_cb = self._row_finger_holes_callback(cells, h)
        cb_list = [holes_cb] if holes_cb is not None else None

        # If a label strip is enabled, the short walls and the dividers
        # need a rectangular NOTCH cut into their top edges so the strip
        # drops in flush with the wall tops. The notch is the strip's
        # width (label_strip_depth) by `thickness` deep, offset by one
        # `thickness` inward from the panel's front-top corner — that
        # `thickness` lip of wood keeps the notch's outer wall from
        # landing on the panel's outer edge (which would create
        # double-cut artifacts at the corner). The strip itself
        # therefore sits `thickness` mm inset from the row's front face;
        # in exchange the cut path is clean.
        if self.label_strip_depth > 0:
            notched_top = _NotchedTopEdge(
                self, None, self.label_strip_depth, t,
                notch_inset=t)
            short_wall_edges = ["F", "f", notched_top, "F"]
            divider_edges = ["e", "f", notched_top, "f"]
        else:
            short_wall_edges = "FfeF"
            divider_edges = "efef"

        with self.saved_context():
            # Long walls (front + back of the row). Both get the divider
            # hole callback so dividers can slot into either side. NOT
            # notched — the strip runs perpendicular to these walls, so
            # its notches are cut into the panels that intersect it.
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

        # Short walls (left + right of the row). Top edges are notched
        # when a label strip is enabled so the strip's ends drop in.
        self.rectangularWall(
            depth, h, short_wall_edges, ignore_widths=[1, 6],
            move="up", label="row short wall")
        self.rectangularWall(
            depth, h, short_wall_edges, ignore_widths=[1, 6],
            move="up", label="row short wall")

        # Internal dividers — full row_height tall, slot into the long-wall
        # finger holes drilled by the callback above. Top edges are
        # notched when a label strip is enabled so the strip passes
        # through and rests on each divider's notch bottom.
        for _ in range(n - 1):
            self.rectangularWall(
                depth, h, divider_edges, move="up", label="row divider")

        # Optional label strip — a flat piece that drops INTO the notches
        # in the short walls + dividers. Sits flush with the wall tops
        # on its top face; supported by the notch bottoms underneath.
        # Length = floor_w (across the row from short wall to short
        # wall); width = label_strip_depth (the notch width); thickness
        # = the row's material thickness (= notch depth, so it fits).
        if self.label_strip_depth > 0:
            self.rectangularWall(
                floor_w, self.label_strip_depth, "eeee",
                move="up", label="row label strip")

    def _emit_utility_tray(self):
        """Emit a drawer-style enclosed utility tray.

        Unlike the open-top mech rows, the utility tray is CLOSED on its
        top face (a lid) and has its opening on ONE LONG SIDE. The user
        installs the tray with the open side facing whichever cavity
        edge will be "up" when the book is stored on a shelf — dice and
        small loose items can't spill out when looking down into the
        cavity (the lid blocks them), and when the book is upright the
        opening faces UP so gravity pulls items back into the closed
        bottom of the tray.

        Five pieces total (same count as the original open-top tray):

        * **Floor** (w × d, edges ``ffef``): tabs on three sides
          mating with the long wall + both short walls; the fourth
          edge is plain ``e`` because it sits at the open long side.
        * **Lid** (w × d, edges ``ffef``): mirror of the floor.
        * **Long wall** (1 piece, w × h, edges ``FFFF``): closed on
          all four edges (floor below, lid above, short walls on each
          end). The OTHER long wall is intentionally omitted — that's
          the drawer opening.
        * **Short walls** (2 pieces, d × h, edges ``FfFe``): tabs on
          three sides (floor + long wall + lid); the fourth edge is
          plain ``e`` because it sits at the open long side. The two
          short walls are identical pieces; the user installs one
          mirrored so both have their open edge at the same cavity end.
        """
        w = self.utility_tray_w
        d = self.utility_tray_d
        h = self.utility_tray_h

        with self.saved_context():
            # Floor — open on its top panel edge (= the long side that
            # will become the drawer opening when assembled).
            self.rectangularWall(w, d, "ffef", move="up",
                                 label="utility tray floor")
            # Lid — same edge spec as the floor; mirrors the floor at
            # the opposite vertical (lid covers the tray's top in 3D).
            self.rectangularWall(w, d, "ffef", move="up",
                                 label="utility tray lid")
            # Long wall (only ONE — the closed long side of the tray).
            # All four edges have finger joints since this wall mates
            # with the floor + lid + both short walls.
            self.rectangularWall(
                w, h, "FFFF", ignore_widths=[1, 6], move="up",
                label="utility tray long wall")

        # Park the cursor to the right of the column above.
        self.rectangularWall(w, h, "FFFF", move="right only")

        # Short walls — bottom mates with floor (F), one side mates
        # with the long wall (f), top mates with the lid (F), and the
        # other side is open (e). The two walls are mirror images in
        # the assembled tray; emitting them with the same edge spec
        # and flipping one during assembly avoids a second edge type.
        self.rectangularWall(
            d, h, "FfFe", ignore_widths=[1, 6], move="up",
            label="utility tray short wall")
        self.rectangularWall(
            d, h, "FfFe", ignore_widths=[1, 6], move="up",
            label="utility tray short wall")

    # -----------------------------------------------------------------
    # Render entry point
    # -----------------------------------------------------------------

    def render(self):
        """Render the book and all configured inserts to the SVG canvas.

        We do **not** call ``super().render()`` here. FlexBook.render() bakes
        in the 7-piece sliding-pin latch (4 brackets + stopper + pin emitted
        as parts, plus the slot/anchor cuts on the cover/wall). Replicating
        only the parts we want lets us swap in a magnet-based closure
        without inheriting any latch hardware.

        The y↔h swap and ``radius``/``c4`` derivation are reproduced from
        :meth:`FlexBook.render` so the cover/spine/side helpers see the same
        ``self.h`` and ``self.y`` they normally would. (FlexBook.render
        swaps these because the author found it easier to think about the
        spine depth as ``h`` and the cover height as ``y`` in the helpers.)
        """
        spine_depth = self.y
        t = self.thickness

        # Closed-book cavity depth = spine_depth - 2*thickness. The map
        # sleeve eats `map_sleeve_depth` of that, leaving the rest for
        # the mech rows. The label strip (if any) is RECESSED into the
        # row's top via notches in the short walls + dividers, so it
        # doesn't add to the row's total height. Warn (don't fail) if
        # the user's settings can't physically close the book — they
        # may be deliberately over-stuffing for a test print.
        cavity_depth = spine_depth - 2 * t
        sleeve_d = self.map_sleeve_depth if self.include_map_sleeve else 0.0
        budget = cavity_depth - sleeve_d - self.row_height
        if budget < 0:
            print(
                f"[BattletechCarryBox] WARNING: closed-book cavity is "
                f"{cavity_depth:.1f}mm but row_height ({self.row_height}) + "
                f"map_sleeve_depth ({sleeve_d}) = "
                f"{self.row_height + sleeve_d:.1f}mm. "
                f"Book will not close cleanly (over budget by {-budget:.1f}mm)."
            )

        # ---- 1. Replicate FlexBook's pre-render setup ------------------
        # Swap y and h on self so the inherited helpers (flexBookSide,
        # flexBookRecessedWall, our overridden flexBookCover and
        # flexBookLatchWall) see the same coordinate system they expect.
        new_y = self.h
        self.h = self.y
        self.y = new_y

        # Spine radius and quarter-arc length used by the cover's flex edge.
        self.radius = self.h / 2
        self.c4 = math.pi * self.radius * 0.5

        # FlexBook scales latchsize by thickness here; we keep the same
        # mutation for compatibility even though no parts read latchsize
        # in this generator (the override of flexBookLatchWall discards it).
        self.latchsize *= self.thickness

        # ---- 2. Emit the book panels (no latch hardware) ---------------
        # Cover, recess wall, latch wall, two sides. The cover and latch
        # wall use OUR overrides (which omit the latch cuts); the recess
        # wall and sides come straight from FlexBook unchanged.
        self.flexBookCover(move="up")
        self.flexBookRecessedWall(self.h, self.y, self.recess_wall, move="mirror right")
        self.flexBookLatchWall(self.h, self.y, self.latchsize, move="right")

        with self.saved_context():
            self.flexBookSide(self.h, self.x, self.radius, move="right")
            self.flexBookSide(self.h, self.x, self.radius, move="mirror right")
        self.flexBookSide(self.h, self.x, self.radius, move="up only")

        # FlexBook.render() now emits the 4 latch brackets, stopper plate,
        # and latch pin (flexbook.py:299-313). We intentionally skip all
        # of that — magnets glued at assembly time replace it.

        # ---- 3. Map sleeve (4 glue-assembled pieces) -------------------
        if self.include_map_sleeve:
            self._emit_map_sleeve()

        # ---- 4. Mech-tray rows ----------------------------------------
        # Each rowN_cells param is a string — parse it, and only emit a row
        # if the cells list is non-empty. This lets users disable rows by
        # clearing the cells field instead of needing a separate boolean
        # per row.
        #
        # Pre-pass: when row_target_outer_width == 0 (the default), compute
        # the target as the widest enabled row's natural outer width. This
        # keeps the uniform-width padding working when the user changes
        # thickness (which makes dividers wider and therefore changes the
        # natural outer widths) without needing to retune the target by
        # hand. A negative value leaves padding disabled.
        parsed_rows = []
        for i in range(1, 4):
            cells_str = getattr(self, f"row{i}_cells")
            depth = getattr(self, f"row{i}_depth")
            cells = _parse_cells(cells_str)
            if cells:
                parsed_rows.append((cells, depth))

        if self.row_target_outer_width == 0 and parsed_rows:
            self.row_target_outer_width = max(
                sum(cells) + (len(cells) + 1) * t
                for cells, _depth in parsed_rows
            )

        for cells, depth in parsed_rows:
            self._emit_mech_row(cells, depth)

        # ---- 5. Utility tray ------------------------------------------
        if self.include_utility_tray:
            self._emit_utility_tray()

        # ---- 6. Dice-tower ramps --------------------------------------
        # One flat panel per ramp, sized
        # ramp_length (tab-edge) x ramp_width (projects into the spine).
        # Tab edge is `f` so it mates with the angled finger holes the
        # recess wall override drilled; other 3 edges are plain `e` (the
        # ramp is cantilevered from the recess wall on its tab edge
        # only). Side-wall dice holes are drilled inside flexBookSide
        # above; no separate part for those.
        if (self.include_dice_tower
                and self.dice_tower_ramp_count > 0
                and self.dice_tower_ramp_length > 0
                and self.dice_tower_ramp_width > 0):
            for _ in range(self.dice_tower_ramp_count):
                self.rectangularWall(
                    self.dice_tower_ramp_length,
                    self.dice_tower_ramp_width,
                    "feee",
                    move="up", label="dice tower ramp")
