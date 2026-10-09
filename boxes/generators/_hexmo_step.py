"""3D (STEP) assembly of a HexmoHexagon module, for checking it in CAD.

The laser output is flat parts; this builds the same module **assembled**, as
simplified solids that a CAD tool (Onshape, FreeCAD, Fusion …) opens as an
assembly.  You can then orbit it, cut sections and measure: whether the
descending spur clears the deck, whether a train fits under it, where risers
stand.

**Simplified parts.** Finger joints, small pin holes, big holes and kites are
left out.  Each part is its outline extruded to ``--thickness`` and placed
where it sits once built:

* ``floor`` / ``deck`` — the hexagon (or half-hexagon) panels; the deck
  reaches over the walls, as cut, and has its ``--deck_slots`` cut through;
* ``wall edge N`` (and the trapezoid's ``long wall``) — the side walls
  between them, with their ``--track_openings`` (holes and notches; a flush
  opening cuts nothing) and the ``--under_track_edges`` opening;
* ``support edge N`` — the support walls (``--support_edges``);
* ``riser bed …`` / ``riser support …`` — each riser's bed, sloping from
  its start height to its end height, and the boards it stands on;
* ``track …`` — each track as a ``RAIL_HEIGHT`` ribbon, ``--track_width``
  wide, on the deck or on its riser bed;
* ``clearance …`` — the train envelope (``--train_envelope`` above the track
  base, ``--under_track_width`` wide), by default only over the tracks on
  risers, the ones that pass under or through the deck (``clearance``:
  ``under``, ``all`` or ``none``).

**Frame.** x/y as the generator's deck frame (hexagon centre, y up, edge 1
at the top); z = 0 is the top of the floor panel, which is how every track
height (``--risers``, ``--track_openings``) is measured.  So the floor panel
spans z = −t…0, the walls 0…l and the deck l…l + t, where l is the wall body.

**Geometry source.** Everything comes from the generator's own plans (the
same calls ``render`` makes), so the 3D model matches what is cut.

Needs the optional ``step`` dependency (``pip install .[step]``, which brings
build123d and the OpenCascade kernel).  Command line::

    python -m boxes.generators._hexmo_step out.step --radius=220 --h=80 …

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass

from boxes.generators._hexmo_deck_slots import trim_segments
from boxes.generators._hexmo_risers import point_at
from boxes.generators._hexmo_track_routes import route_geometry
from boxes.generators._hexmo_track_routes import (
    EDGE_ANGLES, Arc, Line, offset_segments, segments_polyline,
)

# Height of the track ribbon (sleepers + rail).  The train envelope above the
# track base (--train_envelope) includes it.
RAIL_HEIGHT = 3.0
# Straight-line steps per arc when solids follow a curved track.
_ARC_STEPS = 24
# Display colours per kind of part (CSS names), and the clearance's alpha.
_COLOURS = {"panel": "burlywood", "wall": "tan", "support": "peru",
            "riser": "sandybrown", "track": "dimgray", "clearance": "red"}
_CLEARANCE_ALPHA = 0.25


def _bd():
    """Import build123d, with a clear message when the extra isn't installed.

    @returns The build123d module.
    @throws ImportError - When build123d (the ``step`` extra) is missing.
    """
    try:
        import build123d
    except ImportError as err:  # pragma: no cover - depends on the environment
        raise ImportError(
            "3D export needs the optional 'step' dependency: pip install .[step] "
            f"(build123d and the OpenCascade kernel). ({err})") from None
    return build123d


@dataclass
class Part3D:
    """One assembled part.

    @ivar name  - Unique, readable name (shown in the CAD part list).
    @ivar kind  - ``panel``, ``wall``, ``support``, ``riser``, ``track`` or
                  ``clearance``; sets the colour.
    @ivar solid - The build123d solid, in the assembly frame.
    """

    name: str
    kind: str
    solid: object


# ----------------------------------------------------------------- the frame

def _frame(box):
    """The module's inner circumradius, wall body height and thickness.

    Mirrors the start of ``HexmoHexagon.render`` (outside → inside sizes), so
    the plans below are called with exactly the values render uses.

    @param box - A HexmoHexagon with its arguments parsed.
    @returns ``(r, l, t)``: deck circumradius (inner), wall body height
             (floor panel top to deck underside) and material thickness.
    """
    if not hasattr(box, "edges"):
        # adjustSize and the plans need the edge objects, which boxes sets up
        # in open(); nothing is drawn.
        box.open()
    t = box.thickness
    r, h = box.radius, box.h
    if box.outside:
        r -= t / math.cos(math.radians(30))
        if box.top == "none":
            h = box.adjustSize(h, False)
        elif "lid" in box.top and box.top != "angled lid":
            h = box.adjustSize(h) - t
        else:
            h = box.adjustSize(h)
    r, _, _ = box.regularPolygon(6, radius=r)
    return r, h, t


def _unit(degrees):
    a = math.radians(degrees)
    return (math.cos(a), math.sin(a))


# ------------------------------------------------------------ solid builders

def _prism(bd, points, z0, z1):
    """A vertical prism: the plan polygon ``points`` from z0 up to z1."""
    face = bd.Face(bd.Wire.make_polygon([bd.Vector(x, y, z0) for x, y in points], close=True))
    # Extrude straight up whichever way round the outline winds (a face's
    # normal, and so the default direction, follows its winding).
    return bd.extrude(face, z1 - z0, dir=(0, 0, 1))


def _box(bd, centre, size, angle):
    """A box ``size`` = (along, across, height) centred at ``centre`` (x, y, z),
    turned ``angle`` degrees about z (its first axis then points along it)."""
    return bd.Location(centre, (0, 0, angle)) * bd.Box(*size)


# Spacing (mm) of the cross-sections a sloping strip is lofted through.
_LOFT_STEP = 10.0


def _strip(bd, segments, width, top_at, thickness):
    """A strip following a track, ``width`` wide, whose top is ``top_at(s)``.

    Lofted through upright rectangular cross-sections square to the track,
    evenly spaced along it, so it comes out as one smooth solid (top, bottom,
    two sides, two ends) even where it curves and slopes at once.

    @param segments  - The track's centreline pieces (``Line``/``Arc``).
    @param width     - Strip width, centred on the track.
    @param top_at    - Function: distance along the track → top z there.
    @param thickness - Depth below the top.
    @returns A build123d Solid.
    """
    V = bd.Vector
    # Zero-length pieces (a stretch trimmed exactly at a join) have no
    # direction; leave them out.
    segments = [seg for seg in segments if seg.length > 1e-9]
    total = sum(seg.length for seg in segments)
    n = max(2, math.ceil(total / _LOFT_STEP))
    sections = []
    for k in range(n + 1):
        s = total * k / n
        (x, y), (dx, dy) = point_at(segments, s)
        # Half the width either side, square to the direction of travel.
        hx, hy = -dy * width / 2.0, dx * width / 2.0
        top = top_at(s)
        corners = [V(x + hx, y + hy, top), V(x - hx, y - hy, top),
                   V(x - hx, y - hy, top - thickness), V(x + hx, y + hy, top - thickness)]
        sections.append(bd.Face(bd.Wire.make_polygon(corners, close=True)))
    return bd.loft(sections, ruled=False)


def _band_polygon(segments, width):
    """Plan outline of a band ``width`` wide along ``segments`` (a slot)."""
    left = segments_polyline(offset_segments(segments, -width / 2.0), _ARC_STEPS)
    right = segments_polyline(offset_segments(segments, width / 2.0), _ARC_STEPS)
    outline = left + right[::-1]
    # Drop repeated points (a zero-length piece, e.g. where a stretch is
    # trimmed exactly at a join): they would make zero-length edges.
    return [p for i, p in enumerate(outline)
            if i == 0 or math.dist(p, outline[i - 1]) > 1e-6]


# -------------------------------------------------------------------- parts

def _outline(r, t, isTrapezoid):
    """Plan outline of the floor/deck panels (they reach over the walls)."""
    r_out = r + t / math.cos(math.radians(30))
    if isTrapezoid:
        a_out = r_out * math.sqrt(3) / 2
        return [(r_out, 0.0), (r_out / 2, -a_out), (-r_out / 2, -a_out), (-r_out, 0.0)]
    return [(r_out * math.cos(math.radians(60 * k)), r_out * math.sin(math.radians(60 * k)))
            for k in range(6)]


def _panels(bd, box, r, l, t, isTrapezoid, slot_plan):
    outline = _outline(r, t, isTrapezoid)
    floor = _prism(bd, outline, -t, 0.0)
    deck = _prism(bd, outline, l, l + t)
    for slot in slot_plan:
        deck = deck - _prism(bd, _band_polygon(slot["segments"], slot["width"]), l - 1, l + t + 1)
    return [Part3D("floor", "panel", floor), Part3D("deck", "panel", deck)]


def _walls(bd, box, r, l, t, isTrapezoid, opening_plan):
    """Side walls with their openings, between the inner and outer hexagons."""
    apothem = r * math.sqrt(3) / 2
    r_out = r + t / math.cos(math.radians(30))
    edges = sorted(box._TRAPEZOID_EDGES) if isTrapezoid else range(1, 7)
    under_edges = box._underTrackEdges(isTrapezoid)
    under = box._underTrackSpan(l) if under_edges else None
    parts = []
    for edge in edges:
        theta = EDGE_ANGLES[edge]
        u = _unit(theta)
        tan = (-u[1], u[0])                      # anticlockwise along the edge
        mid_in = (apothem * u[0], apothem * u[1])
        mid_out = ((apothem + t) * u[0], (apothem + t) * u[1])
        quad = [(mid_in[0] - tan[0] * r / 2, mid_in[1] - tan[1] * r / 2),
                (mid_in[0] + tan[0] * r / 2, mid_in[1] + tan[1] * r / 2),
                (mid_out[0] + tan[0] * r_out / 2, mid_out[1] + tan[1] * r_out / 2),
                (mid_out[0] - tan[0] * r_out / 2, mid_out[1] - tan[1] * r_out / 2)]
        wall = _prism(bd, quad, 0.0, l)

        def cut(position, width, z0, z1):
            # A cutter through the wall, `width` along it, centred `position`
            # anticlockwise from the edge midpoint, from z0 to z1.
            c = ((apothem + t / 2) * u[0] + position * tan[0],
                 (apothem + t / 2) * u[1] + position * tan[1], (z0 + z1) / 2)
            return _box(bd, c, (width, 4 * t, z1 - z0), theta + 90)

        for opening, notch in opening_plan.get(edge, []):
            top = l if notch else l - t
            if top - opening.height > 1e-9:          # a flush opening cuts nothing
                wall = wall - cut(opening.position, opening.width, opening.height,
                                  top + (1.0 if notch else 0.0))
        if under and edge in under_edges:
            wall = wall - cut(0.0, box.under_track_width, under[0], under[1])
        parts.append(Part3D(f"wall edge {edge}", "wall", wall))
    if isTrapezoid:
        # The long wall lies just inside the centre line, between the slanted
        # walls' inner faces.
        half = r - t / math.sqrt(3)
        parts.append(Part3D("long wall", "wall",
                            _prism(bd, [(-half, -t), (half, -t), (half, 0.0), (-half, 0.0)],
                                   0.0, l)))
    return parts


def _supports(bd, box, r, l, t, isTrapezoid):
    if not box.supports:
        return []
    parts, seen = [], {}
    for support in box._supportLayout(r, isTrapezoid):
        _, _, edge, d, turned = support
        theta = EDGE_ANGLES[edge]
        u = _unit(theta)
        angle = theta + 90 if turned else theta
        solid = _box(bd, (u[0] * d, u[1] * d, l / 2), (box.support_length, t, l), angle)
        seen[edge] = seen.get(edge, 0) + 1
        name = f"support edge {edge}" + ("" if seen[edge] == 1 else f" #{seen[edge]}")
        parts.append(Part3D(name, "support", solid))
    return parts


def _route_name(route, lo, hi):
    start, so, end, eo = route
    return f"{start}:{so:g}-{end}:{eo:g}@{lo:.0f}..{hi:.0f}"


def _risers(bd, riser_plan, t):
    parts = []
    for rp in riser_plan:
        lo, hi = rp["stretch"]
        h0, h1 = rp["heights"]
        tag = _route_name(rp["route"], lo, hi)
        length = (hi - lo) or 1.0
        bed = _strip(bd, rp["segments"], rp["width"],
                     lambda s, h0=h0, h1=h1, length=length: h0 + (h1 - h0) * s / length, t)
        parts.append(Part3D(f"riser bed {tag}", "riser", bed))
        for k, (point, direction, height) in enumerate(rp["stations"], 1):
            angle = math.degrees(math.atan2(direction[1], direction[0])) + 90
            body = height - t
            solid = _box(bd, (point[0], point[1], body / 2), (rp["width"], t, body), angle)
            parts.append(Part3D(f"riser support {tag} #{k}", "riser", solid))
    return parts


@dataclass
class TrackPiece:
    """One stretch of track at a known height.

    A piece that reaches a module edge is run on one thickness further, over
    the wall to the module's outer face (routes end at the wall's inner face),
    so the tracks of joined modules meet.

    @ivar name     - Route and stretch, e.g. ``3:-35-5:-35@0..308``.
    @ivar segments - Centreline pieces, including any run-on over the walls.
    @ivar h0, h1   - Track base height at the stretch's start and end.
    @ivar on_riser - True on a riser bed (under or through the deck).
    @ivar lead     - Run-on at the start (mm), where the stretch proper begins.
    @ivar length   - Length of the stretch proper.
    @ivar ends     - ``[(point, height)]`` for each end at a module edge.
    """

    name: str
    segments: list
    h0: float
    h1: float
    on_riser: bool
    lead: float
    length: float
    ends: list

    def base(self, s):
        """Track base height ``s`` mm along the (run-on) segments."""
        f = min(max((s - self.lead) / (self.length or 1.0), 0.0), 1.0)
        return self.h0 + (self.h1 - self.h0) * f


def _piece(name, segments, heights, on_riser, at_start, at_end, run_on):
    """A :class:`TrackPiece`, run on by ``run_on`` at each end on a module edge."""
    segments = [seg for seg in segments if seg.length > 1e-9]
    length = sum(seg.length for seg in segments)
    lead = run_on if at_start else 0.0
    tail = run_on if at_end else 0.0
    if lead or tail:
        segments = trim_segments(segments, -lead, length + tail)
    ends = []
    if at_start:
        ends.append((segments[0].p0, heights[0]))
    if at_end:
        ends.append((segments[-1].p1, heights[1]))
    return TrackPiece(name, segments, heights[0], heights[1], on_riser, lead, length, ends)


def _track_pieces(box, r, l, t, isTrapezoid, riser_plan):
    """Every track as a :class:`TrackPiece`: on the deck, or on a riser bed.

    A deck route's stretches carried by a riser are left to the riser, so
    each bit of track appears once, at its real height.
    """
    pieces = []
    deck_top = l + t
    apothem = r * math.sqrt(3) / 2
    for g in box._trackRouteGeometries(r, isTrapezoid):
        route = (g.start, g.start_offset, g.end, g.end_offset)
        total = sum(s.length for s in g.segments)
        taken = sorted(rp["stretch"] for rp in riser_plan
                       if all(abs(a - b) < 1e-6 for a, b in zip(rp["route"], route)))
        cursor = 0.0
        for lo, hi in taken + [(total, total)]:
            if lo - cursor > 0.5:
                pieces.append(_piece(_route_name(route, cursor, lo),
                                     trim_segments(list(g.segments), cursor, lo),
                                     (deck_top, deck_top), False,
                                     cursor < 1e-6, lo > total - 1e-6, t))
            cursor = max(cursor, hi)
    for rp in riser_plan:
        lo, hi = rp["stretch"]
        total = sum(s.length for s in route_geometry(*rp["route"], apothem,
                                                     box.track_lead_in).segments)
        pieces.append(_piece(_route_name(rp["route"], lo, hi), rp["segments"], rp["heights"],
                             True, lo < 1e-6, hi > total - 1e-6, t))
    return pieces


# Which tracks get a train-clearance box: only those on risers (the ones that
# run under or through the deck), every track, or none.
CLEARANCE_MODES = ("under", "all", "none")


def _tracks(bd, box, pieces, clearance):
    parts = []
    for piece in pieces:
        parts.append(Part3D(f"track {piece.name}", "track",
                            _strip(bd, piece.segments, box.track_width,
                                   lambda s, p=piece: p.base(s) + RAIL_HEIGHT, RAIL_HEIGHT)))
        if clearance == "all" or (clearance == "under" and piece.on_riser):
            envelope = box.train_envelope
            parts.append(Part3D(f"clearance {piece.name}", "clearance",
                                _strip(bd, piece.segments, box.under_track_width,
                                       lambda s, p=piece: p.base(s) + envelope,
                                       envelope - RAIL_HEIGHT)))
    return parts


def _check_clearance(clearance):
    if clearance not in CLEARANCE_MODES:
        raise ValueError(f"clearance must be one of {', '.join(CLEARANCE_MODES)} "
                         f"(got {clearance!r}).")


def _hexmo_plans(box):
    """The plans render() makes, in the same order: ``(r, l, t, openings, slots, risers)``."""
    r, l, t = _frame(box)
    isTrapezoid = box.trapezoid
    opening_plan = box._trackOpeningPlan(isTrapezoid, l)
    notches = {}
    for edge, entries in opening_plan.items():
        cut = [(o.position, o.width, l - o.height) for o, notch in entries if notch]
        if cut:
            notches[edge] = cut
    slot_plan = box._deckSlotPlan(r, isTrapezoid, notches)
    riser_plan = box._riserPlan(r, isTrapezoid, l, notches)
    return r, l, t, opening_plan, slot_plan, riser_plan


def hexmo_pieces(box):
    """A HexmoHexagon's tracks as :class:`TrackPiece` (no solids built)."""
    r, l, t, _, _, riser_plan = _hexmo_plans(box)
    return _track_pieces(box, r, l, t, box.trapezoid, riser_plan)


