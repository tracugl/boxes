"""Pack a Hexmo module's parts onto laser-bed blanks (``--sheets``).

A laser cutter's bed is smaller than a full sheet of MDF, so the sheet is cut
into blanks that fit it (e.g. a 2400 × 1200 sheet cut at 900 gives two
1200 × 900 blanks and a 600 × 900 one, for a 1300 × 900 bed).  With
``--sheets`` set to those blanks, HexmoHexagon and HexmoRectangle lay their
parts out on as few full sheets' worth of blanks as will take them, instead
of in their usual single strip.

How it works
------------
The generator draws as usual.  Every part it draws is a separate *Part* on
the drawing surface (each ``move`` starts a new one), so just before the
drawing is finished each part's true shape is drawn into a grid of 2 mm
cells, its holes left free (:mod:`_hexmo_nest_shape`).  The parts are then
nested, largest first, each on the first blank with room for it, where it
touches the most (neighbours and the blank's edges), in whichever of its
four quarter turns does that best (:func:`pack`).  So small parts fill a hexagon's corners, the gaps beside a
trapezoid's slanted sides and the big cutouts in decks and floors.  A new
blank is started only when none in use has room, and a new full sheet only
when the sheets so far have no blank left that takes the part.  Each part is
then moved (and turned) onto its blank, the blanks are laid out in a row, and
each blank is outlined and labelled in the annotation colour (cyan), which
the laser software can leave uncut.

``--sheet_spacing`` keeps the parts apart and ``--sheet_margin`` off the
blank's edges; the 2 mm cells round both up a little, never down.

Command line (in the container, from /app)::

    python -m boxes.generators._hexmo_nest OUTDIR [--sheets=1200x900:2,600x900]
        [--sheet_spacing=4] [--sheet_margin=10] [--templates=2] [--guides=3]
        [N@]EDIT_URL ...

Each edit URL (``…/HexmoHexagon?radius=…``; ``N@`` in front for N of that
module) is rendered, and the whole order's parts are nested together, so one
module's small parts fill the gaps around another's.  Each blank is written
as ``OUTDIR/blank-KK-<w>x<h>.svg``, and each module's settings tag as
``OUTDIR/NN-<generator>-settings.svg`` (NN, the URL's place in the list) (files of those
patterns from an earlier run are removed first); a summary gives the blanks
used, how much of them the parts cover, and the full sheets to buy.  ``scripts/hexmo-sheets.sh`` runs it from the
host.

Track templates and guide plates are the same for many modules, so the order
keeps at most ``--templates`` (2: one to work with and a spare) of each
different template piece and ``--guides`` (3: two to use and a spare) of each
different guide plate, telling them apart by shape (:func:`cap_helpers`).

The settings tag (the parameter list the generators draw) is a reference,
not a part to cut: it is never packed onto a blank.  In a generator's own
output it goes after the blanks, and in the command line's it is its own
file; either way it is recoloured to the annotation colour.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

import copy
import math
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path as FilePath
from urllib.parse import parse_qsl, urlsplit

import numpy as np
from affine import Affine

from boxes.Color import Color
from boxes.drawing import Part, Path
from boxes.formats import Formats
from boxes.generators._hexmo_nest_shape import CELL, place_matrix, shape_of

# The blanks a 2400 × 1200 sheet cut at 900 gives: two 1200 × 900, one 600 × 900.
DEFAULT_SHEETS = "1200x900:2,600x900"
# Least gap (mm) between a part and a blank's edge.  The blanks are not cut
# exactly to size: each panel-saw cut loses 3–4 mm of kerf (a sheet's "600"
# piece is nearer 593), the cuts can be a little out of square and the edges
# get knocked, and the blank is never quite square on the laser bed.  10 mm
# all round (20 mm off each dimension) allows for all that.
DEFAULT_MARGIN = 10.0
# Least gap (mm) between two parts.
DEFAULT_SPACING = 4.0
# Gap (mm) between blanks laid out side by side in one drawing.
_BLANK_GAP = 40.0
# Label size (mm) above each blank.
_LABEL_SIZE = 16.0
# Give up after this many full sheets (a part set that big is a mistake).
_MAX_SETS = 200

_NUMBER = r"\d+(?:\.\d*)?"
_BLANK_RE = re.compile(rf"^\s*({_NUMBER})\s*[x×]\s*({_NUMBER})\s*(?::\s*(\d+))?\s*$")


@dataclass(frozen=True)
class BlankSize:
    """One kind of blank and how many of it one full sheet gives."""

    width: float
    height: float
    per_sheet: int = 1

    @property
    def name(self):
        return f"{self.width:g}x{self.height:g}"


@dataclass
class Blank:
    """A blank in use and the parts packed onto it.

    @ivar size   - Its :class:`BlankSize`.
    @ivar parts  - ``[(part, matrix)]``: each part and the Affine move (a
                   quarter turn or none, and a shift) that puts it on the
                   blank, in mm from the blank's lower-left corner.
    @ivar filled - The parts' material area (mm²), for how full it is.
    """

    size: BlankSize
    parts: list = field(default_factory=list)
    filled: float = 0.0


def parse_sheets(text):
    """Parse ``--sheets``: the blanks one full sheet is cut into.

    ``1200x900:2,600x900`` is two 1200 × 900 blanks and one 600 × 900 per
    sheet (width × height, mm; ``:N`` the count, 1 if left out).

    @param text - The option value; blank means none.
    @returns List of :class:`BlankSize`.
    @throws ValueError - On a malformed entry or a zero size or count.
    """
    if not text or not text.strip():
        return []
    sizes = []
    for item in text.split(","):
        match = _BLANK_RE.match(item)
        if not match:
            raise ValueError(f"--sheets entry {item.strip()!r} is not '<width>x<height>[:count]', "
                             "e.g. '1200x900:2'.")
        width, height = float(match[1]), float(match[2])
        count = int(match[3]) if match[3] else 1
        if width <= 0 or height <= 0 or count <= 0:
            raise ValueError(f"--sheets entry {item.strip()!r}: sizes and count must be positive.")
        sizes.append(BlankSize(width, height, count))
    return sizes


def _bounds(part):
    """A part's bounding box ``(xmin, ymin, width, height)``, or None if empty."""
    if not part.pathes:
        return None
    e = part.extents()
    if not math.isfinite(e.xmin):
        return None
    return e.xmin, e.ymin, e.xmax - e.xmin, e.ymax - e.ymin


