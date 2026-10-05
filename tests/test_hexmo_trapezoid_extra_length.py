"""Tests for the trapezoid deck/floor with FingerJoint_extra_length (BOX-65).

``FingerJoint_extra_length`` makes every finger stand proud by that much
extra material, to be sanded flush after glue-up.  On the full hexagon every
edge's finger tips move out by exactly the extra.  The trapezoid panel used
to mix two corner rules (``edgeCorner`` at V0/V1, which grows with the edge
width, and hand-made V2/V5 miters with a bare thickness), so with any extra
its outline overshot its own start by √3 × extra and came out skewed: the
left slant's fingers ended short of flush.  These tests pin the fixed
behaviour: the outline closes, and every edge grows by the extra, while the
panel's centre frame (kites, support slots, the 3D export) stays put.

Outlines are read in the panel's own frame, as the 3D export reads them (no
build123d needed).  These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import math
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

from boxes.generators import _hexmo_step
from boxes.generators.hexmohexagon import HexmoHexagon

T = 3.0
TRAPEZOID = ["--radius=220", f"--thickness={T:g}", "--h=100", "--trapezoid=1",
             "--bottom=spoke", "--edge_width=22", "--spoke_width=60"]
S3 = math.sqrt(3) / 2
# Outward normals of the trapezoid's four sides, in the panel frame.
NORMALS = {"bottom": (0, -1), "right slant": (S3, -0.5), "join edge": (0, 1),
           "left slant": (-S3, -0.5)}


def loops(extra, panel, args=TRAPEZOID):
    """A panel's cut loops at the given extra_length, in its own frame.

    @param extra - FingerJoint_extra_length (multiples of thickness).
    @param panel - ``deck`` or ``floor``.
    @returns ``(outline, holes)``: the outline as an open point list (first
             point = path start, last = path end), and each hole as a list of
             points.
    """
    box = HexmoHexagon()
    box.parseArgs(args + [f"--FingerJoint_extra_length={extra}"])
    frame = next(f for f in _hexmo_step._render_frames(box) if f.name == panel)
    inv = ~frame.matrix
    chains = _hexmo_step._cut_chains(frame.part)

    def points(chain):
        return [tuple(inv * chain[0][1])] + [tuple(inv * seg[-1]) for seg in chain]

    outline = max(chains, key=len)
    return points(outline), [points(c) for c in chains if c is not outline]


def reach(points, normal):
    """How far the points reach along ``normal`` (the side's finger tips)."""
    return max(x * normal[0] + y * normal[1] for x, y in points)


def centroids(holes):
    """The holes' vertex centroids, sorted, as one flat list (for approx)."""
    points = sorted((round(sum(x for x, _ in h) / len(h), 3), round(sum(y for _, y in h) / len(h), 3))
                    for h in holes)
    return [c for p in points for c in p]


@pytest.mark.parametrize("panel", ["deck", "floor"])
@pytest.mark.parametrize("extra", [0.1, 0.25])
class TestWithExtraLength:

    def test_outline_closes(self, panel, extra) -> None:
        outline, _ = loops(extra, panel)
        assert math.dist(outline[0], outline[-1]) < 1e-6

    def test_every_edge_grows_by_the_extra(self, panel, extra) -> None:
        base, _ = loops(0, panel)
        grown, _ = loops(extra, panel)
        offsets = {side: reach(grown, n) - reach(base, n) for side, n in NORMALS.items()}
        assert offsets == pytest.approx({side: extra * T for side in NORMALS}, abs=1e-6)

    def test_holes_stay_put(self, panel, extra) -> None:
        # Kites, support slots and riser slots are drawn from the centre
        # frame, which must not move relative to the panel's sides.
        _, base = loops(0, panel)
        _, grown = loops(extra, panel)
        assert len(grown) == len(base)
        assert centroids(grown) == pytest.approx(centroids(base), abs=2e-3)


def test_matches_the_full_hexagon() -> None:
    # The reference behaviour: every side of the full hexagon's deck grows by
    # the extra.
    hexagon = [a for a in TRAPEZOID if a != "--trapezoid=1"]
    base, _ = loops(0, "deck", hexagon)
    grown, _ = loops(0.1, "deck", hexagon)
    for k in range(6):
        th = math.radians(-90 + 60 * k)
        n = (math.cos(th), math.sin(th))
        assert reach(grown, n) - reach(base, n) == pytest.approx(0.1 * T, abs=1e-6)


def test_miter_without_extra_is_the_original() -> None:
    # With no extra the V2/V5 steps are the long-standing t/√3 and 2t/√3, so
    # cut files without extra_length are unchanged.
    box = HexmoHexagon()
    box.parseArgs([f"--thickness={T:g}"])
    assert box._trapezoidMiter(T, T) == (T / math.sqrt(3.0), 2.0 * T / math.sqrt(3.0))
