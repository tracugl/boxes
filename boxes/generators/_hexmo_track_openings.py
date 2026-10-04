"""Track openings in HexmoHexagon joint walls (``--track_openings``).

A track that crosses a module joint *below* deck level (the helix ring's
descending spur) has to pass through the two walls that meet there.  Each
opening is given by its edge, its position along the edge, the track height
and a width::

    --track_openings "5:17.5:92.5:26, 3:-35:85.2:26"

* **position**: mm along the edge from its midpoint, anticlockwise seen from
  above (the convention of the per-edge track guides).  Facing the wall from
  outside, anticlockwise is to the right.
* **height**: the track base, in mm above the floor panel.  This is the
  opening's bottom edge.
* **width** (optional): along the wall; default ``--under_track_width``.

The opening must leave room for the track and train above the track height
(``--train_envelope``: 43 mm by default, a 40 mm N train on 3 mm of track):

* If that still fits one material thickness under the deck, the opening is a
  closed hole from the track height up to one thickness under the deck, like
  the under-deck opening of :mod:`_hexmo_under_track`.
* Otherwise it is a **notch**, open at the top of the wall.  The wall's top
  finger joint is split into a piece either side of it.  The deck's matching
  edge is split the same way, with a plain gap over the notch, so the two
  still mate finger for finger.  The deck itself stays closed over the gap;
  the deck slot along the track (BOX-48) opens it.

**Why the deck edge gets plain stubs.**  A finger joint spaces its fingers
evenly about the middle of whatever length it is given.  A wall's top edge is
two thicknesses shorter than the deck edge it slots into (one at each
corner), and an unsplit pair still lines up because both are centred on the
edge midpoint.  Split pieces are not symmetric about it, so each deck piece
is drawn as a plain stub one thickness long at its corner end, plus a joint
exactly as long as the matching wall piece.  Every pair of joint pieces then
covers the same stretch and spaces its fingers identically.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from boxes.edges import BaseEdge

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_OPENING_RE = re.compile(
    rf"^\s*([1-6])\s*:\s*({_NUMBER})\s*:\s*({_NUMBER})\s*(?::\s*({_NUMBER})\s*)?$")


@dataclass(frozen=True)
class TrackOpening:
    """One ``--track_openings`` entry (see module docstring)."""

    edge: int
    position: float
    height: float
    width: float


def parse_track_openings(text, default_width):
    """Parse ``--track_openings``.

    @param text          - The option value; blank means none.
    @param default_width - Width for entries that do not give one.
    @returns List of :class:`TrackOpening`, in the order given.
    @throws ValueError - On a malformed entry or a non-positive width.
    """
    if not text or not text.strip():
        return []
    openings = []
    for item in text.split(","):
        match = _OPENING_RE.match(item)
        if not match:
            raise ValueError(
                f"--track_openings entry {item.strip()!r} is not "
                "'<edge>:<position>:<height>[:<width>]', e.g. '5:17.5:92.5:26'.")
        edge, position, height, width = match.groups()
        width = float(width) if width is not None else default_width
        if width <= 0:
            raise ValueError(
                f"--track_openings entry {item.strip()!r}: width must be positive.")
        openings.append(TrackOpening(int(edge), float(position), float(height), width))
    return openings


class SplitJointEdge(BaseEdge):
    """A joint edge drawn in pieces: joint, plain gap or notch.

    Pieces, in drawing order:

    * ``("joint", length)``: the base edge (e.g. a finger joint) over ``length``;
    * ``("plain", length)``: a straight edge with no joint;
    * ``("notch", width, depth)``: a rectangular notch ``depth`` deep into the
      panel (the panel is on the left of travel) and ``width`` wide.

    The base edge's widths are reported unchanged, so the panel's corners and
    outline are exactly as with the unsplit edge.
    """

    def __init__(self, boxes, base, pieces) -> None:
        super().__init__(boxes, None)
        self.base = base
        self.pieces = list(pieces)

    @property
    def length(self):
        """Total edge length the pieces cover."""
        return sum(piece[1] for piece in self.pieces)

    def __call__(self, length, **kw):
        if abs(length - self.length) > 1e-6:
            raise ValueError(
                f"split joint edge: pieces cover {self.length:.3f} mm but the edge "
                f"is {length:.3f} mm.")
        for piece in self.pieces:
            if piece[0] == "joint":
                self.base(piece[1])
            elif piece[0] == "plain":
                self.edge(piece[1])
            else:
                _, width, depth = piece
                # Turn into the panel, across the notch, and back out.
                self.corner(90)
                self.edge(depth)
                self.corner(-90)
                self.edge(width)
                self.corner(-90)
                self.edge(depth)
                self.corner(90)

    def startWidth(self) -> float:
        return self.base.startWidth()

    def endWidth(self) -> float:
        return self.base.endWidth()

    def margin(self) -> float:
        return self.base.margin()


def wall_and_deck_pieces(wall_length, deck_length, notches):
    """Piece lists for a wall top edge and its deck edge, notched to match.

    Positions are measured along the wall's top edge in its drawing direction,
    from the edge midpoint; the deck edge is drawn the same way round (both
    anticlockwise once the wall is fitted with that direction anticlockwise).

    @param wall_length - Wall top-edge length (the wall body).
    @param deck_length - Deck edge length (wall_length + 2t: it runs on past
                         each wall end by one thickness).
    @param notches     - ``(position, width, depth)`` per notch.
    @returns ``(wall_pieces, deck_pieces)``.
    @throws ValueError - If notches overlap each other or run off the wall.
    """
    stub = (deck_length - wall_length) / 2.0
    spans = sorted((wall_length / 2.0 + pos - w / 2.0, wall_length / 2.0 + pos + w / 2.0, depth)
                   for pos, w, depth in notches)
    wall, deck = [], [("plain", stub)]
    cursor = 0.0
    for lo, hi, depth in spans:
        if lo - cursor < 0:
            raise ValueError("track openings: two notches on one wall overlap, or a "
                             "notch runs off the end of the wall.")
        wall.append(("joint", lo - cursor))
        deck.append(("joint", lo - cursor))
        wall.append(("notch", hi - lo, depth))
        deck.append(("plain", hi - lo))
        cursor = hi
    if wall_length - cursor < 0:
        raise ValueError("track openings: a notch runs off the end of the wall.")
    wall.append(("joint", wall_length - cursor))
    deck.append(("joint", wall_length - cursor))
    deck.append(("plain", stub))
    return wall, deck


def rect_circle_gap(rect, circle):
    """Clear distance between an axis-aligned rectangle and a circle.

    @param rect   - ``(x0, x1, y0, y1)``.
    @param circle - ``(cx, cy, r)``.
    @returns Distance from the circle's edge to the rectangle (negative if
             they overlap).
    """
    x0, x1, y0, y1 = rect
    cx, cy, r = circle
    dx = max(x0 - cx, 0.0, cx - x1)
    dy = max(y0 - cy, 0.0, cy - y1)
    return math.hypot(dx, dy) - r