def hexmo_parts(box, clearance="under"):
    """Build the assembled parts of a HexmoHexagon module.

    @param box       - A HexmoHexagon with its arguments parsed (no render needed).
    @param clearance - Train-clearance boxes: ``under`` (default) over the
                       tracks on risers only, ``all`` over every track, or
                       ``none``.
    @returns List of :class:`Part3D`.
    @throws ValueError - From the generator's own checks (the same settings
                         that refuse to render refuse to export), an unknown
                         ``clearance``, or ``--lower_ground`` (whose cut-back
                         deck, lower plate and stepped walls only the exact
                         parts model).
    @throws ImportError - When the optional build123d dependency is missing.
    """
    _check_clearance(clearance)
    if getattr(box, "lower_ground", 0) > 0:
        raise ValueError("The simple 3D parts don't model --lower_ground; use the "
                         "exact ones (--step_detail exact, the default).")
    bd = _bd()
    r, l, t, opening_plan, slot_plan, riser_plan = _hexmo_plans(box)
    isTrapezoid = box.trapezoid
    return (_panels(bd, box, r, l, t, isTrapezoid, slot_plan)
            + _walls(bd, box, r, l, t, isTrapezoid, opening_plan)
            + _supports(bd, box, r, l, t, isTrapezoid)
            + _risers(bd, riser_plan, t)
            + _tracks(bd, box, _track_pieces(box, r, l, t, isTrapezoid, riser_plan),
                      clearance))


