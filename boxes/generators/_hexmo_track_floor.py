"""A spoke floor that follows the tracks (``--bottom=spoke``).

The original spoke floor (now ``--bottom=kites``) is a rim round the edge plus
six straight spokes from the centre, with kite-shaped openings between them.
Those spokes are only where the floor happens to stay solid: nothing on the
floor stands on them in particular.

The floor carries only what stands on it; the deck's own tracks are on the
deck and leave no mark on it.  It keeps the rim (the walls' finger joints) and
strips under the risers and subways.  On the full hexagon it also keeps a
strip ``--spoke_width`` wide along every connection a track can make across
the module, from each edge to the edge two round from it (1–3, 3–5, 5–1 and
2–4, 4–6, 6–2), on the centre line as ``--track_routes`` would draw them:
these carry the support walls, so every module of a size has the same
spokes.  A strip is widened, if need be, to hold a support beside its spoke
with _supportLand of board round the slot.  The trapezoid keeps only a
straight spoke down its middle, from the long edge to edge 4.  Everything else
is cut away, with a round cutout in the middle of the hexagon unless
``--center_cutout`` is off.

The support walls stand on the strips.  On the full hexagon there are six,
one beside each spoke near its start, just outside its train corridor
(_supportCorridor: ``--under_track_width`` and _SUPPORT_SWING of it either
side, room for long cars swinging out on curves) and every other
spoke's, where a subway can run: each in its own corner, the six alike round
the hexagon, about ``--support_position`` from the centre.  The deck's own
tracks don't move them (a support may stand under one).  A riser, subway or
deck slot in the way moves one to the nearest free place beside its spoke,
within _SUPPORT_HOME_REACH, or leaves it out.  The trapezoid has one down its
middle, where its deck sags most.  A
support is never put under a deck slot (no deck above to carry), across a
riser or lower-level track, within a thickness and _SUPPORT_END_CLEAR of a wall
or another support, or (with ``--lower_ground``) half under the deck and half
under the lower plate.

All geometry is in the true-centre frame (the inner hexagon's centre, y up),
as the track routes are; the trapezoid's floor callback sits one thickness
below it.

The module name starts with an underscore, so generator discovery skips it.
This mixin is not a generator.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from boxes.generators._hexmo_risers import point_at
from boxes.generators._hexmo_track_routes import EDGE_ANGLES, route_geometry, segments_polyline

# Every connection a track can make across a module: each edge to the edge
# two round from it.  The trapezoid has edges 3, 4 and 5 only: 3–5.
_SPOKE_ROUTES = ((1, 3), (3, 5), (5, 1), (2, 4), (4, 6), (6, 2))


@dataclass(frozen=True)
class TrackSupport:
    """One support wall standing on the floor's strips (true-centre frame).

    @ivar centre - The middle of the support's slot.
    @ivar along  - Unit vector along the support.
    @ivar route  - Index of the spoke (_spokeRoutes) it stands beside, or −1
                   for the trapezoid's, in the middle of its open deck.
    """

    centre: tuple
    along: tuple
    route: int

    @property
    def angle(self):
        """The support's direction in degrees (for the drawing turtle)."""
        return math.degrees(math.atan2(self.along[1], self.along[0]))