def is_settings_tag(part):
    """Whether a Part is the generators' settings tag (their parameter list).

    It is a reference, not a part to cut, so it is never packed onto a blank
    (see :func:`lay_out` and :func:`main` for where it goes instead).
    """
    return getattr(part, "settings_tag", False)


def as_reference(part):
    """Recolour a Part to the annotation colour (cyan), so none of it is cut or etched."""
    for path in part.pathes:
        path.params["rgb"] = Color.ANNOTATIONS
        for c in path.path:
            if c[0] == "T":
                c[5]["rgb"] = Color.ANNOTATIONS
    return part


# Most of each different helper part an order's cut files keep: the track
# templates (one to work with and a spare) and guide plates (two to use and a
# spare), however many modules carry them.
HELPER_LIMITS = {"template": 2, "guide": 3}


def _shape_key(part):
    """A part's shape, wherever it lies: its paths relative to its lower-left
    corner, to 0.01 mm, with any text.  Equal keys are interchangeable parts."""
    xmin, ymin, _, _ = _bounds(part)
    key = []
    for path in part.pathes:
        key.append(tuple((c[0], round(c[1] - xmin, 2), round(c[2] - ymin, 2),
                          c[4] if c[0] == "T" else None) for c in path.path))
    return tuple(sorted(key))


