"""Track-laying guide plate shared by HexmoHexagon and HexmoRectangle.

A HexmoRectangle's short (end) wall joins a HexmoHexagon / trapezoid side
wall face to face, so both generators must produce the *same* guide: one jig
that fits either module and holds the track at the same place across the
joint.  Keeping the whole guide in this one mixin guarantees that.

**Wall hole frame.**  Every method takes ``(s, l)``, the hexagon side wall's
alignment-pattern frame: x runs up the wall from the wall-body edge furthest
from the deck (x = 0) to the edge under the deck (x = l), and y runs along the
wall (0 … s), centred on the wall and so on the track centreline.

* HexmoHexagon passes its own ``(side_orig, l)``.
* HexmoRectangle passes ``(_hexWallLength(), _hexWallHeight())``, the frame of
  the hex wall it mates with.  Its end-wall holes are placed in that same
  frame, see ``tests/test_hexmo_wall_alignment.py``.

The rect's deck is its base plate, at the *bottom* of its end-wall panel, but
the frame is measured from the deck side either way, so the guide is
identical.

The module name starts with an underscore, so generator discovery
(``getAllBoxGenerators``) skips it.  This mixin is not a generator.

Host requirements: the ``_SPACER``, ``_R2`` and ``_R3`` constants, the
``--corner_holes`` and ``--track_*`` arguments, and the usual Boxes drawing
methods.
"""
from __future__ import annotations

from boxes import boolarg
from boxes.Color import Color


