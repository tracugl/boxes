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
  track and train: ``--train_envelope`` mm below the top (43 by default: 3 mm
  of N track and a 40 mm train; about 70 for HO);
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

from boxes import boolarg


class HexmoUnderTrackMixin:
    """Size, checks and drawing of the under-deck track opening."""

    # Default --train_envelope: 3 mm of N track plus a 40 mm train.
    _UNDER_TRACK_ENVELOPE = 43.0
    # Minimum solid material between the opening and any other hole or slot.
    _UNDER_TRACK_CLEAR = 5.0
    # --subway_ports: the upright cable slot at each end of an access wall
    # (length up the wall where it stands between a pilot pair, width; mm),
    # and the least wood between it and the pilots beside it.  Outside the
    # pair it runs the access openings' height.
    _CABLE_SLOT = (30.0, 14.0)
    _CABLE_SLOT_WOOD = 4.0

    def _addUnderTrackArgs(self):
        """Register --under_track_height, --under_track_width and --train_envelope.

        Called from each generator's ``__init__`` next to its own switch
        (HexmoHexagon --under_track_edges, HexmoRectangle --under_track), so
        the shared option names, defaults and help text are identical.
        """
        self.argparser.add_argument(
            "--under_track_height", action="store", type=float, default=0.0,
            help="Under-deck track opening: height (mm) of the lower track above "
                 "the floor panel.  The opening's top edge is always one material "
                 "thickness under the deck.  With --subway_ports (the default) its "
                 "bottom edge is one thickness above the floor, the same as the "
                 "top, so a wall has no up side and the track bridges it; without, "
                 "the bottom edge is this height and the wall carries the track.  "
                 "0 (default) puts the track as high as still leaves "
                 "--train_envelope for the track and train.")
        self.argparser.add_argument(
            "--under_track_width", action="store", type=float, default=30.0,
            help="Under-deck track opening: width (mm) along the wall, centred on "
                 "the wall's centre line (the track centreline).")
        self.argparser.add_argument(
            "--train_envelope", action="store", type=float,
            default=self._UNDER_TRACK_ENVELOPE,
            help="Height (mm) a lower track needs above its track height: track "
                 "plus the tallest train, with a little margin.  43 (default) is "
                 "3 mm of N track and a 40 mm train; about 70 suits HO.  Sets the "
                 "under-deck opening's automatic height, and whether a track "
                 "opening can be a closed hole or must be a notch open at the top.")
        self.argparser.add_argument(
            "--subway_ports", action="store", type=boolarg, default=True,
            help="Subway-ready walls (default on): every wall that joins another "
                 "module gets the under-deck opening (--under_track_height, "
                 "--under_track_width) in its middle, where the spoke meets it, "
                 "so a subway can carry on through any joint; and each such access "
                 "wall (--access_openings) an upright 14 × 30 mm cable slot at each end, "
                 "between its end pair of Ø6 pilots, clear of the subway's supports, "
                 "lining up through the joint.  On HexmoRectangle the end walls and "
                 "short dividers; on the trapezoid its short walls (and its long "
                 "wall's middle post); on the full hexagon all six.  Walls whose "
                 "middle already has a track or spur opening, the lowered "
                 "--lower_ground walls, and walls too small for it are left as "
                 "they are.")

    def _underTrackSpan(self, body):
        """Bottom and top of the opening, in mm above the floor panel.

        With --subway_ports (the default) the opening is the same top and
        bottom: one thickness under the deck and one above the floor, so a
        wall has no "up side" and goes in either way up.  The track height
        (--under_track_height, or the automatic one) is still checked to leave
        the train room under the deck; the track bridges the wall at a joint.
        Without it, the opening's bottom is the track height, so the wall
        carries the track at the joint.

        @param body - Wall body height: floor panel top to deck underside (mm).
        @returns ``(bottom, top)``.
        @throws ValueError - If the width is not positive, the opening would
                             reach into the floor joint (closer than one
                             thickness to the floor panel), or the track height
                             leaves no opening under the deck.
        """
        t = self.thickness
        width = self.under_track_width
        if self.train_envelope <= 0:
            raise ValueError(
                f"--train_envelope must be positive (got {self.train_envelope:g}).")
        if width <= 0:
            raise ValueError(
                f"--under_track_width must be positive (got {width:g}).")
        top = body - t
        height = self.under_track_height
        bottom = top - self.train_envelope if height == 0 else height
        if bottom < t:
            raise ValueError(
                f"under-deck track opening: its bottom at {bottom:g} mm would cut "
                f"into the floor joint; keep it at least {t:g} mm above the floor "
                "panel (raise --under_track_height, or --h).")
        if bottom >= top:
            raise ValueError(
                f"--under_track_height {height:g} leaves no opening under the deck: "
                f"the opening's top is {top:g} mm above the floor panel.")
        if self.subway_ports:
            # Symmetric: as far above the floor as the top is under the deck.
            return body - top, top
        return bottom, top

    def _portFits(self, body):
        """Whether a --subway_ports opening fits a wall of this height.

        --subway_ports is on by default, so a wall too low for the opening
        simply goes without one.

        @param body - Wall body height (mm).
        @returns True when _underTrackSpan accepts it.
        """
        try:
            self._underTrackSpan(body)
        except ValueError:
            return False
        return True

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

    def _drawCablePill(self, along, across, along_x, length=None):
        """One upright cable slot (--subway_ports), at a wall end.

        @param along   - Its centre along the wall.
        @param across  - Its centre up (or down) the wall.
        @param along_x - As for _drawUnderTrackOpening.
        @param length  - Its length up the wall (default the 30 mm of
                         _CABLE_SLOT); it is _CABLE_SLOT's 14 mm wide.
        """
        default, width = self._CABLE_SLOT
        length = default if length is None else length
        if along_x:
            self.rectangularHole(along, across, width, length, r=width / 2,
                                 center_x=True, center_y=True)
        else:
            self.rectangularHole(across, along, length, width, r=width / 2,
                                 center_x=True, center_y=True)
