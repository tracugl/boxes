"""Track routes across a Hexmo hexagon: parsing and geometry.

A *route* carries one track across a HexmoHexagon deck, from the midpoint
region of one edge to another, crossing each edge square to it.  The old
fixed options (``--track_left`` …, and the trapezoid's single curve) are all
routes, and ``--track_routes`` lists any others, each with its own offset at
each end.  HexmoHexagon etches the routes, cuts track templates for them and
builds track-guide plates from where they cross the walls.  This module holds
only the maths, so it can be tested without drawing anything.

**Frame.**  Origin at the hexagon centre, y up, the frame ``drawTrackLines``
draws in.  Edges are numbered as on a flat-top hexagon, by the direction of
their outward normal: 1 top (90°), 2 upper-right (30°), 3 lower-right (330°),
4 bottom (270°), 5 lower-left (210°), 6 upper-left (150°).  Edge midpoints sit
one apothem ``A`` from the centre.

**Shapes.**  Two edges two apart (120° between normals) are joined by a curve:
a straight lead-in, one 60° arc and a straight lead-out.  Two opposite edges
are joined by a straight, or by a reverse ("S") curve between two lead-ins if
the offsets differ.  Adjacent edges would need a far tighter curve than any
track can take, so they are refused.

**Offsets.**  On a curve a positive offset is away from the curve's centre
(its outside), as it is for the ``--track_line_count`` families.  On a straight
it is to the right of travel from the first edge to the second.  Equal offsets
on a curve give the concentric curve ``(A − L)·√3 + offset``.

**Largest arc.**  Each lead-in runs along its edge's inward normal, and the two
normal lines meet at a point V.  A 60° arc tangent to both lines has tangent
length ``r·tan 30°`` from V, so the biggest arc that still leaves a straight of
at least ``L`` (``--track_lead_in``) at each end is

    r = (min(|V − S|, |V − E|) − L) / tan 30°,

where S and E are the crossing points.  The shorter end gets exactly ``L``,
and the other end takes up the difference as a longer straight.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Outward-normal direction (degrees) of each edge of the flat-top hexagon.
EDGE_ANGLES = {1: 90.0, 2: 30.0, 3: 330.0, 4: 270.0, 5: 210.0, 6: 150.0}

_TAN30 = math.tan(math.radians(30.0))
_EPS = 1e-9

# One route: "<edge>[:<offset>]-<edge>[:<offset>]".  Offsets are signed decimals.
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_ROUTE_RE = re.compile(
    rf"^\s*([1-6])\s*(?::\s*({_NUMBER}))?\s*-\s*([1-6])\s*(?::\s*({_NUMBER}))?\s*$")


# --------------------------------------------------------------------- parsing

@dataclass(frozen=True)
class RouteSpec:
    """One parsed ``--track_routes`` entry.

    ``None`` offsets mean "use the ``--track_line_count`` family": the route
    is drawn once per family offset, the same at both ends.
    """

    start: int
    end: int
    start_offset: float | None
    end_offset: float | None


def parse_track_routes(text):
    """Parse the ``--track_routes`` option.

    Entries are comma-separated, each ``A[:offset]-B[:offset]``, e.g.
    ``"1:-17.5-5:17.5"``.  An offset given at only one end applies to both.

    @param text - The option value; empty or blank means no routes.
    @returns List of :class:`RouteSpec`, in the order given.
    @throws ValueError - On any malformed entry or a route from an edge to itself.
    """
    if not text or not text.strip():
        return []
    specs = []
    for item in text.split(","):
        match = _ROUTE_RE.match(item)
        if not match:
            raise ValueError(
                f"--track_routes entry {item.strip()!r} is not "
                "'<edge>[:<offset>]-<edge>[:<offset>]' with edges 1–6, "
                "e.g. '1:-17.5-5:17.5'.")
        a, oa, b, ob = match.groups()
        start, end = int(a), int(b)
        if start == end:
            raise ValueError(
                f"--track_routes entry {item.strip()!r} starts and ends on edge {start}.")
        oa = float(oa) if oa is not None else None
        ob = float(ob) if ob is not None else None
        # One offset given: it applies to both ends.
        if oa is None:
            oa = ob
        if ob is None:
            ob = oa
        specs.append(RouteSpec(start, end, oa, ob))
    return specs


def expand_routes(specs, family_offsets):
    """Resolve family routes into one concrete route per track.

    @param specs          - Parsed routes (see :func:`parse_track_routes`).
    @param family_offsets - The ``--track_line_count`` family offsets, used
                            for routes given without offsets.
    @returns List of ``(start, start_offset, end, end_offset)`` tuples.
    """
    routes = []
    for spec in specs:
        if spec.start_offset is None:
            routes += [(spec.start, off, spec.end, off) for off in family_offsets]
        else:
            routes.append((spec.start, spec.start_offset, spec.end, spec.end_offset))
    return routes


# -------------------------------------------------------------------- segments

def _right(v):
    """Unit vector to the right of direction ``v`` (y-up frame)."""
    return (v[1], -v[0])


def _left(v):
    """Unit vector to the left of direction ``v`` (y-up frame)."""
    return (-v[1], v[0])


@dataclass(frozen=True)
class Line:
    """A straight piece of a route, from ``p0`` to ``p1``."""

    p0: tuple
    p1: tuple

    @property
    def length(self):
        return math.dist(self.p0, self.p1)

    @property
    def direction(self):
        """Unit direction of travel; ``(0, 0)`` for a zero-length piece."""
        length = self.length
        if length < _EPS:
            return (0.0, 0.0)
        return ((self.p1[0] - self.p0[0]) / length, (self.p1[1] - self.p0[1]) / length)

    def offset(self, d, direction=None):
        """The parallel line ``d`` mm to the right of travel.

        @param d         - Lateral distance (negative = left).
        @param direction - Travel direction to use when this piece has zero
                           length (a zero lead-in has no direction of its own).
        @returns The shifted :class:`Line`.
        """
        nx, ny = _right(direction or self.direction)
        return Line((self.p0[0] + d * nx, self.p0[1] + d * ny),
                    (self.p1[0] + d * nx, self.p1[1] + d * ny))

    def points(self, steps):
        return [self.p0, self.p1]


@dataclass(frozen=True)
class Arc:
    """A circular piece: ``sweep`` radians from ``start_angle`` about ``centre``.

    Positive sweep turns left (anticlockwise in the y-up frame).
    """

    centre: tuple
    radius: float
    start_angle: float
    sweep: float

    def point(self, angle):
        return (self.centre[0] + self.radius * math.cos(angle),
                self.centre[1] + self.radius * math.sin(angle))

    @property
    def p0(self):
        return self.point(self.start_angle)

    @property
    def p1(self):
        return self.point(self.start_angle + self.sweep)

    @property
    def length(self):
        return abs(self.sweep) * self.radius

    def offset(self, d, direction=None):
        """The concentric arc ``d`` mm to the right of travel.

        On a left turn the right-hand side is the outside, so the radius grows;
        on a right turn it shrinks.

        @returns The shifted :class:`Arc`, or ``None`` if its radius would
                 collapse to zero or below (the caller skips it).
        """
        radius = self.radius + d if self.sweep > 0 else self.radius - d
        if radius <= 0:
            return None
        return Arc(self.centre, radius, self.start_angle, self.sweep)

    def points(self, steps):
        return [self.point(self.start_angle + self.sweep * k / steps)
                for k in range(steps + 1)]


@dataclass(frozen=True)
class RouteGeometry:
    """A solved route.

    @ivar start, start_offset, end, end_offset - The route as requested.
    @ivar segments - ``Line``/``Arc`` pieces in travel order, joined end to end.
    @ivar radius   - The arc radius (curves and S-curves), or ``None`` for a
                     plain straight.
    """

    start: int
    start_offset: float
    end: int
    end_offset: float
    segments: tuple
    radius: float | None


def offset_segments(segments, d):
    """Shift a whole route ``d`` mm to the right of travel.

    Lines shift sideways and arcs change radius about the same centre, so the
    shifted route stays parallel and every piece still joins the next.

    @param segments - The route's pieces.
    @param d        - Lateral distance (negative = left).
    @returns The shifted pieces, or ``None`` if an arc would collapse.
    """
    shifted = []
    for i, seg in enumerate(segments):
        direction = None
        if isinstance(seg, Line) and seg.length < _EPS:
            # A zero-length lead-in still has to move sideways with its
            # neighbours; borrow the direction of travel from the next piece
            # (or the previous one at the far end).
            neighbour = segments[i + 1] if i + 1 < len(segments) else segments[i - 1]
            direction = _tangent_at(neighbour, start=(i + 1 < len(segments)))
        moved = seg.offset(d, direction)
        if moved is None:
            return None
        shifted.append(moved)
    return tuple(shifted)


def _tangent_at(seg, start=True):
    """Unit direction of travel at the start (or end) of a piece."""
    if isinstance(seg, Line):
        return seg.direction
    angle = seg.start_angle if start else seg.start_angle + seg.sweep
    # Travel along an anticlockwise arc is 90° ahead of the radius.
    sign = 1.0 if seg.sweep > 0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def segments_polyline(segments, arc_steps):
    """Flatten a route into one polyline, without repeating the join points.

    Zero-length pieces still add their (repeated) end point, which keeps the
    point count the same as the original drawing code for ``--track_lead_in 0``.

    @param segments  - The route's pieces.
    @param arc_steps - Straight-line steps per arc.
    @returns List of ``(x, y)`` points.
    """
    points = [segments[0].p0]
    for seg in segments:
        points += seg.points(arc_steps)[1:]
    return points


# -------------------------------------------------------------------- geometry

def _edge_frame(edge, apothem):
    """Midpoint, inward unit normal and anticlockwise unit tangent of an edge."""
    th = math.radians(EDGE_ANGLES[edge])
    out = (math.cos(th), math.sin(th))
    midpoint = (apothem * out[0], apothem * out[1])
    inward = (-out[0], -out[1])
    tangent = (-out[1], out[0])
    return midpoint, inward, tangent


def edge_position(edge, point, apothem):
    """Where ``point`` sits along ``edge``: mm anticlockwise from its midpoint."""
    midpoint, _, tangent = _edge_frame(edge, apothem)
    return ((point[0] - midpoint[0]) * tangent[0]
            + (point[1] - midpoint[1]) * tangent[1])


def _separation(a, b):
    """Angle (degrees, 0–180) between the outward normals of edges a and b."""
    diff = abs(EDGE_ANGLES[a] - EDGE_ANGLES[b]) % 360.0
    return min(diff, 360.0 - diff)


def route_geometry(start, start_offset, end, end_offset, apothem, lead_in):
    """Solve one route.

    @param start, end   - Edge numbers (1–6).
    @param start_offset - Offset at the start edge (see module docstring).
    @param end_offset   - Offset at the end edge.
    @param apothem      - Deck apothem ``A`` (edge midpoints' distance from centre).
    @param lead_in      - Minimum straight at each end (``--track_lead_in``).
    @returns :class:`RouteGeometry`.
    @throws ValueError - If the edges are adjacent or equal, or the offsets
                         leave no room for the lead-ins.
    """
    sep = _separation(start, end)
    name = f"track route {start}-{end}"
    if sep < 1.0:
        raise ValueError(f"{name} starts and ends on the same edge.")
    if sep < 90.0:
        raise ValueError(
            f"{name}: edges {start} and {end} are adjacent, so the curve would be "
            "far too tight.  Join edges two apart (a curve) or opposite each "
            "other (a straight).")
    if sep > 150.0:
        segments, radius = _straight(start, start_offset, end, end_offset,
                                     apothem, lead_in, name)
    else:
        segments, radius = _curve(start, start_offset, end, end_offset,
                                  apothem, lead_in, name)
    return RouteGeometry(start, start_offset, end, end_offset, tuple(segments), radius)


def _curve(start, so, end, eo, apothem, lead_in, name):
    """Straight / 60° arc / straight between edges two apart (see module docstring)."""
    m_a, d_a, t_a = _edge_frame(start, apothem)
    m_b, d_b, t_b = _edge_frame(end, apothem)
    # The curve's centre lies beyond the edge between the two, so its outside
    # at each end is the way along the edge that points away from that edge.
    between = ((m_a[0] + m_b[0]) / 2.0, (m_a[1] + m_b[1]) / 2.0)
    u_a = t_a if t_a[0] * between[0] + t_a[1] * between[1] < 0 else (-t_a[0], -t_a[1])
    u_b = t_b if t_b[0] * between[0] + t_b[1] * between[1] < 0 else (-t_b[0], -t_b[1])
    s = (m_a[0] + so * u_a[0], m_a[1] + so * u_a[1])
    e = (m_b[0] + eo * u_b[0], m_b[1] + eo * u_b[1])

    # V: where the two inward normal lines through S and E meet.
    # Solve s + p·d_a = e + q·d_b for p, q (2×2 linear system).
    det = d_a[0] * (-d_b[1]) - d_a[1] * (-d_b[0])
    rx, ry = e[0] - s[0], e[1] - s[1]
    p = (rx * (-d_b[1]) - ry * (-d_b[0])) / det
    q = (d_a[0] * ry - d_a[1] * rx) / det
    v = (s[0] + p * d_a[0], s[1] + p * d_a[1])
    tangent_len = min(p, q) - lead_in
    if tangent_len <= _EPS:
        raise ValueError(
            f"{name}: offsets {so:g} / {eo:g} leave no room for the "
            f"{lead_in:g} mm lead-ins, so the curve would be too tight.")
    radius = tangent_len / _TAN30

    # Arc ends: tangent_len back from V along each lead-in line.
    a0 = (v[0] - tangent_len * d_a[0], v[1] - tangent_len * d_a[1])
    a1 = (v[0] - tangent_len * d_b[0], v[1] - tangent_len * d_b[1])
    # Turning from heading d_a to heading −d_b: left if the cross product is positive.
    cross = d_a[0] * (-d_b[1]) - d_a[1] * (-d_b[0])
    side = _left(d_a) if cross > 0 else _right(d_a)
    centre = (a0[0] + radius * side[0], a0[1] + radius * side[1])
    start_angle = math.atan2(a0[1] - centre[1], a0[0] - centre[0])
    sweep = math.radians(60.0) * (1.0 if cross > 0 else -1.0)
    arc = Arc(centre, radius, start_angle, sweep)
    return [Line(s, a0), arc, Line(a1, e)], radius


def _straight(start, so, end, eo, apothem, lead_in, name):
    """Straight between opposite edges, or an S-curve if the offsets differ."""
    m_a, d_a, _ = _edge_frame(start, apothem)
    m_b, _, _ = _edge_frame(end, apothem)
    right = _right(d_a)
    s = (m_a[0] + so * right[0], m_a[1] + so * right[1])
    e = (m_b[0] + eo * right[0], m_b[1] + eo * right[1])
    shift = eo - so
    if abs(shift) < _EPS:
        return [Line(s, e)], None

    # Reverse curve between the two lead-ins: two equal arcs of radius R that
    # cover the run D and the sideways shift δ: δ = 2R(1 − cos φ), D = 2R sin φ,
    # so R = (D² + δ²) / (4δ).
    p1 = (s[0] + lead_in * d_a[0], s[1] + lead_in * d_a[1])
    p2 = (e[0] - lead_in * d_a[0], e[1] - lead_in * d_a[1])
    run = (p2[0] - p1[0]) * d_a[0] + (p2[1] - p1[1]) * d_a[1]
    if run <= _EPS:
        raise ValueError(f"{name}: the lead-ins leave no room for the S-curve.")
    radius = (run * run + shift * shift) / (4.0 * abs(shift))
    phi = math.asin(min(1.0, run / (2.0 * radius)))
    # Shift to the right → the first arc turns right (clockwise), then left.
    turn = -1.0 if shift > 0 else 1.0
    side1 = _left(d_a) if turn > 0 else _right(d_a)
    c1 = (p1[0] + radius * side1[0], p1[1] + radius * side1[1])
    c2 = (p2[0] - radius * side1[0], p2[1] - radius * side1[1])
    arc1 = Arc(c1, radius, math.atan2(p1[1] - c1[1], p1[0] - c1[0]), turn * phi)
    arc2 = Arc(c2, radius, math.atan2(arc1.p1[1] - c2[1], arc1.p1[0] - c2[0]), -turn * phi)
    return [Line(s, p1), arc1, arc2, Line(arc2.p1, e)], radius


# ------------------------------------------------------------------- templates

def route_template_steps(geometry):
    """The track-template centreline for a route.

    Steps are ``("line", length)`` / ``("arc", degrees, radius)``, positive
    degrees turning left, as ``drawTrackTemplate`` expects.  Zero-length
    lead-ins are dropped.  The result is put in a canonical form: the first
    arc turns right, and of the route and its reverse, the smaller sequence is
    kept.  A template can be turned over or turned round, so routes that are
    mirror images or reversals of each other give the same steps and can
    share one template.

    @param geometry - A solved :class:`RouteGeometry`.
    @returns Tuple of steps.
    """
    # Rounded to 1e-9 mm: the solver's floating-point noise (1e-13) would
    # otherwise make two equal lead-ins compare unequal.
    steps = []
    for seg in geometry.segments:
        if isinstance(seg, Line):
            if seg.length > _EPS:
                steps.append(("line", round(seg.length, 9)))
        else:
            steps.append(("arc", round(math.degrees(seg.sweep), 9), round(seg.radius, 9)))
    forward = _mirror_first_arc_right(steps)
    backward = _mirror_first_arc_right(
        [("arc", -st[1], st[2]) if st[0] == "arc" else st for st in reversed(steps)])
    return min(forward, backward, key=_template_key)


def _mirror_first_arc_right(steps):
    """Mirror the steps if needed so the first arc turns right."""
    first_arc = next((st for st in steps if st[0] == "arc"), None)
    if first_arc is not None and first_arc[1] > 0:
        steps = [("arc", -st[1], st[2]) if st[0] == "arc" else st for st in steps]
    return tuple(steps)


def _template_key(steps):
    """Rounded form of a step sequence, for comparing and de-duplicating."""
    return tuple((st[0],) + tuple(round(x, 3) for x in st[1:]) for st in steps)


def template_key(steps):
    """Public de-duplication key for :func:`route_template_steps` output."""
    return _template_key(steps)
