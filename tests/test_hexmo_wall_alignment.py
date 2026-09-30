"""Regression tests: HexmoRectangle end walls must pin to HexmoHexagon walls.

A HexmoRectangle (straight module) joins a HexmoHexagon side wall face to
face, and the two are registered with dowels through their small pilot holes
and medium holes.  For the dowels to pass straight through, every
registration hole on the rectangle's short (end) wall must sit at the same
position relative to the wall centre, which is also the track centreline, as
the matching hole on the hexagon's side wall built with the same
``--radius``, ``--thickness`` and ``--outside``.

Both walls are measured from what the generators actually draw:

* **Hexagon** — holes recorded while ``drawAlignmentHoles`` runs.  Its frame is
  the hex wall pattern frame (x up the wall, y along it, 0 … s), centred on
  the wall, so the along-wall offset is ``y − s/2``.
* **Rectangle** — holes recorded while the short-wall callback runs, mapped
  back into that callback's origin through the drawing context's affine
  transform (``ctx._m``), so any ``moveTo`` shifts inside the callback are
  included.  The rectangularWall frame has x along the wall (0 … W − 2t) and
  y = 0 at the deck (base plate) side, so the offset is ``x − (W − 2t)/2``.

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

SMALL, MEDIUM, BIG = 3.0, 12.5, 35.0   # hole radii shared by both (BIG at h=100)
TRACKED = (SMALL, MEDIUM, BIG)

# (radius, thickness, outside): the N-scale build, the HO default, and both
# --outside modes.  The original bug is 1.8 mm at N scale and 0.2 mm at HO.
BUILDS = [
    (190, 3, 1), (190, 3, 0),
    (500, 6, 1), (500, 6, 0),
    (300, 4, 1),
]


def _args(radius, thickness, outside):
    """CLI args shared by both generators for one build."""
    return [f"--radius={radius}", f"--thickness={thickness}", f"--outside={outside}"]


def hex_wall_holes(radius, thickness, outside):
    """Registration holes on a HexmoHexagon side wall.

    @returns Sorted ``(along, from_deck, radius)`` tuples for the small,
             medium and big holes.  ``along`` is the offset from the wall centre and
             ``from_deck`` is the distance from the deck-side edge of the wall
             body.
    """
    box = HexmoHexagon()
    box.parseArgs(_args(radius, thickness, outside))
    box.open()
    frames: list[tuple[float, float]] = []
    holes: list[tuple[float, float, float]] = []
    inside = [False]
    orig_hole, orig_align = box.hole, box.drawAlignmentHoles

    def hole(x, y, r=0.0, d=0.0, **kw):
        if inside[0] and len(frames) == 1 and r in TRACKED:
            holes.append((x, y, r))
        return orig_hole(x, y, r=r, d=d, **kw)

    def align(s, l, text):
        frames.append((s, l))
        inside[0] = True
        try:
            return orig_align(s, l, text)
        finally:
            inside[0] = False

    box.hole, box.drawAlignmentHoles = hole, align
    box.render()
    s, l = frames[0]
    return sorted((round(y - s / 2, 3), round(l - x, 3), r) for x, y, r in holes)


def rect_end_wall_holes(radius, thickness, outside):
    """Registration holes on a HexmoRectangle short (end) wall.

    @returns Sorted ``(along, from_deck, radius)`` tuples, as for
             :func:`hex_wall_holes`.
    """
    box = HexmoRectangle()
    box.parseArgs(_args(radius, thickness, outside))
    box.open()
    holes: list[tuple[float, float, float]] = []
    state = {"origin": None, "length": None, "calls": 0}
    orig_hole, orig_wall = box.hole, box.rectangularWall

    def hole(x, y, r=0.0, d=0.0, **kw):
        if state["origin"] is not None and r in TRACKED:
            px, py = (~state["origin"]) * (box.ctx._m * (x, y))
            holes.append((px, py, r))
        return orig_hole(x, y, r=r, d=d, **kw)

    def wall(x, y, edges="eeee", *a, callback=None, **kw):
        cbs = list(callback or [])
        if cbs and getattr(cbs[0], "__name__", "") == "short_wall_cb":
            state["calls"] += 1
            inner = cbs[0]

            def measured():
                # Record only the first short wall; both are identical.
                if state["calls"] == 1:
                    state["origin"], state["length"] = box.ctx._m, x
                try:
                    return inner()
                finally:
                    state["origin"] = None

            cbs[0] = measured
        return orig_wall(x, y, edges, *a, callback=cbs or callback, **kw)

    box.hole, box.rectangularWall = hole, wall
    box.render()
    half = state["length"] / 2
    return sorted((round(px - half, 3), round(py, 3), r) for px, py, r in holes)


def _key(holes):
    """Round measured holes to 0.01 mm so float noise can't split a match."""
    return {(round(a, 2), round(fd, 2), r) for a, fd, r in holes}


@pytest.mark.parametrize("build", BUILDS, ids=lambda b: "r{}-t{}-outside{}".format(*b))
class TestRectEndWallMatchesHexWall:

    def test_every_rect_hole_has_a_hex_counterpart(self, build) -> None:
        """Each rect end-wall hole lines up with a hex wall hole of the same size.

        The rect cuts a deliberate subset: no end-most corner column, and no
        gap clusters, because those would land on the divider finger slots.
        So the check is subset, not equality.
        """
        rect, hexa = _key(rect_end_wall_holes(*build)), _key(hex_wall_holes(*build))
        assert rect <= hexa, f"rect holes with no hex partner: {sorted(rect - hexa)}"

    def test_registration_pins_present(self, build) -> None:
        """The pin directly above/below each end medium exists on the rect."""
        rect = rect_end_wall_holes(*build)
        medium_alongs = {round(a, 2) for a, _, r in rect if r == MEDIUM}
        assert len(medium_alongs) == 2
        pins = [h for h in rect if h[2] == SMALL and round(h[0], 2) in medium_alongs]
        assert len(pins) == 4

    def test_holes_symmetric_about_wall_centre(self, build) -> None:
        rect = _key(rect_end_wall_holes(*build))
        assert rect == {(round(-a, 2) + 0.0, fd, r) for a, fd, r in rect}
