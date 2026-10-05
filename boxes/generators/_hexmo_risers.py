"""Riser boards for a descending track (``--risers``).

A track that drops through the deck slot (or runs under the deck) needs
something to stand on.  A riser is:

* a **track bed**: one flat strip following the track's path in plan, the
  track's width wide, cut as its own part and flexed very slightly to the
  slope (a few per cent over a module, so the strip's plan shape is used);
* **supports**: small boards standing across the track on the floor panel,
  each cut to the bed's height at that point.  Their bottom tabs drop into
  slots cut in the floor panel and their top tabs into slots in the bed, so
  both locate exactly.  Standing across the track, their tops are level.

Each entry is ``ROUTE[@FROM..TO]~H0..H1[/WIDTH]``:

* ``ROUTE``: the ``--track_routes`` syntax (offsets default to 0);
* ``@FROM..TO``: the stretch, in mm along the route from its start, as for
  ``--deck_slots`` (default: the whole route);
* ``H0..H1``: the track height (track base, i.e. the bed's top) above the
  floor panel at the start and end of the stretch, rising or falling evenly;
* ``/WIDTH``: the bed width, default ``--track_width``.

The heights are introduced by ``~``, not ``=``: the boxes web server splits
each URL parameter on every ``=``, so a value cannot contain one.

Supports go 15 mm in from each end of the bed and evenly between, no more
than ``--riser_spacing`` apart.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from boxes.generators._hexmo_deck_slots import _tangent
from boxes.generators._hexmo_track_routes import Line, parse_track_routes

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_RISER_RE = re.compile(
    rf"^\s*(?P<route>[^@~/]+?)\s*"
    rf"(?:@\s*(?P<lo>{_NUMBER})?\s*\.\.\s*(?P<hi>{_NUMBER})?\s*)?"
    rf"~\s*(?P<h0>{_NUMBER})\s*\.\.\s*(?P<h1>{_NUMBER})\s*"
    rf"(?:/\s*(?P<width>{_NUMBER})\s*)?$")

# Supports sit this far in from each end of the bed.
END_INSET = 15.0


@dataclass(frozen=True)
class RiserSpec:
    """One ``--risers`` entry (see module docstring)."""

    start: int
    start_offset: float
    end: int
    end_offset: float
    lo: float | None
    hi: float | None
    h0: float
    h1: float
    width: float | None


def parse_risers(text):
    """Parse ``--risers``.

    @param text - The option value; blank means none.
    @returns List of :class:`RiserSpec` (``width`` None = the default).
    @throws ValueError - On a malformed entry, an empty stretch or a
                         non-positive width.
    """
    if not text or not text.strip():
        return []
    risers = []
    for item in text.split(","):
        match = _RISER_RE.match(item)
        if not match:
            raise ValueError(
                f"--risers entry {item.strip()!r} is not "
                "'<route>[@<from>..<to>]~<h0>..<h1>[/<width>]', "
                "e.g. '3:-17.5-5:-35~72.5..65.2'.")
        try:
            (spec,) = parse_track_routes(match["route"])
        except ValueError as err:
            raise ValueError(f"--risers entry {item.strip()!r}: {err}") from None
        lo = float(match["lo"]) if match["lo"] is not None else None
        hi = float(match["hi"]) if match["hi"] is not None else None
        width = float(match["width"]) if match["width"] is not None else None
        if width is not None and width <= 0:
            raise ValueError(f"--risers entry {item.strip()!r}: width must be positive.")
        if lo is not None and hi is not None and hi <= lo:
            raise ValueError(f"--risers entry {item.strip()!r}: empty stretch.")
        risers.append(RiserSpec(spec.start, spec.start_offset or 0.0, spec.end,
                                spec.end_offset or 0.0, lo, hi,
                                float(match["h0"]), float(match["h1"]), width))
    return risers


def point_at(segments, s):
    """Centreline point and unit direction ``s`` mm along ``segments``."""
    pos = 0.0
    for seg in segments:
        length = seg.length
        if s <= pos + length or seg is segments[-1]:
            a = min(max(s - pos, 0.0), length)
            if isinstance(seg, Line):
                d = seg.direction
                return (seg.p0[0] + a * d[0], seg.p0[1] + a * d[1]), d
            sign = 1.0 if seg.sweep > 0 else -1.0
            angle = seg.start_angle + sign * a / seg.radius
            point = seg.point(angle)
            return point, (-sign * math.sin(angle), sign * math.cos(angle))
        pos += length
    raise ValueError("empty route")


def support_stations(length, spacing):
    """Distances along a bed of ``length`` where supports stand.

    15 mm in from each end, and evenly between them no more than
    ``spacing`` apart.  A bed too short for two gets one, in the middle.

    @param length  - Bed length (mm).
    @param spacing - Largest gap between neighbouring supports (mm).
    @returns Sorted distances from the bed's start.
    """
    span = length - 2 * END_INSET
    if span <= 0:
        return [length / 2.0]
    gaps = max(1, math.ceil(span / spacing))
    return [END_INSET + span * k / gaps for k in range(gaps + 1)]


def strip_outline(segments, width):
    """Turtle steps for the bed strip's outline, as a part (anticlockwise).

    From the middle of the start cap: across to the right-hand side,
    forwards along it, across the end cap, back along the left-hand side,
    and across the start cap.  On a left-turning arc the right side is the
    outer one (radius + w/2) and is traversed turning left; the left side
    is traversed backwards, turning right.

    @returns ``(start, heading, steps)`` like ``slot_outline``.
    @throws ValueError - If an arc is too tight for the strip.
    """
    half = width / 2.0
    t0 = _tangent(segments[0], start=True)
    right = (t0[1], -t0[0])
    steps = [("edge", half), ("corner", 90.0, 0.0)]
    for seg in segments:
        steps.append(_strip_side(seg, half, forwards=True))
    steps += [("corner", 90.0, 0.0), ("edge", width), ("corner", 90.0, 0.0)]
    for seg in reversed(segments):
        steps.append(_strip_side(seg, half, forwards=False))
    steps += [("corner", 90.0, 0.0), ("edge", half)]
    return segments[0].p0, math.degrees(math.atan2(right[1], right[0])), steps


def _strip_side(seg, half, forwards):
    if isinstance(seg, Line):
        return ("edge", seg.length)
    left_turn = seg.sweep > 0
    degrees = math.degrees(seg.sweep)
    if forwards:      # right-hand side, forwards
        radius = seg.radius + half if left_turn else seg.radius - half
        turn = degrees
    else:             # left-hand side, backwards
        radius = seg.radius - half if left_turn else seg.radius + half
        turn = -degrees
    if radius <= 0:
        raise ValueError(
            f"--risers: a {2 * half:g} mm bed is too wide for an R{seg.radius:.0f} curve.")
    return ("corner", turn, radius)


def strip_points(segments, width, step=2.0):
    """Points round the strip's edges (for its bounding box)."""
    half = width / 2.0
    total = sum(seg.length for seg in segments)
    n = max(2, int(math.ceil(total / step)))
    points = []
    for k in range(n + 1):
        p, d = point_at(segments, total * k / n)
        points += [(p[0] - half * d[1], p[1] + half * d[0]),
                   (p[0] + half * d[1], p[1] - half * d[0])]
    return points



