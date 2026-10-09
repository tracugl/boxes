"""Hand-access openings in walls nothing joins (``--access_openings``).

A track under the deck (a subway, the helix's lower level) needs a hand to
re-rail a train.  A wall that joins no other module needs no registration
holes, so it can carry large rounded-rectangle openings instead, leaving a
band of wood above and below and a post at each end.

Used on HexmoRectangle's long walls and long supports (one opening per cell),
and on the HexmoHexagon trapezoid's long wall and the full hexagon's chosen
side walls: two each, either side of a middle post as wide as the spoke, so
the post stands over the floor's spoke (and the support on it).

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


def check_access_size(width, height, where):
    """Refuse an opening too small for a hand.

    @param width, height - The opening (mm).
    @param where         - What to name in the message.
    @throws ValueError - If it is smaller than ACCESS_MIN.
    """
    if width < ACCESS_MIN[0] or height < ACCESS_MIN[1]:
        raise ValueError(
            f"--access_openings: {where} leaves only a {width:.0f} × {height:.0f} mm "
            f"opening (a hand needs about {ACCESS_MIN[0]:g} × {ACCESS_MIN[1]:g}); "
            "use a taller --h or a bigger module.")


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
