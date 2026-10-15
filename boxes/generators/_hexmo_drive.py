"""Export helix-ring layouts for the drivable 3D preview (Hexmo Drive).

The preview (``docs/hexmohexagon/drive/index.html``) shows a layout built from
the real cut parts and runs a train round it.  For each layout this module
writes, into the viewer's folder:

* ``<name>.glb`` — every cut part, placed and coloured, as a binary glTF
  (the web's 3D model format; metres, y up, as glTF requires);
* ``<name>.track.json`` — the track as a graph the train runs on (mm, z up);
* ``layouts.json`` — the list of layouts exported so far, for the viewer's
  picker.

A layout is one helix ring (``N250``, ``N250-ground``, ``HO``, ``HO-ground``:
the keys of :data:`_hexmo_helix_ring.RINGS`), or two of them joined entry to
entry (``<ring>-x2``) for running full loops: down one helix, along the lower
level, up the other and back along the upper level.  A *dogbone*
(:data:`DOGBONES`, e.g. ``N250-dogbone``) is a pair of rings of another kind:
a double-track main line with a single-track loop round each ring.

The track graph
---------------
Each track piece (:func:`_hexmo_step.hexmo_pieces` / :func:`rect_pieces`) is
sampled along its centreline into a polyline of rail-top points.  Pieces meet
end to end at module edges and where a deck track hands over to a riser; a
turnout leg starts part-way along the through road, so the through road is
split wherever another piece's end touches it.  The polylines are then the
graph's *edges* and their clustered end points its *nodes*.

At a node, a train coming in along one edge may leave along any edge whose
direction there is roughly opposite to the incoming one (straight on).  Two
such choices make a turnout, which the viewer resolves by its setting.  Edges
that leave in about the same direction (a turnout's two roads, seen from
their heel ends) never connect, so a train can't reverse through a frog.

The model is the layout *as built*: a deck slot that runs out at a module
edge is cut with a narrow strip of deck left across its mouth, over the wall,
to hold the deck in one piece until it is in place; the builder then cuts it
away (see ``_deckSlotPlan``).  Trains run through there, so the exported decks
have those strips removed.

Needs the optional ``step`` dependency (build123d) for the glTF; the track
graph alone (:func:`layout_track`) does not.

Command line (in the container, from /app)::

    python -m boxes.generators._hexmo_drive [--out=DIR] [--all] [LAYOUT ...]

e.g. ``N250-ground-x2 HO-ground-x2``; ``--all`` exports every layout.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from boxes.generators import _hexmo_step as S
from boxes.generators._hexmo_risers import point_at

# Spacing (mm) of the polyline samples along each track.
_STEP = 5.0
# End points closer than this (mm, in plan and in height) are one node.
_JOIN = 1.0
# Staging track (mm) run on from each dead end at a single ring's entry, so a
# train has somewhere to start and to run into.
_STAGING = 1500.0
# Mesh tolerances for the glTF (mm, radians): fine enough for the openings'
# rounded corners, coarse enough to keep a pair of rings to ~20 MB.
_LINEAR_DEFLECTION = 0.3
_ANGULAR_DEFLECTION = 0.35
# Where the viewer lives, relative to the repository root.
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "hexmohexagon" / "drive"


def dogbone_n250():
    """The N dogbone's ring: single-track loop, double-track main, Peco turnouts.

    The helix ring's shape and module settings (radius 250 and the rest),
    with no spur, risers or subway, track on the deck only.  The ring carries
    one track down the middle of the trapezoids (``3:0-5:0``, R335, through
    the middle of their slanted ends).  On M6 two legs lead from the entry's
    double track (±20 at edge 1) into it (tightest R294, where they swing in
    from the main), one towards M1 and one towards M5,
    so the main line's two tracks are the two ends of the loop: continuous
    running with no turnout on a curve (the ring is tighter than any Peco N
    curved turnout).  The entry carries the double track straight (40 mm
    apart) with a Peco N medium crossover (``--crossovers``) centred on it.
    Two of these rings make the dogbone, joined entry to entry (a pair): the
    second ring's entry is turned round, so its crossover goes the other way.

    @returns ``(modules, entry_args)`` for :func:`_hexmo_step._ring_layout`.
    """
    from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N250, HELIX_RING_N250
    helix_only = ("--track_routes", "--track_openings", "--deck_slots", "--risers",
                  "--under_track_edges", "--trapezoid")
    common = [a for a in HELIX_RING_N250["M6"] if not a.startswith(helix_only)]
    modules = {f"M{k}": common + ["--trapezoid=1", "--track_routes=3:0-5:0"]
               for k in range(1, 6)}
    modules["M6"] = common + ["--track_routes=1:-20-5:0,3:0-1:-20"]
    # The entry: double track (the N spacing, 40 mm) with the crossover
    # centred on its 427 mm deck (284.3 mm toe to toe), and no lower level.
    entry = [a for a in HELIX_ENTRY_N250
             if not a.startswith(("--turnouts=", "--under_track=", "--subway"))]
    return modules, entry + ["--track_line_count=2", "--crossovers=71:-20:20"]


def dual_dogbone_n250():
    """The N dual-ring dogbone's ring: double track round the ring, Peco turnouts.

    As :func:`dogbone_n250`, but the ring keeps both tracks: inner
    ``3:-15-5:-15`` (R320) and outer ``3:25-5:25`` (R360), 40 mm apart.  On
    the entry two Peco N Code 80 medium turnouts split the main's two tracks
    (±20) into four, the legs settling at ±60, and a crossover of the same
    turnouts joins the main's two tracks.  The three interleave along the
    deck (x from its far end, M6 at 427):

    * the −20 track: the crossover's first turnout (toe 15), then at its heel
      the splitting turnout (toe 138.7), its leg parallel at −60 by 406.4,
      leaving the 20 mm lead-in at the M6 end;
    * the +20 track: the splitting turnout (toe 20, heel 143.7), then the
      crossover's second turnout (from 175.6), its toe at 299.3.

    The crossover's diagonal stays between the main's two tracks and the
    splitting legs go outward, so nothing crosses.  Turning the other ring
    round doesn't mirror a crossover, so its entry is the mirror image (the
    crossover from +20 to −20, the splitting turnouts swapped to match): the
    two crossovers are opposite hands, one left to right and one right to
    left.  On
    M6 four legs carry them into the ring: ±20 to the inner track (R280) and
    ±60 to the outer (R240, the tightest; a radius-250 hexagon has no room
    for more).  Each loop's two ends are the main's two tracks, so the
    turnouts choose the inner or outer loop at each end, and running is
    continuous whichever is set.

    @returns ``(modules, entry_args, second_entry_args)``: the second ring's
             entry is the mirror image (see :func:`_pair_rings`).
    """
    from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N250, HELIX_RING_N250
    helix_only = ("--track_routes", "--track_openings", "--deck_slots", "--risers",
                  "--under_track_edges", "--trapezoid")
    common = [a for a in HELIX_RING_N250["M6"] if not a.startswith(helix_only)]
    modules = {f"M{k}": common + ["--trapezoid=1", "--track_routes=3:25-5:25,3:-15-5:-15"]
               for k in range(1, 6)}
    modules["M6"] = common + [
        "--track_routes=1:-20-5:15,1:-60-5:-25,3:15-1:-20,3:-25-1:-60"]
    entry = [a for a in HELIX_ENTRY_N250
             if not a.startswith(("--turnouts=", "--under_track=", "--subway"))]
    # All facing M6 (see above for how they interleave), and the mirror image.
    entry += ["--track_line_count=2"]
    return (modules,
            entry + ["--turnouts=138.7:-20:-60,20:20:60", "--crossovers=15:-20:20"],
            entry + ["--turnouts=20:-20:-60,138.7:20:60", "--crossovers=15:20:-20"])


def dual_dogbone_ho():
    """The HO dual-ring dogbone's ring: :func:`dual_dogbone_n250` at HO size.

    The HO ring's shape and module settings (radius 500, 6 mm stock), track
    on the deck only.  The ring keeps a double track at the HO spacing,
    80 mm: ``3:40-5:40`` (R740) and ``3:-40-5:-40`` (R660).  On the entry's
    866 mm deck two Peco HO medium turnouts (SL-E95/96: 219 mm, R914, 12°;
    the rectangle's defaults) split the main's two tracks (±40) into four,
    the legs back parallel at ±120 546 mm from their toes, and a crossover
    of the same turnouts (568.5 mm toe to toe) joins the main's two tracks.
    They interleave as on N (x from the deck's far end, M6 at 866):

    * the −40 track: the crossover's first turnout (toe 10), then at its heel
      the splitting turnout (toe 229), its leg parallel at −120 by 775,
      inside the 23 mm lead-in at the M6 end;
    * the +40 track: the splitting turnout (toe 15, heel 234), then the
      crossover's second turnout (from 360), its toe at 578.5.

    The second ring's entry is the mirror image, so the two crossovers are
    opposite hands.  On M6 four legs carry the main's tracks (±40) into the
    ring's inner track and the split legs (±120) into its outer, so each
    loop's two ends are the main's two tracks and running is continuous
    whichever way the turnouts are set.

    @returns ``(modules, entry_args, second_entry_args)``.
    """
    from boxes.generators._hexmo_helix_ring import helix_entry_ho, helix_ring_ho
    helix_only = ("--track_routes", "--track_openings", "--deck_slots", "--risers",
                  "--under_track_edges", "--trapezoid")
    common = [a for a in helix_ring_ho()["M6"] if not a.startswith(helix_only)]
    modules = {f"M{k}": common + ["--trapezoid=1", "--track_routes=3:40-5:40,3:-40-5:-40"]
               for k in range(1, 6)}
    modules["M6"] = common + [
        "--track_routes=1:-40-5:40,1:-120-5:-40,3:40-1:-40,3:-40-1:-120"]
    entry = [a for a in helix_entry_ho()
             if not a.startswith(("--turnouts=", "--under_track=", "--subway="))]
    entry += ["--track_line_count=2", "--track_spacing=80"]
    return (modules,
            entry + ["--turnouts=229:-40:-120,15:40:120", "--crossovers=10:-40:40"],
            entry + ["--turnouts=15:-40:-120,229:40:120", "--crossovers=10:40:-40"])


@dataclass(frozen=True)
class RingPair:
    """Two different rings joined entry to entry: ``first`` as it is,
    ``second`` turned round onto its entry's far end.  Each is a key of
    :data:`_hexmo_helix_ring.RINGS` or a ring definition; their entries must
    match where they meet (the same entry rectangle)."""

    first: object
    second: object


def ho_ground_and_ho():
    """An HO pair with the lower level between them, one ring opened up.

    Ring A is ``HO-ground`` (upper and lower ground for scenery), ring B the
    plain ``HO`` ring.  Both have the same entry rectangle, the lower level
    running through it on the floor, so the two join as an ``HO-x2`` does.
    """
    return RingPair("HO-ground", "HO")


# Dogbone layouts: name → the function giving its ring.  Two of the ring,
# joined entry to entry (as a ``-x2`` pair), make the layout; a
# :class:`RingPair` joins two different rings.
DOGBONES = {"N250-dogbone": dogbone_n250, "N250-dual-dogbone": dual_dogbone_n250,
            "HO-dual-dogbone": dual_dogbone_ho, "HO-ground-HO": ho_ground_and_ho}


def layouts():
    """Every layout name: the dogbones, then each helix ring alone and paired.

    @returns e.g. ``["N250-dogbone", "N250", "N250-x2", …]``.
    """
    from boxes.generators._hexmo_helix_ring import RINGS
    return list(DOGBONES) + [name for ring in RINGS for name in (ring, f"{ring}-x2")]


def parse_layout(name):
    """``(ring, mode)`` for a layout name.

    @returns ``ring``: a key of :data:`_hexmo_helix_ring.RINGS` or a ring
             definition (:func:`_hexmo_step._ring_layout` takes either);
             ``mode``: ``"single"`` (one ring, with staging) or ``"pair"`` (two
             rings, entry to entry; every dogbone is one).
    @throws ValueError - For an unknown name.
    """
    from boxes.generators._hexmo_helix_ring import RINGS
    if name in DOGBONES:
        return DOGBONES[name](), "pair"
    ring, mode = (name[:-3], "pair") if name.endswith("-x2") else (name, "single")
    if ring not in RINGS:
        raise ValueError(f"unknown layout {name!r}; choose from {', '.join(layouts())}")
    return ring, mode


# ------------------------------------------------------------------ polylines

def piece_polyline(piece, angle, offset):
    """A piece's rail-top centreline as ``[[x, y, z], ...]`` in the ring frame.

    @param piece  - :class:`_hexmo_step.TrackPiece`, in its module's frame.
    @param angle  - The module's turn about z (degrees).
    @param offset - The module's (dx, dy) in the ring frame.
    @returns Points every ``_STEP`` mm or less, both ends included.
    """
    total = sum(seg.length for seg in piece.segments)
    n = max(1, math.ceil(total / _STEP))
    pts = []
    for k in range(n + 1):
        s = total * k / n
        p, _ = point_at(piece.segments, s)
        x, y = S._place_point(p, angle, offset)
        pts.append([x, y, piece.base(s) + S.RAIL_HEIGHT])
    return pts


def entry_subway(box, angle, offset):
    """The lower level's straight under the entry rectangle (``--subway``).

    :func:`_hexmo_step.rect_pieces` lists only the deck tracks; the subway bed
    carries the lower level on the centre line at ``--under_track_height``,
    from the M6 joint to the far end.
    """
    lay, _, _ = S._rect_frame(box)
    reach = lay.H / 2 + lay.t
    z = box.under_track_height + S.RAIL_HEIGHT
    n = math.ceil(2 * reach / _STEP)
    return [[*S._place_point((-reach + 2 * reach * k / n, 0.0), angle, offset), z]
            for k in range(n + 1)]


def ring_lines(ring):
    """Every track of one ring as labelled polylines, in the ring frame.

    @param ring - Key of :data:`_hexmo_helix_ring.RINGS`, or a ring definition.
    @returns ``(lines, far_y)``: ``[{"label", "pts"}]``, and the y (mm) of the
             entry rectangle's far end, where a second ring's entry butts on.
    """
    lines, far_y = [], None
    for name, box, kind, angle, offset in S._ring_layout(ring):
        pieces = S.hexmo_pieces(box) if kind == "hexmo" else S.rect_pieces(box)
        for piece in pieces:
            lines.append({"label": f"{name} {piece.name}",
                          "pts": piece_polyline(piece, angle, offset)})
        if kind == "rect":
            lay, _, _ = S._rect_frame(box)
            # The entry is turned -90°, so its far end (+x) points up y.
            far_y = offset[1] + lay.H / 2 + lay.t
            if getattr(box, "subway", None):
                lines.append({"label": f"{name} lower level",
                              "pts": entry_subway(box, angle, offset)})
    return lines, far_y


def turned(pts, far_y):
    """Points turned 180° about the entry's far end: the second ring's copy.

    Turning about the point (0, far_y) maps (x, y) to (−x, 2·far_y − y), so
    the copy's entry meets the original's face to face, every track in line.
    """
    return [[-x, 2 * far_y - y, z] for x, y, z in pts]


def staging(lines):
    """A straight staging track off each entry dead end, pointing at the ring.

    Each runs on ``_STAGING`` mm from the far end of the entry line (and of
    the lower level), level and in line with it, and is listed far end first,
    so a train standing on it in the listed direction heads into the layout.

    @param lines - The ring's polylines (from :func:`ring_lines`).
    @returns New ``{"label", "pts", "staging": True}`` polylines.
    """
    out = []
    for line in lines:
        if not line["label"].startswith("entry ") or "turnout" in line["label"]:
            continue
        pts = line["pts"]
        # The far end is the one further from the ring centre.
        if math.hypot(*pts[0][:2]) > math.hypot(*pts[-1][:2]):
            far, near = pts[0], pts[1]
        else:
            far, near = pts[-1], pts[-2]
        dx, dy = far[0] - near[0], far[1] - near[1]
        d = math.hypot(dx, dy)
        ux, uy = dx / d, dy / d
        n = math.ceil(_STAGING / _STEP)
        run = [[far[0] + ux * _STAGING * (1 - k / n), far[1] + uy * _STAGING * (1 - k / n), far[2]]
               for k in range(n + 1)]
        out.append({"label": f"staging {line['label'][len('entry '):]}", "pts": run,
                    "staging": True})
    return out


# ------------------------------------------------------------------ graph

def _near(a, b):
    """Whether two points are one node (within ``_JOIN`` in plan and height)."""
    return math.dist(a[:2], b[:2]) < _JOIN and abs(a[2] - b[2]) < _JOIN


def _touch(pts, e):
    """Where point ``e`` lies inside polyline ``pts`` (not at its ends).

    @returns The index of the polyline segment it lies on, or None.
    """
    if _near(pts[0], e) or _near(pts[-1], e):
        return None
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        if length2 < 1e-12:
            continue
        # The foot of the perpendicular from e onto the segment, as a fraction.
        t = ((e[0] - a[0]) * dx + (e[1] - a[1]) * dy) / length2
        if -1e-6 <= t <= 1 + 1e-6:
            q = [a[0] + t * dx, a[1] + t * dy, a[2] + t * (b[2] - a[2])]
            if _near(q, e):
                return i
    return None


def split_at_touches(lines):
    """Split each polyline where another polyline's end lies on its interior.

    That is where a turnout leg leaves its through road: the through road
    becomes two edges meeting at the toe, so the toe is a node.

    @param lines - ``[{"pts": [...], ...}]``.
    @returns A new list, touched polylines cut in two at the touch (the
             touching end point inserted exactly); other keys are kept.
    """
    ends = [p for line in lines for p in (line["pts"][0], line["pts"][-1])]
    out = []
    for line in lines:
        pieces = [line["pts"]]
        for e in ends:
            cut = []
            for pts in pieces:
                i = _touch(pts, e)
                cut += [pts] if i is None else [pts[:i + 1] + [e], [e] + pts[i + 1:]]
            pieces = cut
        out += [{**line, "pts": pts} for pts in pieces]
    return out


def _leaving(pts, end):
    """Unit plan direction leaving a node along a polyline from its ``end``.

    Taken over a few samples (about 15 mm) so a sample's rounding can't skew it.
    """
    if end == 0:
        a, b = pts[0], pts[min(3, len(pts) - 1)]
    else:
        a, b = pts[-1], pts[max(-4, -len(pts))]
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def build_graph(lines):
    """Nodes, edges and the moves a train may make at each node.

    @param lines - Polylines already split at their touches.
    @returns ``{"nodes": [...], "edges": [...]}``.  Each edge has its rounded
             ``pts``, ``from``/``to`` node ids, a ``label`` and a
             ``staging`` flag.  Each node has its ``pos``, its ``ends``
             (``[edge, end]``, end 0 = the edge's start, 1 = its end),
             ``links`` (pairs of ends a train may pass between) and
             ``turnout`` (an end there has two ways on).
    """
    nodes, edges = [], []

    def node_for(p):
        for k, n in enumerate(nodes):
            if _near(n["pos"], p):
                return k
        nodes.append({"pos": p, "ends": []})
        return len(nodes) - 1

    for k, line in enumerate(lines):
        pts = line["pts"]
        a, b = node_for(pts[0]), node_for(pts[-1])
        edges.append({"id": k, "label": line["label"],
                      "pts": [[round(c, 2) for c in p] for p in pts],
                      "from": a, "to": b, "staging": line.get("staging", False)})
        nodes[a]["ends"].append([k, 0])
        nodes[b]["ends"].append([k, 1])
    for n in nodes:
        n["links"] = []
        for i, (ea, enda) in enumerate(n["ends"]):
            for eb, endb in n["ends"][i + 1:]:
                da = _leaving(edges[ea]["pts"], enda)
                db = _leaving(edges[eb]["pts"], endb)
                # Straight on: the two leave the node in opposite directions
                # (more than 120° apart).
                if da[0] * db[0] + da[1] * db[1] < -0.5:
                    n["links"].append([[ea, enda], [eb, endb]])
        n["pos"] = [round(c, 2) for c in n["pos"]]
        n["turnout"] = any(sum(1 for link in n["links"] if end in link) > 1
                           for end in n["ends"])
    return {"nodes": nodes, "edges": edges}


def _pair_rings(ring):
    """The two rings of a pair: ``(first, second)``.

    A ring definition may give the second ring its own entry, as a third
    element ``(modules, entry_args, second_entry_args)``: turning the second
    ring round doesn't mirror its entry, so an entry that must be the other
    hand (a crossover going the other way) is given separately.  A
    :class:`RingPair` gives two different rings.
    """
    if isinstance(ring, RingPair):
        return ring.first, ring.second
    if isinstance(ring, tuple) and len(ring) == 3:
        modules, first, second = ring
        return (modules, first), (modules, second)
    return ring, ring


def layout_track(name):
    """A layout's track graph, ready for ``<name>.track.json``.

    @param name - A layout name (see :func:`layouts`).
    @returns ``{"layout", "scale", "nodes", "edges"}``; ``scale`` is the
             model scale (160 for N, 87 for HO).
    """
    ring, mode = parse_layout(name)
    if mode == "single":
        lines, _ = ring_lines(ring)
        lines = lines + staging(lines)
    else:
        first, second = _pair_rings(ring)
        lines, far_y = ring_lines(first)
        lines = ([{**ln, "label": f"A {ln['label']}"} for ln in lines]
                 + [{**ln, "label": f"B {ln['label']}", "pts": turned(ln["pts"], far_y)}
                    for ln in ring_lines(second)[0]])
    scale = 87.0 if name.startswith("HO") else 160.0
    return {"layout": name, "scale": scale, **build_graph(split_at_touches(lines))}


# ------------------------------------------------------------------ export

# How far a mouth cutter reaches past the deck's outer edge (mm), and how
# close (mm, beyond the wall thickness) a slot end must be to that edge to
# count as running out there.
_MOUTH_REACH = 2.0


def _mouth_cutters(bd, box):
    """Boxes over the strip left across each deck slot's mouth at a module edge.

    A slot that runs out at a module edge stops at (or just past) the wall's
    inner face; the deck reaches one thickness further, over the wall, and
    that strip is cut away by hand once the deck is in place.  Each cutter
    runs from the slot's end out past the deck's edge, as wide as the slot
    and a little thicker than the deck.

    @param bd  - The build123d module.
    @param box - A HexmoHexagon with its arguments parsed.
    @returns build123d solids, in the module's frame.
    """
    from shapely.geometry import Point, Polygon
    r, l, t, _, slot_plan, _ = S._hexmo_plans(box)
    outline = Polygon(S._outline(r, t, box.trapezoid)).exterior
    cutters = []
    for slot in slot_plan:
        segments = slot["segments"]
        total = sum(seg.length for seg in segments)
        for s, inner in ((0.0, min(1.0, total)), (total, max(0.0, total - 1.0))):
            (x, y), _ = point_at(segments, s)
            if outline.distance(Point(x, y)) > t + _MOUTH_REACH:
                continue                  # ends inside the deck: no strip
            # Outward, from a point 1 mm back along the slot to its end: the
            # direction point_at reports there can be (0, 0), where the slot
            # is trimmed exactly at a join and its last piece has no length.
            (ix, iy), _ = point_at(segments, inner)
            d = math.hypot(x - ix, y - iy) or 1.0
            dx, dy = (x - ix) / d, (y - iy) / d
            length = t + 2 * _MOUTH_REACH + 1.0
            centre = (x + dx * (length / 2 - 0.5), y + dy * (length / 2 - 0.5), l + t / 2)
            cutters.append(S._box(bd, centre, (length, slot["width"], t + 2.0),
                                  math.degrees(math.atan2(dy, dx))))
    return cutters


def _as_built(parts, cutters):
    """A module's parts with the deck's slot-mouth strips cut away.

    @param parts   - The module's :class:`_hexmo_step.Part3D`, its own frame.
    @param cutters - From :func:`_mouth_cutters`.
    """
    if not cutters:
        return parts
    out = []
    for p in parts:
        solid = p.solid
        if p.name == "deck":
            for cutter in cutters:
                solid = solid - cutter
        out.append(S.Part3D(p.name, p.kind, solid))
    return out


def ring_parts_as_built(ring):
    """Every part of a helix ring, placed, decks as built (see module notes).

    As :func:`_hexmo_step.ring_parts`, with each module's deck-slot mouths
    opened.

    @param ring - Key of :data:`_hexmo_helix_ring.RINGS`, or a ring definition.
    @returns List of :class:`_hexmo_step.Part3D`.
    """
    bd = S._bd()
    parts = []
    for name, box, kind, angle, offset in S._ring_layout(ring):
        # The cutters come from the slot plan, worked out before the render
        # that module_parts makes.
        cutters = _mouth_cutters(bd, box) if kind == "hexmo" else []
        built = _as_built(S.module_parts(box, kind, "none", "exact"), cutters)
        where = bd.Location((offset[0], offset[1], 0), (0, 0, angle))
        parts += [S.Part3D(f"{name} {p.name}", p.kind, where * p.solid) for p in built]
    return parts


def layout_parts(name):
    """Every cut part of a layout, placed (the second ring of a pair turned).

    @returns List of :class:`_hexmo_step.Part3D`.
    """
    bd = S._bd()
    ring, mode = parse_layout(name)
    if mode == "single":
        return ring_parts_as_built(ring)
    first, second = _pair_rings(ring)
    _, far_y = ring_lines(first)
    # The second ring: turned 180° about z, then moved so the turn is about
    # the entry's far end (as :func:`turned` does to the track).
    where = bd.Location((0, 2 * far_y, 0), (0, 0, 180))
    return ([S.Part3D(f"A {p.name}", p.kind, p.solid) for p in ring_parts_as_built(first)]
            + [S.Part3D(f"B {p.name}", p.kind, where * p.solid)
               for p in ring_parts_as_built(second)])


def export_layout(name, out=DEFAULT_OUT):
    """Write ``<name>.glb`` and ``<name>.track.json`` into ``out``.

    @param name - A layout name (see :func:`layouts`).
    @param out  - The viewer's folder.
    @returns ``(edges, turnouts, dead_ends)`` counts, for a summary.
    @throws ImportError - Without the optional ``step`` dependency.
    """
    bd = S._bd()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    track = layout_track(name)
    (out / f"{name}.track.json").write_text(json.dumps(track))
    bd.export_gltf(S.assembly(layout_parts(name), label=name), str(out / f"{name}.glb"),
                   binary=True, linear_deflection=_LINEAR_DEFLECTION,
                   angular_deflection=_ANGULAR_DEFLECTION)
    write_manifest(out)
    nodes = track["nodes"]
    return (len(track["edges"]), sum(n["turnout"] for n in nodes),
            sum(len(n["ends"]) == 1 for n in nodes))


def write_manifest(out):
    """List the layouts exported into ``out`` in ``layouts.json``.

    ``{"layouts": [...], "version": {name: stamp}}``: dogbones first, then
    pairs, the scenery (ground) versions first among those (the viewer opens
    on the first when no layout is asked for); and for each, a stamp from
    its files' modification times, which the viewer adds to their URLs so a
    re-export is never mixed with a browser's cached copy of the last one.
    """
    out = Path(out)
    names = [n for n in layouts() if (out / f"{n}.glb").exists()
             and (out / f"{n}.track.json").exists()]
    names.sort(key=lambda n: (n not in DOGBONES, not n.endswith("-x2"), "-ground" not in n,
                              layouts().index(n)))
    version = {n: int(max((out / f"{n}.glb").stat().st_mtime,
                          (out / f"{n}.track.json").stat().st_mtime))
               for n in names}
    (out / "layouts.json").write_text(json.dumps({"layouts": names, "version": version}))


def main(argv=None):
    """Command line: see the module docstring."""
    argv = sys.argv[1:] if argv is None else argv
    out, names = DEFAULT_OUT, []
    for arg in argv:
        if arg.startswith("--out="):
            out = Path(arg.split("=", 1)[1])
        elif arg == "--all":
            names += layouts()
        elif arg.startswith("-"):
            print(__doc__.split("\n\n")[0])
            print(f"usage: python -m boxes.generators._hexmo_drive [--out=DIR] [--all] "
                  f"[{'|'.join(layouts())} ...]")
            return 2
        else:
            names.append(arg)
    for name in names or ["N250-ground-x2"]:
        edges, turnouts, dead = export_layout(name, out)
        print(f"{name}: {edges} track pieces, {turnouts} turnouts, {dead} dead ends")
    print(f"wrote to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
