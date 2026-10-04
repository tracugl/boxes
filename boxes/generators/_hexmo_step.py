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
* ``clearance …`` — the train envelope over each track: ``--train_envelope``
  above the track base, ``--under_track_width`` wide.

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
from boxes.generators._hexmo_track_routes import (
    EDGE_ANGLES, offset_segments, segments_polyline,
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


def _strip(bd, left, right, tops, thickness):
    """A strip following a track, whose top follows ``tops`` (one z per point).

    Built face by face (a closed shell of triangles and vertical quads), so it
    can slope along a curving track.

    @param left, right - Matching plan points down each side of the strip.
    @param tops        - Top z at each pair of points.
    @param thickness   - Depth below the top.
    @returns A build123d Solid.
    """
    V = bd.Vector
    top = [(V(l[0], l[1], z), V(r[0], r[1], z)) for l, r, z in zip(left, right, tops)]
    bot = [(V(l[0], l[1], z - thickness), V(r[0], r[1], z - thickness))
           for l, r, z in zip(left, right, tops)]

    def face(*pts):
        return bd.Face(bd.Wire.make_polygon(list(pts), close=True))

    faces = []
    for (l0, r0), (l1, r1), (bl0, br0), (bl1, br1) in zip(top, top[1:], bot, bot[1:]):
        # Top and bottom as two triangles each (always planar), sides as
        # vertical quads.
        faces += [face(l0, r0, r1), face(l0, r1, l1), face(bl0, br1, br0),
                  face(bl0, bl1, br1), face(l0, l1, bl1, bl0), face(r0, br0, br1, r1)]
    (l, r), (bl, br) = top[0], bot[0]
    faces.append(face(l, bl, br, r))
    (l, r), (bl, br) = top[-1], bot[-1]
    faces.append(face(l, r, br, bl))
    return bd.Solid(bd.Shell(faces))


def _sides(segments, width):
    """Matching point lists down each side of a track ``width`` wide, and the
    distance along the centreline at each pair."""
    left = segments_polyline(offset_segments(segments, -width / 2.0), _ARC_STEPS)
    right = segments_polyline(offset_segments(segments, width / 2.0), _ARC_STEPS)
    centre = segments_polyline(segments, _ARC_STEPS)
    # Drop repeated points (a zero-length piece, e.g. where a stretch is
    # trimmed exactly at a join): they would make zero-area faces.
    keep = [0] + [i for i in range(1, len(centre))
                  if math.dist(centre[i], centre[i - 1]) > 1e-6]
    left, right, centre = ([pts[i] for i in keep] for pts in (left, right, centre))
    along = [0.0]
    for a, b in zip(centre, centre[1:]):
        along.append(along[-1] + math.dist(a, b))
    return left, right, along


def _band_polygon(segments, width):
    """Plan outline of a band ``width`` wide along ``segments`` (a slot)."""
    left, right, _ = _sides(segments, width)
    return left + right[::-1]


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
        left, right, along = _sides(rp["segments"], rp["width"])
        length = along[-1] or 1.0
        tops = [h0 + (h1 - h0) * s / length for s in along]
        parts.append(Part3D(f"riser bed {tag}", "riser", _strip(bd, left, right, tops, t)))
        for k, (point, direction, height) in enumerate(rp["stations"], 1):
            angle = math.degrees(math.atan2(direction[1], direction[0])) + 90
            body = height - t
            solid = _box(bd, (point[0], point[1], body / 2), (rp["width"], t, body), angle)
            parts.append(Part3D(f"riser support {tag} #{k}", "riser", solid))
    return parts


def _track_pieces(box, r, l, t, isTrapezoid, riser_plan):
    """Every track as ``(name, segments, heights)``: on the deck or a riser bed.

    A deck route's stretches carried by a riser are left to the riser, so
    each bit of track appears once, at its real height.
    """
    pieces = []
    deck_top = l + t
    for g in box._trackRouteGeometries(r, isTrapezoid):
        route = (g.start, g.start_offset, g.end, g.end_offset)
        total = sum(s.length for s in g.segments)
        taken = sorted(rp["stretch"] for rp in riser_plan
                       if all(abs(a - b) < 1e-6 for a, b in zip(rp["route"], route)))
        cursor = 0.0
        for lo, hi in taken + [(total, total)]:
            if lo - cursor > 0.5:
                pieces.append((_route_name(route, cursor, lo),
                               trim_segments(list(g.segments), cursor, lo),
                               (deck_top, deck_top)))
            cursor = max(cursor, hi)
    for rp in riser_plan:
        pieces.append((_route_name(rp["route"], *rp["stretch"]), rp["segments"], rp["heights"]))
    return pieces


def _tracks(bd, box, pieces):
    parts = []
    for name, segments, (h0, h1) in pieces:
        left, right, along = _sides(segments, box.track_width)
        length = along[-1] or 1.0
        bases = [h0 + (h1 - h0) * s / length for s in along]
        parts.append(Part3D(f"track {name}", "track",
                            _strip(bd, left, right, [z + RAIL_HEIGHT for z in bases],
                                   RAIL_HEIGHT)))
        left, right, _ = _sides(segments, box.under_track_width)
        envelope = box.train_envelope
        parts.append(Part3D(f"clearance {name}", "clearance",
                            _strip(bd, left, right, [z + envelope for z in bases],
                                   envelope - RAIL_HEIGHT)))
    return parts


def hexmo_parts(box):
    """Build the assembled parts of a HexmoHexagon module.

    @param box - A HexmoHexagon with its arguments parsed (no render needed).
    @returns List of :class:`Part3D`.
    @throws ValueError - From the generator's own checks (the same settings
                         that refuse to render refuse to export).
    @throws ImportError - When the optional build123d dependency is missing.
    """
    bd = _bd()
    r, l, t = _frame(box)
    isTrapezoid = box.trapezoid
    # The same plans render() makes, in the same order.
    opening_plan = box._trackOpeningPlan(isTrapezoid, l)
    notches = {}
    for edge, entries in opening_plan.items():
        cut = [(o.position, o.width, l - o.height) for o, notch in entries if notch]
        if cut:
            notches[edge] = cut
    slot_plan = box._deckSlotPlan(r, isTrapezoid, notches)
    riser_plan = box._riserPlan(r, isTrapezoid, l, notches)
    return (_panels(bd, box, r, l, t, isTrapezoid, slot_plan)
            + _walls(bd, box, r, l, t, isTrapezoid, opening_plan)
            + _supports(bd, box, r, l, t, isTrapezoid)
            + _risers(bd, riser_plan, t)
            + _tracks(bd, box, _track_pieces(box, r, l, t, isTrapezoid, riser_plan)))


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


def export_step_file(box, path):
    """Write a HexmoHexagon module's 3D assembly to a STEP file.

    @param box  - A HexmoHexagon with its arguments parsed.
    @param path - Output file path.
    @throws ValueError, ImportError - As for :func:`hexmo_parts`.
    """
    bd = _bd()
    bd.export_step(assembly(hexmo_parts(box)), str(path))


def main(argv=None):
    """``python -m boxes.generators._hexmo_step OUT.step [generator args…]``."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[0])
        print("usage: python -m boxes.generators._hexmo_step OUT.step [--option=value …]")
        return 2
    from boxes.generators.hexmohexagon import HexmoHexagon
    box = HexmoHexagon()
    box.parseArgs(argv[1:])
    export_step_file(box, argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