# --------------------------------------------------------------- kite spine
#
# On a spoke floor the kite cut-outs leave nothing for a riser support to
# slot into.  So a solid **spine** is left along each riser's path: a band
# following the track, the bed's width plus a margin each side wide.  Each
# kite keeps its full size apart from that band: it is cut along the band's
# two edges, and the openings either side of it are kept.  Supports can then
# stand anywhere along the track.
#
# A kite is split by one band edge (a polyline that crosses it) by walking
# its outline between the two crossing points and back along the edge.  The
# band edges are run straight on well past the riser's ends, so a band that
# stops inside a kite still crosses it cleanly.

def _side(polyline, p):
    """+1 if p is left of the polyline (at its nearest segment), −1 if right."""
    best, sign = math.inf, 1.0
    for a, b in zip(polyline, polyline[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        if length2 < 1e-12:
            continue
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
        q = (a[0] + t * dx, a[1] + t * dy)
        d = math.dist(p, q)
        if d < best:
            best = d
            sign = 1.0 if dx * (p[1] - a[1]) - dy * (p[0] - a[0]) > 0 else -1.0
    return sign


def _crossings(polygon, polyline):
    """Where a polyline crosses a polygon's outline, in order along the polyline.

    @returns ``[(polyline segment index, polygon edge index, point)]``.
    """
    hits = []
    n = len(polygon)
    for i, (a, b) in enumerate(zip(polyline, polyline[1:])):
        found = []
        for j in range(n):
            c, d = polygon[j], polygon[(j + 1) % n]
            den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
            if abs(den) < 1e-12:
                continue
            t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
            u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
            if 0 <= t < 1 and 0 <= u < 1:
                found.append((t, j, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))))
        hits += [(i, j, p) for _, j, p in sorted(found)]
    return hits


