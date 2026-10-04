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

from io import BytesIO

from boxes.formats import Formats
from boxes.generators import _hexmo_step

STEP = "step"

# How the web server labels the download.
Formats.http_headers.setdefault(STEP, [("Content-type", "model/step")])


class HexmoStepFormatMixin:
    """``--format step`` for a Hexmo generator.

    Host requirements: list this mixin before ``Boxes`` in the class bases (so
    its ``open``/``close`` wrap Boxes'), call :meth:`_addStepFormat` in
    ``__init__``, and set ``_STEP_KIND`` to ``"hexagon"`` or ``"rectangle"``.
    """

    _STEP_KIND = "hexagon"

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

    def open(self):
        """Open as usual; for STEP, onto an SVG surface that is thrown away."""
        if self.format != STEP:
            return super().open()
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
        try:
            if self._STEP_KIND == "rectangle":
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
