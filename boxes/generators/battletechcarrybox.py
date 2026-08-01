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
   cover that holds paper hex maps, with a finger-pull notch at its mouth.
2. **Mech-tray rows** — up to three independently liftable finger-jointed
   open-top boxes, each with its own slot-in dividers, so different cell
   widths can coexist (e.g. 60 mm cells for assault mechs + 40 mm cells for
   lights).
3. **Utility tray** — a small open-top box for dice, tokens, and pens.

Every dimension is exposed as an argparser argument so the box can be
re-rendered for different mini sizes, paper sizes, or row counts.
"""

import logging
import textwrap

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
    "Medium+Medium+Heavy+Medium+Medium",                # 1 heavy, centred, + 4 mediums
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
        if d <= 0:
            # OPEN-CORNER form. With no lip there is no outer notch wall to
            # draw: the pen is already at notch-floor level, because the
            # preceding edge was wrapped in :class:`_ShortenedEdge` and
            # stopped `n` mm short of the corner. Drawing a wall here would
            # retrace the `n` mm of the preceding edge that we deliberately
            # gave up, cutting the same line twice.
            #
            # Sequence: walk `w` along the notch floor, turn OUT of the panel
            # (-90 CW), walk `n` back up to edge level, turn to resume along
            # the edge (+90 CCW), walk the remaining `length - w`.
            self.polyline(w, -90, n, 90, length - w)
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


class _ShortenedEdge(edges.BaseEdge):
    """Wraps another edge, drawing it a fixed amount shorter than asked.

    :meth:`Boxes.rectangularWall` decides every edge's length itself, so a
    panel feature that needs one side to stop short has no way to say so.
    This wrapper is that way: it passes ``length - shorten`` down to the edge
    it wraps and leaves everything else — joint geometry, widths, margins —
    untouched.

    Used for the corner where a label-strip notch sits flush, with no lip
    (``label_strip_inset = 0``). There the notch's outer wall would lie
    exactly on the adjacent edge's own line, so cutting both traces the same
    few millimetres twice. Shortening the adjacent edge by the notch depth
    lets :class:`_NotchedTopEdge` skip that wall entirely: the outline
    reaches the notch floor once and turns straight along it.

    The layout maths in ``rectangularWall`` reads ``spacing()``, which
    :class:`BaseEdge` derives from ``startWidth()`` and ``margin()`` — all
    three are delegated, so the part reserves its usual space on the sheet
    and simply comes out ``shorten`` mm shorter on this one side.
    """

    char = None
    description = "Edge drawn shorter than its nominal length"

    def __init__(self, boxes_, base, shorten) -> None:
        # `settings` is None: this wrapper has no geometry of its own, it only
        # rescales the call it forwards.
        super().__init__(boxes_, None)
        self.base = base
        self.shorten = shorten

    def __call__(self, length, **kw):
        self.base(max(0.0, length - self.shorten), **kw)

    def startWidth(self) -> float:
        return self.base.startWidth()

    def endWidth(self) -> float:
        return self.base.endWidth()

    def margin(self) -> float:
        return self.base.margin()


class _FingerPullEdge(edges.BaseEdge):
    """A plain straight edge with a semicircular bite out of its middle.

    Used on the two panels that would otherwise be impossible to get hold
    of: the utility tray lid's drawer-mouth edge, and one short edge of the
    map sleeve face. Both close onto their contents flush, with no proud
    surface or tab anywhere, so the notch is the only thing that gives a
    fingertip somewhere to hook. Which edge each panel puts it on is the
    caller's choice — see :meth:`BattletechCarryBox._finger_pull_edge`,
    which also clamps the radius to what the panel can spare.

    The cut is a true semicircle of ``radius`` mm sitting on the edge line:
    the mouth is ``2 * radius`` wide and the deepest point reaches
    ``radius`` mm into the panel. Both ends of the diameter are ordinary
    90 degree convex panel corners, so the panel outline stays one closed
    path and needs no separate hole cut.

    Drawn from the edge's start corner heading along the edge with the panel
    interior on the LEFT (:meth:`Boxes.rectangularWall` traverses its edges
    counter-clockwise), the trace is:

    1. straight run up to the notch mouth;
    2. ``+90`` to point INTO the panel (same sign convention as
       :class:`_NotchedTopEdge`);
    3. ``-180`` swept at ``radius`` — because the turn is to the right while
       the heading points inwards, the arc centre lands on the edge line and
       the semicircle bulges into the material;
    4. ``+90`` to resume the original heading, now ``2 * radius`` further
       along the edge;
    5. the matching straight run to the far corner.

    The three turns sum to zero, so the caller's heading is unchanged and the
    edge consumes exactly its nominal ``length``. Kerf compensation is
    :meth:`Boxes.corner`'s job: it shrinks the swept radius by ``burn`` for
    the concave arc and rounds the two convex corners by ``burn``, so the
    finished notch measures ``radius`` in the wood rather than in the path.
    """

    char = None
    description = "Straight edge with a central semicircular finger pull"

    def __init__(self, boxes_, settings, radius) -> None:
        # `settings` is unused — there is no finger geometry to configure —
        # but BaseEdge takes the slot, so callers pass None.
        super().__init__(boxes_, settings)
        self.radius = radius

    def __call__(self, length, **kw):
        r = self.radius
        # Straight run either side of the notch. Both are equal, which is
        # what centres the pull on the edge.
        run = (length - 2 * r) / 2
        if r <= 0 or run <= 0:
            # Radius disabled, or so large the notch would swallow the whole
            # edge (and with it the corners the adjacent joints rely on).
            # Fall back to a plain edge so the panel still closes cleanly;
            # the caller clamps and warns before it ever gets here.
            self.edge(length)
            return
        self.edge(run)
        self.corner(90)
        self.corner(-180, r)
        self.corner(90)
        self.edge(run)


class BattletechCarryBox(FlexBook):
    """BattleTech-themed flex-spine carry book with map sleeve, mech rows, and utility tray."""

    ui_group = "FlexBox"

    #: Floor on ``dice_hole_wall``, in mm. Stops a user-supplied 0 (or a
    #: negative) leaving the dice hole flush with the bulge's outer edge,
    #: which would cut the bulge open.
    DICE_HOLE_MIN_WALL = 1.0

    #: Wood left between a deflector ramp's inner tip and the living-hinge
    #: flex at the back of the spine, in mm. The ramp protrudes
    #: ``dice_tower_ramp_width`` into a cavity only ``y / 2`` deep, so on a
    #: shallow spine the ramp would otherwise press against — or cut through
    #: — the flex. Fixed rather than a UI parameter to keep the dice-tower
    #: option from growing yet another knob.
    DICE_RAMP_FLEX_CLEARANCE = 5.0

    #: Characters per line when warnings are wrapped onto the SVG canvas.
    WARNING_WRAP_COLUMNS = 96

    #: Font size (mm) for the on-canvas warning block. Larger than the 4 mm
    #: boxes uses for part labels, since the point is to be noticed.
    WARNING_FONTSIZE = 5.0

    description = """
A FlexBook sized for a BattleTech kit: paper hex maps slide into a glued sleeve
on the inside of one cover, up to three independent mech-tray rows hold the
miniatures (each row gets its own cell layout), and a small removable utility
tray rides along for dice and pens.

**Closure:** FlexBook's 7-piece sliding-pin latch hardware is suppressed, and
so is the magnet closure that replaced it. What holds the book shut is the row
of mechanical latch tabs on the latch wall, which poke up through matching
slots in the front cover: lift the cover straight up to open, drop it straight
down to close. The tabs locate the cover positively against sliding, so it
cannot shuffle off sideways in a bag, but nothing pulls the cover DOWN — there
is no sprung, magnetic, or friction catch. Held upside down and shaken, the
cover will come off. Add a strap, elastic, or your own magnets if you want a
positive hold; the panels are plain in that area, so there is room for any of
them.

**Latch doubler (thin material):** With `latch_doubler` enabled (default), an
extra plain-edged plate is emitted carrying the same latch-tab profile. Glue
it flat onto the inner (cavity-facing) face of the latch wall before assembly
so the tabs become double thickness (6 mm at 3 mm material) and don't snap.
The cover's tab slots are automatically widened to receive the thicker tabs.
Disable `latch_doubler` to return to a single-thickness latch with t-wide
slots.

Both pieces carry two matching Ø`latch_dowel_d` holes near the lid-side edge.
Push a dowel or drill blank through both before you clamp: nothing else holds
the doubler in register, and if it slides even a couple of mm while the glue is
wet the stacked tabs will miss the cover's slots and the latch won't close.
Pull the dowel once dry, or leave it in as a shear pin. Set `latch_dowel_d`
to 0 to omit the holes.

**Cover slot strength:** the tab slots are otherwise close to the cover's free
edge, leaving a thin bridge of wood that can snap. Two settings (both on by
default) reinforce it: `latch_cover_lip` extends the front cover into a small
overhanging lip past the latch wall and moves the slots inboard by the same
amount, widening that bridge (the lip also serves as a finger-pull); and
`latch_cover_reinforcement` emits a thin strip to glue onto the inner face of
the cover along the opening edge, flush with the free edge and just outboard of
the slots, doubling the bridge thickness. Set the lip to 0 and/or disable the
reinforcement to go back to edge-adjacent single-thickness slots.

**Finger pulls:** the map stack and the utility tray both sit flush with
nothing proud to grip, so each gets a semicircular notch to hook a fingertip
into. On the **utility tray lid** it is centred on the open (drawer-mouth)
edge. On the **map sleeve face** it is centred on one short edge — that notch
is what marks the sleeve's mouth, so glue the short strip along the *opposite*
short edge and install the sleeve with the notched end away from the spine.
Sizes come from `utility_tray_finger_hole_r` and `map_sleeve_finger_hole_r`
(radius in mm, so each mouth is twice that wide); set either to 0 for a plain
edge.

