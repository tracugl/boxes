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