# ---------------------------------------------------------------- rectangle

def _shift(seg, dx, dy):
    """A ``Line``/``Arc`` moved by (dx, dy)."""
    if isinstance(seg, Line):
        return Line((seg.p0[0] + dx, seg.p0[1] + dy), (seg.p1[0] + dx, seg.p1[1] + dy))
    return Arc((seg.centre[0] + dx, seg.centre[1] + dy), seg.radius, seg.start_angle, seg.sweep)


def _rect_frame(box):
    """``(lay, ground, deck_underside)`` for a HexmoRectangle.

    The rectangle has no floor panel: its walls stand on the ground, one
    thickness below the hexagons' floor-panel top (z = 0), and reach up to the
    deck, whose top is level with the hexagons' at the same ``--h``.
    """
    if not hasattr(box, "edges"):
        box.open()
    lay = box._rectLayout()
    ground = -lay.t
    return lay, ground, ground + lay.h


def rect_pieces(box):
    """A HexmoRectangle's deck tracks as :class:`TrackPiece`, centred frame.

    The frame has x along the long axis, from −(H/2 + t) to +(H/2 + t), and
    y across it, both centred; the turnouts face +x.
    """
    lay, _, underside = _rect_frame(box)
    t, H, inner = lay.t, lay.H, lay.W - 2 * lay.t
    deck_top = underside + t
    pieces = []
    if box.track_lines:
        for off in box._trackOffsets():
            pieces.append(_piece(f"straight {off:g}", [Line((-H / 2, off), (H / 2, off))],
                                 (deck_top, deck_top), False, True, True, t))
        for k, leg in enumerate(box._turnoutLegs(H, inner), 1):
            moved = [_shift(seg, -H / 2, -inner / 2) for seg in leg]
            pieces.append(_piece(f"turnout {k} leg", moved, (deck_top, deck_top), False,
                                 False, True, t))
    return pieces