Override `inner depth in mm` (the `y` parameter) if your tallest mech is taller
than the default 55 mm row height. The tray heights are derived from `y`, so
that is the only number you need to change: `row_height` and `utility_tray_h`
both default to 0 = "work it out from the cavity", and grow or shrink with `y`
automatically. Set either to a positive value to pin it instead.
"""

    def __init__(self) -> None:
        # We deliberately skip FlexBook.__init__ and call Boxes.__init__
        # directly. FlexBook's __init__ calls buildArgParser with its own
        # defaults (x=75, y=35, h=125), and buildArgParser can only run
        # once per generator. Re-doing the setup here lets us register the
        # same FingerJoint + Flex edge settings, supply BattleTech-sized
        # defaults, and add our own arguments — all in one pass.
        Boxes.__init__(self)
        # Finger-joint geometry, all in multiples of `thickness`:
        #
        # `finger` / `space` = 4 (vs the library default 2) gives 12 mm
        # fingers separated by 12 mm gaps on 3 mm stock, roughly halving the
        # finger count per edge. Coarser teeth suit this box for three
        # reasons: the panels are long (a 261 mm row wall would otherwise
        # carry ~20 fingers), fewer/wider fingers mean fewer stress risers
        # and less charring on MDF, and wide slots are far easier to clear
        # of primer and to glue up cleanly than a dense comb.
        #
        # `play` = 0.2 (= 0.6 mm total slot clearance on 3 mm stock, ~0.3 mm
        # per side). The box is intended for 3 mm MDF that gets primed and
        # painted before assembly: `play` is the TOTAL finger-in-slot gap, so
        # it is split across both sides, and each side must swallow paint film
        # on BOTH the finger edge and the slot wall. MDF primer builds up
        # ~0.15-0.2 mm per absorbent cut edge, so some gap avoids having to
        # sand fuzzy fingers back. The design is glue-assembled, so the
        # residual gap after painting is exactly what the glue fills.
        # Override --FingerJoint_play / _finger / _space to tune.
        self.addSettingsArgs(edges.FingerJointSettings,
                             finger=4.0, space=4.0, play=0.2)
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
        # Spine depth = 75 mm so the closed cavity (69 mm interior) holds a
        # 10 mm map sleeve plus a 58 mm tray stack with 1 mm of slack. That
        # gives 55 mm of clearance above each tray floor, measured off the
        # tallest mech in a BattleTech box rather than guessed — the earlier
        # 90 mm spine carried 70 mm of clearance, i.e. 15 mm of dead air the
        # minis never used and the carrier had to be thick enough to hold.
        # The tray heights are DERIVED from this y — see
        # :meth:`_resolve_cavity_heights` — so changing y here (or in the UI)
        # resizes the rows and the utility tray to match.
        self.buildArgParser(x=266.0, y=75.0, h=311.0)

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
        self.argparser.add_argument(
            "--map_sleeve_finger_hole_r", action="store", type=float,
            default=25.0,
            help="Radius (mm) of the semicircular finger pull cut into one "
                 "SHORT edge of the map sleeve face — the edge at the open "
                 "mouth, opposite the short glue strip. A stack of paper "
                 "maps sits flush inside the pocket with no tab to grab, so "
                 "the notch is what lets you press a fingertip onto the top "
                 "sheet and slide the stack out. The mouth is twice this "
                 "wide and reaches this far down the face. The default 25 mm "
                 "is deliberately bigger than the tray lid's 15 mm: paper "
                 "has to be dragged out by friction against the top sheet "
                 "rather than hooked, so the opening wants a whole thumb "
                 "pad, not a fingertip. Set 0 for a plain edge. Values that "
                 "would leave less than two thicknesses of wood at the "
                 "face's corners are clamped, with a warning.")

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
            "--row_height", action="store", type=float, default=0.0,
            help="Shared interior height (mm) of every mech-tray row — the "
                 "vertical space inside each cell for the mech itself. "
                 "Internal dividers stop at this height. Leave at 0 to "
                 "derive it from the spine cavity: "
                 "`y - 2*thickness - map_sleeve_depth - thickness - "
                 "cavity_slack`, which is 55 mm at the default y = 75. "
                 "Deriving it means a change to `inner depth in mm` (y) "
                 "automatically resizes the trays to match. Set a positive "
                 "value to pin the height and ignore the cavity (a warning "
                 "is logged if it cannot close).")
        self.argparser.add_argument(
            "--cavity_slack", action="store", type=float, default=1.0,
            help="Clearance (mm) left along the spine-depth axis when "
                 "row_height / utility_tray_h are derived from y. Absorbs "
                 "paint film, glue squeeze-out and cover bow so the book "
                 "still closes. Only consulted for values left at 0.")
        self.argparser.add_argument(
            "--include_label_strip", action="store", type=boolarg, default=True,
            help="Recess a name-plate strip into the top of each mech row, "
                 "for writing or labelling which mech lives in which cell. "
                 "Disable to leave the short walls and dividers with plain "
                 "top edges and emit no strip.")
        self.argparser.add_argument(
            "--label_strip_depth", action="store", type=float, default=12.0,
            help="Depth (mm) of the name-plate strip, measured across the "
                 "row's depth axis. Both short walls and every divider get a "
                 "rectangular notch cut into their top edge (this wide x "
                 "`thickness` deep); the strip is a flat piece sized "
                 "floor_w x this depth x thickness that drops into those "
                 "notches from above. The strip's TOP face sits flush with "
                 "the wall tops — assembled row height is still exactly "
                 "row_height, no protrusion. The strip covers the front part "
                 "of each cell's open top; the BACK part stays open for "
                 "inserting the mech.")
        self.argparser.add_argument(
            "--label_strip_inset", action="store", type=float, default=3.0,
            help="Distance (mm) from the row's front edge to the near side "
                 "of the label strip — the lip of wood left in front of it. "
                 "0 puts the strip hard against the front edge with no lip, "
                 "which cuts fine but leaves the notch open at the corner, "
                 "so the strip is held only by friction against the panels "
                 "behind it. A few mm gives the notch a closed outer wall "
                 "and something for the strip to sit against. Increase to "
                 "move the strip back over the cells.")
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

        # ---- Latch tabs / slots -----------------------------------------
        # FlexBook's sliding-pin latch is suppressed (see the panel overrides
        # below) and so is the magnet closure that replaced it, which leaves
        # these tabs as the entire closure. Small mechanical tabs on the latch
        # wall's top edge poke through matching slots in the cover: lift the
        # cover straight up to open, drop it straight down to close. Tab
        # height = thickness so each tab sits flush with the cover's outer
        # face.
        #
        # Note what they do and don't do. They locate the cover positively
        # against SLIDING, so it can't shuffle off sideways in a bag. Nothing
        # pulls the cover DOWN — there is no catch of any kind — so an
        # inverted, shaken book will shed its cover. That is a deliberate
        # design choice, not an oversight; see the class description.
        self.argparser.add_argument(
            "--latch_tab_count", action="store", type=int, default=2,
            help="Number of mechanical latch tabs along the lid-side edge "
                 "of the latch wall. 2 is enough to prevent rotation; 1 "
                 "allows the cover to pivot. 0 disables tabs entirely.")
        self.argparser.add_argument(
            "--latch_tab_width", action="store", type=float, default=60.0,
            help="Width (mm) of each latch tab along the closing seam. "
                 "Wider tabs are easier to align but more visible from "
                 "outside the cover.")
        self.argparser.add_argument(
            "--latch_tab_spacing", action="store", type=float, default=120.0,
            help="Distance (mm) between adjacent latch tab centres. Wider "
                 "spacing resists twisting better; keep the outermost tab "
                 "clear of the cover's corners.")
        self.argparser.add_argument(
            "--latch_tab_clearance", action="store", type=float, default=0.3,
            help="Per-side clearance (mm) between the latch tab and the "
                 "matching cover slot — accounts for laser kerf and "
                 "assembly tolerance. Total slot oversize is 2× this.")
        self.argparser.add_argument(
            "--latch_doubler", action="store", type=boolarg, default=True,
            help="Emit a glue-on doubler plate that laminates onto the inner "
                 "(cavity-facing) face of the latch wall, carrying the SAME "
                 "tab profile so the latch tabs become 2× thickness "
                 "(e.g. 6 mm at 3 mm material) — much stronger against "
                 "snapping. When enabled, the cover's tab slots are "
                 "automatically widened and re-centred to receive the "
                 "doubled-thickness tabs. The doubler is a plain-edged "
                 "rectangle (no finger joints) sized to the latch wall's "
                 "footprint; it also stiffens the whole wall against "
                 "bending. Because the "
                 "doubler eats one thickness off the cavity's cell-width "
                 "axis, the cover (x) is automatically widened by one "
                 "thickness when this is on, so the trays keep their fit. "
                 "Disable to return to a single-thickness latch, t-wide "
                 "cover slots, and the un-widened cover.")
        self.argparser.add_argument(
            "--latch_dowel_d", action="store", type=float, default=6.0,
            help="Diameter (mm) of the two registration holes cut through "
                 "BOTH the latch wall and its doubler, at matching "
                 "positions. Drop a dowel or drill blank of this size "
                 "through both before clamping: nothing else locates the "
                 "two pieces during glue-up, and if they slide even a "
                 "couple of mm the stacked tabs no longer line up with the "
                 "cover's slots and the latch will not close. The dowel can "
                 "be pulled once the glue sets or left in as a shear pin. "
                 "Only cut when latch_doubler is on — with a single-piece "
                 "latch there is nothing to register, so the holes would be "
                 "pointless perforations. Set 0 to omit them.")
        self.argparser.add_argument(
            "--latch_dowel_spacing", action="store", type=float, default=220.0,
            help="Distance (mm) between the two registration holes along "
                 "the latch wall's lid-side edge, placed symmetrically about "
                 "the middle of that edge. Wide spacing registers better "
                 "against rotation, so prefer the largest value that still "
                 "clears the wall's finger joints — the generator clamps "
                 "and warns if it does not.")
        self.argparser.add_argument(
            "--latch_dowel_inset", action="store", type=float, default=12.0,
            help="Distance (mm) from the latch wall's lid-side edge to the "
                 "registration-hole centres. Kept near that edge rather than "
                 "at mid-depth, since the tabs it is protecting the alignment "
                 "of are on that edge and a dowel close to them registers "
                 "them more directly. The default 12 leaves 9 mm of wood to "
                 "the edge with a 6 mm hole; values that leave less than two "
                 "thicknesses, or that put a hole under a tab, are clamped or "
                 "refused with a warning.")
        self.argparser.add_argument(
            "--latch_cover_lip", action="store", type=float, default=8.0,
            help="Length (mm) by which the front cover is extended PAST the "
                 "latch wall at the opening edge, forming a small overhanging "
                 "lip. The tab slots are moved inboard by "
                 "the same amount, so the strip of material between each slot "
                 "and the cover's free edge (the bit that snaps) grows from "
                 "~thickness to ~thickness+lip. The lip also doubles as a "
                 "finger-pull for opening. Set to 0 for no lip (slots sit "
                 "close to the edge as before). Only applied when latch tabs "
                 "are enabled.")
        self.argparser.add_argument(
            "--latch_cover_reinforcement", action="store", type=boolarg, default=True,
            help="Emit a glue-on reinforcement strip that laminates onto the "
                 "INNER face of the front cover along the opening edge, in "
                 "the lip region OUTBOARD of the tab slots. It makes the "
                 "slot-to-edge bridge double thickness so it resists snapping "
                 "when the cover is pried open. The strip carries no slots "
                 "(the tabs sit just inboard of it) and glues flush with the "
                 "cover's free edge. Most useful together with a non-zero "
                 "latch_cover_lip; disable to skip the extra part.")

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
            "--utility_tray_h", action="store", type=float, default=0.0,
            help="Internal height (top-to-bottom) of the utility tray in "
                 "mm. Same axis as row_height for the mech rows, but the "
                 "tray is CLOSED top and bottom, so its assembled exterior "
                 "is `utility_tray_h + 2*thickness` — one thickness taller "
                 "than an open-top row of the same internal height. Leave "
                 "at 0 to derive it as `row_height - thickness` (67 mm at "
                 "the defaults), which makes the tray's exterior exactly "
                 "match the rows' so they share a flat top profile inside "
                 "the cavity. Determines the drawer-mouth aperture "
                 "(utility_tray_w × utility_tray_h), so taller values let "
                 "bulkier items pass through the open long side, at the "
                 "cost of standing proud of the rows.")
        self.argparser.add_argument(
            "--utility_tray_finger_hole_r", action="store", type=float,
            default=15.0,
            help="Radius (mm) of the semicircular finger pull cut into the "
                 "middle of the utility tray LID's open edge — the one at "
                 "the drawer mouth. The assembled tray sits flush against "
                 "the mech rows with nothing to grip, so this notch is what "
                 "you hook a fingertip into to slide it out. The mouth is "
                 "twice this wide and reaches this far into the lid; 15 mm "
                 "takes an adult fingertip. Set 0 for a plain lid edge "
                 "(e.g. if the tray is a friction fit and you would rather "
                 "keep the dust seal). Values that would leave less than "
                 "two thicknesses of wood at the lid's corners or in front "
                 "of the opposite finger joint are clamped, with a warning. "
                 "Only the lid is notched — the floor stays solid so "
                 "nothing falls out of the bottom.")

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
            "--include_dice_holes", action="store", type=boolarg, default=True,
            help="Cut the D-shaped dice entry/exit opening into each "
                 "side-wall bulge. Disable to leave the bulges solid while "
                 "still emitting the deflector ramps.")
        self.argparser.add_argument(
            "--dice_hole_wall", action="store", type=float, default=6.0,
            help="Wood (mm) left between the dice opening and the outer edge "
                 "of the side-wall bulge. Because the opening's curve is "
                 "concentric with the bulge, this rim is a constant width all "
                 "the way round the arc, so it reads as a clean band rather "
                 "than a crescent. This is what sizes the opening: hole "
                 "radius = bulge radius (y / 2) - this value, so the opening "
                 "grows and shrinks with the spine automatically. Larger "
                 "values give a stronger bulge and a smaller mouth.")
        self.argparser.add_argument(
            "--dice_hole_radius", action="store", type=float, default=0.0,
            help="Radius (mm) of the D-shaped dice entry/exit opening cut "
                 "into each side-wall bulge. Leave at 0 (recommended) to use "
                 "the bulge's own radius less `dice_hole_wall`, which makes "
                 "the opening concentric with the outer bend and keeps the "
                 "rim an even width. Set a positive value to force a smaller "
                 "radius — the arc then no longer follows the bulge and the "
                 "rim widens toward the sides. Values larger than the "
                 "concentric radius are clamped, with a warning.")
        self.argparser.add_argument(
            "--dice_hole_clearance_finger", action="store", type=float, default=6.0,
            help="Minimum clearance (mm) between the dice hole's flat "
                 "side (diameter) and the side wall's finger-hole row "
                 "where the recess wall mates. Larger values push the "
                 "semicircle further into the bulge (toward its outer "
                 "edge); a value of 0 lets the diameter sit flush against "
                 "the finger-hole row. If the requested clearance plus "
                 "the dice hole radius exceeds the available bulge "
                 "depth, the position is clamped so the curve still "
                 "leaves a minimum gap below the bulge's outer edge "
                 "(a warning is logged).")
        self.argparser.add_argument(
            "--dice_tower_ramp_count", action="store", type=int, default=3,
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
                 "(y_spine / 2 = 37.5 mm by default) so the ramp doesn't "
                 "touch the flex.")
        self.argparser.add_argument(
            "--dice_tower_ramp_offset", action="store", type=float, default=10.0,
            help="Alternating offset (mm) of each ramp's centre from the "
                 "midline of the recess wall's short axis (spine depth "
                 "direction). The first ramp shifts by +offset toward "
                 "one cover, the second by -offset toward the other, "
                 "and so on. A non-zero value creates a 3D zig-zag fall "
                 "path: dice deflect both in height (from the alternating "
                 "ramp angle) and in depth (from this offset). Set to 0 "
                 "to centre every ramp on the spine midline. The usable "
                 "maximum is `y/2 - (ramp_length/2)*cos(ramp_angle)` = "
                 "15.8 mm at the defaults; the offset is clamped there, "
                 "but a value near the cap puts the outermost ramp's tip "
                 "within a millimetre of the cavity wall, which paint "
                 "film and kerf can close up. The default 10 leaves "
                 "~5.8 mm.")
        self.argparser.add_argument(
            "--dice_tower_ramp_end_clearance", action="store", type=float, default=50.0,
            help="Minimum distance (mm) from the recess wall's short "
                 "edges within which NO ramp finger-hole may sit. The "
                 "constraint is enforced on the FULL extent of the "
                 "angled finger-hole row (not just its midpoint), so a "
                 "ramp tilted at 30 deg with length 50 mm extends "
                 "±12.5 mm in y and the row's far end must stay outside "
                 "the clearance zone. Use this to leave room at the top "
                 "of the spine for dice to enter cleanly and at the "
                 "bottom for them to exit without snagging a ramp.")

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
        75 mm by default). ``wall_y`` is the wall's long dimension (=
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
        end_clearance = self.dice_tower_ramp_end_clearance

        # The ramp's finger-hole row is angled at ±`angle` degrees and
        # is `ramp_len` long. Centred on its midpoint, the row's y-axis
        # half-extent is (ramp_len / 2) * |sin(angle)|. To keep NO hole
        # within `end_clearance` of either short edge of the wall, the
        # midpoint y must sit at least (end_clearance + row_half_y_span)
        # inside from each edge.
        row_half_y_span = (ramp_len / 2.0) * abs(math.sin(math.radians(angle)))
        edge_offset = end_clearance + row_half_y_span

        py_min = t + edge_offset
        py_max = t + wall_y - edge_offset
        usable = py_max - py_min

        if usable < 0:
            # The clearance is so large that no ramp midpoint can satisfy
            # the constraint on this wall. Log a warning and fall back to
            # placing the (single) ramp at the wall's centre; the user
            # will see geometry that violates the requested clearance,
            # but at least the part still renders. They can reduce
            # end_clearance, ramp_len, the ramp angle, or grow the wall.
            self._warn(
                "dice_tower_ramp_end_clearance=%.1f mm leaves no room for %d "
                "ramp(s) of length %.1f mm at %.1f deg on a wall of long-axis "
                "length %.1f mm. Falling back to centred placement — reduce "
                "end_clearance, ramp_length, ramp_angle, or grow y (spine "
                "depth) / h (cover height).",
                end_clearance, n, ramp_len, angle, wall_y,
            )
            positions_y = [t + wall_y / 2.0] * n
        elif n == 1:
            positions_y = [py_min + usable / 2.0]
        else:
            step = usable / (n - 1)
            positions_y = [py_min + i * step for i in range(n)]

        # X position: centre each ramp's tab line on the wall's short
        # axis, then offset alternately by ``dice_tower_ramp_offset`` so
        # consecutive ramps zig-zag in spine depth as well as angle. A
        # die falling through the dice hole therefore deflects in TWO
        # dimensions on each bounce, slowing the descent and randomising
        # the orientation more thoroughly than a pure angle-only zig-zag.
        midline_x = wall_h / 2.0
        offset = self.dice_tower_ramp_offset
        # Clamp the offset so the tab line stays within the wall after
        # accounting for the ramp's own x-projection. The row spans
        # ±(ramp_len/2)*cos(tilt) in x; the row's far edge must stay
        # inside [t_margin, wall_h - t_margin]. We use the wall's edge
        # as the constraint (t_margin = 0); a hole touching the very
        # edge would still cut, just without surrounding wood.
        row_half_x_span = (ramp_len / 2.0) * abs(math.cos(math.radians(angle)))
        max_offset = max(0.0, midline_x - row_half_x_span)
        if offset > max_offset:
            self._warn(
                "dice_tower_ramp_offset=%.1f mm exceeds the %.1f mm room "
                "available on a wall of short-axis length %.1f mm with "
                "ramp_length=%.1f mm at %.1f deg. Clamping to %.1f mm.",
                offset, max_offset, wall_h, ramp_len, angle, max_offset,
            )
            offset = max_offset

        for i, py in enumerate(positions_y):
            # Alternate angle sign so ramps zig-zag in y.
            tilt = angle if i % 2 == 0 else -angle
            # Alternate x-offset so ramps zig-zag in spine depth too.
            centre_x = midline_x + (offset if i % 2 == 0 else -offset)
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

        # Dice entry/exit opening — a single D-shaped circular segment cut
        # into the bulge, flat side toward the main side-wall body and curve
        # toward the bulge's outer edge. One wide continuous mouth beats two
        # small round holes: dice don't have to line up with a fixed centre,
        # they can fall through anywhere along the chord.
        #
        # The arc shares the bulge's CENTRE — panel-local (h/2, x + 2t) — so
        # with its radius set to (r - dice_hole_wall) by
        # :meth:`_resolve_dice_hole_radius` the leftover rim is a constant
        # width all the way round, instead of the crescent you get from two
        # arcs of different radii.
        #
        # Sharing the centre means the flat side can no longer be the
        # diameter: the diameter line sits at panel-y = x + 2t, only 0.5t
        # above the finger-hole row at x + 1.5t that mates the recess wall,
        # which would leave almost no wood between the two cuts. So we raise
        # the flat side to a CHORD, `dice_hole_clearance_finger` above that
        # row, and cut only the segment above it.
        if self.include_dice_tower and self.include_dice_holes:
            cx_mid = h / 2.0
            hr = self.dice_hole_radius
            bulge_centre_y = x + 2 * t
            finger_holes_y = x + 1.5 * t
            chord_y = finger_holes_y + self.dice_hole_clearance_finger
            chord_offset = chord_y - bulge_centre_y
            if abs(chord_offset) >= hr:
                # The chord has been pushed past the arc — no segment exists.
                # Only reachable with a large dice_hole_clearance_finger on a
                # shallow spine, since the radius itself is already bounded.
                self._warn(
                    "dice_hole_clearance_finger=%.1f mm pushes the opening's "
                    "flat side outside a %.1f mm radius arc, leaving no "
                    "opening to cut. Dice opening omitted — reduce "
                    "dice_hole_clearance_finger or dice_hole_wall, or grow y "
                    "(spine depth).",
                    self.dice_hole_clearance_finger, hr,
                )
            else:
                self._circular_segment_hole(cx_mid, bulge_centre_y, hr,
                                            chord_offset)

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
    # to dislodge in a bag). We swap the whole thing for the row of tabs on
    # the latch wall's lid-side edge — see this class's docstring/description,
    # which is also where the consequence is spelled out: the tabs locate the
    # cover but nothing holds it down.
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

    def _draw_latch_dowel_holes(self, h, y):
        """Cut the two glue-up registration holes into a latch panel.

        Called by BOTH :meth:`flexBookLatchWall` and
        :meth:`flexBookLatchDoubler`, from the same point in each method's
        drawing sequence (just before the tabbed lid-side edge), so both
        panels see the identical local frame: local ``+x`` runs along the lid-side
        edge, local ``+y`` points INTO the panel. Since the doubler's
        rectangle matches the wall's nominal ``h`` x ``y`` footprint, one set
        of local coordinates lands on the same spot in both parts — which is
        the entire point, and the reason this is one shared method rather
        than two copies that could drift apart.

        Nothing else locates the doubler against the wall during glue-up:
        the side walls only loosely corral it, and wet glue lets it slide.
        A couple of mm of slip is enough that the stacked tabs miss the
        cover's slots and the latch will not close. Dropping a dowel through
        both holes pins them until the glue sets.

        Placement is a symmetric pair, ``±latch_dowel_spacing/2`` about the
        middle of the lid-side edge, ``latch_dowel_inset`` in from that edge.
        Two properties come out of that:

        * sitting near the lid-side edge puts the dowels close to the tabs
          whose alignment they exist to protect, which registers them more
          directly than a hole out at mid-depth would;
        * a symmetric pattern is unchanged by an end-for-end flip, so the
          user cannot fit the doubler the wrong way round along the edge.

        Three things are checked, and they fail differently on purpose:

        * **Spacing** into the finger joints at the ends of the edge — clamped,
          because the holes only slide inward and nothing is lost.
        * **Inset** too close to either long edge — clamped for the same reason.
        * **Diameter** too large for the wall's depth, or a hole landing under
          a tab — refused, holes omitted. A hole narrowed to fit is a hole the
          user's dowel will not enter, and a hole through a tab root trades
          the problem being solved for a worse one; in both cases silently
          producing something useless is worse than producing nothing.

        Args:
            h: The wall's short (side-to-side) dimension in mm — the axis the
                inset is measured along.
            y: The wall's long lid-side edge length in mm — the axis the
                pair is spaced along.
        """
        # Only meaningful with two pieces to register against each other.
        if not self.latch_doubler or self.latch_dowel_d <= 0:
            return

        t = self.thickness
        d = self.latch_dowel_d
        r = d / 2
        rim = 2 * t  # one t for the joint being cleared, one structural

        # Depth: the hole has to fit between the two long edges with a rim on
        # each side. If it cannot, no inset works and a thinner dowel is the
        # only fix — so refuse rather than clamp.
        if h - d - 2 * rim < 0:
            self._warn(
                "latch_dowel_d=%.1f mm cannot fit across the latch wall's "
                "%.1f mm depth with a %.1f mm rim on each side, so the "
                "registration holes were omitted. Use a thinner dowel, or set "
                "latch_dowel_d=0 to silence this and align the doubler to the "
                "wall by eye.",
                d, h, rim,
            )
            return

        # Inset: clamp into the band where the hole clears both long edges.
        inset = self.latch_dowel_inset
        lo, hi = rim + r, h - rim - r
        if not lo <= inset <= hi:
            clamped = min(max(inset, lo), hi)
            self._warn(
                "latch_dowel_inset=%.1f mm puts the registration holes within "
                "%.1f mm of a latch wall edge, so it was clamped to %.1f mm "
                "(the usable band is %.1f-%.1f mm at this dowel size).",
                inset, rim, clamped, lo, hi,
            )
            inset = clamped

        # Spacing: keep both holes clear of the finger joints at the ends of
        # the lid-side edge. Clamping just slides them inward.
        max_spacing = y - d - 2 * rim
        spacing = self.latch_dowel_spacing
        if max_spacing <= 0:
            self._warn(
                "the latch wall is too short (%.1f mm) to fit two %.1f mm "
                "registration holes clear of its finger joints, so they "
                "were omitted.",
                y, d,
            )
            return
        if spacing > max_spacing:
            self._warn(
                "latch_dowel_spacing=%.1f mm would put a registration hole "
                "into the latch wall's finger joints, so it was clamped to "
                "%.1f mm — the widest pair leaving a %.1f mm rim at each "
                "end of the lid-side edge.",
                spacing, max_spacing, rim,
            )
            spacing = max_spacing

        centres = [y / 2 - spacing / 2, y / 2 + spacing / 2]

        # Tab roots. The dowels now sit near the lid-side edge, the same edge
        # the tabs stand on, so a wide tab or an unlucky spacing can put a hole
        # straight through the root of one. That would weaken the exact feature
        # the dowel exists to align, so refuse instead of quietly cutting it.
        if self.latch_tab_count > 0 and self.latch_tab_width > 0:
            half_tab = self.latch_tab_width / 2
            for k in range(self.latch_tab_count):
                tab_along = (k - (self.latch_tab_count - 1) / 2) \
                    * self.latch_tab_spacing + y / 2
                for c_along in centres:
                    if abs(c_along - tab_along) < half_tab + r + t:
                        self._warn(
                            "a registration hole at %.1f mm along the "
                            "lid-side edge would cut into the root of the "
                            "latch tab centred at %.1f mm, so the holes were "
                            "omitted. Respace them (latch_dowel_spacing), or "
                            "narrow/respace the tabs.",
                            c_along, tab_along,
                        )
                        return

        for c_along in centres:
            self.hole(c_along, inset, d=d)

    def flexBookCover(self, move=None):
        """Emit the cover panel without FlexBook's latch slot or anchor holes.

        This is a verbatim copy of :meth:`FlexBook.flexBookCover` with the
        three ``rectangularHole`` calls removed — those holes were the pin
        slot and the two square anchor holes for the under-cover latch
        brackets, and nothing in the tab-only closure uses them.
        """
        x, y = self.x, self.y
        c4 = self.c4
        t = self.thickness

        # Opening-edge lip: extend the FRONT cover past the latch wall by
        # this amount so the tab slots move inboard, away from the free edge.
        # Only meaningful when tabs exist — with no tabs there is nothing to
        # move, so the lip collapses to 0.
        lip = self.latch_cover_lip if self.latch_tab_count > 0 else 0.0

        tw = 2 * x + 6 * t + 2 * c4 + t + lip
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
        self.edges["e"](x + t + lip)  # front cover, extended by the opening lip
        self.corner(90, 2 * t)
        self.edges["e"](y / 2)
        # FlexBook drills three rectangular holes here for the latch hardware
        # (pin slot + 2 anchor holes). We replace them with through-cut
        # rectangular slots that receive the latch tabs on the latch wall's
        # lid-side edge.
        #
        # Coordinate frame: the cursor is at the midpoint of the cover's
        # latch-end edge, facing along the edge (heading is +y world UP).
        # Local +x is the cursor's heading; local +y is 90° CCW from
        # heading (boxes convention — the arc-centre of a +90 corner lies
        # in local +y direction, which is LEFT of motion). For this cursor
        # that puts local +y at -x world — i.e. INTO the cover panel,
        # away from the latch edge. So positive LY values move INTO the
        # panel; that's where we want the through-slots that receive the
        # latch wall's tabs.
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
            # Slot depth (across the wall thickness) and centre depend on
            # whether a latch doubler is laminated to the wall. A single
            # wall is t thick and occupies the LY band [t, 2t] (its outer
            # face flush with the cover's latch-end edge at LY=t, inner face
            # at LY=2t), so the slot centres at 1.5t with depth t. The
            # doubler adds a second t of material on the INNER face, growing
            # the wall toward the cavity to the band [t, 3t] — so the slot
            # must grow to depth 2t and re-centre at 2t to span both layers.
            if self.latch_doubler:
                tab_thickness = 2 * t
                slot_center_ly = 2 * t
            else:
                tab_thickness = t
                slot_center_ly = 1.5 * t
            slot_dy = tab_thickness + 2 * self.latch_tab_clearance
            # Shift every slot inboard by the opening lip so they stay over
            # the (stationary) latch-wall tabs after the cover edge moved out.
            for k in range(self.latch_tab_count):
                offset = (k - (self.latch_tab_count - 1) / 2) * self.latch_tab_spacing
                self.rectangularHole(offset, slot_center_ly + lip, slot_dx, slot_dy)
        self.edges["e"](y / 2)
        self.corner(90, 2 * t)
        self.edges["e"](x + t + lip + 2 * c4 + t)  # front cover (+lip) + spine
        self.edges["h"](x + t)
        self.corner(90, 2 * t)
        self.edges["h"](y)
        self.corner(90, 2 * t)

        self.move(tw, th, move)

    def flexBookLatchWall(self, h, y, latchSize, callback=None, move=None):
        """Emit the latch-end wall with its tab protrusions.

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
        * Two through-holes near the lid-side edge, matching a pair cut into
          the doubler, that take a dowel to hold the two pieces in register
          while they are glued (see :meth:`_draw_latch_dowel_holes`). Only
          cut when ``latch_doubler`` is on — with a single-piece latch there
          is nothing to register against.

        The tabs are the whole closure: they locate the cover against sliding
        but nothing holds it down, so an inverted book will shed its cover.
        See the class description. ``latchSize`` is accepted for FlexBook
        signature parity but is unused.
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
        #                               (`f` kept for parity with FlexBook)
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
        # Glue-up registration holes, placed just inside the panel from the
        # lid-side edge (the 4th edge, drawn next).
        # Cursor is at (x_adjust + tab_extent, t + y), heading -y world
        # (about to draw the left edge going DOWN). Local +x = heading
        # (-y world); local +y is 90° CCW from heading (boxes convention,
        # = +x world from this cursor), which points INTO the wall panel
        # from the lid-side edge. Positive LY therefore moves a feature
        # INTO the panel. The midpoint of the lid-side edge sits at +y/2
        # along the cursor's heading direction, so the pair goes at
        # local (y/2 ± spacing/2, +inset). The doubler cuts these at
        # identical coordinates.
        self._draw_latch_dowel_holes(h, y)
        # Lid-side edge: a polyline with tab protrusions (or a plain edge
        # if `latch_tab_count == 0`). The polyline INCLUDES the final 90°
        # corner that closes the panel outline, so we don't add another
        # `self.corner(90)` after it.
        self.polyline(*self._build_tabbed_edge_polyline(y))

        self.move(tw, th, move)

    def flexBookLatchDoubler(self, h, y, move=None):
        """Emit the glue-on reinforcement plate for the latch wall.

        At thin material (e.g. 3 mm) the latch tabs are fragile fins that
        snap easily. This part is laminated flat onto the INNER
        (cavity-facing) face of :meth:`flexBookLatchWall`, carrying the
        identical tab profile on its lid-side edge so that, once glued, the
        tabs stack into a 2×-thickness fin (6 mm at t=3 mm). The combined
        wall also resists bending far better than a single sheet.

        Geometry mirrors :meth:`flexBookLatchWall` exactly so the tabs line
        up when the two pieces are stacked:

        * The three structural edges (bottom, floor-side, top) are plain
          ``e`` butt edges — the doubler is glued to the wall's face and
          carries no load into the side walls or back cover, so it needs no
          finger joints. Its rectangle therefore matches the latch wall's
          NOMINAL footprint (``h`` × ``y``), nesting snugly between the two
          side walls which locate it during glue-up.
        * The lid-side edge reuses :meth:`_build_tabbed_edge_polyline` with
          the same ``y`` length, so its tab centres coincide with the latch
          wall's tabs and the fins stack cleanly.
        * The same two dowel registration holes are cut at the same local
          coordinates as the wall's (see :meth:`_draw_latch_dowel_holes`).
          The tabs are what make this necessary: they only stack into a
          usable 2t fin if the two pieces are glued in register, and nothing
          else holds them there while the glue is wet.

        ``h`` and ``y`` carry the same (post-swap) meaning as in
        :meth:`flexBookLatchWall`: ``h`` is the short (side-to-side) edge,
        ``y`` is the long lid-side edge.
        """
        t = self.thickness

        # The lid-side tabs protrude ``t`` mm out of the panel rectangle in
        # the -x direction (same as the latch wall). Reserve that strip in
        # the move envelope and shift the local origin right by it so the
        # leftward-poking tabs stay within bounds. Match the latch wall's
        # ``y + 2t`` envelope height so the two parts read as the same size
        # in the SVG layout.
        tab_extent = t if self.latch_tab_count > 0 else 0
        tw, th = h + tab_extent, y + 2 * t

        if self.move(tw, th, move, True):
            return

        self.moveTo(tab_extent, t)

        # Three plain glue edges, drawn in the same order as the latch wall
        # (bottom h, floor-side y, top h) so the cursor finishes at the
        # top-left corner heading down the lid-side edge.
        self.edges["e"](h)
        self.corner(90)
        self.edges["e"](y)
        self.corner(90)
        self.edges["e"](h)
        self.corner(90)

        # Glue-up registration holes, at the SAME local coordinates as the
        # latch wall's (see :meth:`flexBookLatchWall` for the coordinate-frame
        # derivation) — that correspondence is what lets a dowel through both
        # pin the two pieces together.
        self._draw_latch_dowel_holes(h, y)

        # Lid-side edge with the matching tab protrusions; the polyline
        # includes the final 90° corner that closes the outline.
        self.polyline(*self._build_tabbed_edge_polyline(y))

        self.move(tw, th, move)

    def flexBookCoverReinforcement(self, y, move=None):
        """Emit the glue-on bridge-reinforcement strip for the front cover.

        The tab slots sit a short distance in from the cover's free opening
        edge; the wood between a slot and that edge (the "bridge") is the
        part that snaps when the cover is pried. This flat strip laminates
        onto the INNER face of the front cover, flush with the free edge,
        filling exactly the bridge band OUTBOARD of the slots so that band
        becomes double thickness. It deliberately stops just shy of the
        slots (a 0.5 mm gap) so it never overlaps one — the tabs only
        protrude one ``thickness`` and so reach the cover's outer face but
        not this inner strip, leaving them free to lift out when opening.

        ``y`` is the cover's opening-edge length (post-swap ``self.y``); the
        strip runs the full length of that edge for maximum stiffness.

        The strip width is derived from the same slot geometry used in
        :meth:`flexBookCover` (centre + half-depth), plus the opening lip,
        so it always lands exactly against the slots regardless of the
        doubler / lip settings.
        """
        t = self.thickness
        clr = self.latch_tab_clearance
        lip = self.latch_cover_lip if self.latch_tab_count > 0 else 0.0

        # Reproduce flexBookCover's slot centre + depth, then take the
        # outboard slot edge as the inboard limit of the bridge band.
        if self.latch_doubler:
            slot_center_ly, slot_dy = 2 * t, 2 * t + 2 * clr
        else:
            slot_center_ly, slot_dy = 1.5 * t, t + 2 * clr
        slot_near_edge = slot_center_ly + lip - slot_dy / 2.0
        strip_width = slot_near_edge - 0.5  # 0.5 mm shy of the slots

        if strip_width <= 0:
            # No room to reinforce (e.g. lip=0 with thin material) — skip
            # rather than emit a degenerate sliver.
            return

        self.rectangularWall(y, strip_width, "eeee", move=move,
                             label="cover latch reinforcement")

    # -----------------------------------------------------------------
    # Part-emission helpers
    # -----------------------------------------------------------------

    def _circular_segment_hole(self, x, y, r, chord_offset=0.0):
        """Cut a circular-segment ("D" shaped) hole in the current panel.

        The hole is the part of a circle of radius ``r`` centred on panel-local
        ``(x, y)`` that lies ABOVE a horizontal chord sitting ``chord_offset``
        mm above that centre. The curved side is therefore an arc of a circle
        concentric with ``(x, y)`` — which is what lets the dice hole share a
        centre, and so a uniform wall thickness, with the side wall's bulge.

        ``chord_offset = 0`` puts the chord on the diameter and gives a plain
        semicircle. Positive values raise the chord toward the apex, making a
        shallower and narrower D; negative values drop it below the centre,
        giving more than half a circle. The chord's half-width works out at
        ``sqrt(r**2 - chord_offset**2)``, so the caller must keep
        ``abs(chord_offset) < r`` or the chord misses the circle entirely.

        Implementation note: boxes' :class:`Context._arc` approximates each arc
        with a single cubic Bezier whose control-point formula divides by
        ``ax*by - ay*bx``. That denominator vanishes at 180°, yielding NaN
        control points and a degenerate straight line in the output SVG. Boxes'
        own :meth:`Boxes.circle` sidesteps this by emitting ten 36° arcs in
        sequence; we do the same, splitting whatever sweep we need into
        sub-arcs of at most 30° so each Bezier stays faithful, then close the
        chord with an explicit ``line_to`` (boxes' Context exposes no
        ``close_path``).

        Args:
            x: Panel-local x of the arc's CENTRE.
            y: Panel-local y of the arc's CENTRE — note this is the centre,
                not the chord, unlike a plain semicircle helper.
            r: Arc radius in mm.
            chord_offset: Height of the flat chord above the centre, in mm.

        Raises:
            ValueError: If ``abs(chord_offset) >= r``, i.e. the chord does not
                intersect the circle and there is no segment to cut.
        """
        if abs(chord_offset) >= r:
            raise ValueError(
                f"chord_offset {chord_offset:.2f} must be smaller than "
                f"radius {r:.2f} for a circular segment to exist")

        # Half-angle subtended by the chord, measured from the centre. The arc
        # we keep runs from this angle round to its mirror on the far side.
        a0 = math.asin(chord_offset / r)
        a1 = math.pi - a0
        sweep = a1 - a0
        # Cap each sub-arc at 30° so no single Bezier approximation degenerates.
        n_segments = max(2, math.ceil(sweep / (math.pi / 6)))

        # Finish any open path so this hole starts a fresh subpath.
        self.ctx.stroke()
        with self.saved_context():
            self.set_source_color(Color.INNER_CUT)
            # Translate the local frame so the arc's centre is at the local
            # origin. boxes' Context applies a y-flip at output time; sweeping
            # cairo's ``arc`` (CCW in cairo's native y-down frame) over
            # increasing angle traces the +y side of the origin in cairo-local
            # coords, which after the output y-flip lands UP relative to the
            # panel — i.e. toward the bulge's apex, which is what we want.
            self.moveTo(x, y)
            # Start the path at the chord's right-hand end.
            start = (r * math.cos(a0), r * math.sin(a0))
            self.ctx.move_to(*start)
            for i in range(n_segments):
                self.ctx.arc(0, 0, r,
                             a0 + sweep * i / n_segments,
                             a0 + sweep * (i + 1) / n_segments)
            # Cursor is now at the chord's left-hand end; close the chord.
            self.ctx.line_to(*start)
            self.ctx.stroke()

    def _emit_half_ellipse_ramp(self, length, width, move=None, label="dice tower ramp"):
        """Emit one half-elliptical dice-tower ramp panel.

        The panel's tab side (the straight ``length`` mm edge) is a
        finger-jointed ``"f"`` edge that slots into the angled finger
        holes drilled on the recess wall by
        :meth:`_drill_recess_ramp_holes`. The opposite side is a
        half-ellipse with semi-major axis ``length / 2`` (along the tab)
        and semi-minor axis ``width`` (perpendicular protrusion away
        from the recess wall).

        Visually, the half-ellipse outline echoes the semicircular
        dice-hole cut in the side-wall bulge so the tower's interior
        and exterior cutouts share a family resemblance. Functionally,
        the deflection surface for a falling die is still the flat
        face of the panel — the outline shape only affects silhouette,
        not bounce mechanics.

        Implementation: the half-ellipse is approximated by 32 short
        straight segments, each emitted via :meth:`corner` +
        :meth:`edge`. boxes' burn-correction handles the small
        per-segment turns correctly; 32 segments make the polygonal
        approximation indistinguishable from a smooth curve at laser
        kerf widths.
        """
        f_edge = self.edges["f"]
        # Overall bounding box. The tab edge's finger joints extend
        # outward by ``spacing()`` on the tab side; the curved side
        # is flush with the panel boundary on the other.
        overallwidth = length + 2 * f_edge.spacing()
        overallheight = width + f_edge.spacing()

        if self.move(overallwidth, overallheight, move, True):
            return

        # Move so the tab edge starts at panel-local (0, 0) with the
        # tab tabs extending into negative y. The curve then walks
        # through positive y.
        self.moveTo(f_edge.spacing(), f_edge.margin())

        # 1. Tab edge — finger joints that mate with the recess wall.
        f_edge(length)
        # Cursor: (length, 0), heading +x.

        # 2. Half-ellipse curve back to (0, 0).
        # Parametric form: x(t) = a + a*cos(t), y(t) = b*sin(t),
        # for t in [0, π]. At t=0: (2a, 0) = (length, 0). At t=π:
        # (0, 0). At t=π/2: (a, b) = (length/2, width) — the apex.
        a = length / 2.0
        b = width
        n_segments = 32
        prev_heading_deg = 0.0
        for i in range(1, n_segments + 1):
            t_prev = (i - 1) * math.pi / n_segments
            t_cur = i * math.pi / n_segments
            pxp = a + a * math.cos(t_prev)
            pyp = b * math.sin(t_prev)
            px = a + a * math.cos(t_cur)
            py = b * math.sin(t_cur)
            seg_len = math.hypot(px - pxp, py - pyp)
            seg_heading_deg = math.degrees(math.atan2(py - pyp, px - pxp))
            # Turn is the heading delta, normalised to (-180, 180].
            turn = seg_heading_deg - prev_heading_deg
            while turn > 180:
                turn -= 360
            while turn <= -180:
                turn += 360
            self.corner(turn)
            self.edge(seg_len)
            prev_heading_deg = seg_heading_deg

        self.move(overallwidth, overallheight, move, label=label)

    def _emit_map_sleeve(self):
        """Emit the four flat pieces that glue into the map sleeve.

        The sleeve is a thin pocket: one inner face (sits flush against
        the inside of a cover) plus three narrow strip walls (top, bottom,
        and the spine-side end). The opposite short edge is intentionally
        left open so maps slide in and out when the book opens.

        All pieces use plain butt edges (``"eeee"``) because they are
        glue-assembled — no finger joints would survive the strip's narrow
        depth. The user is expected to clamp + glue the strips between the
        cover and the inner face. The one exception is the inner face's TOP
        short edge, which carries a semicircular finger pull (see
        :class:`_FingerPullEdge`): a stack of paper maps sits flush in the
        pocket with nothing proud to pinch, so the notch is what gives a
        fingertip enough purchase on the top sheet to slide the stack out.

        Because the face is otherwise symmetric, that notch is what marks
        which short side is the mouth — the short glue strip goes on the
        OTHER short edge, and the sleeve is then installed with the notched
        end away from the spine.

        Outer dimensions:
        * Inner face: ``(map_sleeve_w + 2t)`` × ``(map_sleeve_h + 2t)`` —
          the +2t accounts for the surrounding strip walls so the maps
          fit the *internal* width/height the user specified.
        * Long strips (left + right, parallel to the cover height):
          ``map_sleeve_depth`` × ``(map_sleeve_h + 2t)`` — same length
          as the inner face's height so the strips fully back the face's
          left/right edges.
        * Short strip (spine-side end): ``map_sleeve_depth`` × ``map_sleeve_w``
          — fits BETWEEN the two long strips at the spine corner; its
          ``w`` length equals the inner-face width minus the two long
          strips' thicknesses (= ``w + 2t − 2t = w``).
        """
        t = self.thickness
        w = self.map_sleeve_w
        h = self.map_sleeve_h
        d = self.map_sleeve_depth

        # Inner face that sits against the cover. Its TOP short edge carries
        # the finger pull; glue the short strip along the BOTTOM short edge so
        # the notch ends up at the sleeve's open mouth. The face is otherwise
        # symmetric, so which short edge is "top" is decided here rather than
        # at assembly — see the docstring.
        self.rectangularWall(
            w + 2 * t, h + 2 * t,
            ["e", "e", self._finger_pull_edge(
                self.map_sleeve_finger_hole_r, "map_sleeve_finger_hole_r",
                w + 2 * t, h + 2 * t, "map sleeve face"), "e"],
            move="up", label="map sleeve face")

        # Two long strips (left + right of the sleeve, parallel to the
        # cover height). Length matches the inner face's height
        # (h + 2t) so the strips fully back the face's long edges
        # rather than stopping short of the corners.
        self.rectangularWall(d, h + 2 * t, "eeee", move="up", label="map sleeve strip (long)")
        self.rectangularWall(d, h + 2 * t, "eeee", move="up", label="map sleeve strip (long)")

        # One short strip on the spine side — the opposite short side is left open.
        # Length is w (not w + 2t) so the strip fits BETWEEN the two long
        # strips at the spine end of the sleeve.
        self.rectangularWall(d, w, "eeee", move="up", label="map sleeve strip (short)")

    def _row_finger_holes_callback(self, cells, height, floor_w=None):
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

        Why the cell block is centred
        -----------------------------
        A row's two long walls are cut as identical pieces, and the panel
        OUTLINE is already mirror-symmetric about its vertical centreline
        (``FFeF`` puts the same ``F`` edge on both ends, and the bottom
        ``F`` finger pattern is itself centred). So the only thing that
        can give the piece a handedness — a "this face out" side — is the
        divider hole pattern.

        Filler padding (see :meth:`_emit_mech_row`) makes ``floor_w``
        wider than the cells strictly need. If that slack all sat at the
        trailing end, the hole pattern would sit off-centre, and flipping
        one wall over to face the other way would shift every hole by the
        full filler width — 6 mm on the default 4-heavy row, 23 mm on the
        default 1-heavy-4-medium row. The dividers then simply don't
        reach. Splitting the slack evenly across both ends instead keeps
        the pattern centred, so either wall can be installed either way
        round.

        Note that this makes the piece reversible only when the cell
        sequence is itself palindromic (as the default 4-heavy and
        6-medium rows are). A row like ``Heavy+Medium+Medium`` has
        intrinsically asymmetric divider spacing, and no amount of
        centring can make a mirrored copy line up.

        Args:
            cells: List of cell widths in mm for this row.
            height: Length of each finger-hole row in mm. Pass the divider
                height (NOT the wall height) so the holes stop short of
                the wall top when called with a shorter height, leaving the
                label strip band unbroken.
            floor_w: Final floor width in mm, i.e. the cells' natural width
                plus any filler padding. Used to centre the cell block. Pass
                ``None`` to pack the cells hard against the leading edge.

        Returns:
            A callable suitable for the ``callback=[...]`` parameter of
            :meth:`rectangularWall`, or ``None`` if the row has no internal
            dividers (single cell ⇒ no holes needed).
        """
        if len(cells) <= 1:
            return None

        t = self.thickness

        # Half the filler slack, used as the leading offset so the cell
        # block ends up centred in the floor.
        natural_floor_w = sum(cells) + (len(cells) - 1) * t
        lead = 0.0
        if floor_w is not None and floor_w > natural_floor_w:
            lead = 0.5 * (floor_w - natural_floor_w)

        def cb():
            pos = lead - 0.5 * t
            # cells[:-1] because there are len(cells)-1 dividers — the last
            # cell has no divider to its right (the outer wall closes the row).
            for cell_w in cells[:-1]:
                pos += cell_w + t
                self.fingerHolesAt(pos, 0, height)

        return cb

    def _label_strip_enabled(self):
        """Whether rows should get a label strip, notches and all.

        Two call sites depend on this — the one that cuts the notches into the
        short walls and dividers, and the one that emits the strip itself — and
        they must agree or you get notched panels with no strip to fill them
        (or worse, a strip and nowhere to put it). Hence one predicate rather
        than the condition written twice.

        A zero or negative ``label_strip_depth`` counts as off as well as the
        checkbox: a strip with no depth is not a part, and
        :class:`_NotchedTopEdge` would fall back to a plain edge anyway.

        Returns:
            True if the label strip and its notches should be emitted.
        """
        return self.include_label_strip and self.label_strip_depth > 0

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
        widened to make the outer dimensions match. The extra width is just
        empty floor — no extra divider — and it is split EVENLY between the
        two ends, so a 4-heavy row (240 mm of cells + 5 walls = 255 mm
        natural) gets a 3 mm strip of unused floor at each end, ending up
        the same outer size as a 6-medium row (240 + 7 walls = 261 mm
        natural, no filler). This keeps the tray system visually uniform
        regardless of the cell mix.

        Centring the slack rather than dumping it at one end also keeps the
        long walls' divider holes symmetric, so the two identical long-wall
        pieces can each be installed either face outward — see
        :meth:`_row_finger_holes_callback`.

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
                self._warn(
                    "a row's natural outer width %.1f mm exceeds "
                    "row_target_outer_width %.1f mm; rendering that row at "
                    "its natural width, so rows will not be uniform.",
                    natural_outer_w, target_outer_w,
                )
            floor_w = natural_floor_w

        # Finger hole callback drills divider mating holes in the long
        # walls, spanning the divider's full height.
        holes_cb = self._row_finger_holes_callback(cells, h, floor_w)
        cb_list = [holes_cb] if holes_cb is not None else None

        # If a label strip is enabled, the short walls and the dividers need a
        # rectangular NOTCH cut into their top edges so the strip drops in
        # flush with the wall tops. The notch is `label_strip_depth` wide by
        # `thickness` deep, set back from the panel's front-top corner by
        # `label_strip_inset` — that lip of wood gives the notch a closed
        # outer wall for the strip to sit against. At an inset of 0 the notch
        # opens straight onto the corner instead: still a clean cut, but the
        # strip is then held by friction against the panels behind it alone.
        if self._label_strip_enabled():
            inset = max(0.0, self.label_strip_inset)
            # _NotchedTopEdge silently falls back to a plain edge if the notch
            # cannot fit, which would leave the strip with nothing holding it.
            # Catch that here instead, where we can name the culprit.
            if inset + self.label_strip_depth > depth:
                self._warn(
                    "label_strip_inset=%.1f mm plus label_strip_depth=%.1f mm "
                    "exceeds the %.1f mm row depth, so the notch does not fit "
                    "and the strip has nothing to sit in. Reduce the inset or "
                    "the strip depth, or deepen the row.",
                    inset, self.label_strip_depth, depth,
                )
            notched_top = _NotchedTopEdge(
                self, None, self.label_strip_depth, t,
                notch_inset=inset)
            # rectangularWall traverses bottom, right, top, left — so the top
            # edge's start corner is where the RIGHT edge (index 1) finishes.
            # With no lip, that edge has to stop at the notch floor instead of
            # climbing to the corner, or the notch's wall retraces its last
            # `t` mm. See :class:`_ShortenedEdge`.
            near_edge = "f"
            if inset <= 0:
                near_edge = _ShortenedEdge(self, self.edges["f"], t)
            short_wall_edges = ["F", near_edge, notched_top, "f"]
            divider_edges = ["e", near_edge, notched_top, "f"]
        else:
            short_wall_edges = "Ffef"
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
        #
        # Length = floor_w + 2t: the strip extends from one short wall's
        # OUTER face to the other's, so its ends pass THROUGH the
        # short-wall notches (which are cut across the full panel
        # thickness) and are captured by them rather than just butting
        # against the inner faces. This also matches the floor panel's
        # outer dimensions in the SVG: with "ffff" edges the floor's
        # finger tabs extend t past nominal on each side, giving the
        # floor a bounding box of floor_w + 2t × depth + 2t — the strip
        # therefore lines up visually with the floor for an at-a-glance
        # check that both pieces span the same row width.
        #
        # Width = label_strip_depth (the notch width); thickness = the
        # row's material thickness (= notch depth, so it fits flush).
        if self._label_strip_enabled():
            self.rectangularWall(
                floor_w + 2 * t, self.label_strip_depth, "eeee",
                move="up", label="row label strip")

    def _finger_pull_edge(self, radius, param, edge_length, panel_depth, what):
        """Build a :class:`_FingerPullEdge`, clamped to what the panel allows.

        Shared by the two panels that carry a pull notch — the utility tray
        lid and the map sleeve face. Both are thin flat panels held only at
        their edges, and in both the notch is centred on one edge and eats
        ``radius`` mm into the panel, so the same two bounds apply:

        * **Sideways** — each end of the notch mouth has to stay clear of
          the panel's two adjacent corners. A radius of half the edge length
          would reach both corners exactly, so the limit is
          ``edge_length / 2`` less a rim.
        * **Depthways** — the deepest point has to stay clear of whatever
          the opposite edge carries, so the limit is ``panel_depth`` less a
          rim.

        Every rim is ``2 * t``. One thickness is what the thing being cleared
        actually occupies — a finger joint on the tray lid, a glued strip
        wall on the sleeve face — and the second is structural: a
        single-thickness rim beside a fingertip-sized opening is exactly
        where a thin panel snaps the first time someone pulls on it.

        Args:
            radius: The radius the user asked for, in mm. ``0`` or negative
                disables the notch.
            param: Name of the argparser option that supplied ``radius``,
                used to make any warning actionable.
            edge_length: Length of the edge the notch is centred on, in mm.
            panel_depth: Extent of the panel perpendicular to that edge, in
                mm — how far the notch has room to cut.
            what: Human-readable panel name for warning messages.

        Returns:
            A :class:`_FingerPullEdge`. Its radius is ``0`` — i.e. it draws
            a plain straight edge — when the user disabled the notch or the
            panel is too small to carry one.
        """
        t = self.thickness
        r = radius

        if r > 0:
            max_r = min(edge_length / 2 - 2 * t, panel_depth - 2 * t)
            if max_r <= 0:
                self._warn(
                    "the %s is too small for a finger pull (a %.1f x %.1f mm "
                    "panel at thickness %.1f mm leaves no room for the notch "
                    "plus a rim), so its edge was left plain. Enlarge the "
                    "panel or set %s=0 to silence this.",
                    what, edge_length, panel_depth, t, param,
                )
                r = 0.0
            elif r > max_r:
                self._warn(
                    "%s=%.1f mm would cut past what the %s can give up, so "
                    "it was clamped to %.1f mm. That is the largest "
                    "semicircle leaving a %.1f mm rim at the panel's corners "
                    "and in front of its opposite edge.",
                    param, r, what, max_r, 2 * t,
                )
                r = max_r

        return _FingerPullEdge(self, None, r)

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
        * **Lid** (w × d, edges ``ffef``): mirror of the floor, except
          that its open edge carries a semicircular finger pull (see
          :class:`_FingerPullEdge`). The tray is a closed box wedged
          between the mech rows with no proud surface to grab, so the
          notch is the only purchase for pulling it out. It goes in the
          lid and not the floor for the obvious reason: a hole in the
          floor is a hole dice fall through.
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
            # Lid — same edge spec as the floor, mirroring it at the
            # opposite vertical (the lid covers the tray's top in 3D),
            # except that the open edge is swapped for the finger-pull
            # variant. rectangularWall accepts edge OBJECTS as well as
            # spec characters, so the list below reads as "ffef" with the
            # third entry replaced. At radius 0 _FingerPullEdge draws a
            # plain edge, making the lid byte-identical to the floor.
            self.rectangularWall(
                w, d,
                ["f", "f", self._finger_pull_edge(
                    self.utility_tray_finger_hole_r,
                    "utility_tray_finger_hole_r", w, d,
                    "utility tray lid"), "f"],
                move="up", label="utility tray lid")
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
    # Warning collection
    # -----------------------------------------------------------------

    def _warn(self, message, *args):
        """Record a design warning, both to the log and onto the drawing.

        Warnings here describe geometry that was silently adjusted — a ramp
        clamped, a hole omitted, a tray that will not let the book close. The
        user needs to know, and the log alone is not enough: when the
        generator is driven from the web UI the SVG downloads with HTTP 200
        and nothing on screen says anything was changed, so a log-only
        warning is one you find out about from the laser cutter. Every
        message therefore goes to two places:

        * :mod:`logging`, which reaches stderr on the CLI and the container
          log on the web path;
        * a text block drawn on the SVG canvas by
          :meth:`_emit_warning_block`, which you cannot miss when you open
          the file.

        Messages are deduplicated because several are raised from per-panel
        helpers that run once per side wall, and repeating them adds nothing.

        Args:
            message: A printf-style format string.
            *args: Values for the format string. Interpolation is deferred to
                :mod:`logging`'s own formatting for the log record, then done
                eagerly for the canvas copy.
        """
        logging.warning("BattletechCarryBox: " + message, *args)
        rendered = message % args if args else message
        if rendered not in self._warnings:
            self._warnings.append(rendered)

    def _emit_warning_block(self):
        """Draw any collected warnings onto the canvas as annotation text.

        Emitted as the last "part" so it lands at the end of the layout
        rather than displacing anything. Drawn in
        :data:`Color.ANNOTATIONS`, the same non-cutting colour boxes uses
        for part labels, so a laser job that filters annotations out will
        skip it as it already skips the labels.
        """
        if not self._warnings:
            return

        lines = ["!! BattletechCarryBox: geometry was adjusted !!", ""]
        for i, warning in enumerate(self._warnings, start=1):
            wrapped = textwrap.wrap(warning, self.WARNING_WRAP_COLUMNS)
            # Hanging indent so continuation lines read as part of the entry.
            lines.append(f"{i}. {wrapped[0]}")
            lines.extend(f"   {line}" for line in wrapped[1:])
            lines.append("")

        fontsize = self.WARNING_FONTSIZE
        # 0.61 mm per mm of font size is boxes' own rough advance width for
        # single-digit font sizes (see Boxes.tx_sizes); close enough to
        # reserve a block that the text will not overflow.
        width = self.WARNING_WRAP_COLUMNS * fontsize * 0.61
        height = len(lines) * 1.4 * fontsize

        if self.move(width, height, "up", before=True):
            return
        self.text("\n".join(lines), 0, 0, fontsize=fontsize,
                  color=Color.ANNOTATIONS, align="bottom left")
        self.move(width, height, "up")

    # -----------------------------------------------------------------
    # Spine-depth axis budget
    # -----------------------------------------------------------------

    def _resolve_cavity_heights(self, spine_depth):
        """Fill in any tray heights left at 0 from the spine cavity depth.

        Three settings share the spine-depth axis — ``map_sleeve_depth``,
        ``row_height`` and ``utility_tray_h`` — and they are not independent:
        together they have to fit inside the closed book. Rather than make
        the user keep three numbers consistent by hand, the two tray heights
        default to 0 meaning "derive me", and only the sleeve depth (which
        is dictated by how many map sheets you carry, not by the box) stays
        a free input.

        The budget, from the outside in::

            cavity = spine_depth - 2t          # inside faces of both covers
            usable = cavity - map_sleeve_depth # sleeve lines the far cover

        The sleeve is glued to the inside of ONE cover and the trays sit on
        the other, so they stack along this axis and the sleeve's depth comes
        straight off the top of the tray budget.

        Converting ``usable`` into interior heights needs the panel geometry,
        because "height" means something different for the two tray types:

        * A mech row is OPEN-TOP. Its floor is a ``ffff`` plate whose fingers
          sit in the walls' bottom ``F`` notches, so the floor's underside is
          flush with the wall bottoms and eats one ``t`` below the cell
          interior. Assembled exterior = ``row_height + t``.
        * The utility tray is CLOSED, with a lid as well as a floor, so it
          spends a ``t`` at each end. Assembled exterior =
          ``utility_tray_h + 2t``.

        Hence the ``- t`` and ``- 2t`` below. Both land on the same exterior
        height, which is what makes the tray tops flush with the row tops.
        The label strip does not enter into it: it is recessed into notches
        cut ``t`` deep in the row's top edges, so it sits flush rather than
        standing proud.

        A user-supplied positive value is always honoured — someone doing a
        test print may deliberately over-stuff the box — but we warn if the
        resulting stack cannot close.

        Args:
            spine_depth: The book's spine depth in mm. Pass ``self.y`` BEFORE
                :meth:`render` performs its y↔h swap, since afterwards
                ``self.y`` holds the cover height instead.
        """
        t = self.thickness
        cavity_depth = spine_depth - 2 * t
        sleeve_d = self.map_sleeve_depth if self.include_map_sleeve else 0.0
        usable = cavity_depth - sleeve_d - self.cavity_slack

        if self.row_height <= 0:
            self.row_height = usable - t
        if self.utility_tray_h <= 0:
            # Match the rows' EXTERIOR height, not their interior, so the
            # tray top finishes flush with the row tops.
            self.utility_tray_h = self.row_height - t

        # Tallest thing standing on the tray-side cover, by exterior height.
        row_outer_h = self.row_height + t
        stack = [("mech row", row_outer_h)]
        if self.include_utility_tray:
            stack.append(("utility tray", self.utility_tray_h + 2 * t))
        name, tallest = max(stack, key=lambda pair: pair[1])

        budget = cavity_depth - sleeve_d - tallest
        if budget < 0:
            self._warn(
                "closed-book cavity is %.1f mm, of which map_sleeve_depth "
                "takes %.1f mm, leaving %.1f mm — but the %s stands %.1f mm "
                "tall. Book will not close cleanly (over budget by %.1f mm). "
                "Raise `inner depth in mm` (y) or lower the tray height.",
                cavity_depth, sleeve_d, cavity_depth - sleeve_d, name,
                tallest, -budget,
            )
        elif self.row_height <= 0 or self.utility_tray_h <= 0:
            # Cavity so shallow that the derivation produced a non-positive
            # interior height; the panels would be degenerate.
            self._warn(
                "spine depth %.1f mm is too shallow to derive tray heights "
                "(row_height came out %.1f mm). Raise `inner depth in mm` (y) "
                "or reduce map_sleeve_depth.",
                spine_depth, self.row_height,
            )

    def _resolve_dice_hole_radius(self, spine_depth):
        """Size the dice opening to the side-wall bulge it is cut into.

        The bulge is a half-disc of radius ``spine_depth / 2``, so it shrinks
        with ``y``. A fixed hole radius therefore looks wrong at every ``y``
        but one: too big for a shallow spine, and on a deep one it leaves a
        crescent-shaped gap because its arc has a different radius from the
        bulge's outer bend.

        Both problems go away if the opening's arc is CONCENTRIC with the
        bulge, one ``dice_hole_wall`` inside it::

            bulge radius = spine_depth / 2
            hole radius  = bulge radius - dice_hole_wall

        The rim is then a constant ``dice_hole_wall`` wide everywhere along
        the arc, and the opening tracks ``y`` automatically. That is what a
        ``dice_hole_radius`` of 0 selects.

        A user-supplied positive radius is honoured (smaller openings are a
        legitimate preference — they just don't follow the bulge) but is
        clamped to the concentric radius, since anything larger would break
        through the bulge's outer edge.

        Note this sets the radius only. Where the flat chord sits is
        :meth:`flexBookSide`'s business, since that depends on the recess
        wall's finger row.

        Args:
            spine_depth: The book's spine depth in mm. Pass ``self.y`` BEFORE
                :meth:`render` performs its y↔h swap.
        """
        if not self.include_dice_tower or not self.include_dice_holes:
            return

        bulge_radius = spine_depth / 2.0
        wall = max(self.dice_hole_wall, self.DICE_HOLE_MIN_WALL)
        concentric_radius = bulge_radius - wall

        if concentric_radius <= 0:
            # The rim alone is wider than the bulge. Drop the opening rather
            # than cut through the bulge edge; the ramps are still emitted.
            self._warn(
                "spine depth %.1f mm gives only a %.1f mm bulge, which cannot "
                "hold a dice opening with a %.1f mm wall around it. Opening "
                "omitted — grow y (spine depth) or reduce dice_hole_wall.",
                spine_depth, bulge_radius, wall,
            )
            self.include_dice_holes = False
        elif self.dice_hole_radius <= 0:
            self.dice_hole_radius = concentric_radius
        elif self.dice_hole_radius > concentric_radius:
            self._warn(
                "dice_hole_radius=%.1f mm would break through the %.1f mm "
                "bulge of a %.1f mm spine; clamped to %.1f mm, the concentric "
                "radius that leaves the %.1f mm dice_hole_wall intact.",
                self.dice_hole_radius, bulge_radius, spine_depth,
                concentric_radius, wall,
            )
            self.dice_hole_radius = concentric_radius

    def _resolve_ramp_geometry(self, spine_depth):
        """Clamp the deflector ramps to fit the spine they hang in.

        The ramps are sized in absolute mm but live inside a cavity whose
        dimensions follow ``y``, so on a shallow spine they outgrow it in two
        independent directions. Neither was previously checked.

        **Protrusion.** A ramp sticks ``dice_tower_ramp_width`` out from the
        recess wall into a half-cylindrical cavity of radius
        ``spine_depth / 2``. At the default ``y = 75`` that is 30 mm into a
        37.5 mm radius, leaving a 7.5 mm bypass gap — narrower than a d6, so
        every die has to strike a ramp rather than drop straight past (the
        old 90 mm spine left 15 mm, wide enough for a die to miss entirely).
        By ``y = 60`` the radius IS 30 mm, so the ramp touches the
        living-hinge flex, and below that it passes through it. Capped at
        ``radius - DICE_RAMP_FLEX_CLEARANCE``.

        **Span along the spine depth.** A ramp's tab row is drilled at
        ``dice_tower_ramp_angle``, so it occupies
        ``ramp_length * cos(angle)`` of the recess wall's SHORT axis — which
        is the spine depth. At the defaults that is ``50 * cos(30) = 43.3``
        mm out of 75, fine; but below about ``y = 44`` the row is longer than
        the wall is deep and its finger holes fall off the panel. Capped so
        the row fits with one ``thickness`` of wood at each end.

        We clamp rather than scale up. The 50 × 30 mm ramp is inherited from
        boxes' own DiceTower generator, and a bigger ramp does not tumble
        dice any better — it just eats cavity that the trays want. So the
        settings mean "this big, or smaller if the spine demands it".

        Note this runs BEFORE :meth:`_drill_recess_ramp_holes`, which applies
        its own clamp to ``dice_tower_ramp_offset``. That clamp reads the
        length we may have just reduced, so the two compose in the right
        order.

        Args:
            spine_depth: The book's spine depth in mm. Pass ``self.y`` BEFORE
                :meth:`render` performs its y↔h swap.
        """
        if not self.include_dice_tower or self.dice_tower_ramp_count <= 0:
            return

        t = self.thickness
        spine_radius = spine_depth / 2.0

        # --- Protrusion into the spine cavity ---------------------------
        max_width = spine_radius - self.DICE_RAMP_FLEX_CLEARANCE
        if max_width <= 0:
            self._warn(
                "spine depth %.1f mm leaves no room for deflector ramps once "
                "%.1f mm of flex clearance is allowed. Ramps omitted — grow y "
                "(spine depth) or set dice_tower_ramp_count=0 to drop the "
                "dice tower.",
                spine_depth, self.DICE_RAMP_FLEX_CLEARANCE,
            )
            self.dice_tower_ramp_count = 0
            return
        if self.dice_tower_ramp_width > max_width:
            self._warn(
                "dice_tower_ramp_width=%.1f mm would reach the living-hinge "
                "flex in a spine of radius %.1f mm (y=%.1f); clamped to %.1f "
                "mm, leaving %.1f mm clearance. Grow y to keep deeper ramps.",
                self.dice_tower_ramp_width, spine_radius, spine_depth,
                max_width, self.DICE_RAMP_FLEX_CLEARANCE,
            )
            self.dice_tower_ramp_width = max_width

        # --- Span along the recess wall's short (spine-depth) axis -------
        cos_a = abs(math.cos(math.radians(self.dice_tower_ramp_angle)))
        if cos_a < 1e-9:
            # A vertical ramp has no spine-depth span to constrain.
            return
        max_span = spine_depth - 2 * t
        max_length = max_span / cos_a
        if max_span <= 0:
            self._warn(
                "spine depth %.1f mm is too shallow to seat a ramp tab row at "
                "all. Ramps omitted — grow y (spine depth).",
                spine_depth,
            )
            self.dice_tower_ramp_count = 0
        elif self.dice_tower_ramp_length > max_length:
            self._warn(
                "dice_tower_ramp_length=%.1f mm spans %.1f mm of the %.1f mm "
                "spine-depth axis at %.1f deg, so its finger holes would run "
                "off the recess wall; clamped to %.1f mm. Grow y (spine "
                "depth) or reduce dice_tower_ramp_angle to keep longer ramps.",
                self.dice_tower_ramp_length,
                self.dice_tower_ramp_length * cos_a, spine_depth,
                self.dice_tower_ramp_angle, max_length,
            )
            self.dice_tower_ramp_length = max_length

    # -----------------------------------------------------------------
    # Render entry point
    # -----------------------------------------------------------------

    def render(self):
        """Render the book and all configured inserts to the SVG canvas.

        We do **not** call ``super().render()`` here. FlexBook.render() bakes
        in the 7-piece sliding-pin latch (4 brackets + stopper + pin emitted
        as parts, plus the slot/anchor cuts on the cover/wall). Replicating
        only the parts we want lets us swap in the tab-based closure without
        inheriting any latch hardware.

        The y↔h swap and ``radius``/``c4`` derivation are reproduced from
        :meth:`FlexBook.render` so the cover/spine/side helpers see the same
        ``self.h`` and ``self.y`` they normally would. (FlexBook.render
        swaps these because the author found it easier to think about the
        spine depth as ``h`` and the cover height as ``y`` in the helpers.)
        """
        spine_depth = self.y
        t = self.thickness

        # Collected by _warn() as the resolvers and panel helpers run, then
        # drawn onto the canvas by _emit_warning_block() at the very end.
        self._warnings = []

        self._resolve_cavity_heights(spine_depth)
        self._resolve_dice_hole_radius(spine_depth)
        self._resolve_ramp_geometry(spine_depth)

        # The latch doubler laminates t mm onto the latch wall's INNER
        # (cavity-facing) face, stealing that much from the cavity's
        # cell-width axis — the tight one (only ~2 mm of tray play at the
        # default sizes). Compensate by widening the cover (x) by the same
        # t so the tray layout keeps its clearance with the doubler fitted.
        # The trays are sized from the cell list (independent of x), so they
        # are unchanged; only the cover/side panels grow. Done here rather
        # than in the default x so the compensation tracks both the live
        # thickness AND whether the doubler is actually enabled.
        if self.latch_doubler:
            self.x += t

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
        # Glue-on reinforcement plate for the latch wall (doubles the tab
        # thickness). The cover's tab slots are widened to match in
        # flexBookCover when this is enabled.
        if self.latch_doubler:
            self.flexBookLatchDoubler(self.h, self.y, move="right")
        # Glue-on strip that doubles the cover's slot-to-edge bridge.
        if self.latch_cover_reinforcement and self.latch_tab_count > 0:
            self.flexBookCoverReinforcement(self.y, move="right")

        with self.saved_context():
            self.flexBookSide(self.h, self.x, self.radius, move="right")
            self.flexBookSide(self.h, self.x, self.radius, move="mirror right")
        self.flexBookSide(self.h, self.x, self.radius, move="up only")

        # FlexBook.render() now emits the 4 latch brackets, stopper plate,
        # and latch pin (flexbook.py:299-313). We intentionally skip all
        # of that — the latch wall's tabs replace it.

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
                self._emit_half_ellipse_ramp(
                    self.dice_tower_ramp_length,
                    self.dice_tower_ramp_width,
                    move="up", label="dice tower ramp")

        # ---- 7. Warning block -----------------------------------------
        # Last, so anything _warn() collected while the panels were being
        # emitted is included. Drawn in the annotation colour, not cut.
        self._emit_warning_block()
