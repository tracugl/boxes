"""Upper and lower ground for scenery on a Hexmo trapezoid (``--lower_ground``).

On the helix ring the spur runs down the inner side of each trapezoid, on its
risers, through a slot in the deck.  For scenery the inner side is opened up
into two levels:

* **upper ground** - the deck, carrying the main line, trimmed back to the
  outer edge of the spur's deck slot (or, with ``--upper_edge_gap``, to a set
  distance from the main line's rail edge, never inside the slot);
* **lower ground** - a new plate whose top is ``--lower_ground`` mm above the
  floor panel, from the edge-4 wall out to the spur slot's inner edge.

The 35 mm strip under the spur stays open down to the box floor, so the spur's
risers stand there exactly as before.  The walls follow: the edge-4 wall, and
the inner part of the side walls (edges 3 and 5) from edge 4 to the spur, come
down to carry the lower plate; across the spur the side walls keep its track
opening (cut from the wall top as a notch, its bottom still carrying the bed
end at the joint); from there out they are full height under the deck.  Any
support inside the lower area is shortened to sit under the lower plate.

On the full hexagon (the helix ring's M6) only the side walls on edges 3 and 5
take the stepped profile, so they meet the trapezoids beside it; its deck edge
goes plain over the lowered part, and is cut back by hand.

**Positions.**  Wall positions are mm along an edge from its midpoint,
anticlockwise seen from above, as for ``--track_openings``.  The edge-4 end of
edge 3 is at negative positions, of edge 5 at positive ones.  Both a wall's top
edge and the deck's edge are drawn in increasing position, so ``side / 2 + p``
is the distance along the wall top (``side`` long) and ``t + side / 2 + p``
along the deck edge (one thickness longer at each end).

**Outlines.**  The trimmed deck and the lower plate are drawn as one closed
turtle path each, nominal lengths and turns only, so Boxes' burn correction
(an arc at every corner) keeps them closed.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass

from boxes.generators._hexmo_deck_slots import (
    centreline_points, parse_deck_slots, trim_segments,
)
from boxes.generators._hexmo_risers import _side, spine_kites
from boxes.generators._hexmo_track_openings import SplitJointEdge
from boxes.generators._hexmo_track_routes import (
    EDGE_ANGLES, edge_position, offset_segments, route_geometry, segments_polyline,
)

# Straight-line steps per arc when a curved panel edge is drawn as a polyline
# (a 60° arc of ~300 mm radius in 64 chords is within 0.01 mm of true).
_ARC_STEPS = 64
# Least solid material between a support's slot and the edge of the plate
# carrying it (mm, beyond half the support's thickness).
_SUPPORT_EDGE_CLEAR = 3.0
# How far a spur slot's end may sit from its wall opening's side (mm).
_ALIGN_TOL = 0.5
_ROOT3 = math.sqrt(3.0)


@dataclass(frozen=True)
class WallStep:
    """One side wall's stepped top: lowered, across the spur, then full height.

    @ivar edge     - 3 or 5.
    @ivar pos_in   - Where the lowered part ends: the spur opening's side
                     nearer edge 4 (position, mm).
    @ivar pos_out  - The spur opening's other side.
    @ivar pos_deck - Where the deck's joint starts (``pos_out``, or further
                     out with ``--upper_edge_gap``).  Between ``pos_out`` and
                     here the wall top is full height and plain.
    @ivar band     - Height of the wall top across the spur: the opening's
                     bottom (the spur's track base), mm above the floor panel.
    """

    edge: int
    pos_in: float
    pos_out: float
    pos_deck: float
    band: float

    @property
    def inner_first(self):
        """True when the edge-4 end is at the start of the wall's top edge."""
        return self.edge == 3


@dataclass
class LowerGroundPlan:
    """The solved ``--lower_ground`` layout for one module.

    @ivar height     - Lower plate top, mm above the floor panel.
    @ivar body       - Lowered wall body height (plate underside), ``height - t``.
    @ivar trapezoid  - True on the trapezoid (deck trimmed, lower plate drawn).
    @ivar walls      - Edge → :class:`WallStep` for edges 3 and 5.
    @ivar split      - The spur slot's route ``(start, start_offset, end,
                       end_offset)`` (trapezoid), whose slot and etched track
                       leave the deck; None on the hexagon.
    @ivar deck_curve - The deck's new inner edge in the deck frame (hex centre,
                       y up), edge 3 → edge 5, ends on the walls' inner faces.
    @ivar plate_curve - The lower plate's outer edge (the spur slot's inner
                       edge), likewise.
    @ivar lower      - Indices into ``_supportLayout`` of the supports under
                       the lower plate (shortened); the rest stay under the deck.
    @ivar slot       - The spur slot's centreline pieces (trapezoid), and
    @ivar plate_side - the signed offset (mm, right of travel) of its side
                       the lower plate stops at.
    """

    height: float
    body: float
    trapezoid: bool
    walls: dict
    split: tuple | None = None
    deck_curve: list | None = None
    plate_curve: list | None = None
    lower: frozenset = frozenset()
    slot: tuple | None = None
    plate_side: float = 0.0


class HexmoLowerGroundMixin:
    """``--lower_ground`` and ``--upper_edge_gap`` for HexmoHexagon.

    Host requirements: Boxes drawing methods, ``_trapezoidMiter``,
    ``_supportLayout``, ``_supportPoints`` and ``_trackRouteGeometries``.
    ``render`` calls :meth:`_lowerGroundSplitKey` before planning the deck
    slots and :meth:`_lowerGroundPlan` after, and keeps the result in
    ``_lower_plan`` while drawing.
    """

    # The plan of the last render (set at its start); None before any render
    # and whenever --lower_ground is off.
    _lower_plan = None
    # The spur slot's --deck_slots key while lower ground is on (trapezoid),
    # so that slot is not taken as a riser's bed (see _slotBedKeys).
    _lower_split_key = None

    def _addLowerGroundArgs(self):
        """Register --lower_ground and --upper_edge_gap."""
        self.argparser.add_argument(
            "--lower_ground", action="store", type=float, default=0.0,
            help="Scenery: open the inner side of a trapezoid into upper and "
                 "lower ground.  The height (mm above the floor panel) of the "
                 "top of a new lower ground plate, e.g. 27.8.  It runs from the "
                 "edge-4 wall out to the inner edge of the spur's deck slot (the "
                 "--deck_slots entry from edge 3 to edge 5); the deck is cut back "
                 "to the slot's outer edge, and the strip under the spur stays "
                 "open to the box floor for its risers.  The edge-4 wall, the "
                 "side walls from edge 4 to the spur and any support under the "
                 "lower plate are lowered to carry it; across the spur the side "
                 "walls keep its --track_openings as a notch.  On the full "
                 "hexagon only the walls on edges 3 and 5 are stepped, to meet "
                 "the trapezoids beside it.  0 (default): off.")
        self.argparser.add_argument(
            "--upper_edge_gap", action="store", type=float, default=0.0,
            help="With --lower_ground on a trapezoid: put the deck's new inner "
                 "edge this many mm inside the main line's rail edge (half "
                 "--track_width from the deck-level route from edge 3 to edge 5) "
                 "instead of at the spur slot's outer edge, so there is less to "
                 "sand away.  It never comes inside the spur's slot.  0 "
                 "(default): at the slot's edge.")

    # ------------------------------------------------------------- planning

    def _lowerGroundSplitKey(self, isTrapezoid):
        """Find the spur slot that lower ground splits the trapezoid along.

        Sets ``_lower_split_key`` (the slot's --deck_slots key) so the slot is
        no longer a riser's bed: its strip leaves the deck with the rest of the
        inner side, and the riser gets a bed of its own.

        @throws ValueError - With --lower_ground on a trapezoid, unless exactly
                             one --deck_slots entry runs the whole way from
                             edge 3 to edge 5; or --upper_edge_gap without
                             --lower_ground, or on the full hexagon.
        """
        self._lower_split_key = None
        if self.lower_ground <= 0:
            if self.upper_edge_gap:
                raise ValueError("--upper_edge_gap only applies with --lower_ground.")
            return
        if not isTrapezoid:
            if self.upper_edge_gap:
                raise ValueError("--upper_edge_gap only applies to the trapezoid "
                                 "(--trapezoid 1); the full hexagon's deck is left whole.")
            return
        if self.upper_edge_gap < 0:
            raise ValueError(f"--upper_edge_gap must not be negative "
                             f"(got {self.upper_edge_gap:g}).")
        slots = [s for s in parse_deck_slots(self.deck_slots, self.under_track_width)
                 if {s.start, s.end} == {3, 5} and s.lo is None and s.hi is None]
        if len(slots) != 1:
            raise ValueError(
                "--lower_ground on the trapezoid needs the spur's deck slot: exactly "
                f"one --deck_slots entry running from edge 3 to edge 5 (found {len(slots)}).")
        s = slots[0]
        self._lower_split_key = (s.start, s.start_offset, s.end, s.end_offset,
                                 s.lo, s.hi, s.width)

    def _lowerGroundPlan(self, r, isTrapezoid, l, opening_plan):
        """Solve --lower_ground (see the module docstring).

        @param r            - Inner hexagon circumradius (the deck's).
        @param isTrapezoid  - True for the half-hexagon.
        @param l            - Wall body height (floor panel top to deck underside).
        @param opening_plan - From _trackOpeningPlan: edge → [(opening, notch)].
        @returns :class:`LowerGroundPlan`, or None when off.
        @throws ValueError - If the height leaves no wall under the plate or is
                             above a spur opening; an edge 3/5 wall has no spur
                             opening, or another opening the stepped wall has
                             no room for; the trapezoid's edge-4 wall (lowered
                             all along) has an opening; the slot and the
                             openings do not line up; there is no main line for
                             --upper_edge_gap, or the gap is too large; or a
                             support is neither under the lower plate nor under
                             the deck.
        """
        if self.lower_ground <= 0:
            return None
        t = self.thickness
        height = self.lower_ground
        body = height - t
        if body < t:
            raise ValueError(
                f"--lower_ground {height:g} leaves too little wall under the lower "
                f"plate; it needs to be at least {2 * t:g} mm (two thicknesses).")
        walls = {}
        for edge in (3, 5):
            entries = [o for o, _ in opening_plan.get(edge, [])]
            if not entries:
                raise ValueError(
                    f"--lower_ground needs the spur's --track_openings on edge {edge}: "
                    "the side walls step down to it.")
            # The spur's opening is the one nearest the edge-4 end.
            inward = -1.0 if edge == 3 else 1.0
            o = max(entries, key=lambda o: inward * o.position)
            if o.height < height:
                raise ValueError(
                    f"--lower_ground {height:g} is above the spur's opening on edge "
                    f"{edge} (at {o.height:g} mm); the lower ground must be at or "
                    "below the spur.")
            others = [x for x in entries if x is not o]
            if others:
                raise ValueError(
                    f"--lower_ground: the stepped wall on edge {edge} only has room for "
                    f"the spur's opening (at {o.position:+g} mm), not the one at "
                    f"{others[0].position:+g} mm.")
            pos_in = o.position + inward * o.width / 2
            pos_out = o.position - inward * o.width / 2
            walls[edge] = WallStep(edge, pos_in, pos_out, pos_out, o.height)
        if isTrapezoid and (opening_plan.get(4) or 4 in self._underTrackEdges(True)):
            raise ValueError(
                "--lower_ground lowers the trapezoid's edge-4 wall all along, so it "
                "can't take a --track_openings or --under_track_edges opening.")
        plan = LowerGroundPlan(height, body, isTrapezoid, walls)
        if isTrapezoid:
            self._planTrapezoidGround(plan, r)
        return plan

    def _planTrapezoidGround(self, plan, r):
        """The trapezoid's deck and plate edges, and which supports go low.

        Fills in ``plan.split``, ``deck_curve``, ``plate_curve`` and ``lower``,
        and moves each side wall's ``pos_deck`` to where the deck edge meets it.

        @param plan - The plan so far (heights and wall steps).
        @param r    - Inner hexagon circumradius (the deck's).
        @throws ValueError - If the slot and the wall openings do not line up,
                             from _gapDeckCurve, or from _lowerSupports.
        """
        apothem = r * _ROOT3 / 2
        start, so, end, eo, _, _, width = self._lower_split_key
        plan.split = (start, so, end, eo)
        slot = route_geometry(start, so, end, eo, apothem, self.track_lead_in).segments
        centre = centreline_points(slot)
        inner_mark = (0.0, -apothem)                  # edge 4's midpoint
        sides = []
        for d in (width / 2, -width / 2):
            pts = _towards_3_to_5(segments_polyline(offset_segments(slot, d), _ARC_STEPS),
                                  apothem)
            sides.append((d, pts))
        # The side nearer edge 4 is the plate's edge; the other the slot's outer edge.
        sides.sort(key=lambda side: min(math.dist(p, inner_mark) for p in side[1]))
        (plan.plate_side, plate), (_, outer) = sides
        plan.slot = slot
        # The slot's ends must line up with the wall openings' sides.
        for edge, end_point, step_pos, what in (
                (3, plate[0], plan.walls[3].pos_in, "inner"),
                (5, plate[-1], plan.walls[5].pos_in, "inner"),
                (3, outer[0], plan.walls[3].pos_out, "outer"),
                (5, outer[-1], plan.walls[5].pos_out, "outer")):
            pos = edge_position(edge, end_point, apothem)
            if abs(pos - step_pos) > _ALIGN_TOL:
                raise ValueError(
                    f"--lower_ground: the spur's deck slot reaches edge {edge} with its "
                    f"{what} side at {pos:+.1f} mm, but the wall opening's is at "
                    f"{step_pos:+.1f} mm; make the slot and --track_openings match.")
        deck = outer
        if self.upper_edge_gap > 0:
            deck = self._gapDeckCurve(r, plan, centre, outer)
        for edge, point in ((3, deck[0]), (5, deck[-1])):
            step = plan.walls[edge]
            pos = edge_position(edge, point, apothem)
            plan.walls[edge] = WallStep(edge, step.pos_in, step.pos_out, pos, step.band)
        plan.deck_curve, plan.plate_curve = deck, plate
        plan.lower = self._lowerSupports(r, plan, inner_mark)

    def _gapDeckCurve(self, r, plan, centre, outer):
        """The deck edge ``--upper_edge_gap`` inside the main line, kept out of the slot.

        The deck is the trapezoid less everything inside either the main
        line's offset curve or the slot's outer edge, so its edge follows the
        offset curve wherever that is clear of the slot, and the slot's edge
        wherever it would come inside it (see _upper_envelope).

        @param centre - The slot's centreline points.
        @param outer  - The slot's outer edge, edge 3 → edge 5.
        @returns The deck's inner edge, edge 3 → edge 5, ending on the slants'
                 inner faces.
        @throws ValueError - With no deck-level route from edge 3 to edge 5,
                             or a gap the curves cannot be offset by.
        """
        main = [g for g in self._trackRouteGeometries(r, True)
                if {g.start, g.end} == {3, 5}
                and (g.start, g.start_offset, g.end, g.end_offset) != plan.split]
        if not main:
            raise ValueError("--upper_edge_gap needs the main line: a deck-level "
                             "--track_routes entry from edge 3 to edge 5.")
        apothem = r * _ROOT3 / 2
        d = self.track_width / 2 + self.upper_edge_gap
        mid = centre[len(centre) // 2]
        # The main line nearest the slot, on its outer side; offset towards it.
        best = None
        for g in main:
            for sign in (1.0, -1.0):
                shifted = offset_segments(g.segments, sign * d)
                if shifted is None:
                    continue
                pts = _towards_3_to_5(segments_polyline(shifted, _ARC_STEPS), apothem)
                gap = min(math.dist(mid, p) for p in pts)
                if best is None or gap < best[0]:
                    best = (gap, pts)
        if best is None:
            raise ValueError("--upper_edge_gap is too large for the main line's curve.")
        edge = _upper_envelope(outer, best[1], apothem)
        if edge is None:
            raise ValueError(
                f"--upper_edge_gap {self.upper_edge_gap:g} is too large: the deck's "
                "edge would not reach both side walls.")
        return edge

    def _lowerSupports(self, r, plan, inner_mark):
        """Which supports sit under the lower plate (the rest stay under the deck).

        @param r          - Inner hexagon circumradius (the deck's).
        @param plan       - The plan, with its deck and plate curves.
        @param inner_mark - A point on the edge-4 side of both curves.
        @returns Indices into ``_supportLayout`` of the supports under the plate.
        @throws ValueError - If a support is not wholly on one side: under the
                             lower plate, or under the deck, clear of its edge.
        """
        if not self.supports:
            return frozenset()
        reach = self.thickness / 2 + _SUPPORT_EDGE_CLEAR
        plate_in = _side(plan.plate_curve, inner_mark)
        deck_in = _side(plan.deck_curve, inner_mark)
        lower = set()
        for i, support in enumerate(self._supportLayout(r, True)):
            pts = self._supportPoints(support)
            if all(_side(plan.plate_curve, p) == plate_in
                   and _distance(plan.plate_curve, p) >= reach for p in pts):
                lower.add(i)
            elif not all(_side(plan.deck_curve, p) != deck_in
                         and _distance(plan.deck_curve, p) >= reach for p in pts):
                raise ValueError(
                    f"--lower_ground: the support towards edge {support[2]} at "
                    f"{support[3]:g} mm from the centre is neither under the lower "
                    "plate nor under the deck; move it with --support_edges.")
        return frozenset(lower)

    def _lowerPlateKites(self, r):
        """Kite openings for the lower plate: the floor's, cut short at its edge.

        The floor's kites (see _kitePolygons) are clipped to the lower plate,
        keeping the same frame width (--edge_width) inside its curved edge as
        along its walls; pieces too thin to be worth cutting are left solid.

        @param r - Inner hexagon circumradius (the panels').
        @returns Kite polygons in the plate's centre-callback frame (one
                 thickness below the hexagon centre, as the floor's), or an
                 empty list when the floor has none.
        """
        plan = self._lower_plan
        kites = self._kitePolygons(r, True)
        if not kites:
            return []
        sign = 1.0 if plan.plate_side > 0 else -1.0
        run = 2 * r                    # well past both walls, to cut cleanly
        total = sum(seg.length for seg in plan.slot)
        path = trim_segments(plan.slot, -run, total + run)
        edge = offset_segments(tuple(path), plan.plate_side + sign * self.edge_width)
        if edge is None:
            return []
        lift = self.thickness
        inner = [(x, y + lift) for x, y in segments_polyline(edge, _ARC_STEPS)]
        # spine_kites keeps what is left of its band's left edge and right of
        # its right edge.  Make the plate's edge, run so that edge 4 is on its
        # left, the band's left edge, and a line far beyond the long wall the
        # right edge, so only the part on the plate is kept.
        apothem = r * _ROOT3 / 2
        if _side(inner, (0.0, -apothem + lift)) < 0:
            inner = inner[::-1]
        far = [(p[0], p[1] + 4 * r) for p in inner]
        return spine_kites(kites, [(inner, far)], self._KITE_MIN_PIECE)

    # ---------------------------------------------------------------- walls

    def _wallRuns(self, step, side, l, body, low_joint=True):
        """The stepped wall top as runs in drawing order.

        @param step      - The wall's :class:`WallStep`.
        @param side      - Wall top length.
        @param l         - Full wall body height (under the deck).
        @param body      - Lowered wall body height (under the lower plate).
        @param low_joint - Finger-joint the lowered run into a lower plate (the
                           trapezoid's); on the full hexagon there is none, so
                           it is plain, for a plate cut by hand to sit on.
        @returns ``[(length, height, joint)]``: ``joint`` True for a finger
                 joint (into the lower plate or the deck), False for plain.
        """
        s_in = side / 2 + step.pos_in
        s_out = side / 2 + step.pos_out
        s_deck = side / 2 + step.pos_deck
        if step.inner_first:
            runs = [(s_in, body, low_joint), (s_out - s_in, step.band, False),
                    (s_deck - s_out, l, False), (side - s_deck, l, True)]
        else:
            runs = [(s_deck, l, True), (s_out - s_deck, l, False),
                    (s_in - s_out, step.band, False), (side - s_in, body, low_joint)]
        merged = []
        for length, height, joint in runs:
            if length <= 1e-9:
                continue
            if merged and merged[-1][1] == height and not joint and not merged[-1][2]:
                merged[-1] = (merged[-1][0] + length, height, False)
            else:
                merged.append((length, height, joint))
        return merged

    def _steppedWallBorders(self, runs, side, t_, top, bottom):
        """polygonWall borders and edges for a wall with a stepped top.

        Same stepped-tab corners as the standard wall (see render's
        ``borders0``), but each end's height is its run's, and the top is
        the runs joined by plain vertical steps.

        @param runs   - From :meth:`_wallRuns`.
        @param side   - Wall length.
        @param t_     - The corner tab step (the angled joint's width).
        @param top    - The top joint's edge character (e.g. ``'z'``).
        @param bottom - The bottom edge character.
        @returns ``(borders, edges)``.
        """
        right, left = runs[0][1], runs[-1][1]
        borders = [side, 90, 0, -90, t_, 90, right, 90, t_, -90, 0, 90]
        edge_list = [bottom, "E", top, "E", bottom, "E"]
        for i, (length, height, joint) in enumerate(runs):
            borders.append(length)
            edge_list.append(top if joint else "e")
            if i + 1 < len(runs):
                rise = runs[i + 1][1] - height
                # Travelling along the top (leftwards in the wall's own
                # frame): up is a right turn, down a left turn.
                turn = -90 if rise > 0 else 90
                borders += [turn, abs(rise), -turn]
                edge_list.append("e")
        borders += [90, 0, -90, t_, 90, left, 90, t_, -90, 0, 90]
        edge_list += ["E", bottom, "E", top, "E"]
        return borders, edge_list

    def _wallKeepOut(self, step, side_orig, body):
        """A predicate for holes the lowered wall would cut through.

        In the wall-hole frame (x up from the floor panel, y along the wall),
        a hole must keep ``_UNDER_TRACK_CLEAR`` mm from the lowered top.  The
        rule depends only on the geometry, so the two walls meeting at a
        joint (mirror images) drop the same holes.

        @param step - The wall's :class:`WallStep`, or None for a wall lowered
                      all along (the trapezoid's edge 4).
        @returns ``drop(x0, x1, y0, y1)`` for a hole's bounding box.
        """
        clear = self._UNDER_TRACK_CLEAR
        if step is None:
            return lambda x0, x1, y0, y1: x1 > body - clear
        y_in = side_orig / 2 + step.pos_in
        if step.inner_first:
            return lambda x0, x1, y0, y1: x1 > body - clear and y0 < y_in + clear
        return lambda x0, x1, y0, y1: x1 > body - clear and y1 > y_in - clear

    @contextmanager
    def _holeKeepOut(self, drop):
        """Leave out round and rectangular holes for which ``drop`` is true.

        Shadows ``hole`` and ``rectangularHole`` on the instance for the
        duration (every wall hole is drawn through one of them), then
        restores the class methods.
        """
        hole, rect = self.hole, self.rectangularHole

        def kept_hole(x, y, r=0.0, d=0.0, tabs=0):
            rr = r or d / 2
            if not drop(x - rr, x + rr, y - rr, y + rr):
                hole(x, y, r, d, tabs)

        def kept_rect(x, y, dx, dy, r=0, center_x=True, center_y=True):
            x0 = x - dx / 2 if center_x else x
            y0 = y - dy / 2 if center_y else y
            if not drop(x0, x0 + dx, y0, y0 + dy):
                rect(x, y, dx, dy, r, center_x, center_y)

        self.hole, self.rectangularHole = kept_hole, kept_rect
        try:
            yield
        finally:
            del self.hole, self.rectangularHole

    def _lowerDeckSideEdges(self, char, side_orig, side, edges):
        """The full hexagon's deck edges with edges 3 and 5 plain over the step.

        Across the spur the deck edge was already plain (over its notch); now
        it is plain from the edge-4 end too, since the wall below is lowered
        there.  The deck is cut back by hand.

        @param char  - The deck's joint edge character.
        @param edges - The deck's edges so far: ``char`` or one per side.
        @returns One edge per deck side (``_DECK_SIDE_EDGES`` order).
        """
        base = self.edges[char]
        current = [base] * 6 if isinstance(edges, str) else list(edges)
        t = (side_orig - side) / 2
        out = []
        for edge, existing in zip(self._DECK_SIDE_EDGES, current):
            step = self._lower_plan.walls.get(edge)
            if step is None:
                out.append(existing)
                continue
            s_out = side / 2 + step.pos_out
            if step.inner_first:
                pieces = [("plain", t + s_out), ("joint", side - s_out), ("plain", t)]
            else:
                pieces = [("plain", t), ("joint", s_out), ("plain", side - s_out + t)]
            out.append(SplitJointEdge(self, base, [p for p in pieces if p[1] > 1e-9]))
        return out

    # --------------------------------------------------------------- panels

    def _trapezoidPathPoints(self, r, w):
        """Nominal turtle-path points of drawTrapezoidWall (V0 at the origin).

        @returns ``(S1, S3)``: the starts of the right slant (edge 3) and the
                 left slant (edge 5), each the slant's position ``-r/2``.
        """
        k = w * math.tan(math.radians(30))
        s1 = (r + 1.5 * k, k * _ROOT3 / 2)
        a, b = self._trapezoidMiter(w, w)
        e1 = (s1[0] + (r + a) * 0.5, s1[1] + (r + a) * _ROOT3 / 2)    # V2 corner
        p5 = (e1[0] - 2 * b - 2 * r, e1[1])                            # V5 corner
        s3 = (p5[0] + a * 0.5, p5[1] - a * _ROOT3 / 2)
        return s1, s3

    def _groundPanel(self, r, callback, move, outline):
        """A trapezoid-sized panel with a custom outline (see drawTrapezoidWall).

        Same bounding box, start point and callbacks 0 and 1 as
        drawTrapezoidWall with ``Z`` edges, so the frames the callbacks draw
        in (and the 3D export's) are the same; ``outline(edges, w)`` then
        draws the path from V0.
        """
        edges = [self.edges["Z"]] * 4
        w = edges[0].startWidth()
        H = r * _ROOT3 / 2.0 - 2 * self.thickness
        sp = max(e.spacing() for e in edges)
        tw = 2 * r + 2 * sp / math.sin(math.radians(60))
        th = H + 2 * self.thickness + edges[0].spacing()
        if self.move(tw, th, move, before=True):
            return
        self.moveTo(0.5 * tw - 0.5 * r, edges[0].margin())
        centre_y = H + 2 * self.thickness + (w - self.thickness)
        self.cc(callback, 0, r / 2., centre_y + self.burn)
        self.cc(callback, 1, 0, w + self.burn)
        outline(edges, w)
        self.move(tw, th, move)

    def _panelPoint(self, r, w, p):
        """Deck-frame point (hex centre, y up) → nominal panel coordinates (V0 at 0)."""
        return (r / 2 + p[0], r * _ROOT3 / 2 + w + p[1])

    def _slantPoint(self, r, w, edge, pos):
        """Nominal panel point on a slant's outer line at a wall position."""
        s1, s3 = self._trapezoidPathPoints(r, w)
        if edge == 3:
            return (s1[0] + (r / 2 + pos) * 0.5, s1[1] + (r / 2 + pos) * _ROOT3 / 2)
        return (s3[0] + (r / 2 + pos) * 0.5, s3[1] - (r / 2 + pos) * _ROOT3 / 2)

    def _turtleThrough(self, points, heading, final):
        """Draw straight edges through nominal points; end facing ``final``.

        Each step is a nominal length and turn, so with the burn arcs Boxes
        adds at every corner the path stays an exact offset of the outline.

        @param points  - Nominal points, the first being the current position.
        @param heading - Current heading (degrees).
        @param final   - Heading to turn to at the last point.
        @returns None; the turtle ends at the last point facing ``final``.
        """
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)
            if length < 1e-9:
                continue
            new = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            self.corner(_turn(heading, new))
            self.edge(length)
            heading = new
        self.corner(_turn(heading, final))

    def _drawUpperDeck(self, r, callback, move="right"):
        """The trimmed deck: long wall, both slants out to its new inner edge."""
        plan, t = self._lower_plan, self.thickness
        side = r - 2 * t

        def outline(edges, w):
            s3_, s5_ = (side / 2 + plan.walls[e].pos_deck for e in (3, 5))
            t1 = self._slantPoint(r, w, 3, plan.walls[3].pos_deck)
            t3 = self._slantPoint(r, w, 5, plan.walls[5].pos_deck)
            # Start on the right slant at the deck's edge (burn-offset outwards,
            # as the turtle path is: nominal V0 is one burn above the start).
            n1 = (_ROOT3 / 2, -0.5)
            self.moveTo(t1[0] + self.burn * n1[0], t1[1] + self.burn + self.burn * n1[1], 60)
            a, b = self._trapezoidMiter(w, w)
            _split(self, edges[1], [("joint", side - s3_), ("plain", t)])
            self.edge(a)
            self.corner(120)
            self.edge(b)
            edges[2](2 * r)
            self.edge(b)
            self.corner(120)
            self.edge(a)
            _split(self, edges[3], [("plain", t), ("joint", s5_)])
            curve = [self._panelPoint(r, w, p) for p in reversed(plan.deck_curve[1:-1])]
            self._turtleThrough([t3] + curve + [t1], 300, 60)

        self._groundPanel(r, callback, move, outline)

    def _drawLowerPlate(self, r, callback, move="right"):
        """The lower ground plate: edge 4, both slants in to the spur slot."""
        plan, t = self._lower_plan, self.thickness
        side = r - 2 * t

        def outline(edges, w):
            s3_, s5_ = (side / 2 + plan.walls[e].pos_in for e in (3, 5))
            q1 = self._slantPoint(r, w, 3, plan.walls[3].pos_in)
            q3 = self._slantPoint(r, w, 5, plan.walls[5].pos_in)
            edges[0](r)
            self.edgeCorner(edges[0], edges[1], 60)
            _split(self, edges[1], [("plain", t), ("joint", s3_)])
            curve = [self._panelPoint(r, w, p) for p in plan.plate_curve[1:-1]]
            self._turtleThrough([q1] + curve + [q3], 60, 300)
            _split(self, edges[3], [("joint", side - s5_), ("plain", t)])
            self.edgeCorner(edges[3], edges[0], 60)

        self._groundPanel(r, callback, move, outline)


def _split(box, base, pieces):
    """Draw a joint edge in pieces (zero-length ones left out).

    @param box    - The generator (drawing target).
    @param base   - The joint's edge object.
    @param pieces - ``(kind, length)`` pieces, as for :class:`SplitJointEdge`.
    """
    pieces = [p for p in pieces if p[1] > 1e-9]
    edge = SplitJointEdge(box, base, pieces)
    edge(edge.length)


def _turn(heading, new):
    """The turn from one heading to another.

    @param heading, new - Headings in degrees.
    @returns The turn in degrees, -180..180 (positive anticlockwise).
    """
    return (new - heading + 180.0) % 360.0 - 180.0


def _towards_3_to_5(points, apothem):
    """A polyline across the trapezoid, oriented from edge 3 to edge 5."""
    first = _edge_distance(3, points[0], apothem)
    last = _edge_distance(3, points[-1], apothem)
    return list(points) if first < last else list(reversed(points))


def _edge_distance(edge, p, apothem):
    """How far ``p`` is inside an edge's line (0 on the wall's inner face)."""
    th = math.radians(EDGE_ANGLES[edge])
    return apothem - (p[0] * math.cos(th) + p[1] * math.sin(th))


def _upper_envelope(a, b, apothem):
    """The edge of the region beyond both curves (towards the long wall).

    Both curves cross the trapezoid from edge 3 to edge 5 with x falling all
    the way (each lead-in and the arc between head away from edge 3), so each
    is a function y(x), and the region beyond both is ``y > max(ya, yb)``.

    @param a, b    - Polylines, edge 3 → edge 5, ending on (or near) the
                     slants' inner faces.
    @param apothem - The deck's apothem (the faces' distance from the centre).
    @returns The envelope, edge 3 → edge 5, cut at the slants' inner faces;
             or None if it does not reach both faces (a curve ending far from
             a wall, e.g. a huge --upper_edge_gap).
    """
    # Run both on along their end directions far enough to cross the faces
    # wherever they end, so the shared x range covers the whole trapezoid.
    a, b = _run_on(a, 2 * apothem), _run_on(b, 2 * apothem)
    hi = min(a[0][0], b[0][0])
    lo = max(a[-1][0], b[-1][0])
    xs = sorted({x for x, _ in a + b if lo <= x <= hi} | {lo, hi}, reverse=True)
    grid = []
    for x0, x1 in zip(xs, xs[1:]):
        grid.append(x0)
        # Where the curves cross between two grid points (both are straight
        # there), add the crossing so the envelope keeps its corner.
        d0, d1 = _y_at(a, x0) - _y_at(b, x0), _y_at(a, x1) - _y_at(b, x1)
        if d0 * d1 < 0:
            grid.append(x0 + (x1 - x0) * d0 / (d0 - d1))
    grid.append(xs[-1])
    env = [(x, max(_y_at(a, x), _y_at(b, x))) for x in grid]
    env = _between_slants(env, apothem)
    if env is None or any(abs(_edge_distance(e, p, apothem)) > 1e-6
                          for e, p in ((3, env[0]), (5, env[-1]))):
        return None
    return env


def _y_at(polyline, x):
    """y of a polyline whose x falls all the way, at x (linear between points).

    @param polyline - Points with x falling.
    @param x        - Within the polyline's x range.
    @returns The y there.
    @throws ValueError - If x is outside the range.
    """
    for (x0, y0), (x1, y1) in zip(polyline, polyline[1:]):
        if x1 <= x <= x0:
            return y0 if x0 == x1 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise ValueError("x outside the curve")


def _between_slants(points, apothem):
    """Cut a polyline crossing the trapezoid at the slants' inner faces.

    @param points  - Polyline from beyond edge 3's face to beyond edge 5's.
    @param apothem - The faces' distance from the centre.
    @returns The part between the faces, or None if it does not cross both.
    """
    def beyond(edge, p):
        return -_edge_distance(edge, p, apothem)

    def crossing(edge, p, q):
        f0, f1 = beyond(edge, p), beyond(edge, q)
        k = f0 / (f0 - f1)
        return (p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k)

    i = next((k for k in range(len(points) - 1) if beyond(3, points[k + 1]) <= 0), None)
    j = next((k for k in range(len(points) - 1, 0, -1) if beyond(5, points[k - 1]) <= 0), None)
    if i is None or j is None or j <= i:
        return None
    start = crossing(3, points[i], points[i + 1]) if beyond(3, points[i]) > 0 else points[i]
    end = crossing(5, points[j - 1], points[j]) if beyond(5, points[j]) > 0 else points[j]
    return [start] + points[i + 1:j] + [end]


def _run_on(points, d):
    """A polyline run straight on by ``d`` at both ends.

    @param points - The polyline (two or more points).
    @param d      - How far to extend each end along its last segment (mm).
    @returns The extended polyline.
    """
    def ext(a, b):
        length = math.dist(a, b)
        return (b[0] + (b[0] - a[0]) / length * d, b[1] + (b[1] - a[1]) / length * d)
    return [ext(points[1], points[0])] + list(points) + [ext(points[-2], points[-1])]


def _distance(polyline, p):
    """Shortest distance from ``p`` to a polyline.

    @param polyline - Points.
    @param p        - The point.
    @returns The distance (mm).
    """
    best = math.inf
    for a, b in zip(polyline, polyline[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        f = 0.0 if length2 < 1e-12 else max(0.0, min(1.0, (
            (p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
        best = min(best, math.dist(p, (a[0] + f * dx, a[1] + f * dy)))
    return best