def cap_helpers(parts, limits, seen=None):
    """Keep at most ``limits[kind]`` of each different helper part.

    Helper parts (track templates, guide plates) are marked by the generators
    as they draw them; two are the same when their shapes match
    (:func:`_shape_key`), from whichever module.

    @param parts  - Drawing-surface Parts, in order.
    @param limits - ``{kind: most}`` (see :data:`HELPER_LIMITS`).
    @param seen   - A running count to share across calls (for a whole
                    order); updated in place.
    @returns The parts, less the extra helpers.
    """
    seen = {} if seen is None else seen
    kept = []
    for part in parts:
        kind = getattr(part, "helper", None)
        if kind in limits and _bounds(part) is not None:
            key = (kind, _shape_key(part))
            if seen.get(key, 0) >= limits[kind]:
                continue
            seen[key] = seen.get(key, 0) + 1
        kept.append(part)
    return kept


def _items(parts, sizes, margin, cache):
    """``[(part, shape)]`` for the parts to cut, each checked to fit a blank.

    Empty parts and the settings tag (:func:`is_settings_tag`) are left out.
    Parts of the same shape share one :class:`Shape` (``cache``, by
    :func:`_shape_key`), so N copies of a module are drawn into cells once.

    @throws ValueError - If a part fits no blank, even turned.
    """
    items = []
    for part in parts:
        if _bounds(part) is None or is_settings_tag(part):
            continue
        key = _shape_key(part)
        if key not in cache:
            cache[key] = (shape_of(part), _bounds(part)[:2])
        first, (fx, fy) = cache[key]
        # The same shape, but this copy may lie elsewhere: shift the origin
        # by how far its bounding box is from the first copy's.
        x, y = _bounds(part)[:2]
        shape = replace(first, origin=(first.origin[0] + x - fx, first.origin[1] + y - fy))
        w, h = shape.size
        fits = any(min(w, h) <= min(s.width, s.height) - 2 * margin and
                   max(w, h) <= max(s.width, s.height) - 2 * margin for s in sizes)
        if not fits:
            raise ValueError(
                f"--sheets: a {w:.0f} × {h:.0f} mm part fits none of the blanks "
                f"({', '.join(s.name for s in sizes)}, less {margin:g} mm margins).")
        items.append((part, shape))
    return items