def split_by_polyline(polygon, polyline):
    """Split a polygon in two along a polyline that crosses it once.

    @returns The two pieces, or None if the polyline does not cross the
             outline exactly twice.
    """
    hits = _crossings(polygon, polyline)
    if len(hits) != 2:
        return None
    (i0, j0, p0), (i1, j1, p1) = hits
    inside = polyline[i0 + 1:i1 + 1]            # the cut, from p0 to p1
    n = len(polygon)

    def walk(j_from, p_from, j_to, p_to):
        # Along the outline from p_from (on edge j_from) to p_to (on edge j_to).
        pts, j = [p_from], j_from
        while j != j_to:
            j = (j + 1) % n
            pts.append(polygon[j])
        pts.append(p_to)
        return pts

    piece_a = walk(j1, p1, j0, p0) + inside                  # p1 → p0, then cut p0 → p1
    piece_b = walk(j0, p0, j1, p1) + list(reversed(inside))  # p0 → p1, then cut back
    return [piece_a, piece_b]


def _keep_side(polygon, polyline, side):
    """The part(s) of a polygon on one side (+1 left / −1 right) of a polyline."""
    split = split_by_polyline(polygon, polyline)
    if split is None:
        if _crossings(polygon, polyline):
            return []          # crosses awkwardly: leave it solid
        return [polygon] if _side(polyline, polygon[0]) == side else []
    out = []
    for piece in split:
        # Judge a piece by its outline points off the cut.
        probe = [p for p in piece if p not in polyline]
        probe = probe or piece
        centre = (sum(p[0] for p in probe) / len(probe), sum(p[1] for p in probe) / len(probe))
        if _side(polyline, centre) == side:
            out.append(piece)
    return out


def _width(polygon):
    """Rough width of a piece: 2·area / perimeter (a strip's width)."""
    pts = polygon + polygon[:1]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:]))) / 2
    perimeter = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    return 2 * area / perimeter if perimeter else 0.0


def _clear_width(polygon, step=0.5, enough=None):
    """How wide a piece really is: the diameter of the largest circle inside it.

    _width (2·area / perimeter) is a strip's width, but only half the width
    of a triangle (its inradius), so it wrongly drops a triangle left where a
    riser's spine cuts across a kite.  This finds the largest circle that
    fits, by sampling a grid inside the piece.  2·area / perimeter never
    exceeds this (a convex shape's inradius is at least area / perimeter),
    so it is only computed when that quick measure falls short.

    @param polygon - The piece's outline points.
    @param step    - Grid spacing (mm); the answer is within about this.
    @param enough  - Stop as soon as a circle this wide is found (mm), when
                     only whether it fits matters.
    @returns The diameter (mm), or at least ``enough`` once that is reached.
    """
    quick = _width(polygon)
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    edges = list(zip(polygon, polygon[1:] + polygon[:1]))
    best = 0.0
    y = min(ys) + step / 2
    while y < max(ys):
        x = min(xs) + step / 2
        while x < max(xs):
            if _inside_polygon(polygon, (x, y)):
                best = max(best, min(_segment_distance((x, y), a, b) for a, b in edges))
                if enough is not None and 2 * best >= enough:
                    return 2 * best
            x += step
        y += step
    return max(quick, 2 * best)


def _inside_polygon(polygon, p):
    """Ray-casting point-in-polygon test."""
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > p[1]) != (y1 > p[1]):
            if x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0) > p[0]:
                inside = not inside
    return inside


def _segment_distance(p, a, b):
    """Distance from p to the segment a–b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    f = 0.0 if length2 < 1e-12 else max(0.0, min(1.0, (
        (p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.dist(p, (a[0] + f * dx, a[1] + f * dy))


def spine_kites(kites, spines, min_piece):
    """Cut a solid spine out of the kites under each riser.

    @param kites     - Kite polygons.
    @param spines    - ``(left_edge, right_edge)`` polylines per riser: the
                       band's two edges, in the kites' frame, running in the
                       direction of travel and well past both ends.
    @param min_piece - Pieces narrower than this (the largest circle that fits
                       in them, see _clear_width) are left solid.
    @returns The openings to cut.  Kites the spines miss are unchanged.
    """
    pieces = [list(k) for k in kites]
    for left, right in spines:
        out = []
        for piece in pieces:
            out += _keep_side(piece, left, +1) + _keep_side(piece, right, -1)
        pieces = out
    original = [list(k) for k in kites]
    return [p for p in pieces
            if p in original or _width(p) >= min_piece
            or _clear_width(p, enough=min_piece) >= min_piece]


def point_in_convex(polygon, p):
    """True if p is strictly inside a convex polygon (either winding)."""
    signs = set()
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(cross) > 1e-9:
            signs.add(cross > 0)
    return len(signs) == 1