def rect_parts(box, clearance="under"):
    """Build the assembled parts of a HexmoRectangle (centred frame, see rect_pieces).

    @param box       - A HexmoRectangle with its arguments parsed.
    @param clearance - As for :func:`hexmo_parts` (a rectangle has no risers,
                       so ``under`` gives none).
    @returns List of :class:`Part3D`.
    """
    _check_clearance(clearance)
    bd = _bd()
    lay, ground, underside = _rect_frame(box)
    t, W, H = lay.t, lay.W, lay.H
    inner = W - 2 * t
    x_out = H / 2 + t

    def slab(x0, x1, y0, y1, z0, z1):
        return _prism(bd, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1)

    under = None
    if box.under_track:
        under = box._underTrackSpan(box._hexWallHeight())

    def with_passage(solid, x):
        # The lower level's opening through an end wall or short divider.
        if under is None:
            return solid
        return solid - _box(bd, (x, 0.0, (under[0] + under[1]) / 2),
                            (4 * t, box.under_track_width, under[1] - under[0]), 0)

    parts = [Part3D("deck", "panel", slab(-x_out, x_out, -W / 2, W / 2, underside, underside + t))]
    for k, sign in enumerate((-1, 1), 1):
        y = sign * (W / 2 - t / 2)
        parts.append(Part3D(f"long wall {k}", "wall",
                            slab(-x_out, x_out, y - t / 2, y + t / 2, ground, underside)))
    for k, sign in enumerate((-1, 1), 1):
        x = sign * (H / 2 + t / 2)
        parts.append(Part3D(f"end wall {k}", "wall", with_passage(
            slab(x - t / 2, x + t / 2, -inner / 2, inner / 2, ground, underside), x)))
    for k, pos in enumerate(lay.lane_pos, 1):
        y = -inner / 2 + pos
        parts.append(Part3D(f"long support {k}", "support",
                            slab(-H / 2, H / 2, y - t / 2, y + t / 2, ground, underside)))
    bottom = ground + (t if lay.sw > 0 else 0.0)      # dividers sit on the spoke
    for k, pos in enumerate(lay.div_pos, 1):
        x = -H / 2 + pos
        parts.append(Part3D(f"divider {k}", "support", with_passage(
            slab(x - t / 2, x + t / 2, -inner / 2, inner / 2, bottom, underside), x)))
    if lay.sw > 0:
        parts.append(Part3D("spoke", "panel",
                            slab(-H / 2, H / 2, -lay.sw / 2, lay.sw / 2, ground, ground + t)))
    return parts + _tracks(bd, box, rect_pieces(box), clearance)