class _Bin:
    """One blank being filled: which of its cells are taken, and the FFT of that.

    Whether a part fits at every position of a blank at once is a
    cross-correlation of the part's cells (grown by the spacing) with the
    blank's taken cells: zero where they don't overlap.  How much it would
    touch there is another, of the rim of cells just beyond the spacing with
    the taken cells and the blank's edges.  Both are worked out by FFT, with
    the blank's transforms kept until something more is put on it.
    """

    def __init__(self, size, spacing, margin):
        self.blank = Blank(size)
        self.margin = margin
        nx = int(math.floor((size.width - 2 * margin) / CELL + 1e-9))
        ny = int(math.floor((size.height - 2 * margin) / CELL + 1e-9))
        self.taken = np.zeros((nx, ny), dtype=bool)
        # Spacing in whole cells; the FFT grid has room for it all round, so
        # the correlation never wraps into a position that's tried.
        self.grow = int(math.ceil(spacing / CELL - 1e-9))
        self.fft_size = (nx + 2 * self.grow, ny + 2 * self.grow)
        self.free = nx * ny
        # The (part, shape) items put on it, in order (see _downsize).
        self.items = []
        self._spectrum = None
        self._solid = None

    def spectrum(self):
        if self._spectrum is None:
            self._spectrum = np.fft.rfft2(self.taken, s=self.fft_size)
        return self._spectrum

    def solid(self):
        """FFT of the taken cells with the blank's edges walled in.

        The FFT grid's spare cells all round (where the correlation wraps)
        are filled, so a part's rim touching them counts as touching an edge.
        """
        if self._solid is None:
            nx, ny = self.taken.shape
            walled = np.ones(self.fft_size)
            walled[:nx, :ny] = self.taken
            self._solid = np.fft.rfft2(walled)
        return self._solid

    def best(self, kernels):
        """The free spot where the part touches most, in any of its turns.

        Touching its neighbours and the blank's edges most locks the parts
        together (a trapezoid turned to sit against another's slanted side);
        ties go to the lowest, then leftmost, spot.

        @param kernels - ``[(quarter, cells, grown_spectrum, (rim_spectrum,
                         rim_cells))]`` for this blank size.
        @returns ``(score, i, j, quarter, cells)`` or None if it fits nowhere.
        """
        nx, ny = self.taken.shape
        found = None
        for quarter, cells, spectrum, rim in kernels:
            mw, mh = cells.shape
            if mw > nx or mh > ny:
                continue
            overlap = np.fft.irfft2(self.spectrum() * np.conj(spectrum), s=self.fft_size)
            # Position (i, j) puts the cells' corner on cell (i, j); the grown
            # kernel starts `grow` cells before it.
            overlap = np.roll(overlap, (self.grow, self.grow), axis=(0, 1))[:nx - mw + 1, :ny - mh + 1]
            free = np.argwhere(overlap < 0.5)
            if not len(free):
                continue
            # How much of the rim just beyond the spacing touches other parts
            # or the blank's edges, at each free spot: the most touching spot
            # wins (in hundredths of the rim), then the lowest, then leftmost.
            ring, size = rim
            touch = np.fft.irfft2(self.solid() * np.conj(ring), s=self.fft_size)
            g = self.grow + 1
            touch = np.roll(touch, (g, g), axis=(0, 1))[free[:, 0], free[:, 1]]
            score = (free[:, 1] * (nx + 1) + free[:, 0]
                     - np.round(touch / size * 100) * (nx + 1) * (ny + 1))
            k = int(np.argmin(score))
            if found is None or score[k] < found[0]:
                found = (int(score[k]), int(free[k, 0]), int(free[k, 1]), quarter, cells)
        return found

    def put(self, part, shape, i, j, quarter, cells):
        """Take the part's cells at (i, j) and record where the part goes."""
        mw, mh = cells.shape
        self.taken[i:i + mw, j:j + mh] |= cells
        self.free -= int(cells.sum())
        self._spectrum = self._solid = None
        nx, ny = shape.cells.shape
        ox, oy = shape.origin
        m = place_matrix((nx * CELL, ny * CELL), quarter,
                         self.margin + i * CELL, self.margin + j * CELL)
        self.blank.parts.append((part, m * Affine.translation(-ox, -oy)))
        self.items.append((part, shape))
        self.blank.filled += shape.area


def _grown(cells, steps):
    """Cells grown by ``steps`` cells all round (the spacing), on a bigger grid."""
    out = np.pad(cells, steps)
    for _ in range(steps):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        out = grown.copy()
        out[:, 1:] |= grown[:, :-1]
        out[:, :-1] |= grown[:, 1:]
    return out


def full_sheets(blanks, sizes):
    """Full sheets needed for these blanks: enough of each size at its count per sheet."""
    counts = {}
    for blank in blanks:
        counts[blank.size] = counts.get(blank.size, 0) + 1
    return max((math.ceil(n / s.per_sheet) for s, n in counts.items()), default=0)


def _fill(items, sizes, spacing, margin, kernels_for):
    """Place each item, in order, on the first blank with room (see :func:`pack`).

    @param items       - ``[(part, shape)]`` in the order to place them.
    @param kernels_for - ``(shape, bin) -> kernels`` (see :meth:`_Bin.best`).
    @returns The :class:`_Bin` s used.
    @throws ValueError - If the parts need more than ``_MAX_SETS`` sheets.
    """
    bins, sheets, full = [], 1, set()
    for part, shape in items:
        need = int(shape.cells.sum())
        placed = False
        for k, b in enumerate(bins):
            # A shape that didn't fit a blank never will: it only fills up.
            if (id(shape.cells), k) in full or b.free < need:
                continue
            spot = b.best(kernels_for(shape, b))
            if spot is None:
                full.add((id(shape.cells), k))
                continue
            b.put(part, shape, *spot[1:])
            placed = True
            break
        while not placed:
            for size in sizes:
                if sum(b.blank.size == size for b in bins) >= sheets * size.per_sheet:
                    continue
                b = _Bin(size, spacing, margin)
                spot = b.best(kernels_for(shape, b))
                if spot is not None:
                    bins.append(b)
                    b.put(part, shape, *spot[1:])
                    placed = True
                    break
            else:
                sheets += 1
                if sheets > _MAX_SETS:
                    raise ValueError(f"--sheets: the parts need more than {_MAX_SETS} sheets.")
    return bins


