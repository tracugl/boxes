"""Hand-access openings in walls nothing joins (``--access_openings``).

A track under the deck (a subway, the helix's lower level) needs a hand to
re-rail a train.  A wall that joins no other module needs no registration
holes, so it can carry large openings instead: one rounded rectangle per
stretch of wall, leaving a band of wood above and below and a post at each end.

Used on HexmoRectangle's long walls and long supports (one opening per cell),
the HexmoHexagon trapezoid's long wall (two, split at its middle) and the full
hexagon's chosen side walls (one each).

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

# Wood left above and below each opening, and at each end of its stretch of
# wall (beside a wall end, a divider's slot or the next opening), in mm.
ACCESS_BAND = 12.0
ACCESS_POST = 15.0
# Smallest opening worth cutting (mm): an adult hand, held flat.
ACCESS_MIN = (90.0, 40.0)


def access_spans(lo, hi, count):
    """Where the openings go along a stretch of wall.

    The stretch is split into ``count`` equal openings with a post of
    ACCESS_POST at each end and between neighbours.

    @param lo, hi - The stretch (mm along the wall).
    @param count  - Number of openings.
    @returns ``[(start, end)]`` of each opening.
    """
    width = (hi - lo - (count + 1) * ACCESS_POST) / count
    return [(lo + ACCESS_POST + k * (width + ACCESS_POST),
             lo + ACCESS_POST + k * (width + ACCESS_POST) + width) for k in range(count)]


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