class HexmoTrackFloorMixin:
    """The track-following spoke floor and its supports, for HexmoHexagon."""

    # Smallest opening worth cutting in the floor (mm across): narrower gaps
    # between strips stay solid.
    _FLOOR_MIN_OPENING = 15.0
    # Radius rounding the openings' corners (mm).
    _FLOOR_CORNER = 5.0
    # How far a support's position may move along its track from the middle,
    # in steps (mm), to find a place that takes it.
    _SUPPORT_SEARCH_STEP = 10.0
    # How far a hexagon's support may move from its home (the place it has
    # on a module with no tracks of its own), as a fraction of the apothem,
    # to get clear of the module's tracks; further than that it is left out.
    _SUPPORT_HOME_REACH = 1.0 / 3.0
    # Steps (mm) a hexagon's support is tried at, sideways from its spoke;
    # its strip is widened to leave at least one.
    _SUPPORT_SIDE_STEP = 2.5
    # Extra room either side of a lower track's opening width that a support
    # keeps clear, as a fraction of that width (see _supportCorridor).
    _SUPPORT_SWING = 1.0 / 6.0
    # Polyline steps per arc for the floor's strips.
    _FLOOR_ARC_STEPS = 32
    # The largest central cutout's radius, as a fraction of the apothem.
    _FLOOR_HUB = 1.0 / 3.0
    # Wood between the central cutout and the other openings (mm).
    _FLOOR_WEB = 10.0

    # ------------------------------------------------------------- choice

    def _trackFloor(self, isTrapezoid):
        """Whether this module's floor follows the tracks.

        @param isTrapezoid - True for the half-hexagon.
        @returns True for --bottom=spoke when there is floor inside the rim
                 (else the kite floor, which copes with that itself).
        """
        if self.bottom != "spoke":
            return False
        r, _ = self._innerSize()
        return not self._floorInterior(r, isTrapezoid).is_empty

    def _resetTrackFloor(self):
        """Forget the cached supports (each render works them out)."""
        self._track_supports = None

    # -------------------------------------------------------------- floor

    def _floorInterior(self, r, isTrapezoid):
        """The floor inside its rim (--edge_width), true-centre frame.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon (below its long edge).
        @returns A shapely Polygon (empty if the rim fills it).
        """
        apothem = r * math.sqrt(3.0) / 2.0 - self.edge_width
        if apothem <= 0:
            return Polygon()
        radius = apothem / math.cos(math.radians(30))
        hexagon = Polygon([(radius * math.cos(math.radians(60 * k)),
                            radius * math.sin(math.radians(60 * k))) for k in range(6)])
        if isTrapezoid:
            # The long edge's rim runs edge_width below the true centre.
            hexagon = hexagon.intersection(
                Polygon([(-2 * radius, -self.edge_width), (2 * radius, -self.edge_width),
                         (2 * radius, -2 * radius), (-2 * radius, -2 * radius)]))
        return hexagon

    def _spokeRoutes(self, r, isTrapezoid):
        """The floor's spokes: every connection a track can make, on the centre line.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon (3–5 only).
        @returns List of solved route geometries.
        """
        apothem = r * math.sqrt(3.0) / 2.0
        edges = self._TRAPEZOID_EDGES if isTrapezoid else set(range(1, 7))
        return [route_geometry(a, 0.0, b, 0.0, apothem, self.track_lead_in)
                for a, b in _SPOKE_ROUTES if {a, b} <= edges]

    def _floorStrips(self, r, isTrapezoid, riser_plan):
        """The solid strips: the spokes, the risers and subways, and the
        supports' pads.

        The deck's own tracks leave no strip: they are on the deck, and the
        floor carries only what stands on it.  On the full hexagon the six
        spokes carry the support walls; on the trapezoid only its straight
        middle spoke stays (it ties the floor's outer part to its inner and
        carries the support), the rest open but for the risers and subways.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon.
        @param riser_plan  - From _riserPlan (risers and subways).
        @returns ``(strips, standing)``: shapely geometries of all the solid
                 strips, and of the ones something stands on (risers,
                 subways, the supports' pads), which the central cutout keeps
                 clear of.
        """
        half = self._stripHalf(r, isTrapezoid)
        line = lambda segments: LineString(segments_polyline(segments, self._FLOOR_ARC_STEPS))
        shapes = ([] if isTrapezoid else
                  [line(g.segments).buffer(half) for g in self._spokeRoutes(r, False)])
        if isTrapezoid:
            # The trapezoid's straight spoke down its middle line, from the
            # long edge to edge 4, always: it ties the outer part of the floor
            # to the inner, and carries the support (see _placeTrackSupports).
            apothem = r * math.sqrt(3.0) / 2.0
            shapes.append(LineString([(0.0, 0.0), (0.0, -apothem)])
                          .buffer(self.spoke_width / 2.0, cap_style=2))
        standing = []
        for rp in riser_plan:
            glued = max(rp["heights"]) <= self.thickness + 1e-6
            # A raised bed's supports stand across it, their feet slotted
            # into the floor with _supportLand() of board round them; a bed
            # glued to the floor needs only its own width and _RISER_CLEAR.
            margin = self._RISER_CLEAR if glued else self._supportLand()
            strip = line(rp["segments"]).buffer(rp["width"] / 2.0 + margin)
            if glued:
                # A bed lying wholly on the floor (HO's subway at one
                # thickness) is glued down along its length: it keeps its
                # strip, but the central cutout may run on under it, the bed
                # spanning the hole glued down either side.
                shapes.append(strip)
            else:
                # A raised bed's supports stand on its strip, so the cutout
                # keeps clear of it.
                standing.append(strip)
        if self.supports:
            reach = self.support_length / 2.0
            for support in self._trackSupports(r, isTrapezoid):
                # Every support's slot stands in solid floor with
                # _supportLand() of board all round it (beside it and past its
                # ends): where its strip is too narrow for that (N's 60 mm
                # strip beside a 45 mm train corridor), the strip widens there
                # with straight sides along the support.
                (cx, cy), (ux, uy) = support.centre, support.along
                standing.append(LineString([(cx - ux * reach, cy - uy * reach),
                                            (cx + ux * reach, cy + uy * reach)])
                                .buffer(self.thickness / 2.0 + self._supportLand()))
        standing = unary_union(standing) if standing else None
        strips = unary_union(shapes + ([standing] if standing is not None else []))
        return strips, standing

    def _trackFloorOpenings(self, r, isTrapezoid, riser_plan):
        """The floor's openings: inside the rim, between the strips, and a
        round cutout in the middle.

        Each opening between the strips is rounded at its corners
        (_FLOOR_CORNER) and left solid when narrower than _FLOOR_MIN_OPENING;
        one that would leave a strip floating inside it (a ring) is left solid
        too.  On the full hexagon the middle is a plain circle, as big as it
        can be up to _FLOOR_HUB of the apothem while keeping _FLOOR_WEB of
        wood to the other openings and to anything standing on the floor;
        openings it takes in are left out.

        @returns Lists of ``(x, y)`` points, true-centre frame.
        """
        strips, standing = self._floorStrips(r, isTrapezoid, riser_plan)
        holes = self._floorInterior(r, isTrapezoid).difference(strips)
        pieces = []
        corner = self._FLOOR_CORNER
        for piece in getattr(holes, "geoms", [holes]):
            if piece.is_empty or piece.geom_type != "Polygon" or piece.interiors:
                continue
            if piece.buffer(-self._FLOOR_MIN_OPENING / 2.0).is_empty:
                continue
            rounded = piece.buffer(-corner).buffer(corner)
            pieces += [part for part in getattr(rounded, "geoms", [rounded])
                       if not part.is_empty and part.geom_type == "Polygon"
                       and not part.interiors]
        if not isTrapezoid and not self.center_cutout:
            # No cutout: the middle stays solid, gaps between strips there too.
            hub = Point(0.0, 0.0).buffer(r * math.sqrt(3.0) / 2.0 * self._FLOOR_HUB)
            pieces = [p for p in pieces if not hub.contains(p)]
        if not isTrapezoid and self.center_cutout:
            centre = Point(0.0, 0.0)
            radius = r * math.sqrt(3.0) / 2.0 * self._FLOOR_HUB
            # Openings wholly inside the circle make way for it; the rest,
            # and whatever stands on the floor, keep _FLOOR_WEB clear of it.
            pieces = [p for p in pieces if not centre.buffer(radius).contains(p)]
            for other in pieces + ([standing] if standing is not None else []):
                radius = min(radius, centre.distance(other) - self._FLOOR_WEB)
            if radius >= self._FLOOR_MIN_OPENING / 2.0:
                pieces.append(centre.buffer(radius, quad_segs=32))
        return [list(p.exterior.coords) for p in pieces]

    def drawTrackFloor(self, r, isTrapezoid, riser_plan):
        """Cut the track-following floor's openings (floor centre callback).

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon (callback t below centre).
        @param riser_plan  - From _riserPlan.
        """
        with self.saved_context():
            if isTrapezoid:
                self.moveTo(0, self.thickness)
            for points in self._trackFloorOpenings(r, isTrapezoid, riser_plan):
                self.ctx.move_to(*points[0])
                for x, y in points[1:]:
                    self.ctx.line_to(x, y)
                self.ctx.stroke()

    # ----------------------------------------------------------- supports

    def _supportCorridor(self, width=None):
        """Half the train corridor a support keeps out of (mm), either side of
        a lower track's centre line.

        The track's opening width (--under_track_width) plus _SUPPORT_SWING
        of it each side: room for long cars, whose middles cut inside a curve
        and whose ends swing outside it.  An 89 ft car on the hexagon's
        connection curves needs about 30 mm in HO (R 700) and 17 mm in N
        (R 335) from the track's centre; this gives 40 and 23.3, about 0.9 m
        full-size in either scale.

        @param width - The track's opening width (default --under_track_width).
        @returns The corridor's half width.
        """
        width = self.under_track_width if width is None else width
        return width * (0.5 + self._SUPPORT_SWING)

    def _supportBow(self, r):
        """How far a straight support beside a curved spoke bows away from
        the curve over its length (mm): the sagitta of a --support_length
        chord on the tightest spoke, taken on the curve's inside, where it is
        largest.

        @param r - Inner hexagon circumradius.
        @returns The bow (0 with only straight spokes).
        """
        corridor = self._supportCorridor()
        half = self.support_length / 2.0
        bows = [0.0]
        for g in self._spokeRoutes(r, False):
            if g.radius:
                inner = g.radius - corridor - self.thickness
                bows.append(inner - math.sqrt(max(0.0, inner * inner - half * half))
                            if inner > half else half)
        return max(bows)

    def _stripHalf(self, r, isTrapezoid):
        """Half the width of the strip under a spoke or deck route (mm).

        Half --spoke_width; on the full hexagon, with supports, at least
        enough for a support beside the track: the train corridor
        (_supportCorridor), the slot,
        its land (_supportLand) beyond it, and its bow (_supportBow).  So the
        strip stays straight-sided rather than bulging round each support
        (N's 60 mm strips come out 80 mm, HO's 120 mm 138 mm).

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon (its support stands
                             down its middle spoke, which --spoke_width holds).
        @returns The half width.
        """
        half = self.spoke_width / 2.0
        if isTrapezoid or not self.supports:
            return half
        corridor = self._supportCorridor()
        return max(half, corridor + self.thickness + self._supportLand()
                   + self._supportBow(r) + self._SUPPORT_SIDE_STEP)

    def _supportLand(self):
        """Board kept round a support's slot in the floor (mm): _FLOOR_WEB, or
        three thicknesses on thicker board, so the slot never leaves a sliver
        of board at an opening's edge.

        @returns The land width beside the slot and past its ends.
        """
        return max(self._FLOOR_WEB, 3.0 * self.thickness)

    def _trackSupports(self, r, isTrapezoid):
        """The support walls, one per deck track, worked out once per render.

        @returns List of :class:`TrackSupport` in drawing order.
        """
        if getattr(self, "_placing_supports", False):
            # Placing them asks for the deck slots and risers, whose checks
            # ask for the supports: there are none yet.
            return []
        if getattr(self, "_track_supports", None) is None:
            self._placing_supports = True
            try:
                self._track_supports = self._placeTrackSupports(r, isTrapezoid)
            finally:
                self._placing_supports = False
        return self._track_supports

    def _trackSupportPoints(self, support, n=20):
        """Points along a track support's slot, true-centre frame."""
        sl = self.support_length
        (cx, cy), (ax, ay) = support.centre, support.along
        return [(cx + ax * sl * (k / n - 0.5), cy + ay * sl * (k / n - 0.5))
                for k in range(n + 1)]

    def _placeTrackSupports(self, r, isTrapezoid, accept=None):
        """The support walls that keep the deck from sagging.

        On the full hexagon, one beside each spoke, parallel to it, on the
        half nearest its start (its corner) and on its strip, but outside
        every spoke's train corridor (where a subway can run; the deck's own
        tracks don't count).  Its home is the place nearest
        --support_position from the centre (default half the apothem, where
        the kite floor's supports stood), so every module of a size has the
        same six, alike round the hexagon.  The module's risers, subways and
        deck slots may move one to the free place nearest home beside its
        spoke, no further than _SUPPORT_HOME_REACH of the apothem; failing
        that it is left out.  On
        the trapezoid, one down its middle line, in the middle of the longest
        stretch of deck there (searched _SUPPORT_SEARCH_STEP at a time).  A
        place doesn't take one where it would reach within a thickness and
        _SUPPORT_END_CLEAR of a wall, stand under a deck slot or across a
        riser or lower-level track, come too close to a support already
        placed, or fail ``accept``.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon.
        @param accept      - Optional extra test of a support's slot points
                             (e.g. --lower_ground: wholly under the deck or
                             wholly under the lower plate).
        @returns List of :class:`TrackSupport`.
        """
        if not self.supports:
            return []
        t = self.thickness
        clear = self._SUPPORT_END_CLEAR
        apothem = r * math.sqrt(3.0) / 2.0
        _, l = self._innerSize()
        # The deck slots and risers, as render plans them.
        opening_plan = self._trackOpeningPlan(isTrapezoid, l)
        notches = {}
        for edge, entries in opening_plan.items():
            cut = [(o.position, o.width, l - o.height) for o, notch in entries if notch]
            if cut:
                notches[edge] = cut
        blocked, slot_bands = [], []
        for slot in self._deckSlotPlan(r, isTrapezoid, notches):
            path = LineString(segments_polyline(slot["segments"], 32))
            reach = slot["width"] / 2.0 + t / 2.0 + self._DECK_SLOT_CLEAR + 1.0
            blocked.append(path.buffer(reach))
            slot_bands.append(path.buffer(slot["width"] / 2.0))
        for rp in self._riserPlan(r, isTrapezoid, l, notches):
            # Clear of the bed and its supports' feet, and of the trains on
            # it swinging out on curves (_supportCorridor of its width).
            reach = max(rp["width"] / 2.0 + t + clear + 1.0,
                        self._supportCorridor(rp["width"]) + t / 2.0 + 0.5)
            blocked.append(LineString(segments_polyline(rp["segments"], 32)).buffer(reach))
        blocked = unary_union(blocked) if blocked else None
        edges = sorted(self._TRAPEZOID_EDGES) if isTrapezoid else range(1, 7)
        normals = [(math.cos(math.radians(EDGE_ANGLES[e])),
                    math.sin(math.radians(EDGE_ANGLES[e]))) for e in edges]

        def fits(points):
            for nx, ny in normals:
                if min(apothem - (x * nx + y * ny) for x, y in points) < t + clear:
                    return False
            return not (isTrapezoid and max(y for _, y in points) > -(t + clear))

        placed, placed_points = [], []

        def ok(points):
            if not fits(points):
                return False
            if blocked is not None and LineString(points).intersects(blocked):
                return False
            if accept is not None and not accept(points):
                return False
            return not any(min(math.dist(p, q) for p in points for q in other) < t + clear
                           for other in placed_points)

        if isTrapezoid:
            # The trapezoid's deck sags most in the middle of its longest
            # unsupported stretch (its tracks hug the long wall, and a deck
            # slot leaves the deck inside it hanging).  Down the trapezoid's
            # middle, from the long wall to edge 4, split by any deck slot:
            # one support in the middle of the longest stretch, pointing at
            # edge 4, its floor pad running on out to the rim.
            axis_line = LineString([(0.0, -t), (0.0, -apothem)])
            for band in slot_bands:
                axis_line = axis_line.difference(band)
            stretches = sorted(getattr(axis_line, "geoms", [axis_line]),
                               key=lambda g: g.length, reverse=True)
            if stretches and not stretches[0].is_empty:
                mid = stretches[0].interpolate(0.5, normalized=True)
                axis = (0.0, -1.0)
                step = self._SUPPORT_SEARCH_STEP
                for o in [0.0] + [sign * step * k for k in range(1, 8) for sign in (1, -1)]:
                    support = TrackSupport((0.0, mid.y - o), axis, -1)
                    if ok(self._trackSupportPoints(support)):
                        placed.append(support)
                        placed_points.append(self._trackSupportPoints(support))
                        break
            return placed
        # The full hexagon: one beside each spoke (every connection a track
        # can make), clear of every track path, so all six stand the same
        # way round the hexagon whatever tracks the module carries.
        target = self.support_position or apothem / 2.0
        spokes = self._spokeRoutes(r, False)
        line = lambda g: LineString(segments_polyline(g.segments, self._FLOOR_ARC_STEPS))
        # A lower track's path: the train corridor (_supportCorridor) along
        # every spoke, where a subway
        # can run, widened by half the slot so the support's board stays out
        # of it.  The deck's own tracks don't count: a support may stand
        # under one (nothing hangs under the deck there).
        corridor = self._supportCorridor()
        paths = unary_union([line(g).buffer(corridor + t / 2.0) for g in spokes])
        # The floor the slot must stand on: the strips under the spokes and
        # deck routes (a support beside its track stays on its strip; its
        # land, _supportLand, may widen the strip there).
        strip = self._stripHalf(r, False)
        floor = unary_union([line(g).buffer(strip - t / 2.0 - self._supportLand())
                             for g in spokes])
        # Offsets beside the track's centre line, nearest the track first,
        # out to its strip's edge, on either side.
        # (Starting just clear of the corridor, not touching it.)
        near = corridor + t / 2.0 + 0.5
        far = strip - t / 2.0 - self._supportLand()
        side = self._SUPPORT_SIDE_STEP
        offsets = [near + side * k for k in range(int(max(0.0, far - near) // side) + 1)]
        offsets = [o * sign for o in offsets for sign in (1, -1)]
        step = self._SUPPORT_SEARCH_STEP
        for index, g in enumerate(spokes):
            # Places beside the half of the spoke nearest its start: that is
            # its corner (each spoke's start a turn round from the last's),
            # so no two supports share one.
            length = sum(seg.length for seg in g.segments)
            candidates = []
            for k in range(int(length / 2.0 // step) + 1):
                point, (dx, dy) = point_at(g.segments, step * k)
                for o in offsets:
                    candidates.append(TrackSupport((point[0] - dy * o, point[1] + dx * o),
                                                   (dx, dy), index))
            # Its home: the place nearest --support_position from the centre
            # clear of the spokes alone, the same on every module of a size.
            home = min((c for c in candidates
                        if fits(self._trackSupportPoints(c))
                        and not LineString(self._trackSupportPoints(c)).intersects(paths)),
                       key=lambda c: abs(math.hypot(*c.centre) - target), default=None)
            if home is None:
                continue
            # This module's risers, subways and deck slots may be in the way:
            # the free place nearest home beside the spoke, no further than
            # _SUPPORT_HOME_REACH of the apothem from home.
            reach_home = apothem * self._SUPPORT_HOME_REACH
            candidates = [c for c in candidates if math.dist(c.centre, home.centre) <= reach_home]
            candidates.sort(key=lambda c: math.dist(c.centre, home.centre))
            for support in candidates:
                points = self._trackSupportPoints(support)
                slot = LineString(points)
                if slot.intersects(paths) or not floor.contains(slot) or not ok(points):
                    continue
                placed.append(support)
                placed_points.append(points)
                break
        return placed