def _onto(items, size, spacing, margin, kernels_for):
    """All the items on one new blank of ``size``, or None if they don't all fit."""
    b = _Bin(size, spacing, margin)
    for part, shape in items:
        spot = b.best(kernels_for(shape, b))
        if spot is None:
            return None
        b.put(part, shape, *spot[1:])
    return b


def _downsize(bins, sizes, spacing, margin, kernels_for):
    """Move a blank's parts onto a smaller blank the sheets still have spare.

    The packing fills the big blanks first, so the last of them is often
    nearly empty: a few parts spilled over.  When the full sheets it needs
    have a smaller blank to spare (e.g. a 600 × 900 when two of three are in
    use) and those parts all fit on it, they go there instead, leaving the
    big blank whole for another job.  The full sheets needed never change.

    @returns The bins, some perhaps replaced by smaller ones.
    """
    sheets = full_sheets([b.blank for b in bins], sizes)
    by_area = sorted(sizes, key=lambda z: z.width * z.height)
    bins = list(bins)
    # The emptiest first: they are the likeliest to fit somewhere smaller.
    for b in sorted(bins, key=lambda b: b.blank.filled):
        here = b.blank.size.width * b.blank.size.height
        for size in by_area:
            if size.width * size.height >= here:
                break
            if sum(o.blank.size == size for o in bins) >= sheets * size.per_sheet:
                continue
            smaller = _onto(b.items, size, spacing, margin, kernels_for)
            if smaller is not None:
                bins[bins.index(b)] = smaller
                break
    return bins


def pack(parts, sizes, spacing=DEFAULT_SPACING, margin=DEFAULT_MARGIN):
    """Nest parts by their true shapes onto the fewest full sheets' worth of blanks.

    Largest parts first, each goes on the first blank in use with room for
    it, where it touches the most (its neighbours and the blank's edges), in
    any of its four quarter turns (:class:`_Bin`), so the parts lock together
    and the small ones end up in the gaps around and inside the big ones.
    When none has room a new blank is started: the first size (as listed)
    that the sheets bought so far still have one of and the part fits; if
    there is none, another sheet is bought.  Last, a nearly empty blank's
    parts move to a smaller blank the sheets have spare (:func:`_downsize`).

    @param parts   - Drawing-surface Parts (empty ones and the settings tag
                     are skipped).
    @param sizes   - The blanks one full sheet gives (:func:`parse_sheets`).
    @param spacing - Least gap between two parts (mm).
    @param margin  - Least gap between a part and a blank's edge (mm).
    @returns ``(blanks, sheets)``: the :class:`Blank` s used, grouped in the
             order the sizes are listed, and the number of full sheets.
    @throws ValueError - If a part fits no blank, even turned, there are no
                         sizes, or the parts need more than ``_MAX_SETS`` sheets.
    """
    if not sizes:
        raise ValueError("--sheets: no blank sizes given.")
    shapes = {}
    items = _items(parts, sizes, margin, shapes)
    # Biggest first; equal shapes stay together (sorted is stable).
    items.sort(key=lambda it: -it[1].area)
    kernels = {}

    def kernels_for(shape, b):
        # The FFTs of a shape's four turns, grown by the spacing, and of the
        # rim of cells just beyond that (for how much it touches), per size.
        key = (id(shape.cells), b.blank.size)
        if key not in kernels:
            turns = []
            for quarter in range(4):
                cells = shape.turned(quarter)
                grown = _grown(cells, b.grow)
                rim = _grown(cells, b.grow + 1)
                rim[1:-1, 1:-1] &= ~grown
                turns.append((quarter, cells, np.fft.rfft2(grown, s=b.fft_size),
                              (np.fft.rfft2(rim, s=b.fft_size), max(1, int(rim.sum())))))
            kernels[key] = turns
        return kernels[key]

    bins = _downsize(_fill(items, sizes, spacing, margin, kernels_for), sizes, spacing, margin,
                     kernels_for)
    order = {size: k for k, size in enumerate(sizes)}
    blanks = [b.blank for b in sorted(bins, key=lambda b: order[b.blank.size])]
    return blanks, full_sheets(blanks, sizes)


