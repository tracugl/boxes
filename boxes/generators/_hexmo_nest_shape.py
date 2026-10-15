"""The true shape of a drawn part, as a grid of cells, for nesting (``--sheets``).

:mod:`_hexmo_nest` packs parts by their shapes, not their bounding boxes, so
small parts can go in a hexagon's corners, beside a trapezoid's slanted sides
and inside big cutouts.  Each part is drawn into a coarse grid of
:data:`CELL` mm square cells: a cell is *occupied* when any of the part's
material, or any line or text drawn on it, touches it, and *free* otherwise.
Holes cut right through the part are free, so other parts can be packed into
them.

How a part becomes cells
------------------------
1. Its paths are flattened to polylines in mm (curves sampled), after any
   quarter turn (:func:`polylines`).
2. Open cut polylines that meet end to end are joined, and every closed one
   is a *ring* (:func:`_rings`).
3. The rings are filled on a fine pixel grid (:data:`FINE` mm) with the
   even-odd rule: a pixel inside an odd number of rings is material (the
   outline less its cutouts, plus anything inside a cutout); inside an even
   number, a hole.  Every line and text box is drawn on top, so nothing drawn
   is ever left free.
4. The fine grid is pooled into cells, a cell occupied when any of its
   pixels is, and grown by one fine pixel all round first, so rounding can
   only make a part bigger, never smaller.

If any cut line lies outside every ring (an outline that doesn't close, for
example), the shape can't be trusted and the whole bounding box is occupied:
the part then packs as it would by bounding box.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from affine import Affine
from PIL import Image, ImageDraw

from boxes.Color import Color

# mm per fine pixel, and fine pixels per cell side: cells are 2 mm square.
FINE = 0.5
POOL = 4
CELL = FINE * POOL
# Straight pieces each curve is sampled into.
_CURVE_STEPS = 8
# Endpoints closer than this (mm) are the same point when joining lines.
_JOIN = 0.05
# The cut colours (this fork draws outer and inner cuts in the same red).
_CUT = {tuple(Color.OUTER_CUT), tuple(Color.INNER_CUT)}


@dataclass
class Shape:
    """A part's cells, unturned.

    @ivar cells - Bool array indexed ``[x, y]``: cell (i, j) covers
                  ``[i·CELL, (i+1)·CELL) × [j·CELL, (j+1)·CELL)`` measured from
                  the part's bounding-box corner.
    @ivar area  - The part's material area (mm²), from the fine grid.
    @ivar size   - The part's bounding box ``(width, height)`` (mm).
    @ivar origin - That box's corner ``(xmin, ymin)`` where the part lies now.
    @ivar outline - The area inside its outline, holes included (mm²): how
                    much room it takes, for packing the biggest first.
    """

    cells: np.ndarray
    area: float
    size: tuple
    origin: tuple
    outline: float = 0.0

    def turned(self, quarter):
        """The cells after ``quarter`` quarter turns anticlockwise (0–3).

        Matches :func:`place_matrix`: a cell grid turned with the part.
        """
        # Indexed [x, y]: turning from the x axis towards the y axis is
        # anticlockwise, as Affine.rotation's positive angle is.
        return np.rot90(self.cells, quarter, axes=(0, 1))


def _bezier(p0, c1, c2, p3):
    """Points along a cubic Bézier, its start left out."""
    out = []
    for k in range(1, _CURVE_STEPS + 1):
        t = k / _CURVE_STEPS
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0],
                    a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]))
    return out


def _text_box(command):
    """The four corners of a text command's box, as Path.extents estimates it."""
    _, _, _, m, text, params = command
    h = params["fs"]
    length = len(text) * h * 0.7
    start, end = {"left": (0, 1), "middle": (-0.5, 0.5), "end": (-1, 0)}[params.get("align", "left")]
    return [m * (x, y) for x, y in ((start * length, 0), (end * length, 0),
                                    (end * length, h), (start * length, h))]


def polylines(part):
    """A part's drawing as straight pieces (mm).

    @param part - A drawing-surface Part.
    @returns ``(lines, boxes)``: lines as ``(points, is_cut)``, one per
             subpath, curves sampled; boxes the corners of each text.
    """
    lines, boxes_ = [], []
    for path in part.pathes:
        cut = tuple(path.params.get("rgb", ())) in _CUT
        points = []
        for c in path.path:
            if c[0] == "M":
                if len(points) > 1:
                    lines.append((points, cut))
                points = [(c[1], c[2])]
            elif c[0] == "L":
                points.append((c[1], c[2]))
            elif c[0] == "C" and points:
                points.extend(_bezier(points[-1], (c[3], c[4]), (c[5], c[6]), (c[1], c[2])))
            elif c[0] == "T":
                boxes_.append(_text_box(c))
        if len(points) > 1:
            lines.append((points, cut))
    return lines, boxes_


def _key(point):
    """A point rounded to the join tolerance, for matching line ends."""
    return round(point[0] / _JOIN), round(point[1] / _JOIN)


