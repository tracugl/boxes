"""Under-deck track opening shared by HexmoHexagon and HexmoRectangle.

A lower-level track (for example the helix ring's descending spur) can run
*under* a module's deck and through its joint walls.  The usual centre big
hole is centred halfway up the wall, which suits a train on the floor but not
one running just under the deck.  On the walls the track crosses, the centre
big hole is replaced by a rectangular opening on the wall's centre line that
hangs from just under the deck:

* its **top** is one material thickness below the deck underside, leaving a
  strip of wall under the deck joint;
* its **bottom** is the track height, ``--under_track_height`` mm above the
  floor panel, or, at 0 (the default), as high as still leaves room for the
  track and a 40 mm train (43 mm below the top);
* its **width** along the wall is ``--under_track_width``.

Both generators measure it from the deck, so the openings of joined modules
line up even though their wall frames differ: HexmoHexagon side walls run x
up from the floor panel, HexmoRectangle end walls and dividers run y down from
the deck (their base plate is the deck).  Corners are rounded like rounded-rect
big holes (``--big_hole_roundness``).

The module name starts with an underscore, so generator discovery skips it.
This mixin is not a generator.
"""
from __future__ import annotations


class HexmoUnderTrackMixin:
    """Size, checks and drawing of the under-deck track opening."""

    # Track (3 mm) plus a 40 mm train: the automatic opening height.
    _UNDER_TRACK_ENVELOPE = 43.0
    # Minimum solid material between the opening and any other hole or slot.
    _UNDER_TRACK_CLEAR = 5.0

    def _addUnderTrackArgs(self):
        """Register --under_track_height and --under_track_width.

        Called from each generator's ``__init__`` next to its own switch
        (HexmoHexagon --under_track_edges, HexmoRectangle --under_track), so
        the shared option names, defaults and help text are identical.
        """
        self.argparser.add_argument(
            "--under_track_height", action="store", type=float, default=0.0,
            help="Under-deck track opening: height (mm) of the lower track above "
                 "the floor panel, which is the opening's bottom edge.  The top "
                 "edge is always one material thickness under the deck.  0 "
                 "(default) puts it as high as still leaves 43 mm for the track "
                 "and a 40 mm train.")
        self.argparser.add_argument(
            "--under_track_width", action="store", type=float, default=30.0,
            help="Under-deck track opening: width (mm) along the wall, centred on "
                 "the wall's centre line (the track centreline).")

    def _underTrackSpan(self, body):
        """Bottom and top of the opening, in mm above the floor panel.

        @param body - Wall body height: floor panel top to deck underside (mm).
        @returns ``(bottom, top)``.
        @throws ValueError - If the width is not positive, the opening would
                             reach into the floor joint (closer than one
                             thickness to the floor panel), or the track height
                             leaves no opening under the deck.
        """
        t = self.thickness
        width = self.under_track_width
        if width <= 0:
            raise ValueError(
                f"--under_track_width must be positive (got {width:g}).")
        top = body - t
        height = self.under_track_height
        bottom = top - self._UNDER_TRACK_ENVELOPE if height == 0 else height
        if bottom < t:
            raise ValueError(
                f"under-deck track opening: its bottom at {bottom:g} mm would cut "
                f"into the floor joint; keep it at least {t:g} mm above the floor "
                "panel (raise --under_track_height, or --h).")
        if bottom >= top:
            raise ValueError(
                f"--under_track_height {height:g} leaves no opening under the deck: "
                f"the opening's top is {top:g} mm above the floor panel.")
        return bottom, top

    def _checkUnderTrackClearsCorners(self, s):
        """Make sure the opening keeps clear of the corner hole groups.

        The groups at each wall end reach ``3·_SPACER + _R2`` in from the end
        (the edge of their medium hole).

        @param s - Wall pattern length (mm); the opening is centred on it.
        @throws ValueError - If the opening reaches into a corner group.
        """
        reach = 3 * self._SPACER + self._R2 + self._UNDER_TRACK_CLEAR
        if s / 2.0 - self.under_track_width / 2.0 < reach:
            raise ValueError(
                f"--under_track_width {self.under_track_width:g} mm runs into the "
                f"wall's corner hole groups; at most {s - 2 * reach:.1f} mm fits "
                "on this wall.")

    def _drawUnderTrackOpening(self, centre, lo, hi, along_x):
        """Cut the opening.

        @param centre  - Along-wall position of its centre (the wall centre).
        @param lo, hi  - Its extent up/down the wall, in the caller's frame.
        @param along_x - True when the frame's x runs along the wall (rect
                         walls), False when x runs up the wall (hex side walls).
        """
        width, span = self.under_track_width, hi - lo
        corner = max(0.0, self.big_hole_roundness) * min(width, span) / 2.0
        mid = (lo + hi) / 2.0
        if along_x:
            self.rectangularHole(centre, mid, width, span, r=corner,
                                 center_x=True, center_y=True)
        else:
            self.rectangularHole(mid, centre, span, width, r=corner,
                                 center_x=True, center_y=True)
