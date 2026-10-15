"""Tests for --FingerJoint_glue_gap (this fork): deeper sockets, tips unchanged.

A plug edge ('f') cuts the spaces between its fingers (and its plain ends)
the gap deeper into the panel; a socket edge ('F') cuts its notches the gap
deeper.  Either way the finger and land tips stay where they were, so a
joint still finishes flush, with room at the bottom of each socket for
paint and glue.

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

from boxes import Boxes, edges
from boxes.generators.universalbox import UniversalBox

T = 6.0


class Wall(Boxes):
    """One 300 × 100 wall with a chosen bottom edge and plain other edges."""

    def __init__(self, bottom) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings, finger=5, space=5)
        self.bottom = bottom

    def render(self):
        self.rectangularWall(300, 100, self.bottom + "eee")


def bottom_levels(bottom, gap):
    """The heights (mm above the wall's lowest point) of the bottom edge's
    horizontal runs, and the wall's overall height."""
    box = Wall(bottom)
    box.parseArgs([f"--thickness={T:g}", f"--FingerJoint_glue_gap={gap:g}", "--reference=0",
                   "--labels=0", "--burn=0"])
    box.open()
    box.render()
    box.ctx.stroke()
    pts = [(c[1], c[2]) for part in box.surface.parts for path in part.pathes
           for c in path.path if c[0] in "ML"]
    ymin = min(y for _, y in pts)
    ymax = max(y for _, y in pts)
    levels = set()
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(y0 - y1) < 1e-6 and abs(x0 - x1) > 1.0 and y0 - ymin < 3 * T:
            levels.add(round(y0 - ymin, 3))
    return sorted(levels), round(ymax - ymin, 3)


def test_plug_edge_spaces_step_in_tips_stay() -> None:
    # Fingers stick out one thickness below the wall's edge line.  With a
    # 0.3 mm gap the spaces between them move 0.3 mm into the wall, and the
    # finger tips (the lowest points) and the wall's height don't change.
    plain, height = bottom_levels("f", 0)
    gapped, height_g = bottom_levels("f", 0.05)
    assert plain == [0.0, T]
    assert gapped == [0.0, T + 0.3]
    assert height_g == height


def test_socket_edge_notches_deeper_lands_stay() -> None:
    # Notches cut one thickness into the wall; with the gap, 0.3 mm deeper.
    # The lands between them (the lowest points) don't move.
    plain, height = bottom_levels("F", 0)
    gapped, height_g = bottom_levels("F", 0.05)
    assert plain == [0.0, T]
    assert gapped == [0.0, T + 0.3]
    assert height_g == height


@pytest.mark.parametrize("gap", [0, 0.05])
def test_a_plain_edge_is_untouched(gap) -> None:
    levels, _ = bottom_levels("e", gap)
    assert levels == [0.0]


def test_zero_gap_is_the_usual_drawing() -> None:
    def svg(extra):
        box = UniversalBox()
        box.parseArgs(["--reference=0"] + extra)
        box.metadata["reproducible"] = True
        box.open()
        box.render()
        # The drawing only: the header records the options given.
        return re.sub(r"<!--.*?-->|<metadata>.*?</metadata>|<title>.*?</title>|<desc>.*?</desc>",
                      "", box.close().getvalue().decode(), flags=re.S)

    assert svg([]) == svg(["--FingerJoint_glue_gap=0"])
    assert svg([]) != svg(["--FingerJoint_glue_gap=0.05"])


# ------------------------------------------------------------------ 3D export

def L(a, b):
    return ("L", a, b)


def loop_of(*pts):
    return [L(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))]


def corners(loop):
    return [tuple(round(v, 6) for v in seg[1]) for seg in loop]


def test_tidy_drops_a_spike() -> None:
    from boxes.generators._hexmo_step import _tidy_loop
    # A square whose bottom edge steps in 0.3 at the start, from the corner
    # the left edge ends at: down to (0, 0), back up to (0, 0.3).
    loop = loop_of((0, 10), (0, 0), (0, 0.3), (10, 0.3), (10, 10))
    assert corners(_tidy_loop(loop)) == [(0, 10), (0, 0.3), (10, 0.3), (10, 10)]


def test_tidy_joins_a_corner_loop() -> None:
    from boxes.generators._hexmo_step import _tidy_loop
    # Both edges step in 0.3: the outline runs past the true corner (0.3, 0.3),
    # round two 0.3 mm runs and back across itself.
    loop = loop_of((0.3, 10), (0.3, 0), (0, 0), (0, 0.3), (10, 0.3), (10, 10))
    assert corners(_tidy_loop(loop)) == [(0.3, 10), (0.3, 0.3), (10, 0.3), (10, 10)]


def test_tidy_leaves_a_clean_loop_alone() -> None:
    from boxes.generators._hexmo_step import _tidy_loop
    # Fingers: real 6 mm steps, no detours.
    loop = loop_of((0, 0), (15, 0), (15, -6), (45, -6), (45, 0), (60, 0), (60, 80), (0, 80))
    assert _tidy_loop(loop) == loop


@pytest.mark.parametrize("module", ["M1", "entry"])
def test_glue_gap_parts_are_valid_solids(module) -> None:
    pytest.importorskip("build123d")
    from boxes.generators import _hexmo_step as S
    from boxes.generators._hexmo_helix_ring import helix_entry_ho, helix_ring_ho
    from boxes.generators.hexmohexagon import HexmoHexagon
    from boxes.generators.hexmorectangle import HexmoRectangle
    if module == "entry":
        box, parts_of = HexmoRectangle(), S.exact_rect_parts
        box.parseArgs(helix_entry_ho() + ["--FingerJoint_glue_gap=0.05"])
    else:
        box, parts_of = HexmoHexagon(), S.exact_hexmo_parts
        box.parseArgs(helix_ring_ho()[module] + ["--FingerJoint_glue_gap=0.05"])
    parts = parts_of(box, clearance="none")
    assert parts and [p.name for p in parts if not p.solid.is_valid] == []
