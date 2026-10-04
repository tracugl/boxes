"""Turnouts etched on a straight module's deck (``--turnouts``).

A HexmoRectangle carries straight track, which is where turnouts fit: a
commercial turnout is a straight-bodied piece 120–220 mm long, too long for the
curving tracks of a hexagon module.  The helix ring's entry rectangle uses two
of them to split one entry line into the three tracks that M6 takes at edge 1.

Each entry is ``toe:from:to``:

* ``toe``  — mm along the deck from its start (x = 0) to the turnout's toe
  (the tips of the switch blades);
* ``from`` — the lateral offset of the through road, as for the deck's track
  lines (mm from the centre line, positive towards +y);
* ``to``   — the lateral offset the diverging leg settles at; its sign gives the
  hand of the turnout.

The turnout faces +x, so its diverging leg spreads towards the end of the deck
at x = length.  The through road is the deck's existing straight track line; this
module only adds the diverging leg.

**Leg geometry** (in a frame with x along the deck, y across it):

1. from the toe, a ``radius`` curve turning towards ``to`` until it reaches
   the crossing ``angle`` (this models the turnout's diverging road);
2. a straight at that angle, past the heel (``length`` mm after the toe), until
   it is one reverse-curve's rise short of ``to``;
3. a ``reverse_radius`` curve back to parallel at ``to``;
4. a straight to the end of the deck.

Steps 2–4 are flexible track laid after the turnout.  Peco's N medium turnout
(SL-E395/396) is 123.7 mm long with a 457 mm diverging radius and a 14° angle,
which puts the diverging road 16.9 mm off the through road at the heel.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from boxes.generators._hexmo_track_routes import Arc, Line

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_ENTRY_RE = re.compile(rf"^\s*({_NUMBER})\s*:\s*({_NUMBER})\s*:\s*({_NUMBER})\s*$")


@dataclass(frozen=True)
class TurnoutSpec:
    """One ``--turnouts`` entry: toe position and the two roads' offsets."""

    toe: float
    start: float
    end: float


@dataclass(frozen=True)
class TurnoutLeg:
    """A solved diverging leg.

    @ivar segments      - ``Line``/``Arc`` pieces from the toe to the end of the deck.
    @ivar heel          - Point on the leg's centreline level with the turnout's heel.
    @ivar parallel_from - x where the leg is back parallel at its target offset.
    """

    segments: tuple
    heel: tuple
    parallel_from: float


def parse_turnouts(text):
    """Parse ``--turnouts``.

    @param text - The option value; blank means none.
    @returns List of :class:`TurnoutSpec`.
    @throws ValueError - On a malformed entry, a toe before the deck's start,
                         or a leg that does not diverge.
    """
    if not text or not text.strip():
        return []
    specs = []
    for item in text.split(","):
        match = _ENTRY_RE.match(item)
        if not match:
            raise ValueError(
                f"--turnouts entry {item.strip()!r} is not '<toe>:<from>:<to>', "
                "e.g. '10:0:-35'.")
        toe, start, end = (float(v) for v in match.groups())
        if toe < 0:
            raise ValueError(f"--turnouts entry {item.strip()!r}: the toe is before "
                             "the start of the deck.")
        if abs(end - start) < 1e-9:
            raise ValueError(f"--turnouts entry {item.strip()!r}: the diverging leg "
                             "must end at a different offset from the through road.")
        specs.append(TurnoutSpec(toe, start, end))
    return specs


def turnout_leg(spec, deck_length, length, radius, angle, reverse_radius):
    """Solve one turnout's diverging leg.

    @param spec           - The :class:`TurnoutSpec`.
    @param deck_length    - Deck length along the track; the leg runs to its end.
    @param length         - Turnout length, toe to heel.
    @param radius         - Diverging road radius.
    @param angle          - Crossing angle, degrees.
    @param reverse_radius - Radius of the flexible-track curve back to parallel.
    @returns :class:`TurnoutLeg`.
    @throws ValueError - If the turnout's curve is longer than the turnout, the
                         target is too close to spread to, or the leg is not
                         back to parallel before the end of the deck.
    """
    theta = math.radians(angle)
    if radius * math.sin(theta) > length + 1e-9:
        raise ValueError(
            f"--turnouts: a {radius:g} mm curve reaches {angle:g}° only "
            f"{radius * math.sin(theta):.0f} mm on, past the {length:g} mm turnout.")
    side = 1.0 if spec.end > spec.start else -1.0
    spread = abs(spec.end - spec.start)
    # Lateral rise of each piece, measured away from the through road.
    curve_rise = radius * (1 - math.cos(theta))
    heel_rise = curve_rise + (length - radius * math.sin(theta)) * math.tan(theta)
    reverse_rise = reverse_radius * (1 - math.cos(theta))
    straight_rise = spread - curve_rise - reverse_rise
    if spread - reverse_rise < heel_rise - 1e-9:
        raise ValueError(
            f"--turnouts: the leg at {spec.toe:g} mm is too close to spread to "
            f"{spec.end:g}; it is already {heel_rise:.1f} mm off the through road at "
            f"the heel and needs {reverse_rise:.1f} mm more to straighten, so the "
            f"tracks must be at least {heel_rise + reverse_rise:.1f} mm apart.")
    x0, y0 = spec.toe, spec.start
    # 1. The turnout's diverging road: a curve from the toe to the crossing angle.
    centre1 = (x0, y0 + side * radius)
    first = Arc(centre1, radius, -side * math.pi / 2, side * theta)
    # 2. The straight at the crossing angle, through the heel.
    p1 = first.p1
    run = straight_rise / math.sin(theta)
    p2 = (p1[0] + run * math.cos(theta), p1[1] + side * run * math.sin(theta))
    straight = Line(p1, p2)
    # 3. The reverse curve back to parallel (turning away from `side`).
    # Its centre is one radius from p2, square to the direction of travel on
    # the side it turns towards (always ahead in x, across in y).
    centre3 = (p2[0] + reverse_radius * math.sin(theta),
               p2[1] - side * reverse_radius * math.cos(theta))
    start3 = math.atan2(p2[1] - centre3[1], p2[0] - centre3[0])
    reverse = Arc(centre3, reverse_radius, start3, -side * theta)
    p3 = reverse.p1
    if p3[0] > deck_length + 1e-9:
        raise ValueError(
            f"--turnouts: the leg from {spec.toe:g} mm runs past the end of the "
            f"{deck_length:.0f} mm deck before it is back parallel at {spec.end:g} "
            f"(it needs {p3[0] - spec.toe:.0f} mm from the toe).")
    tail = Line(p3, (deck_length, p3[1]))
    heel = (x0 + length, y0 + side * heel_rise)
    segments = (first, straight, reverse) + ((tail,) if tail.length > 1e-9 else ())
    return TurnoutLeg(segments, heel, p3[0])