def _place(part, matrix, dx=0.0):
    """Move (and turn) a part onto its blank, the blank's corner at (dx, 0)."""
    part.transform(1.0, Affine.translation(dx, 0.0) * matrix, False)


def _line_width(parts):
    """The drawing's line width, for the blanks' outlines."""
    for part in parts:
        for path in part.pathes:
            return path.params.get("lw", 0.1)
    return 0.1


def _outline(x0, blank, label, lw):
    """A Part with a blank's outline and its label above it (annotation colour)."""
    w, h = blank.size.width, blank.size.height
    part = Part("blank")
    part.pathes.append(Path([["M", x0, 0.0], ["L", x0 + w, 0.0], ["L", x0 + w, h],
                             ["L", x0, h], ["L", x0, 0.0]],
                            {"rgb": Color.ANNOTATIONS, "lw": lw}))
    text = {"ff": ("sans-serif", False, False), "fs": _LABEL_SIZE, "lw": lw,
            "rgb": Color.ANNOTATIONS, "align": "left"}
    pos = (x0, h + _LABEL_SIZE * 0.5)
    part.pathes.append(Path([["T", *pos, Affine.translation(*pos), label, text]],
                            {"rgb": Color.ANNOTATIONS, "lw": lw}))
    return part


def blank_label(k, blank, total):
    """``Blank 2 of 5: 1200 × 900`` — the label drawn above a blank."""
    return f"Blank {k} of {total}: {blank.size.width:g} × {blank.size.height:g} (not to be cut)"


def lay_out(surface, blanks):
    """Put the packed blanks in a row on the surface, each outlined and labelled.

    Moves every packed part onto its blank.  The settings tag, a reference and
    not a part to cut, goes after the last blank, recoloured to the
    annotation colour like the outlines; empty parts stay where they are.

    @param surface - The drawing surface the parts are on.
    @param blanks  - From :func:`pack`.
    """
    lw = _line_width(surface.parts)
    x0 = 0.0
    outlines = []
    for k, blank in enumerate(blanks, 1):
        for part, matrix in blank.parts:
            _place(part, matrix, x0)
        outlines.append(_outline(x0, blank, blank_label(k, blank, len(blanks)), lw))
        x0 += blank.size.width + _BLANK_GAP
    for part in surface.parts:
        if is_settings_tag(part) and _bounds(part) is not None:
            xmin, ymin, _, _ = _bounds(part)
            _place(as_reference(part), Affine.translation(-xmin, -ymin), x0)
            x0 += _bounds(part)[2] + _BLANK_GAP
    surface.parts.extend(outlines)


