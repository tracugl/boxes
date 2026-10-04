"""Deck slots along a descending track (``--deck_slots``).

A track that drops away from the deck (the helix ring's spur) runs in an open
slot cut through the deck along its path, so the train passes down through
it.  Each slot follows a track *route* (see :mod:`_hexmo_track_routes`), over
part or all of its length, at a set width::

    --deck_slots "1:-17.5-5:17.5@157.., 3:35-1:0@..262/26"

* ``ROUTE``: the same ``A:offset-B:offset`` route syntax as ``--track_routes``
  (offsets default to 0);
* ``@FROM..TO`` (optional): the stretch, in mm along the route's centreline
  from its start; either end may be left off (``@157..`` runs to the end,
  ``@..262`` from the start).  Default: the whole route;
* ``/WIDTH`` (optional): default ``--under_track_width``.

A slot that reaches a deck edge is run ``OVERRUN`` past the wall's inner
face, where routes end.  The deck reaches one material thickness further,
over the top of the wall, so a narrow strip of deck (thickness − OVERRUN) is
left across the slot's mouth.  That is on purpose: a slot from edge to edge
would otherwise cut the deck in two, and the strip holds it together until it
is fitted, then is cut away.  The wall below must be notched there
(``--track_openings``), which also leaves that deck edge plain; otherwise the
slot would cut through the deck's finger slots.  A slot must also keep clear of the deck's support slots, since a
support wall standing there would block the track anyway.

**Cutting.**  The outline is drawn with the turtle, like
``Boxes.rectangularHole``: clockwise, starting one burn width inside the
hole, with straights as ``edge`` and curves as ``corner(angle, radius)``, so
the usual burn compensation applies.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from boxes.generators._hexmo_track_routes import Arc, Line, parse_track_routes

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_SLOT_RE = re.compile(
    rf"^\s*(?P<route>[^@/]+?)\s*"
    rf"(?:@\s*(?P<lo>{_NUMBER})?\s*\.\.\s*(?P<hi>{_NUMBER})?\s*)?"
    rf"(?:/\s*(?P<width>{_NUMBER})\s*)?$")

# How far past the wall's inner face a slot reaching a deck edge is run.  It
# stops short of the deck's outer edge, leaving a strip to cut once fitted.
OVERRUN = 1.0


@dataclass(frozen=True)
class DeckSlot:
    """One ``--deck_slots`` entry.  ``None`` bounds mean the route's ends."""

    start: int
    start_offset: float
    end: int
    end_offset: float
    lo: float | None
    hi: float | None
    width: float


def parse_deck_slots(text, default_width):
    """Parse ``--deck_slots``.

    @param text          - The option value; blank means none.
    @param default_width - Width for entries that do not give one.
    @returns List of :class:`DeckSlot`.
    @throws ValueError - On a malformed entry, an empty stretch or a
                         non-positive width.
    """
    if not text or not text.strip():
        return []
    slots = []
    for item in text.split(","):
        match = _SLOT_RE.match(item)
        if not match:
            raise ValueError(
                f"--deck_slots entry {item.strip()!r} is not "
                "'<route>[@<from>..<to>][/<width>]', e.g. '1:-17.5-5:17.5@157..'.")
        try:
            (spec,) = parse_track_routes(match["route"])
        except ValueError as err:
            raise ValueError(f"--deck_slots entry {item.strip()!r}: {err}") from None
        lo = float(match["lo"]) if match["lo"] is not None else None
        hi = float(match["hi"]) if match["hi"] is not None else None
        width = float(match["width"]) if match["width"] is not None else default_width
        if width <= 0:
            raise ValueError(f"--deck_slots entry {item.strip()!r}: width must be positive.")
        if lo is not None and hi is not None and hi <= lo:
            raise ValueError(f"--deck_slots entry {item.strip()!r}: empty stretch.")
        slots.append(DeckSlot(spec.start, spec.start_offset or 0.0, spec.end,
                              spec.end_offset or 0.0, lo, hi, width))
    return slots


def _length(seg):
    return seg.length