class HexmoTrackGuideMixin:
    """Guide-plate geometry and drawing, mixed into both Hexmo generators."""

    _GUIDE_MIN_WEB = 5  # min material between a track-guide window and the wall end (mm)

    def _addTrackGuideArgs(self):
        """Register --track_guide and --track_guide_clearance.

        Called from each generator's ``__init__`` after its --track_* options,
        so the option names, defaults and help text are identical in both.
        """
        self.argparser.add_argument(
            "--track_guide", action="store", type=boolarg, default=False,
            help="Add a track-laying guide plate: a temporary jig that is "
                 "dowelled to a wall's outer face (any HexmoHexagon side wall "
                 "or HexmoRectangle end wall; the same plate fits all of them) "
                 "through two corner-group pins, and stands above the deck, with one "
                 "rectangular window per track (exactly --track_width wide).  "
                 "Every track crosses a wall perpendicularly at its centre, so "
                 "one guide fits every standard wall.  When the tracks are "
                 "asymmetric, flip the plate over for the other end of a curve.")
        self.argparser.add_argument(
            "--track_guide_clearance", action="store", type=float, default=30.0,
            help="Height (mm) of each --track_guide window.  The window floor "
                 "sits one material thickness below the deck surface, and this "
                 "height is the vertical room left for roadbed, risers and "
                 "scenery, so the track can move up and down but not sideways.")

    def _cornerGroupHoles(self, s, l):
        """List the corner registration holes shared by all side-panel variants.

        Each end of a side panel (top and bottom edges) carries an L-shaped cluster
        of small pilot holes at its two corners, plus one medium hole centred on the
        panel's x-midpoint at 3 × _SPACER from the edge.  Together these form the
        'group-of-8' referenced in the alignment-hole pattern: 8 small holes total
        (3 per corner L × 2 corners, but the two inward L-legs share the centre-line
        column) surrounding the 2 centre-line medium holes.

        All positions use fixed _SPACER offsets so the clusters sit the same physical
        distance from the panel edges regardless of how wide or tall the panel is.
        The HexmoHexagon side-wall layout.  HexmoHexagon draws it through
        ``_drawCornerGroup8`` (from drawAlignmentHoles and
        drawAlignmentHolesLong).  :meth:`_trackGuidePins` filters it for both
        generators, because the rect's end-wall holes are placed in this same
        frame.

        **Frame.**  The side-wall hole frame: x runs up the wall from the
        wall-body bottom (x = 0) to its top under the deck (x = l); y runs
        along the wall (0 … s).

        @param s - Panel height (pre-shrink side0 value), used for y-axis positions.
        @param l - Panel width (slant length), used for x-axis positions.
        @returns ``(x, y, radius)`` tuples in drawing order (the order is kept
                 stable so the SVG output does not change).
        """
        sp = self._SPACER
        r2 = self._R2
        r3 = self._R3

        # Always drawn: the two medium registration holes (one near each end,
        # on the panel centre line) plus the pilot holes directly above and
        # below each medium (the "centre-line pins" at x = sp and x = l − sp,
        # y = 3·sp / s − 3·sp).  These give registration with minimal pierces.
        holes = [
            (l - sp, s - 3 * sp, r3),  # top medium: pin above
            (l / 2,  s - 3 * sp, r2),  # top-centre medium hole
            (l - sp, 3 * sp,     r3),  # bottom medium: pin above
            (l / 2,  3 * sp,     r2),  # bottom-centre medium hole
            (sp,     s - 3 * sp, r3),  # top medium: pin below
            (sp,     3 * sp,     r3),  # bottom medium: pin below
        ]

        # The six surrounding pilot holes per end (four corner L-clusters) are
        # only drawn in the full 'g6' pattern; 'g2' omits them to save pierces.
        if self.corner_holes != "g6":
            return holes

        return holes + [
            # Top-right and top-left corner L-clusters.
            (l - sp,     s - sp,     r3),
            (l - sp,     s - 2 * sp, r3),
            (l - 2 * sp, s - sp,     r3),
            (sp,         s - sp,     r3),
            (sp,         s - 2 * sp, r3),
            (2 * sp,     s - sp,     r3),
            # Bottom-right and bottom-left corner L-clusters.
            (l - sp,     sp,         r3),
            (l - sp,     2 * sp,     r3),
            (l - 2 * sp, sp,         r3),
            (sp,         sp,         r3),
            (sp,         2 * sp,     r3),
            (2 * sp,     sp,         r3),
        ]

    def _trackOffsets(self):
        """Signed offsets (mm) of each track centreline from the reference line.

        Shared by :meth:`drawTrackLines` (radial offsets of the etched arcs)
        and :meth:`drawTrackGuide` (window positions along the wall), so the
        guide windows can never drift out of step with the etched deck guide.

        'centred' (default) is symmetric about 0, so odd counts land a line on
        the centreline and even counts straddle it.  'outer' is one-sided
        (0, +spacing, +2·spacing, …), so the centreline is the minimum radius
        and every extra line steps outward (larger radius) only.  The whole
        family is then biased by --track_center_offset, which composes with
        either mode and is the sole placement control for a single track.
        Positive always means outward, i.e. toward the outside of a curve.

        @returns One offset per track (empty when --track_line_count < 1).
        """
        n_lines = self.track_line_count
        spacing = self.track_spacing
        if self.track_offset == "outer":
            offsets = [i * spacing for i in range(n_lines)]
        else:
            offsets = [(i - (n_lines - 1) / 2.0) * spacing for i in range(n_lines)]
        return [self.track_center_offset + o for o in offsets]

    def _trackGuidePins(self, s, l):
        """The wall holes the track guide dowels through.

        Just two holes: the small Ø(2·_R3) pilot directly above each end's
        medium hole, on the deck side (wall-frame ``x > l/2``).  Both
        --corner_holes patterns have these, so the guide is the same either
        way.  Two pins fix both position and rotation.  Staying near the deck
        keeps the plate short.  Skipping the g6 corner L-clusters, which sit
        _SPACER from each wall end, keeps it narrow.  The holes are taken from
        :meth:`_cornerGroupHoles` itself, so they match the wall exactly.

        @param s - Wall reference length (``side_orig``), the same ``s`` the
                   HexmoHexagon side walls pass to ``_drawCornerGroup8``.
        @param l - Wall body height (the ``l`` passed to the same method).
        @returns ``(x, y, radius)`` tuples in the wall hole frame.
        """
        holes = self._cornerGroupHoles(s, l)
        medium_ys = {y for _, y, r in holes if r == self._R2}
        return [(x, y, r) for x, y, r in holes
                if r == self._R3 and x > l / 2.0 and y in medium_ys]

    def _trackGuideHalfWidth(self, s, l):
        """Half the guide plate's width, measured from the wall centre.

        The plate is just wide enough to leave one _SPACER of solid material
        beyond the outermost pin centre or window edge on either side.  It is
        symmetric about the wall centre, so its outline is unchanged when the
        plate is flipped for the other end of a curve.

        @param s - Wall reference length (``side_orig``).
        @param l - Wall body height.
        @returns Half-width in mm.
        @throws ValueError - Propagated from :meth:`_trackGuideWindows`.
        """
        centre = s / 2.0
        reach = [abs(y - centre) for _, y, _ in self._trackGuidePins(s, l)]
        reach += [abs(cx - centre) + w / 2.0
                  for cx, _, w, _ in self._trackGuideWindows(s, l)]
        return max(reach) + self._SPACER

    def _trackGuideBase(self, s, l):
        """Wall-frame height (x) of the guide plate's bottom edge.

        One _SPACER below the lowest pin, the same edge margin the wall itself
        gives its holes.

        @param s - Wall reference length (``side_orig``).
        @param l - Wall body height.
        @returns The wall-frame x that maps to guide-frame y = 0.
        """
        return min(x for x, _, _ in self._trackGuidePins(s, l)) - self._SPACER

    def _trackGuideDeckY(self, s, l):
        """Guide-frame height of the deck top surface.

        In the wall frame the deck top is ``x = l + t``: the wall body ends at
        ``l``, and the deck panel's thickness ``t`` sits on top of it (the
        wall's top fingers fill the deck's edge slots).

        @param s - Wall reference length (``side_orig``).
        @param l - Wall body height.
        @returns y (mm) measured up from the plate's bottom edge.
        """
        return l + self.thickness - self._trackGuideBase(s, l)

    def _trackGuideWindowFloor(self, s, l):
        """Guide-frame height of the bottom edge of every window.

        One material thickness below the deck top surface, which is level
        with the deck's underside.  The window floor then always sits below
        the track, so the plate can never lift it, even when the plate rides
        a little high on its dowels (pin clearance, burn) or the deck edge is
        sanded.

        @param s - Wall reference length (``side_orig``).
        @param l - Wall body height.
        @returns y (mm) measured up from the plate's bottom edge.
        """
        return self._trackGuideDeckY(s, l) - self.thickness

    def _trackGuideSize(self, s, l):
        """Outer size of the track-guide plate, in the guide's own frame.

        The frame has x along the wall, from the plate's left edge at wall
        position ``s/2 − half-width`` (see :meth:`_trackGuideHalfWidth`), and y
        up from the plate's bottom edge (see :meth:`_trackGuideBase`).  The
        plate runs from just below the pins, past the windows (see
        :meth:`_trackGuideWindowFloor`), to one _SPACER of solid material
        above them.

        @param s - Wall reference length (``side_orig``).
        @param l - Wall body height.
        @returns ``(width, height)`` in mm.
        @throws ValueError - Propagated from :meth:`_trackGuideWindows`.
        """
        height = (self._trackGuideWindowFloor(s, l) + self.track_guide_clearance
                  + self._SPACER)
        return 2.0 * self._trackGuideHalfWidth(s, l), height

    def _trackGuideWindows(self, s, l):
        """Compute the track-guide windows, one per track.

        Each window starts at :meth:`_trackGuideWindowFloor`, one material
        thickness below the deck top, and rises by
        --track_guide_clearance, leaving room for roadbed and scenery.  Its
        width is exactly --track_width (rectangularHole compensates for laser
        burn), so the track cannot shift sideways.  Tracks cross every wall
        perpendicularly at its centre, offset along the wall by the same
        amounts as the etched lines: at a curve end the radial direction lies
        along the wall, and on the straight the lateral offset does.

        @param s - Wall reference length (``side_orig``).
        @param l - Wall body height.
        @returns List of ``(centre_x, bottom_y, width, height)`` tuples, with
                 ``centre_x`` measured along the wall (0 … s) and ``bottom_y``
                 in the guide frame.
        @throws ValueError - If the clearance or track width is not positive,
                             or a window would reach within
                             ``_GUIDE_MIN_WEB`` of either wall end (the track
                             must cross the wall itself).
        """
        width = self.track_width
        clearance = self.track_guide_clearance
        if clearance <= 0:
            raise ValueError(
                f"--track_guide_clearance must be positive (got {clearance}).")
        if width <= 0:
            raise ValueError(
                f"--track_width must be positive for the track guide (got {width}).")

        floor_y = self._trackGuideWindowFloor(s, l)
        windows = []
        for off in self._trackOffsets():
            cx = s / 2.0 + off
            # A track crossing past the wall's end would miss the module
            # joint entirely, so windows must stay over the wall with a web
            # of margin.
            if (cx - width / 2.0 < self._GUIDE_MIN_WEB
                    or cx + width / 2.0 > s - self._GUIDE_MIN_WEB):
                raise ValueError(
                    f"track guide window at offset {off:+.1f} mm "
                    f"(width {width} mm) does not fit within the {s:.1f} mm wall; "
                    "reduce --track_spacing, --track_center_offset or "
                    "--track_line_count.")
            windows.append((cx, floor_y, width, clearance))
        return windows

    def drawTrackGuide(self, s, l, move="right"):
        """Draw the track-laying guide plate.

        The plate is dowelled to the outer face of any standard HexmoHexagon
        side wall or HexmoRectangle end wall
        through the small pilot holes nearest the deck (:meth:`_trackGuidePins`).
        No medium holes are cut.  The pins and the plate outline are both
        symmetric about the wall centre, so the plate fits either way round
        and can be flipped face-down.

        **Frame mapping.**  The wall's hole frame has x up the wall and y
        along it.  The guide frame has x along the wall, starting at wall
        position ``shift = s/2 − half-width``, and y up from the plate's
        bottom edge, which sits at wall-frame height :meth:`_trackGuideBase`.
        A pin at wall ``(x, y)`` is therefore drawn at guide
        ``(y − shift, x − base)``.  This mirrors the along-wall axis, which is
        harmless because the pins are symmetric about the wall centre.

        When the tracks are not symmetric about the centre (--track_offset
        outer, or a --track_center_offset), an arrow is etched pointing to the
        outside of the curve.  The other end of a curve is its mirror image,
        so the plate is flipped over for that end.

        @param s    - Wall reference length (``side_orig``).
        @param l    - Wall body height.
        @param move - Layout direction passed to rectangularWall.
        @throws ValueError - Propagated from :meth:`_trackGuideWindows`.
        """
        width, height = self._trackGuideSize(s, l)
        # Compute (and validate) before drawing, so an error never leaves
        # half a part in the layout.
        windows = self._trackGuideWindows(s, l)
        pins = self._trackGuidePins(s, l)
        base = self._trackGuideBase(s, l)
        shift = s / 2.0 - width / 2.0
        offsets = self._trackOffsets()
        asymmetric = sorted(offsets) != sorted(-o for o in offsets)

        def features():
            for x, y, r in pins:
                self.hole(y - shift, x - base, r)
            for cx, y0, w, h in windows:
                self.rectangularHole(cx - shift, y0, w, h,
                                     center_x=True, center_y=False)
            if asymmetric:
                # Label in the solid band above the windows.  stroke=True so
                # lasers that vector-etch by stroke colour still trace it.
                self.text("outside of curve ->", x=width / 2.0,
                          y=height - self._SPACER / 2.0, align="middle center",
                          fontsize=self._SPACER * 0.4, color=Color.ETCHING,
                          stroke=True)

        self.rectangularWall(width, height, "eeee", callback=[features],
                             move=move, label="track guide")