# --------------------------------------------------------------------- ring

def _ring_layout(ring):
    """Each module of a helix ring with its placement.

    Every module sits two outer apothems from the ring centre, edge 4 facing
    it, turned so M(n)'s edge 5 meets M(n+1)'s edge 3: M6 at the top (90°),
    M1 at 150°, … M5 at 30°.  The entry rectangle runs on from M6 edge 1,
    turnout end first.

    @param ring - Key of :data:`_hexmo_helix_ring.RINGS`, e.g. ``"N"``.
    @returns ``[(name, box, kind, angle°, (dx, dy))]``: place a part by
             turning it ``angle`` about z, then moving it by (dx, dy).
    @throws KeyError - For an unknown ring.
    """
    from boxes.generators._hexmo_helix_ring import RINGS
    from boxes.generators.hexmohexagon import HexmoHexagon
    from boxes.generators.hexmorectangle import HexmoRectangle
    modules, entry_args = RINGS[ring]
    layout = []
    m6_centre = a_out = None
    for k, name in enumerate(["M6", "M1", "M2", "M3", "M4", "M5"]):
        box = HexmoHexagon()
        box.parseArgs(modules[name])
        r, _, t = _frame(box)
        a_out = (r + t / math.cos(math.radians(30))) * math.sqrt(3) / 2
        alpha = 90 + 60 * k
        centre = (2 * a_out * math.cos(math.radians(alpha)),
                  2 * a_out * math.sin(math.radians(alpha)))
        if name == "M6":
            m6_centre = centre
        layout.append((name, box, "hexmo", alpha - 90, centre))
    entry = HexmoRectangle()
    entry.parseArgs(entry_args)
    lay, _, _ = _rect_frame(entry)
    reach = a_out + lay.H / 2 + lay.t
    layout.append(("entry", entry, "rect", -90, (m6_centre[0], m6_centre[1] + reach)))
    return layout


def _place_point(point, angle, offset):
    a = math.radians(angle)
    x, y = point
    return (x * math.cos(a) - y * math.sin(a) + offset[0],
            x * math.sin(a) + y * math.cos(a) + offset[1])


DETAILS = ("exact", "simple")


def module_parts(box, kind, clearance="under", detail="exact"):
    """A module's parts: ``kind`` is ``hexmo`` or ``rect``, ``detail`` ``exact``/``simple``."""
    if detail not in DETAILS:
        raise ValueError(f"detail must be one of {', '.join(DETAILS)} (got {detail!r}).")
    if detail == "exact":
        return (exact_hexmo_parts if kind == "hexmo" else exact_rect_parts)(box, clearance)
    return (hexmo_parts if kind == "hexmo" else rect_parts)(box, clearance)


def ring_parts(ring="N", clearance="under", detail="exact"):
    """Every part of a helix ring, placed, each name prefixed by its module.

    @param ring      - Key of :data:`_hexmo_helix_ring.RINGS`.
    @param clearance - As for :func:`hexmo_parts`.
    @param detail    - ``exact`` (real cut outlines) or ``simple`` (slabs).
    @returns List of :class:`Part3D`.
    """
    bd = _bd()
    parts = []
    for name, box, kind, angle, offset in _ring_layout(ring):
        built = module_parts(box, kind, clearance, detail)
        where = bd.Location((offset[0], offset[1], 0), (0, 0, angle))
        parts += [Part3D(f"{name} {p.name}", p.kind, where * p.solid) for p in built]
    return parts


def ring_track_ends(ring="N"):
    """Where every track meets a module edge, placed: ``[(module, (x, y), height)]``.

    For checking that joined modules' tracks meet (same place, same height).
    """
    ends = []
    for name, box, kind, angle, offset in _ring_layout(ring):
        pieces = hexmo_pieces(box) if kind == "hexmo" else rect_pieces(box)
        for piece in pieces:
            for point, height in piece.ends:
                ends.append((name, _place_point(point, angle, offset), height))
    return ends


