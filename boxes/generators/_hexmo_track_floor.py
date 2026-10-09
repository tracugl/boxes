"""A spoke floor that follows the tracks (``--bottom=spoke``).

The original spoke floor (now ``--bottom=kites``) is a rim round the edge plus
six straight spokes from the centre, with kite-shaped openings between them.
Those spokes are only where the floor happens to stay solid: nothing on the
floor stands on them in particular.

What the floor actually carries is the rim (the walls' finger joints), the
support walls, and anything under the tracks: riser supports, a subway's
supports, a bed lying on the floor.  So this floor keeps the rim plus a strip
``--spoke_width`` wide under every track (every deck route, every riser and
subway path), and cuts everything else away.  The support walls then stand on
the strips, turned across the track under each deck route and spaced evenly
along it (``--support_spacing``), so each one sits wholly on solid floor and
props the deck right under the trains.  Where one won't fit across its track
it slides along itself, or stands along the track under the rails; and deck
with no track over it gets a fill-in support on a half-spoke, as the kite floor
had, on its own pad of floor.

A support is left out where it would stand under a deck slot (no deck above
to carry), across a riser or a lower-level track, too near a wall or another
support, or (with ``--lower_ground``) half under the deck and half under the
lower plate.  A module with no track routes keeps the kite floor.

All geometry is in the true-centre frame (the inner hexagon's centre, y up),
as the track routes are; the trapezoid's floor callback sits one thickness
below it.

The module name starts with an underscore, so generator discovery skips it.
This mixin is not a generator.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from boxes.generators._hexmo_risers import point_at
from boxes.generators._hexmo_track_routes import EDGE_ANGLES, segments_polyline


@dataclass(frozen=True)
class TrackSupport:
    """One support wall standing across a deck route (true-centre frame).

    @ivar centre - The middle of the support's slot.
    @ivar along  - Unit vector along the support (across the track).
    @ivar route  - Index of the deck route it stands under, or −1 for a
                   fill-in support on a half-spoke (deck with no track over it).
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
    # A support's first and last positions this far in from each end of its
    # route (mm), clear of the walls the route starts and ends at.
    _SUPPORT_ROUTE_INSET = 40.0
    # Polyline steps per arc for the floor's strips.
    _FLOOR_ARC_STEPS = 32

    def _addTrackFloorArgs(self):
        """Register --support_spacing."""
        self.argparser.add_argument(
            "--support_spacing", action="store", type=float, default=150.0,
            help="Track-following spoke floor (--bottom=spoke with track routes): "
                 "the largest gap (mm) between support walls along each deck "
                 "track.  Each support stands across its track, on the floor's "
                 "strip under it.")

    # ------------------------------------------------------------- choice

    def _trackFloor(self, isTrapezoid):
        """Whether this module's floor follows its tracks.

        @param isTrapezoid - True for the half-hexagon.
        @returns True for --bottom=spoke with at least one track route.
        """
        if self.bottom != "spoke":
            return False
        if getattr(self, "_track_floor_routes", None) is None:
            r, _ = self._innerSize()
            self._track_floor_routes = bool(self._trackRouteGeometries(r, isTrapezoid))
        return self._track_floor_routes

    def _resetTrackFloor(self):
        """Forget the cached routes and supports (each render works them out)."""
        self._track_floor_routes = None
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

    def _floorStrips(self, r, isTrapezoid, riser_plan):
        """The solid strips: one under every track, plus the supports.

        @param r           - Inner hexagon circumradius.
        @param isTrapezoid - True for the half-hexagon.
        @param riser_plan  - From _riserPlan (risers and subways).
        @returns A shapely geometry.
        """
        half = self.spoke_width / 2.0
        shapes = []
        for g in self._trackRouteGeometries(r, isTrapezoid):
            shapes.append(LineString(segments_polyline(g.segments, self._FLOOR_ARC_STEPS))
                          .buffer(half))
        for rp in riser_plan:
            width = max(self.spoke_width, rp["width"] + 2 * self._RISER_CLEAR)
            shapes.append(LineString(segments_polyline(rp["segments"], self._FLOOR_ARC_STEPS))
                          .buffer(width / 2.0))
        if self.supports:
            # Each support stands on a pad as wide as a strip: one slid off
            # its track, or a fill-in on a half-spoke, still has solid floor
            # all round its slot.
            apothem = r * math.sqrt(3.0) / 2.0
            run_on = self.thickness + self._SUPPORT_END_CLEAR
            for support in self._trackSupports(r, isTrapezoid):
                # The slot, run on a little past each end for wood beyond it.
                (cx, cy), (ux, uy) = support.centre, support.along
                reach = self.support_length / 2.0 + run_on
                ends = [(cx - ux * reach, cy - uy * reach), (cx + ux * reach, cy + uy * reach)]
                if support.route < 0:
                    # A fill-in on a half-spoke: its pad runs on out to the rim,
                    # a short spoke, so it isn't left floating in an opening.
                    far = apothem - math.hypot(cx, cy)
                    ends = [ends[0], (cx + ux * far, cy + uy * far)]
                shapes.append(LineString(ends).buffer(half, cap_style=2))
        return unary_union(shapes)

    def _trackFloorOpenings(self, r, isTrapezoid, riser_plan):
        """The floor's openings: inside the rim, between the strips.

        Each is rounded at its corners (_FLOOR_CORNER) and left solid when
        narrower than _FLOOR_MIN_OPENING.  An opening that would leave a strip
        floating inside it (a ring) is left solid too.

        @returns Lists of ``(x, y)`` points, true-centre frame.
        """
        holes = self._floorInterior(r, isTrapezoid).difference(
            self._floorStrips(r, isTrapezoid, riser_plan))
        pieces = getattr(holes, "geoms", [holes])
        out = []
        corner = self._FLOOR_CORNER
        for piece in pieces:
            if piece.is_empty or piece.geom_type != "Polygon" or piece.interiors:
                continue
            if piece.buffer(-self._FLOOR_MIN_OPENING / 2.0).is_empty:
                continue
            rounded = piece.buffer(-corner).buffer(corner)
            for part in getattr(rounded, "geoms", [rounded]):
                if not part.is_empty and part.geom_type == "Polygon" and not part.interiors:
                    out.append(list(part.exterior.coords))
        return out

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
        """The support walls across the deck tracks, worked out once per render.

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
        """Stand supports across each deck route, evenly spaced along it.

        Positions run from _SUPPORT_ROUTE_INSET in from each end of the route,
        at most --support_spacing apart.  At each, the support is centred on
        the track; where that doesn't fit it slides along its own length,
        either way, as far as still keeps both rails over it.  A position is
        left out where no slide fits: the support would reach within a
        thickness and _SUPPORT_END_CLEAR of a wall, stand under a deck slot or
        across a riser or lower-level track, come too close to a support
        already placed, or fail ``accept``.

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
        blocked = []
        for slot in self._deckSlotPlan(r, isTrapezoid, notches):
            reach = slot["width"] / 2.0 + t / 2.0 + self._DECK_SLOT_CLEAR + 1.0
            blocked.append(LineString(segments_polyline(slot["segments"], 32)).buffer(reach))
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
        steps = int(reach_off // 2.5)
        offsets = [0.0] + [sign * 2.5 * k for k in range(1, steps + 1) for sign in (1, -1)]

        def ok(points):
            if not fits(points):
                return False
            if blocked is not None and LineString(points).intersects(blocked):
                return False
            if accept is not None and not accept(points):
                return False
            return not any(min(math.dist(p, q) for p in points for q in other) < t + clear
                           for other in placed_points)

        placed, placed_points = [], []

        def place(candidates):
            """Keep the first candidate that fits; True if one did."""
            for support in candidates:
                points = self._trackSupportPoints(support)
                if ok(points):
                    placed.append(support)
                    placed_points.append(points)
                    return True
            return False

        for index, g in enumerate(self._trackRouteGeometries(r, isTrapezoid)):
            length = sum(seg.length for seg in g.segments)
            inset = min(self._SUPPORT_ROUTE_INSET, length / 2.0)
            run = length - 2 * inset
            n = max(1, math.ceil(run / self.support_spacing) + 1) if run > 0 else 1
            stations = ([inset + run * k / (n - 1) for k in range(n)] if n > 1
                        else [length / 2.0])
            for s in stations:
                point, (dx, dy) = point_at(g.segments, s)
                across = (-dy, dx)
                # Across the track, centred or slid along itself; failing
                # that, along the track right under the rails (where the deck
                # strip is too narrow to stand one across it).
                place([TrackSupport((point[0] + across[0] * o, point[1] + across[1] * o),
                                    across, index) for o in offsets]
                      + [TrackSupport(point, (dx, dy), index)])
        # Deck with no track over it still needs propping: try a support at
        # each half-spoke, halfway out (where the kite floor had them),
        # wherever none of the track supports is already within
        # --support_spacing of it.
        slide = [0.0] + [sign * 5.0 * k for k in range(1, int(apothem / 4 // 5) + 1)
                         for sign in (1, -1)]
        for edge in edges:
            th = math.radians(EDGE_ANGLES[edge])
            u = (math.cos(th), math.sin(th))
            d = apothem / 2.0
            if any(math.dist(sp.centre, (u[0] * d, u[1] * d)) < self.support_spacing
                   for sp in placed):
                continue
            place([TrackSupport((u[0] * (d + o), u[1] * (d + o)), u, -1) for o in slide])
        return placed
