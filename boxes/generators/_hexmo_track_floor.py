"""A spoke floor that follows the tracks (``--bottom=spoke``).

The original spoke floor (now ``--bottom=kites``) is a rim round the edge plus
six straight spokes from the centre, with kite-shaped openings between them.
Those spokes are only where the floor happens to stay solid: nothing on the
floor stands on them in particular.

This floor keeps the rim (the walls' finger joints) and a strip
``--spoke_width`` wide along every connection a track can make across the
module: from each edge to the edge two round from it, so 1–3, 3–5, 5–1 and
2–4, 4–6, 6–2 on the full hexagon (3–5 on the trapezoid), on the centre line
as ``--track_routes`` would draw them.  Every module of a size then has the
same spokes, whatever track it carries.  The module's own tracks (deck routes
at their offsets), risers and subways get a strip too.  Everything else is cut
away.

The support walls stand on the strips: one across each deck track, at its
middle, so it props the deck right under the trains.  Where the middle won't
take one it moves along the track to the nearest place that will; there it
stands across the track, slid along itself if need be (as far as still keeps
both rails over it), or failing that along the track under the rails.  A
module with no deck tracks gets one across the middle of each spoke instead.
A support is never put under a deck slot (no deck above to carry), across a
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
    """One support wall standing on a track's strip (true-centre frame).

    @ivar centre - The middle of the support's slot.
    @ivar along  - Unit vector along the support.
    @ivar route  - Index of the deck route (or spoke) it stands under, or −1
                   for the trapezoid's, in the middle of its open deck.
    @ivar lying  - True when it lies along its strip, which then holds the
                   whole slot; False for one standing across a track, which
                   needs a boss of floor round it.
    """

    centre: tuple
    along: tuple
    route: int
    lying: bool = True

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
        """The solid strips: the spokes, every track, and the supports' pads.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon.
        @param riser_plan  - From _riserPlan (risers and subways).
        @returns ``(strips, standing)``: shapely geometries of all the solid
                 strips, and of the ones something stands on (risers,
                 subways, the supports' pads), which the central cutout keeps
                 clear of.
        """
        half = self.spoke_width / 2.0
        line = lambda segments: LineString(segments_polyline(segments, self._FLOOR_ARC_STEPS))
        shapes = [line(g.segments).buffer(half)
                  for g in self._spokeRoutes(r, isTrapezoid)
                  + self._trackRouteGeometries(r, isTrapezoid)]
        if isTrapezoid:
            # The trapezoid's straight spoke down its middle line, from the
            # long edge to edge 4, always: it ties the outer part of the floor
            # to the inner, and carries the support (see _placeTrackSupports).
            apothem = r * math.sqrt(3.0) / 2.0
            shapes.append(LineString([(0.0, 0.0), (0.0, -apothem)]).buffer(half, cap_style=2))
        standing = []
        for rp in riser_plan:
            width = max(self.spoke_width, rp["width"] + 2 * self._RISER_CLEAR)
            standing.append(line(rp["segments"]).buffer(width / 2.0))
        if self.supports:
            # Each support stands on a round boss: a circle about its middle
            # holding the whole slot with a thickness and _SUPPORT_END_CLEAR
            # of wood past each end, so a support longer than its strip is
            # wide (or slid along it) bulges the strip smoothly rather than
            # notching the openings.
            reach = self.support_length / 2.0 + self.thickness + self._SUPPORT_END_CLEAR
            for support in self._trackSupports(r, isTrapezoid):
                # One lying along its strip (the trapezoid's on its middle
                # spoke, a hexagon's along its track) is held by the strip;
                # one standing across a track gets a round boss.
                if not support.lying:
                    standing.append(Point(*support.centre).buffer(reach, quad_segs=32))
                # Its slot, with a thickness and clearance of wood past each
                # end, is always solid floor (the central cutout keeps clear).
                (cx, cy), (ux, uy) = support.centre, support.along
                standing.append(LineString([(cx - ux * reach, cy - uy * reach),
                                            (cx + ux * reach, cy + uy * reach)])
                                .buffer(self.thickness / 2.0 + self._SUPPORT_END_CLEAR))
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
        if not isTrapezoid:
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

        On the full hexagon, one per deck track (or per spoke if it has
        none), lying along it down the middle of its strip, where the track
        is --support_position from the centre (default half the apothem,
        where the kite floor's supports stood), so they don't crowd the
        middle.  On the trapezoid, one on its spoke (the 3–5
        connection on the centre line), at the place nearest the middle of
        its floor: the deck's open middle, away from every wall (its tracks
        hug the long wall).  Failing the best place, the next best along it,
        trying places _SUPPORT_SEARCH_STEP apart in order of nearness (then
        of nearness to the track's middle).  At each place a hexagon's lies
        along the track, nudged sideways within its strip if need be, or else
        stands
        across the track, centred or slid along itself as far as still keeps
        both rails over it, or failing that along the track under the rails.
        A place doesn't take it where it would reach within a thickness and
        _SUPPORT_END_CLEAR of a wall, stand under a deck slot or across a
        riser or lower-level track, come too close to a support already
        placed, or fail ``accept``.  A track with no such place gets none.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon.
        @param accept      - Optional extra test of a support's slot points
                             (e.g. --lower_ground: wholly under the deck or
                             wholly under the lower plate).
        @returns List of :class:`TrackSupport`.
        """
        if not self.supports:
            return []
        t, sl = self.thickness, self.support_length
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
            reach = rp["width"] / 2.0 + t + clear + 1.0
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

        # How far a support may slide along itself and still carry both rails.
        reach_off = max(0.0, sl / 2.0 - self.track_width / 2.0 - clear)
        slides = [0.0] + [sign * 2.5 * k for k in range(1, int(reach_off // 2.5) + 1)
                          for sign in (1, -1)]
        # How far one lying along its track may move sideways and stay within
        # the strip, with its slot's half a thickness and clearance inside.
        nudge_off = max(0.0, self.spoke_width / 2.0 - t / 2.0 - clear)
        nudges = [0.0] + [sign * 2.5 * k for k in range(1, int(nudge_off // 2.5) + 1)
                          for sign in (1, -1)]

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
        else:
            # The full hexagon: one per deck track (or per spoke if it has
            # none), where the track is --support_position from the centre.
            target = self.support_position or apothem / 2.0
            tracks = self._trackRouteGeometries(r, False) or self._spokeRoutes(r, False)
            nearness = lambda p: abs(math.hypot(*p) - target)
        for index, g in enumerate(tracks):
            length = sum(seg.length for seg in g.segments)
            step = self._SUPPORT_SEARCH_STEP
            places = [step * k for k in range(int(length // step) + 1)]
            places.sort(key=lambda s: (nearness(point_at(g.segments, s)[0]),
                                       abs(s - length / 2.0)))
            for s in places:
                point, (dx, dy) = point_at(g.segments, s)
                across = (-dy, dx)
                # Along the track, down the middle of its strip, nudged
                # sideways within it if need be; failing that, across the
                # track, centred or slid along itself.
                candidates = ([TrackSupport((point[0] + across[0] * o, point[1] + across[1] * o),
                                            (dx, dy), index) for o in nudges]
                              + [TrackSupport((point[0] + across[0] * o, point[1] + across[1] * o),
                                              across, index, lying=False) for o in slides])
                chosen = next((c for c in candidates if ok(self._trackSupportPoints(c))), None)
                if chosen is not None:
                    placed.append(chosen)
                    placed_points.append(self._trackSupportPoints(chosen))
                    break
        return placed