def _close(a, b):
    return abs(a[0] - b[0]) <= _JOIN and abs(a[1] - b[1]) <= _JOIN


def _rings(lines):
    """Closed rings from the cut lines, joining open ones that meet end to end.

    @param lines - ``[(points, is_cut)]`` from :func:`polylines`.
    @returns ``(rings, loose)``: point lists that close, and cut lines left open.
    """
    rings, open_ = [], []
    for points, cut in lines:
        if not cut:
            continue
        (rings if _close(points[0], points[-1]) and len(points) > 2 else open_).append(list(points))
    # Join open lines end to end: index each by its two ends.
    ends = {}
    for k, points in enumerate(open_):
        for end in (points[0], points[-1]):
            ends.setdefault(_key(end), []).append(k)
    used, loose = set(), []
    for k in range(len(open_)):
        if k in used:
            continue
        used.add(k)
        chain = list(open_[k])
        while not _close(chain[0], chain[-1]):
            nxt = next((j for j in ends.get(_key(chain[-1]), []) if j not in used), None)
            if nxt is None:
                break
            used.add(nxt)
            piece = open_[nxt]
            chain.extend(piece[1:] if _close(piece[0], chain[-1]) else piece[-2::-1])
        (rings if _close(chain[0], chain[-1]) and len(chain) > 2 else loose).append(chain)
    return rings, loose


def _pixels(points, x0, y0):
    """mm points to fine-pixel coordinates from the corner (x0, y0)."""
    return [((x - x0) / FINE, (y - y0) / FINE) for x, y in points]


def _grow(mask):
    """A bool mask grown by one pixel in all eight directions."""
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    grown = out.copy()
    grown[:, 1:] |= out[:, :-1]
    grown[:, :-1] |= out[:, 1:]
    return grown


def bounds(lines, boxes_):
    """``(xmin, ymin, xmax, ymax)`` of the lines and text boxes."""
    xs = [p[0] for points, _ in lines for p in points] + [p[0] for b in boxes_ for p in b]
    ys = [p[1] for points, _ in lines for p in points] + [p[1] for b in boxes_ for p in b]
    return min(xs), min(ys), max(xs), max(ys)


def shape_of(part):
    """A part's :class:`Shape` (see the module notes for how).

    @param part - A drawing-surface Part with something drawn.
    @returns Its Shape.
    """
    lines, boxes_ = polylines(part)
    xmin, ymin, xmax, ymax = bounds(lines, boxes_)
    w, h = xmax - xmin, ymax - ymin
    # The fine grid covers whole cells, with the part from its corner.
    nx, ny = math.ceil(w / CELL + 1e-9) or 1, math.ceil(h / CELL + 1e-9) or 1
    size = (nx * POOL, ny * POOL)

    def drawn(draw_fn):
        img = Image.new("1", size, 0)
        draw_fn(ImageDraw.Draw(img))
        # Pillow's arrays are [row, column] = [y, x]; ours are [x, y].
        return np.asarray(img, dtype=bool).T

    rings, _ = _rings(lines)
    material = np.zeros(size, dtype=bool)
    inside = np.zeros(size, dtype=bool)
    for ring in rings:
        fill = drawn(lambda d, r=ring: d.polygon(_pixels(r, xmin, ymin), fill=1))
        material ^= fill
        inside |= fill

    def strokes(which):
        def draw(d):
            for points, cut in lines:
                if which(cut):
                    d.line(_pixels(points, xmin, ymin), fill=1, width=1)
        return drawn(draw)

    cut_lines = strokes(lambda cut: cut)
    # Every cut line must lie on or inside a ring, or the outline isn't closed.
    trusted = bool(rings) and not (cut_lines & ~_grow(_grow(inside))).any()
    if trusted:
        others = strokes(lambda cut: not cut) | drawn(
            lambda d: [d.polygon(_pixels(b, xmin, ymin), fill=1) for b in boxes_])
        fine = _grow(material | cut_lines | others)
        area = float(material.sum()) * FINE * FINE
        outline = float(inside.sum()) * FINE * FINE
    else:
        # Not a shape to trust: all of the bounding box is the part.
        fine = np.ones(size, dtype=bool)
        area = outline = w * h
    cells = fine.reshape(nx, POOL, ny, POOL).any(axis=(1, 3))
    return Shape(cells, area, (w, h), (xmin, ymin), outline)


def place_matrix(size, quarter, x, y):
    """The move that puts a part (turned) on a blank.

    @param size    - The :class:`Shape` grid's size in mm, ``(nx·CELL, ny·CELL)``.
    @param quarter - Quarter turns anticlockwise (0–3).
    @param x, y    - Where the turned grid's corner goes (mm).
    @returns Affine taking the part's coordinates, measured from its bounding
             box's corner, to the blank's.
    """
    gw, gh = size
    # After the turn the grid lies on the other side of an axis: move it back.
    back = [(0, 0), (gh, 0), (gw, gh), (0, gw)][quarter]
    return Affine.translation(x + back[0], y + back[1]) * Affine.rotation(90 * quarter)