class HexmoSheetsMixin:
    """``--sheets``: lay a Hexmo generator's parts out on laser blanks.

    Mixed into HexmoHexagon and HexmoRectangle after the STEP mixin; call
    :meth:`_addSheetArgs` in ``__init__``.  ``close`` packs the drawn parts
    (see the module notes) before the drawing is finished, for the 2D
    formats only, and keeps ``sheets_used``: ``(blanks, full sheets)``.
    """

    def _addSheetArgs(self):
        """Register --sheets, --sheet_spacing and --sheet_margin."""
        self.argparser.add_argument(
            "--sheets", action="store", type=str, default="",
            help="Lay the parts out on laser blanks: the blanks one full sheet is cut "
                 "into, 'WIDTHxHEIGHT:COUNT' comma-separated (mm).  E.g. "
                 f"'{DEFAULT_SHEETS}': a 2400 × 1200 sheet cut at 900 for a 1300 × 900 "
                 "bed.  The parts are nested by their true shapes (small ones in the "
                 "corners and cutouts of big ones), turned where that fits better, on "
                 "as few full sheets as take them; each blank is outlined and labelled in the "
                 "annotation colour (cyan, not to be cut), side by side.  Blank "
                 "(default): the usual layout.")
        self.argparser.add_argument(
            "--sheet_spacing", action="store", type=float, default=DEFAULT_SPACING,
            help="With --sheets: least gap between two parts (mm).")
        self.argparser.add_argument(
            "--sheet_margin", action="store", type=float, default=DEFAULT_MARGIN,
            help="With --sheets: least gap between a part and the blank's edge (mm).  The "
                 "default 10 allows for blanks cut a little under size (saw kerf) or out "
                 "of square, knocked edges, and placing the blank on the bed.")

    def close(self):
        """Pack the parts onto the --sheets blanks, then finish as usual."""
        sizes = parse_sheets(getattr(self, "sheets", ""))
        # Not for the 3D formats: their SVG is drawn only to be thrown away
        # (see _hexmo_step_format).
        if sizes and self.ctx is not None and not getattr(self, "_step_discard", False):
            self.ctx.stroke()
            blanks, sheets = pack(self.surface.parts, sizes, self.sheet_spacing,
                                  self.sheet_margin)
            lay_out(self.surface, blanks)
            self.sheets_used = (blanks, sheets)
        return super().close()


# ------------------------------------------------------------------ command line

def _generator(name):
    """The generator class called ``name`` (e.g. HexmoHexagon).

    Generators live in a module named after the class in lower case; any
    other is looked for among all of them (slower: that imports every one).
    """
    import importlib

    import boxes.generators
    try:
        return getattr(importlib.import_module(f"boxes.generators.{name.lower()}"), name)
    except (ImportError, AttributeError):
        pass
    for cls in boxes.generators.getAllBoxGenerators().values():
        if cls.__name__ == name:
            return cls
    raise ValueError(f"no generator called {name!r}")


def parse_target(text):
    """``(count, generator, args)`` from ``[N@]EDIT_URL``.

    @param text - An edit URL (``…/HexmoHexagon?radius=…``), optionally
                  prefixed ``N@`` for N of that module.
    @throws ValueError - On a malformed count or a URL with no generator.
    """
    count = 1
    match = re.match(r"^(\d+)@(.*)$", text.strip())
    if match:
        count, text = int(match[1]), match[2]
    if count < 1:
        raise ValueError(f"{text}: the count must be at least 1.")
    url = urlsplit(text)
    name = url.path.strip("/").split("/")[-1]
    if not name:
        raise ValueError(f"{text}: not an edit URL (no generator name).")
    args = [f"--{k}={v}" for k, v in parse_qsl(url.query, keep_blank_values=True)
            if k not in ("render", "format", "sheets")]
    return count, name, args


def render_parts(name, args):
    """Render a generator and return ``(box, parts)``: its drawn, non-empty Parts."""
    box = _generator(name)()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    box.open()
    box.render()
    box.ctx.stroke()
    return box, [p for p in box.surface.parts if _bounds(p) is not None]


def blank_svg(box, blank, label):
    """One blank as its own SVG: the parts on it, its outline and label."""
    surface, _ = Formats().getSurface("svg")
    surface.parts = []
    parts = [copy.deepcopy(p) for p, _ in blank.parts]
    for part, (_, matrix) in zip(parts, blank.parts):
        _place(part, matrix)
    surface.parts = parts + [_outline(0.0, blank, label, _line_width(parts))]
    surface.set_metadata(box.metadata)
    return surface.finish(box.inner_corners).getvalue()