# ------------------------------------------------------------- exact parts
#
# The exact parts are the real cut outlines.  The generator renders as usual
# (at burn 0, so every part is its nominal size) while its drawing code records
# each assembled part's frame (HexmoStepFormatMixin._stepFrame): the drawing
# transform at the part's local origin and where that origin sits in 3D.  Each
# part's cut paths are then taken off the sheet, mapped back to the part's own
# x/y, closed into loops, sorted into outline and holes, extruded and placed.

# Points per curve when a loop is approximated by a polygon (for nesting
# tests and the bed's slot cut-outs; the solids keep the true curves).
_CURVE_STEPS = 6
# Two path ends closer than this (mm) join.
_JOIN = 1e-3
# An outline whose own ends are this close (mm) is closed with a straight
# line: a panel drawn a fraction of a millimetre short of closing (as the
# trapezoid was with FingerJoint_extra_length before BOX-65) would otherwise
# be lost and its holes taken for outlines.
_BRIDGE = 1.0


def _is_cut(rgb):
    from boxes.Color import Color
    return rgb is not None and any(
        all(abs(a - b) < 1e-6 for a, b in zip(rgb, c)) for c in (Color.OUTER_CUT, Color.INNER_CUT))


def _cut_chains(part):
    """A drawn Part's cut paths as chains of segments, in sheet coordinates.

    A segment is ``("L", p0, p1)`` or ``("C", p0, c1, c2, p1)`` (a cubic
    Bézier: holes and rounded corners).  Zero-length segments (under _JOIN)
    are dropped, and the next segment starts where the last kept one ended,
    so a chain stays continuous: moving on to a dropped segment's end would
    leave a hairline gap the 3D faces cannot close.
    """
    chains = []
    for path in part.pathes:
        if not _is_cut(path.params.get("rgb")):
            continue
        chain, cur = [], None
        for cmd in path.path:
            c = cmd[0]
            if c == "M":
                if chain:
                    chains.append(chain)
                chain, cur = [], (cmd[1], cmd[2])
            elif c == "L" and cur is not None:
                end = (cmd[1], cmd[2])
                if math.dist(cur, end) > _JOIN:
                    chain.append(("L", cur, end))
                    cur = end
            elif c == "C" and cur is not None:
                # Destination first, then the two control points.
                end, c1, c2 = (cmd[1], cmd[2]), (cmd[3], cmd[4]), (cmd[5], cmd[6])
                if max(math.dist(cur, q) for q in (end, c1, c2)) > _JOIN:
                    chain.append(("C", cur, c1, c2, end))
                    cur = end
        if chain:
            chains.append(chain)
    return chains


def _reverse(chain):
    return [("L", s[2], s[1]) if s[0] == "L" else ("C", s[4], s[3], s[2], s[1])
            for s in reversed(chain)]


def _start(chain):
    return chain[0][1]


def _end(chain):
    return chain[-1][-1]


def _merge_lines(loop):
    """Merge consecutive collinear straight segments (fewer faces)."""
    out = []
    for seg in loop:
        if out and seg[0] == "L" and out[-1][0] == "L":
            a, b, c = out[-1][1], out[-1][2], seg[2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(cross) < 1e-9 * max(1.0, math.dist(a, c)) and \
                    (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) > 0:
                out[-1] = ("L", a, c)
                continue
        out.append(seg)
    return out


def _close_loops(chains):
    """Join chains end to end into closed loops (open leftovers are dropped)."""
    loops, pending = [], []
    for ch in chains:
        (loops if math.dist(_start(ch), _end(ch)) < _JOIN else pending).append(ch)
    while pending:
        cur = pending.pop(0)
        grown = True
        while grown and math.dist(_start(cur), _end(cur)) >= _JOIN:
            grown = False
            for i, other in enumerate(pending):
                if math.dist(_end(cur), _start(other)) < _JOIN:
                    cur = cur + other
                elif math.dist(_end(cur), _end(other)) < _JOIN:
                    cur = cur + _reverse(other)
                elif math.dist(_start(cur), _end(other)) < _JOIN:
                    cur = other + cur
                elif math.dist(_start(cur), _start(other)) < _JOIN:
                    cur = _reverse(other) + cur
                else:
                    continue
                pending.pop(i)
                grown = True
                break
        gap = math.dist(_start(cur), _end(cur))
        if gap < _JOIN:
            loops.append(cur)
        elif gap < _BRIDGE:
            loops.append(cur + [("L", _end(cur), _start(cur))])
    return [_merge_lines(loop) for loop in loops if abs(_area(_polygon(loop))) > 1e-6]


def _polygon(loop):
    """A loop's outline as a polygon (curves sampled)."""
    pts = []
    for seg in loop:
        if seg[0] == "L":
            pts.append(seg[1])
        else:
            p0, c1, c2, p1 = seg[1:]
            for k in range(_CURVE_STEPS):
                u = k / _CURVE_STEPS
                a, b, c, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
                pts.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p1[0],
                            a * p0[1] + b * c1[1] + c * c2[1] + d * p1[1]))
    return pts


def _area(pts):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2


def _inside(point, poly):
    """Even-odd point-in-polygon test."""
    x, y = point
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _depths(polys):
    """How many other loops contain each loop (0 = an outline, 1 = a hole …)."""
    areas = [abs(_area(p)) for p in polys]
    depths = []
    for i, poly in enumerate(polys):
        probes = poly[: min(5, len(poly))]
        depth = 0
        for j, other in enumerate(polys):
            if i != j and areas[j] > areas[i] and \
                    sum(_inside(p, other) for p in probes) * 2 > len(probes):
                depth += 1
        depths.append(depth)
    return depths