def trim_segments(segments, lo, hi):
    """The part of a route between ``lo`` and ``hi`` mm along it.

    @param segments - The route's pieces (``Line``/``Arc``), in order.
    @param lo, hi   - Distances along the centreline, ``0 ≤ lo < hi``.  ``hi``
                      may run past the end, and ``lo`` before the start, by
                      extending the end (or start) straight on.
    @returns The trimmed pieces.
    """
    out = []
    pos = 0.0
    for seg in segments:
        length = _length(seg)
        a, b = max(lo, pos), min(hi, pos + length)
        if b - a > 1e-9:
            out.append(_sub(seg, a - pos, b - pos))
        pos += length
    if lo < 0:
        first = segments[0]
        d = _tangent(first, start=True)
        p = first.p0
        out.insert(0, Line((p[0] + lo * d[0], p[1] + lo * d[1]), p))
    if hi > pos:
        last = segments[-1]
        d = _tangent(last, start=False)
        p = last.p1
        extra = hi - pos
        out.append(Line(p, (p[0] + extra * d[0], p[1] + extra * d[1])))
    return out


def _sub(seg, a, b):
    """The stretch [a, b] (mm from its start) of one piece."""
    if isinstance(seg, Line):
        d = seg.direction
        return Line((seg.p0[0] + a * d[0], seg.p0[1] + a * d[1]),
                    (seg.p0[0] + b * d[0], seg.p0[1] + b * d[1]))
    sign = 1.0 if seg.sweep > 0 else -1.0
    start = seg.start_angle + sign * a / seg.radius
    return Arc(seg.centre, seg.radius, start, sign * (b - a) / seg.radius)


def _tangent(seg, start=True):
    if isinstance(seg, Line):
        return seg.direction
    angle = seg.start_angle if start else seg.start_angle + seg.sweep
    sign = 1.0 if seg.sweep > 0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def slot_outline(segments, width):
    """Turtle steps for a slot of ``width`` along ``segments``.

    The outline runs clockwise (inside on the right): from the middle of the
    start cap to the left-hand side, forwards along it, across the end cap,
    back along the right-hand side, and across the start cap to the start.
    On a left-turning arc the left side is the inner one (radius − w/2) and
    the right side the outer; on a right turn the reverse.

    @param segments - The (trimmed) centreline pieces.
    @param width    - Slot width.
    @returns ``(start, heading, steps)``: the start point (middle of the
             start cap, before the burn shift), the initial heading in degrees,
             and ``[("edge", length) | ("corner", degrees, radius)]``.
    @throws ValueError - If an arc is too tight for the slot (inner side
                         radius ≤ 0).
    """
    half = width / 2.0
    t0 = _tangent(segments[0], start=True)
    left = (-t0[1], t0[0])
    start = segments[0].p0
    steps = [("edge", half), ("corner", -90.0, 0.0)]
    for seg in segments:
        steps.append(_side_step(seg, half, side=+1))
    steps += [("corner", -90.0, 0.0), ("edge", width), ("corner", -90.0, 0.0)]
    for seg in reversed(segments):
        steps.append(_side_step(seg, half, side=-1))
    steps += [("corner", -90.0, 0.0), ("edge", half)]
    heading = math.degrees(math.atan2(left[1], left[0]))
    return start, heading, steps


def _side_step(seg, half, side):
    """One side of the slot along one piece: +1 left side forwards, −1 right side backwards."""
    if isinstance(seg, Line):
        return ("edge", seg.length)
    degrees = math.degrees(seg.sweep)
    left_turn = seg.sweep > 0
    if side > 0:
        radius = seg.radius - half if left_turn else seg.radius + half
        turn = degrees
    else:
        radius = seg.radius + half if left_turn else seg.radius - half
        turn = -degrees
    if radius <= 0:
        raise ValueError(
            f"--deck_slots: a {2 * half:g} mm slot is too wide for an "
            f"R{seg.radius:.0f} curve.")
    return ("corner", turn, radius)


def centreline_points(segments, step=2.0):
    """Points along the slot centreline, about ``step`` mm apart (for checks)."""
    points = []
    for seg in segments:
        n = max(1, int(math.ceil(_length(seg) / step)))
        if isinstance(seg, Line):
            points += [(seg.p0[0] + (seg.p1[0] - seg.p0[0]) * k / n,
                        seg.p0[1] + (seg.p1[1] - seg.p0[1]) * k / n) for k in range(n + 1)]
        else:
            points += [seg.point(seg.start_angle + seg.sweep * k / n) for k in range(n + 1)]
    return points