def settings_svg(box, tag):
    """The settings tag on its own, as a reference SVG (annotation colour)."""
    surface, _ = Formats().getSurface("svg")
    part = as_reference(copy.deepcopy(tag))
    xmin, ymin, _, _ = _bounds(part)
    _place(part, Affine.translation(-xmin, -ymin))
    surface.parts = [part]
    surface.set_metadata(box.metadata)
    return surface.finish(box.inner_corners).getvalue()


def main(argv=None):
    """Command line: see the module docstring."""
    argv = sys.argv[1:] if argv is None else argv
    settings = {"sheets": DEFAULT_SHEETS, "sheet_spacing": f"{DEFAULT_SPACING:g}",
                "sheet_margin": f"{DEFAULT_MARGIN:g}",
                "templates": str(HELPER_LIMITS["template"]), "guides": str(HELPER_LIMITS["guide"])}
    targets = []
    for arg in argv[1:]:
        key = arg[2:].split("=", 1)[0] if arg.startswith("--") else None
        if key in settings and "=" in arg:
            settings[key] = arg.split("=", 1)[1]
        else:
            targets.append(arg)
    if not argv or argv[0].startswith("-") or not targets:
        print(__doc__.split("\n\n")[0])
        print("usage: python -m boxes.generators._hexmo_nest OUTDIR [--sheets=…] "
              "[--sheet_spacing=…] [--sheet_margin=…] [--templates=2] [--guides=3] "
              "[N@]EDIT_URL ...")
        return 2
    out = FilePath(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    # Clear this command's own files from an earlier run (and nothing else),
    # so a smaller order doesn't leave stale blanks behind.  (Earlier
    # versions wrote one set of blanks per module: NN-<generator>-blank-….)
    for pattern in ("blank-[0-9][0-9]-*.svg", "[0-9][0-9]-*-blank-[0-9][0-9]-*.svg",
                    "[0-9][0-9]-*-settings.svg"):
        for old in out.glob(pattern):
            old.unlink()
    sizes = parse_sheets(settings["sheets"])
    spacing, margin = float(settings["sheet_spacing"]), float(settings["sheet_margin"])
    limits = {"template": int(settings["templates"]), "guide": int(settings["guides"])}
    seen, pool, box = {}, [], None
    # Render every module, then nest the whole order's parts together, so
    # one module's small parts fill the gaps around another's.
    for g, target in enumerate(targets, 1):
        count, name, args = parse_target(target)
        box, parts = render_parts(name, args)
        # The settings tag is a reference: written once, as its own file.
        for tag in [p for p in parts if is_settings_tag(p)][:1]:
            (out / f"{g:02d}-{name}-settings.svg").write_bytes(settings_svg(box, tag))
        # N of a module: N copies of every part to cut.  Only a few of each
        # different template and guide plate for the whole order: earlier
        # modules keep theirs, later ones drop repeats.
        copies = cap_helpers([copy.deepcopy(p) for _ in range(count) for p in parts
                              if not is_settings_tag(p)], limits, seen)
        pool += copies
        print(f"{g:02d} {name} ×{count}: {len(copies)} parts")
    blanks, sheets = pack(pool, sizes, spacing, margin)
    for k, blank in enumerate(blanks, 1):
        file = out / f"blank-{k:02d}-{blank.size.name}.svg"
        file.write_bytes(blank_svg(box, blank, blank_label(k, blank, len(blanks))))
    tally = {}
    for blank in blanks:
        tally[blank.size.name] = tally.get(blank.size.name, 0) + 1
    filled = sum(b.filled for b in blanks) / sum(b.size.width * b.size.height for b in blanks)
    print("blanks in all: " + ", ".join(f"{n} × {name}" for name, n in tally.items())
          + f" ({filled:.0%} covered by parts) → {sheets} full sheets to buy")
    print(f"wrote to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
