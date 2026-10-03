"""Big-hole drawing shared by HexmoHexagon and HexmoRectangle.

The big holes are both weight reduction and the under-board train
pass-through, so they must line up from module to module: HexmoHexagon side
wall → HexmoRectangle end wall → short dividers → next module.  Both
generators place them at the same centres (see each generator's alignment
layout).  This mixin is the single place that decides each hole's *shape and
size*, so the holes stay identical on every panel.

``--big_hole_width`` / ``--big_hole_height`` shrink every rounded-rect big
hole around its existing centre.  Callers pass the radius ``r`` they place
holes with, and placement (centres, counts, packing) keeps using it, so the
holes never move.  Only the drawn size changes, plus any clearance check that
asks :meth:`_bigHoleHalfExtent` for the real size, such as the rect's
long-support keep-out.

The module name starts with an underscore, so generator discovery
(``getAllBoxGenerators``) skips it.  This mixin is not a generator.
"""
from __future__ import annotations


class HexmoBigHoleMixin:
    """Shape and size of the big holes, mixed into both Hexmo generators."""

    def _addBigHoleSizeArgs(self):
        """Register --big_hole_width and --big_hole_height.

        Called from each generator's ``__init__`` right after
        --big_hole_roundness, so the option names, defaults and help text are
        identical in both.
        """
        for name, axis in (("width", "along the wall"), ("height", "up the wall")):
            self.argparser.add_argument(
                f"--big_hole_{name}", action="store", type=float, default=0.0,
                help=f"--big_hole_shape=rounded_rect only: the big holes' {name} "
                     f"in mm ({axis}).  0 (default) keeps the automatic size, "
                     "a square of side h − 30.  A smaller value shrinks every big "
                     "hole around its own centre on both HexmoHexagon and "
                     "HexmoRectangle, so the holes still line up module to module "
                     "(they double as the under-board train pass-through).  "
                     "Positions and counts never change.  A narrower hole can fit "
                     "where the full size is dropped, e.g. between a "
                     "HexmoRectangle's long supports.  Must not exceed the "
                     "automatic size.")

    def _bigHoleHalfExtent(self, r):
        """Half-width (along the wall) and half-height (up the wall) of a big hole.

        @param r - Placement radius of the hole (the automatic half-size).
        @returns ``(half_width, half_height)`` in mm.  ``(r, r)`` unless
                 rounded_rect is selected and a size is set.
        @throws ValueError - If a size is negative or larger than ``2·r``.
        """
        if self.big_hole_shape != "rounded_rect":
            return r, r
        halves = []
        for name in ("width", "height"):
            size = getattr(self, f"big_hole_{name}")
            if size < 0 or size > 2 * r + 1e-9:
                raise ValueError(
                    f"--big_hole_{name} must be between 0 (automatic) and "
                    f"{2 * r:.1f} mm, the automatic size at this --h "
                    f"(got {size:g}).")
            halves.append(size / 2 if size > 0 else r)
        return tuple(halves)

    def _drawBigHole(self, x, y, r, along_x=True):
        """Draw one big through-hole centred at (x, y).

        Honours ``--big_hole_shape``.  A circle of radius ``r`` by default, or,
        with ``rounded_rect``, a rounded rectangle centred on the same point.
        It is a square of side ``2·r`` unless --big_hole_width / --big_hole_height
        shrink it.  The corner radius is ``--big_hole_roundness`` × half the
        shorter side; :meth:`Boxes.rectangularHole` clamps it to at most half the
        side, so any roundness value is safe.  A box too short for big holes
        (``r ≤ 0``, i.e. ``--h ≤ 2·_SPACER``) gets none.

        @param x       - Hole centre x (mm, callback frame).
        @param y       - Hole centre y (mm, callback frame).
        @param r       - Placement radius of the hole (mm).
        @param along_x - True when the panel's x axis runs along the wall (rect
                         panels, hex supports).  False on the hex side walls,
                         whose hole frame has x running *up* the wall, so width
                         and height swap axes there.
        @throws ValueError - Propagated from :meth:`_bigHoleHalfExtent`.
        """
        if r <= 0:
            return
        if self.big_hole_shape != "rounded_rect":
            self.hole(x, y, r)
            return
        half_w, half_h = self._bigHoleHalfExtent(r)
        corner = max(0.0, self.big_hole_roundness) * min(half_w, half_h)
        dx, dy = (2 * half_w, 2 * half_h) if along_x else (2 * half_h, 2 * half_w)
        self.rectangularHole(x, y, dx, dy, r=corner, center_x=True, center_y=True)
