"""``--format step``: a Hexmo generator's 3D assembly instead of its laser parts.

Mixed into HexmoHexagon and HexmoRectangle.  It adds ``step`` to their
``--format`` choices (on those two generators only) and a ``--step_clearance``
option.  With ``step`` chosen, the generator still opens and renders as usual
(so every setting is checked exactly as for the laser output), drawing onto a
throw-away SVG surface; ``close`` then returns the module's STEP assembly
(see :mod:`_hexmo_step`) in place of the SVG.

The web server needs no changes: the Format menu is built from the choices,
and any format other than SVG is sent as a download named after the
generator, here ``HexmoHexagon.step``.

Needs the optional ``step`` dependency (``pip install .[step]``).  Without it,
asking for ``step`` fails with a clear message, and the other formats are
unaffected (nothing here imports it until a STEP file is wanted).

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from boxes.formats import Formats
from boxes.generators import _hexmo_step

STEP = "step"

# How the web server labels the download.
Formats.http_headers.setdefault(STEP, [("Content-type", "model/step")])


@dataclass
class PartFrame:
    """Where one drawn part sits in the assembled module.

    Recorded while the part is being drawn (see
    :meth:`HexmoStepFormatMixin._stepFrame`).

    @ivar part   - The drawing surface's Part the outline went into.
    @ivar matrix - The drawing transform at the part's local origin (sheet ←
                   local), so its outline can be mapped back to local x/y.
    @ivar name   - Part name in the 3D assembly.
    @ivar kind   - Colour class (``panel``, ``wall``, ``support``, ``riser``),
                   or ``bedholes`` for a riser bed's outline, whose holes are
                   cut into the sloping 3D bed.
    @ivar origin, ex, ey - Where local (0, 0) sits in the assembly and the
                   directions of local x and y (3D, unit).
    @ivar depth  - The part's thickness span along ex × ey, ``(z0, z1)``.
    """

    part: object
    matrix: object
    name: str
    kind: str
    origin: tuple
    ex: tuple
    ey: tuple
    depth: tuple


class HexmoStepFormatMixin:
    """``--format step`` for a Hexmo generator.

    Host requirements: list this mixin before ``Boxes`` in the class bases (so
    its ``open``/``close`` wrap Boxes'), call :meth:`_addStepFormat` in
    ``__init__``, and set ``_STEP_KIND`` to ``"hexagon"`` or ``"rectangle"``.
    """

    _STEP_KIND = "hexagon"
    # Set to a list while an exact 3D export renders; None otherwise, so the
    # drawing code's _stepFrame calls cost nothing for normal output.
    _step_frames = None

    def _stepFrame(self, name, kind, origin, ex, ey, depth):
        """Record the part being drawn and where it goes in the assembly.

        Call with the turtle at the part's local origin.  Does nothing unless
        an exact 3D export is rendering.

        @param name   - Part name, e.g. ``wall edge 3``.
        @param kind   - See :class:`PartFrame`.
        @param origin - 3D point where local (0, 0) sits.
        @param ex, ey - 3D unit directions of local x and y.
        @param depth  - Thickness span ``(z0, z1)`` along ex × ey.
        """
        if self._step_frames is None:
            return
        self._step_frames.append(PartFrame(self.surface._p, self.ctx._m, name, kind,
                                           tuple(origin), tuple(ex), tuple(ey), tuple(depth)))

    def _addStepFormat(self):
        """Offer ``step`` in --format and add --step_clearance."""
        for action in self.argparser._actions:
            if action.dest == "format":
                # A new list: the original may be shared with other generators.
                action.choices = list(action.choices) + [STEP]
                action.help = (action.help or "") + (
                    "  'step' (HexmoHexagon and HexmoRectangle): the module assembled "
                    "in 3D, to open in CAD (Onshape, FreeCAD, Fusion …), instead of "
                    "the laser parts.")
        self.argparser.add_argument(
            "--step_clearance", action="store", type=str, default="under",
            choices=list(_hexmo_step.CLEARANCE_MODES),
            help="With --format step: where to show the train-clearance boxes "
                 "(--train_envelope high, --under_track_width wide).  'under' "
                 "(default): over the tracks on risers, the ones that pass under or "
                 "through the deck; 'all': over every track; 'none'.")
        self.argparser.add_argument(
            "--step_detail", action="store", type=str, default="exact",
            choices=["exact", "simple"],
            help="With --format step: 'exact' (default) builds every part from "
                 "its real cut outline (finger joints, holes, kites, notches), "
                 "at its nominal size (no burn), so you can check how the parts "
                 "fit; 'simple' uses plain slabs, quicker and lighter.")

    def open(self):
        """Open as usual; for STEP, onto an SVG surface that is thrown away."""
        if self.format != STEP:
            return super().open()
        if self.step_detail == "exact":
            # Record each assembled part's frame as it is drawn, at nominal
            # size (no burn compensation).
            self.burn = 0.0
            self._step_frames = []
        self.format = "svg"
        try:
            return super().open()
        finally:
            self.format = STEP

    def close(self):
        """Finish as usual; for STEP, return the 3D assembly instead.

        @returns A file-like object with the output, as Boxes.close does.
        @throws ValueError - For STEP without the optional dependency (with how
                             to install it), or from the 3D export's checks.
        """
        if self.format != STEP:
            return super().close()
        if self.ctx is None:
            return None
        self.format = "svg"
        try:
            super().close()                 # finish (and discard) the SVG
        finally:
            self.format = STEP
        frames, self._step_frames = self._step_frames, None
        try:
            if self.step_detail == "exact":
                build = (_hexmo_step.exact_rect_parts if self._STEP_KIND == "rectangle"
                         else _hexmo_step.exact_hexmo_parts)
                parts = build(self, self.step_clearance, frames=frames)
            elif self._STEP_KIND == "rectangle":
                parts = _hexmo_step.rect_parts(self, self.step_clearance)
            else:
                parts = _hexmo_step.hexmo_parts(self, self.step_clearance)
            bd = _hexmo_step._bd()
        except ImportError as err:
            # A ValueError is shown to the web user as an error page, not a
            # server error; say what to install.
            raise ValueError(
                "--format step needs the optional 'step' dependency (build123d and "
                f"the OpenCascade kernel): pip install .[step]  ({err})") from None
        data = BytesIO()
        bd.export_step(_hexmo_step.assembly(parts, label=type(self).__name__), data)
        data.seek(0)
        return data
