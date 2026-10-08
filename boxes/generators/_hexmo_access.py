"""Hand-access openings in the walls (``--access_openings``, on by default).

A track under the deck (a subway, the helix's lower level) needs a hand to
re-rail a train.  Each wall's registration and weight holes give way to large
rounded-rectangle openings, leaving a band of wood above and below, a post at
each end, and the Ø6 registration pilots nearest the openings' ends, so a wall
that joins another module still lines up with it.

Used on HexmoRectangle's long walls and long supports (one opening per cell),
its end walls and short dividers, and on every HexmoHexagon wall: two openings
either side of a middle post as wide as the spoke, so the post stands over the
floor's spoke (and the support on it) and carries the subway opening.  With
--subway_ports each end of the wall also gets an upright cable slot, between
its end pilot pair (see end_pills).

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

# Wood left above and below each opening, and at each end of its stretch of
# wall (beside a wall end, a divider's slot or the next opening), in mm.
ACCESS_BAND = 12.0
ACCESS_POST = 15.0
# Smallest opening worth cutting (mm): fingers and a smaller hand, held flat
# (an adult man's hand is about 90 mm across the knuckles).
ACCESS_MIN = (70.0, 40.0)


def access_pair(lo, hi, middle):
    """Two openings either side of a middle post.

    @param lo, hi  - The stretch of wall (mm along it).
    @param middle  - The middle post's width (the spoke's).
    @returns ``[(start, end), (start, end)]``, with ACCESS_POST at each end.
    """
    centre = (lo + hi) / 2
    return [(lo + ACCESS_POST, centre - middle / 2), (centre + middle / 2, hi - ACCESS_POST)]


def access_fits(width, height):
    """Whether an opening is big enough for a hand (ACCESS_MIN).

    The openings are on by default, so a module too small for them keeps its
    normal walls rather than being refused.

    @param width, height - The opening (mm).
    @returns True when it is at least ACCESS_MIN.
    """
    return width >= ACCESS_MIN[0] and height >= ACCESS_MIN[1]


def access_spans(lo, hi, posts):
    """The openings along a stretch of wall, around the parts kept solid.

    @param lo, hi - The wall body (mm along it); the openings start
                    ACCESS_POST in from each end.
    @param posts  - ``[(start, end)]`` to keep solid: the middle post, slots
                    for crossing panels, track openings, each already widened
                    by whatever wood it needs.
    @returns ``[(start, end)]`` of the gaps between them, those shorter than
             FINGER_MIN left out (too narrow to reach through).
    """
    spans = []
    start, end = lo + ACCESS_POST, hi - ACCESS_POST
    for a, b in sorted(posts):
        if a > start:
            spans.append((start, min(a, end)))
        start = max(start, b)
    if end > start:
        spans.append((start, end))
    return [(a, b) for a, b in spans if b - a >= FINGER_MIN]


# The Ø6 registration pilots kept beside the openings, and the wood left
# between a pilot and an opening (mm).
PILOT_CLEAR = 5.0
# Narrowest opening still worth cutting once pilots are kept beside it:
# room for fingers.
FINGER_MIN = 35.0


def recorded_holes(box, draw):
    """The round holes ``draw`` would cut, recorded instead of drawn.

    Shadows ``hole`` and ``rectangularHole`` on the instance while ``draw``
    runs (every wall hole goes through one of them), then restores them.

    Positions are given in the frame current when this is called, even where
    ``draw`` moves the origin between holes.

    @param box  - The generator.
    @param draw - Callable drawing a wall's normal holes.
    @returns ``[(x, y, r)]`` for each round hole.
    """
    found = []
    to_start = ~box.ctx._m

    def record(x, y, r=0.0, d=0.0, tabs=0):
        px, py = to_start * (box.ctx._m * (x, y))
        found.append((px, py, r or d / 2))

    box.hole = record
    box.rectangularHole = lambda *a, **k: None
    try:
        draw()
    finally:
        del box.hole, box.rectangularHole
    return found


def end_columns(pilots):
    """Keep-solid stretches round a wall's outermost pilot columns.

    A wall that joins another module always keeps the Ø6 pilot pair nearest
    each of its ends.  Those are the corner groups' outer pilots, which sit
    at the same place on every HexmoHexagon side wall and HexmoRectangle end
    wall, so a dowel passes through both walls at every joint, whatever
    openings each has.

    @param pilots - ``[(along, across, r)]`` of the wall's pilot holes.
    @returns ``[(start, end)]`` for :func:`access_spans`: each end column
             with PILOT_CLEAR of wood round it (empty if there are none).
    """
    if not pilots:
        return []
    r = max(p[2] for p in pilots)
    along = [p[0] for p in pilots]
    return [(c - r - PILOT_CLEAR, c + r + PILOT_CLEAR) for c in (min(along), max(along))]


def end_pills(pilots, length, width, wood, lo, hi):
    """Upright cable slots at a wall's ends, beside or between pilot pairs.

    Wiring crosses a joint near the wall's ends, clear of a subway's bed and
    supports down the middle.  Each slot goes just outside the outermost
    column of the wall's Ø6 pilots (see end_columns), between it and the wall
    end, ``wood`` clear of the pilots and level with the middle of the pair,
    so it lines up through every joint as they do.  Where that would bring it
    nearer the wall end than ``lo``/``hi`` (a column close to the end), it
    stands in a column instead, centred between the column's outermost two
    pilots: the outermost column, or the next one in where that one is also
    too near the end.  Any pilots between such a pair (the full corner groups
    have two) give way to it.

    @param pilots - ``[(along, across, r)]`` of the wall's pilot holes.
    @param length - The slot's length up the wall (mm).
    @param width  - Its width along the wall (mm).
    @param wood   - Least wood between the slot and a pilot (mm).
    @param lo, hi - How near the wall's ends a slot's edge may come, in the
                    pilots' frame.  Callers put them the same distance in from
                    the shared hole pattern's ends, so joined walls choose the
                    same column.
    @returns ``[(along, across)]`` of each slot's centre: at most one per end
             (none where the wall is too low for it).  The slot is upright:
             ``length`` across the wall, ``width`` along it.
    """
    if not pilots:
        return []
    r = max(p[2] for p in pilots)
    columns = sorted({round(p[0], 6) for p in pilots})
    pills = []
    outside = r + wood + width / 2           # end column to slot centre
    for ordered, ok, out in ((columns, lambda c: c - width / 2 >= lo, -outside),
                             (columns[::-1], lambda c: c + width / 2 <= hi, outside)):
        # Outside the end column, towards the wall end, where there's room.
        end = ordered[0]
        across = sorted(p[1] for p in pilots if abs(p[0] - end) < 1e-6)
        if len(across) >= 2 and ok(end + out):
            pills.append((end + out, (across[0] + across[-1]) / 2))
            continue
        for c in ordered[:3]:
            across = sorted(p[1] for p in pilots if abs(p[0] - c) < 1e-6)
            if not ok(c) or len(across) < 2:
                continue
            bottom, top = across[0] + r + wood, across[-1] - r - wood
            if top - bottom >= length:
                pills.append((c, (bottom + top) / 2))
            break
    # On a short wall both ends could pick the same column.
    return list(dict.fromkeys(pills))


def openings_with_pilots(spans, pilots, middles):
    """Shrink the openings to keep Ø6 pilot pairs beside them.

    The pilots come in pairs across the wall (one near the floor, one near
    the deck), so they are grouped by their position along it.  In each
    opening the pairs nearest its two ends stay, the opening shrinks to clear
    them by PILOT_CLEAR, and any pairs between are dropped.  Where that leaves
    less than ACCESS_MIN wide (pairs close together, as on a hexagon side
    wall), the pair at the opening's middle end (beside the middle post or a
    divider, listed in ``middles``) is dropped instead and the opening runs to
    it; if even that leaves less than FINGER_MIN, the opening keeps its full
    size and loses its pilots.

    @param spans   - ``[(start, end)]`` of the full-size openings along the wall.
    @param pilots  - ``[(along, across, r)]`` of the wall's pilot holes.
    @param middles - Positions along the wall of the middle post / dividers.
    @returns ``(openings, kept)``: the openings ``[(start, end)]`` and the
             pilots ``[(along, across, r)]`` to cut.
    """
    clear_of = lambda r: r + PILOT_CLEAR
    columns = sorted({round(a, 3) for a, _, _ in pilots})
    dropped = set()
    openings = []
    for lo, hi in spans:
        inside = [c for c in columns
                  if lo - clear_of(3.0) < c < hi + clear_of(3.0)]
        if not inside:
            openings.append((lo, hi))
            continue
        r = max(p[2] for p in pilots)
        first, last = inside[0], inside[-1]
        # Which end of the opening faces the middle (a post or divider)?
        mid_at_hi = min(abs(hi - m) for m in middles) < min(abs(lo - m) for m in middles) \
            if middles else True
        a, b = first + clear_of(r), last - clear_of(r)
        if len(inside) > 1 and b - a >= ACCESS_MIN[0]:
            dropped.update(inside[1:-1])
            openings.append((max(lo, a), min(hi, b)))
            continue
        # Keep only the pair at the wall-end side of the opening.
        if mid_at_hi:
            a, b = first + clear_of(r), hi
            keep = first
        else:
            a, b = lo, last - clear_of(r)
            keep = last
        if b - a >= FINGER_MIN:
            dropped.update(c for c in inside if c != keep)
            openings.append((max(lo, a), min(hi, b)))
        else:
            dropped.update(inside)
            openings.append((lo, hi))
    kept = [p for p in pilots if round(p[0], 3) not in dropped]
    return openings, kept
