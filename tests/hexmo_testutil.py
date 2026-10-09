"""Shared helpers for the Hexmo test modules (not itself a test module).

Two things every Hexmo test that measures drawn geometry needs:

* :func:`apply` — map a point through an ``affine.Affine`` drawing transform.
  affine 3 deprecates ``*`` for matrix multiplication in favour of ``@``; the
  helper uses ``@`` and falls back to ``*`` only on an older affine without
  matmul support (pyproject allows ``affine>=2.0``).
* :data:`IGNORE_CORE_MATMUL` — a pytest ``filterwarnings`` mark for the one
  warning upstream's ``boxes/drawing.py`` raises on *every* move and point
  ("Use `@` matmul instead of `*` …").  That file is upstream's, not this
  fork's, so it isn't changed here; the filter is scoped to warnings raised
  from ``boxes.drawing`` only, so the same warning from any of *our* files
  (and every other warning) still shows.  Without it a Hexmo run collects
  millions of warnings and takes several times longer.
"""
from __future__ import annotations

import pytest
from affine import Affine

IGNORE_CORE_MATMUL = pytest.mark.filterwarnings(
    r"ignore:Use `@` matmul instead of `\*` mul operator:PendingDeprecationWarning:boxes\.drawing"
)

_HAS_MATMUL = hasattr(Affine, "__matmul__")


def apply(matrix: Affine, point):
    """Map ``point`` through ``matrix`` (matrix @ (x, y)).

    @param matrix - An ``affine.Affine`` transform (e.g. ``box.ctx._m`` or its
                    inverse ``~m``).
    @param point  - ``(x, y)``.
    @returns The transformed ``(x, y)``.
    """
    return matrix @ point if _HAS_MATMUL else matrix * point


# The original hole-pattern walls.  Access walls (--access_openings) with
# subway ports (--subway_ports) are the default; tests of the original walls'
# hole layout switch both off.
PLAIN_WALLS = ["--access_openings=0", "--subway_ports=0"]
