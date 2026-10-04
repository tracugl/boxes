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



# ---------------------------------------------------------------- kite ribs
#
# On a spoke floor the kite cut-outs leave nothing for a riser support to
# slot into.  Where a support stands over a kite, a solid rib is left across
# that kite instead: a bar along the support's footprint line (across the
# track), wide enough for its finger slots plus a margin each side, running
# right across the kite so both ends join the rim or a spoke.  Kites are
# convex, so each rib just clips the kite to the two sides of the bar.

def clip_half_plane(polygon, origin, normal, offset):
    """Keep the part of a convex polygon where (p − origin)·normal ≥ offset.

    Sutherland–Hodgman clipping against one line.

    @param polygon - Vertices in order.
    @param origin  - A point on the reference line.
    @param normal  - Unit normal of the line.
    @param offset  - Signed distance of the clip line from ``origin``.
    @returns The clipped polygon (possibly empty).
    """
    def side(p):
        return (p[0] - origin[0]) * normal[0] + (p[1] - origin[1]) * normal[1] - offset

    out = []
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        sa, sb = side(a), side(b)
        if sa >= 0:
            out.append(a)
        if (sa >= 0) != (sb >= 0):
            t = sa / (sa - sb)
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out


def min_width(polygon):
    """Smallest width of a convex polygon (over its edge directions)."""
    best = math.inf
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        length = math.dist(a, b)
        if length < 1e-9:
            continue
        nx, ny = (b[1] - a[1]) / length, -(b[0] - a[0]) / length
        best = min(best, max(abs((p[0] - a[0]) * nx + (p[1] - a[1]) * ny) for p in polygon))
    return best


def _inside_convex(polygon, p):
    """True if p is strictly inside a convex polygon (either winding)."""
    signs = set()
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(cross) > 1e-9:
            signs.add(cross > 0)
    return len(signs) == 1


def rib_kites(kites, ribs, rib_width, min_piece):
    """Split kites with solid ribs under riser supports.

    @param kites     - Convex kite polygons.
    @param ribs      - ``(point, across, length)`` per support: its
                       footprint's centre, the unit direction of the
                       footprint line (across the track) and its length.
    @param rib_width - Width of each rib (along the track).
    @param min_piece - Pieces narrower than this are dropped (left solid).
    @returns The openings to cut: kites unaffected by any rib unchanged, the
             others split either side of their ribs.
    """
    out = []
    half = rib_width / 2.0
    for kite in kites:
        pieces = [kite]
        for point, across, length in ribs:
            # Only ribs whose footprint (plus the rib margin) reaches the kite.
            reach = length / 2.0 + half
            samples = [(point[0] + across[0] * reach * k / 10.0,
                        point[1] + across[1] * reach * k / 10.0) for k in range(-10, 11)]
            if not any(_inside_convex(kite, s) for s in samples):
                continue
            normal = (-across[1], across[0])     # along the track
            split = []
            for piece in pieces:
                for sign in (1.0, -1.0):
                    part = clip_half_plane(piece, point, (sign * normal[0], sign * normal[1]), half)
                    if len(part) >= 3:
                        split.append(part)
            pieces = split
        out += [p for p in pieces if p is kite or min_width(p) >= min_piece]
    return out
