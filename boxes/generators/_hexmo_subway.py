"""A subway: a level lower track running under the deck (``--subway``).

The helix's lower level leaves M6 under the entry rectangle and carries on
under the deck of whatever module comes next.  Such a track needs a bed and
supports (a riser at one height) and an opening in every wall it crosses.  One
``--subway`` setting gives all of that, the same way on every Hexmo module:

* **HexmoHexagon** (full or trapezoid): ``A:oa-B:ob~HEIGHT[/WIDTH]``, a route
  as for ``--track_routes``, the track height (its base, mm above the floor
  panel) and the bed width (default ``--under_track_width``).  It adds the wall
  openings at both ends of the route (``--track_openings``) and a level riser
  along it (``--risers``); every check, the floor slots and the 3D export then
  see them as if they had been given by hand.  The bed runs on through the
  wall openings at both ends to the walls' outer faces.  Several subways may
  be given, comma-separated.
* **HexmoRectangle**: ``HEIGHT[/WIDTH]``.  The track runs down the centre line
  from end wall to end wall, through the under-deck openings (``--under_track``,
  turned on at this height and width), on one level bed from the outer face of
  one end wall to the other's, through the short dividers, whose supports slot
  into the floor strip down the middle lane (the spoke) in each cell.

Either way the bed reaches the module's outside, so the beds of two joined
modules meet at the joint with no gap.  It is _SUBWAY_BED_CLEAR narrower than
the wall openings it passes through, so it slides through them.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from boxes.generators._hexmo_track_routes import edge_position, route_geometry

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_ROUTE_RE = re.compile(
    rf"^\s*([1-6])\s*:\s*({_NUMBER})\s*-\s*([1-6])\s*:\s*({_NUMBER})\s*"
    rf"~\s*({_NUMBER})\s*(?:/\s*({_NUMBER}))?\s*$")
_RECT_RE = re.compile(rf"^\s*({_NUMBER})\s*(?:/\s*({_NUMBER}))?\s*$")
# Any apothem works for finding where a route meets its edges: a route crosses
# each edge at its offset there, whatever the module's size.
_NOMINAL_APOTHEM = 1000.0


@dataclass(frozen=True)
class Subway:
    """One parsed ``--subway`` route (HexmoHexagon).

    @ivar start, start_offset, end, end_offset - The route, as for
          ``--track_routes``.
    @ivar height - Track height (its base) above the floor panel (mm).
    @ivar width  - Bed and opening width (mm).
    """

    start: int
    start_offset: float
    end: int
    end_offset: float
    height: float
    width: float


class HexmoSubwayMixin:
    """``--subway`` for HexmoHexagon and HexmoRectangle."""

    # How much narrower the bed is than the wall openings it passes through
    # (mm, in all: half each side), so it slides through them.
    _SUBWAY_BED_CLEAR = 1.0

    def _subwayBedWidth(self, width):
        """The bed's width for a subway ``width`` wide (its wall openings').

        @param width - The subway's width.
        @returns The bed (and its supports') width.
        """
        return width - self._SUBWAY_BED_CLEAR

    def _addSubwayArgs(self, rectangle=False):
        """Register --subway (help worded for the generator).

        @param rectangle - True for HexmoRectangle (straight, centre line).
        """
        if rectangle:
            text = ("A subway: a level lower track under the deck, down the centre "
                    "line from end wall to end wall.  'HEIGHT[/WIDTH]': the track "
                    "height (its base, mm above the floor strip) and the bed width "
                    "(default --under_track_width), e.g. '23.8'.  One level bed runs "
                    "from the outer face of one end wall to the other's, through the "
                    "short dividers, so it meets the next module's bed at the joint; "
                    "its supports slot into the floor strip (the spoke) in each cell, "
                    "and the end walls and short dividers get the under-deck opening "
                    "(--under_track) at this height and width.  Empty (default): none.")
        else:
            text = ("A subway: a level lower track under the deck.  "
                    "'A:offset-B:offset~HEIGHT[/WIDTH]', a route as for "
                    "--track_routes, the track height (its base, mm above the floor "
                    "panel) and the bed width (default --under_track_width), e.g. "
                    "'4:0-1:0~23.8'.  Adds the wall openings at both ends "
                    "(--track_openings) and a level riser along the route "
                    "(--risers), whose bed runs on through the openings to the walls' "
                    "outer faces, so it meets the next module's bed at the joint.  "
                    "Several may be given, comma-separated.  Empty (default): none.")
        self.argparser.add_argument("--subway", action="store", type=str, default="",
                                    help=text)

    # ------------------------------------------------------------- hexagon

    def _subways(self):
        """Parse --subway (HexmoHexagon form).

        @returns List of :class:`Subway`.
        @throws ValueError - On a malformed entry, or a height or width that is
                             not positive.
        """
        out = []
        for item in filter(str.strip, self.subway.split(",")):
            m = _ROUTE_RE.match(item)
            if not m:
                raise ValueError(
                    f"--subway: {item.strip()!r} is not 'A:offset-B:offset~HEIGHT[/WIDTH]', "
                    "e.g. '4:0-1:0~23.8'.")
            height = float(m[5])
            width = float(m[6]) if m[6] else self.under_track_width
            if height <= 0 or width <= 0:
                raise ValueError(f"--subway: {item.strip()!r} needs a positive height "
                                 "and width.")
            out.append(Subway(int(m[1]), float(m[2]), int(m[3]), float(m[4]), height, width))
        return out

    def _withSubwayOpenings(self, text):
        """--track_openings with each subway's wall openings added.

        Each subway crosses the wall at both ends of its route, at its height
        and width; the opening is a closed hole or a notch by the usual rule.

        @param text - The --track_openings setting.
        @returns The combined setting.
        """
        extra = [f"{edge}:{pos:g}:{s.height:g}:{s.width:g}"
                 for s, edge, pos in self._subwayWallCrossings()]
        return ",".join(filter(None, [text.strip()] + extra))

    def _subwayWallCrossings(self):
        """Where each subway crosses a wall: both ends of its route.

        @returns ``[(subway, edge, position)]``, the position along the edge
                 as for --track_openings.
        """
        out = []
        for s in self._subways():
            g = route_geometry(s.start, s.start_offset, s.end, s.end_offset,
                               _NOMINAL_APOTHEM, 0.0)
            for edge, point in ((s.start, g.segments[0].p0), (s.end, g.segments[-1].p1)):
                pos = round(edge_position(edge, point, _NOMINAL_APOTHEM), 6) + 0.0
                out.append((s, edge, pos))
        return out

    def _withSubwayRisers(self, text):
        """--risers with a level riser along each subway's route added.

        @param text - The --risers setting.
        @returns The combined setting.
        """
        extra = [f"{s.start}:{s.start_offset:g}-{s.end}:{s.end_offset:g}"
                 f"~{s.height:g}..{s.height:g}/{self._subwayBedWidth(s.width):g}"
                 for s in self._subways()]
        return ",".join(filter(None, [text.strip()] + extra))

    # ----------------------------------------------------------- rectangle

    def _rectSubway(self):
        """Parse --subway (HexmoRectangle form).

        @returns ``(height, width)``, or None when off.
        @throws ValueError - On a malformed value, a height or width that is
                             not positive, or an --under_track opening set to a
                             different height or width.
        """
        if not self.subway.strip():
            return None
        m = _RECT_RE.match(self.subway)
        if not m:
            raise ValueError(f"--subway: {self.subway.strip()!r} is not 'HEIGHT[/WIDTH]', "
                             "e.g. '23.8'.")
        height = float(m[1])
        width = float(m[2]) if m[2] else self.under_track_width
        if height <= 0 or width <= 0:
            raise ValueError("--subway needs a positive height and width.")
        if self.under_track and (abs(self.under_track_height - height) > 1e-9
                                 or abs(self.under_track_width - width) > 1e-9):
            raise ValueError(
                f"--subway {self.subway.strip()} runs through the under-deck openings, "
                f"but --under_track is set to {self.under_track_height:g} mm high and "
                f"{self.under_track_width:g} mm wide; leave --under_track off (the "
                "subway turns it on) or make them match.")
        return height, width