def _normal(frame):
    ex, ey = frame.ex, frame.ey
    return (ex[1] * ey[2] - ex[2] * ey[1], ex[2] * ey[0] - ex[0] * ey[2],
            ex[0] * ey[1] - ex[1] * ey[0])


def _world_point(frame, p, z=0.0):
    (ox, oy, oz), ex, ey, n = frame.origin, frame.ex, frame.ey, _normal(frame)
    x, y = p
    return (ox + x * ex[0] + y * ey[0] + z * n[0],
            oy + x * ex[1] + y * ey[1] + z * n[1],
            oz + x * ex[2] + y * ey[2] + z * n[2])


def _frame_loops(frame):
    """A recorded part's cut loops in its own frame (true curves kept)."""
    inv = ~frame.matrix

    def local(seg):
        return (seg[0],) + tuple(inv * p for p in seg[1:])

    return [[local(seg) for seg in loop] for loop in _close_loops(_cut_chains(frame.part))]


def _wire(bd, frame, loop, z):
    """A loop as a 3D wire (straight and Bézier edges) on the frame's plane at z."""
    edges = []
    for seg in loop:
        pts = [bd.Vector(*_world_point(frame, p, z)) for p in seg[1:]]
        edges.append(bd.Edge.make_line(*pts) if seg[0] == "L" else bd.Edge.make_bezier(*pts))
    return bd.Wire(edges)


def _frame_solid(bd, frame, loops, polys, depths):
    """Extrude a part's outline (holes cut) and place it.

    Loops nested two deep are the holes of a piece that drops out of a hole
    (a deck slot's cut-out, when it is a riser bed); the bed carries them.
    """
    z0, z1 = frame.depth
    solids = []
    for loop, poly, depth in zip(loops, polys, depths):
        if depth != 0:
            continue
        holes = [h for h, hp, d in zip(loops, polys, depths) if d == 1 and _inside(hp[0], poly)]
        face = bd.Face(_wire(bd, frame, loop, z0), [_wire(bd, frame, h, z0) for h in holes])
        solids.append(bd.extrude(face, z1 - z0, dir=_normal(frame)))
    if not solids:
        return None
    solid = solids[0]
    for extra in solids[1:]:
        solid = solid + extra
    return solid


def _render_frames(box):
    """Render ``box`` at burn 0, recording its assembled parts' frames."""
    box.burn = 0.0
    box._step_frames = []
    try:
        box.open()
        box.render()
        return list(box._step_frames)
    finally:
        box._step_frames = None


def _exact_from_frames(bd, frames):
    """Exact solids for the recorded parts, and the riser beds' slot outlines.

    @returns ``(parts, bed_holes)``: :class:`Part3D` list, and polygons (plan,
             the deck frame) of every slot cut in a riser bed.
    """
    parts, bed_holes = [], []
    for frame in frames:
        loops = _frame_loops(frame)
        polys = [_polygon(loop) for loop in loops]
        depths = _depths(polys)

        def plan(poly):
            return [_world_point(frame, p)[:2] for p in poly]

        if frame.kind == "bedholes":
            # A separate bed: its holes are its support slots.
            bed_holes += [plan(p) for p, d in zip(polys, depths) if d == 1]
            continue
        if frame.name == "deck":
            # A slot's cut-out that is a riser bed carries these slots.
            bed_holes += [plan(p) for p, d in zip(polys, depths) if d == 2]
        solid = _frame_solid(bd, frame, loops, polys, depths)
        if solid is not None:
            parts.append(Part3D(frame.name, frame.kind, solid))
    return parts, bed_holes


def _exact_beds(bd, riser_plan, t, bed_holes):
    """Each riser bed, sloping as set, with its support slots cut through."""
    parts = []
    for rp in riser_plan:
        lo, hi = rp["stretch"]
        h0, h1 = rp["heights"]
        length = (hi - lo) or 1.0
        bed = _strip(bd, rp["segments"], rp["width"],
                     lambda s, h0=h0, h1=h1, length=length: h0 + (h1 - h0) * s / length, t)
        band = _band_polygon(rp["segments"], rp["width"])
        for hole in bed_holes:
            cx = sum(x for x, _ in hole) / len(hole)
            cy = sum(y for _, y in hole) / len(hole)
            if _inside((cx, cy), band):
                bed = bed - _prism(bd, hole, -10.0, 1000.0)
        parts.append(Part3D(f"riser bed {_route_name(rp['route'], lo, hi)}", "riser", bed))
    return parts


def exact_hexmo_parts(box, clearance="under", frames=None):
    """The exact parts of a HexmoHexagon module, assembled.

    @param box       - A HexmoHexagon with its arguments parsed.  Unless
                       ``frames`` is given it is rendered here (at burn 0), so
                       pass a fresh one.
    @param clearance - As for :func:`hexmo_parts`.
    @param frames    - Part frames from a render already done with capture on
                       (the ``--format step`` path).
    @returns List of :class:`Part3D`.
    """
    _check_clearance(clearance)
    bd = _bd()
    if frames is None:
        frames = _render_frames(box)
    parts, bed_holes = _exact_from_frames(bd, frames)
    r, l, t, _, _, riser_plan = _hexmo_plans(box)
    return (parts + _exact_beds(bd, riser_plan, t, bed_holes)
            + _tracks(bd, box, _track_pieces(box, r, l, t, box.trapezoid, riser_plan),
                      clearance))


def exact_rect_parts(box, clearance="under", frames=None):
    """The exact parts of a HexmoRectangle, assembled (frame as rect_pieces)."""
    _check_clearance(clearance)
    bd = _bd()
    if frames is None:
        frames = _render_frames(box)
    parts, _ = _exact_from_frames(bd, frames)
    return parts + _tracks(bd, box, rect_pieces(box), clearance)


# Where the line drawing is seen from (front right, above) and what it looks at.
_VIEW_FROM = (900.0, -1200.0, 900.0)
_VIEW_LINE = 0.15


# Parts that aren't cut (the track ribbons and clearance boxes are guides,
# not laser parts), so the line drawing leaves them out.
_NOT_CUT = ("track", "clearance")


def _drawn_parts(parts, deck=False):
    """The parts a line drawing shows: the cut parts only (the cut sheet's red
    lines), and the decks only when ``deck`` is set."""
    return [p for p in parts if p.kind not in _NOT_CUT
            and (deck or not (p.name == "deck" or p.name.endswith(" deck")))]


def line_drawing(parts, out, deck=False):
    """Draw the assembled parts in 3D as an SVG line drawing (hidden lines removed).

    Seen from the front right, above, at 1:1 in mm.  Only the cut parts are
    drawn; the track ribbons and clearance boxes are left out.

    @param parts - :class:`Part3D` list (one module, or a whole ring).
    @param out   - File path or binary file object to write the SVG to.
    @param deck  - Draw the decks too; off shows inside the modules.
    """
    bd = _bd()
    shown = [p.solid for p in _drawn_parts(parts, deck)]
    compound = bd.Compound(shown)
    centre = compound.bounding_box().center()
    eye = (centre.X + _VIEW_FROM[0], centre.Y + _VIEW_FROM[1], centre.Z + _VIEW_FROM[2])
    visible, _ = compound.project_to_viewport(eye, viewport_up=(0, 0, 1),
                                              look_at=(centre.X, centre.Y, centre.Z))
    svg = bd.ExportSVG(scale=1.0, margin=10)
    svg.add_layer("visible", line_weight=_VIEW_LINE)
    svg.add_shape(visible, layer="visible")
    svg.write(out)


def assembly(parts, label="hexmo module"):
    """One build123d Compound of the parts, each named and coloured."""
    bd = _bd()
    children = []
    for part in parts:
        solid = part.solid
        solid.label = part.name
        alpha = _CLEARANCE_ALPHA if part.kind == "clearance" else 1.0
        solid.color = bd.Color(_COLOURS[part.kind], alpha)
        children.append(solid)
    return bd.Compound(children=children, label=label)


def export_step_file(box, path, clearance="under", detail="exact"):
    """Write a HexmoHexagon module's 3D assembly to a STEP file.

    @param box       - A HexmoHexagon with its arguments parsed (and not yet
                       rendered: the exact parts render it).
    @param path      - Output file path.
    @param clearance - As for :func:`hexmo_parts`.
    @param detail    - ``exact`` (real cut outlines) or ``simple`` (slabs).
    @throws ValueError, ImportError - As for :func:`hexmo_parts`.
    """
    bd = _bd()
    bd.export_step(assembly(module_parts(box, "hexmo", clearance, detail)), str(path))


def export_ring_step_file(path, ring="N", clearance="under", detail="exact"):
    """Write a whole helix ring (six modules and the entry) to one STEP file."""
    bd = _bd()
    bd.export_step(assembly(ring_parts(ring, clearance, detail), label=f"helix ring {ring}"),
                   str(path))


def main(argv=None):
    """Command line.

    * ``OUT.step [--clearance=MODE] [--detail=exact|simple] [generator args…]``
      — one HexmoHexagon;
    * ``OUT.step --ring=N [--clearance=MODE] [--detail=…]`` — the whole helix ring
      (``--ring=N-ground`` with the scenery's upper and lower ground);
    * ``OUT.svg …`` — the same, drawn as a 3D line drawing; ``--deck`` adds
      the decks.

    ``--clearance`` (``under``, ``all`` or ``none``), ``--detail`` (``exact``,
    the default, or ``simple``) and ``--ring`` are the exporter's own; every
    other option goes to the generator.
    """
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[0])
        print("usage: python -m boxes.generators._hexmo_step OUT.step|OUT.svg "
              "[--ring=N|N-ground|N250|N250-ground|HO|HO-ground] [--clearance=under|all|none] [--detail=exact|simple] "
              "[--deck] [--option=value …]")
        return 2
    clearance, ring, detail, deck = "under", None, "exact", False
    rest = []
    for arg in argv[1:]:
        if arg == "--deck":
            deck = True
        elif arg.startswith("--clearance="):
            clearance = arg.split("=", 1)[1]
        elif arg.startswith("--detail="):
            detail = arg.split("=", 1)[1]
        elif arg.startswith("--ring="):
            ring = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    if argv[0].lower().endswith(".svg"):
        if ring:
            parts = ring_parts(ring, "none", detail)
        else:
            from boxes.generators.hexmohexagon import HexmoHexagon
            box = HexmoHexagon()
            box.parseArgs(rest)
            parts = module_parts(box, "hexmo", "none", detail)
        line_drawing(parts, argv[0], deck=deck)
    elif ring:
        export_ring_step_file(argv[0], ring, clearance, detail)
    else:
        from boxes.generators.hexmohexagon import HexmoHexagon
        box = HexmoHexagon()
        box.parseArgs(rest)
        export_step_file(box, argv[0], clearance, detail)
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
