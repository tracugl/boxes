"""Tests for ``--format svg_3d``: the module assembled, as a line drawing.

HexmoHexagon and HexmoRectangle can output their 3D assembly drawn from the
front right, above, with hidden lines removed, as an SVG: a quick look at
the built module without CAD.  ``--view_deck`` adds the deck (off by default,
so you see inside); ``--step_detail`` picks exact or simple parts.

Needs the optional ``step`` dependency for the drawing itself.
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

from boxes.generators import _hexmo_step
from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N, HELIX_RING_N
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle


def output(cls, args):
    box = cls()
    box.parseArgs(args)
    box.open()
    box.render()
    return box.close().getvalue()


def lines(svg):
    return len(re.findall(rb"<path", svg))


@pytest.mark.parametrize("cls", [HexmoHexagon, HexmoRectangle])
def test_offered_by_the_hexmo_generators(cls) -> None:
    box = cls()
    choices = next(a.choices for a in box.argparser._actions if a.dest == "format")
    assert "svg_3d" in choices


def test_hexagon_drawing() -> None:
    pytest.importorskip("build123d")
    svg = output(HexmoHexagon, HELIX_RING_N["M6"] + ["--format=svg_3d"])
    assert b"<svg" in svg[:400] and lines(svg) > 50


def test_rectangle_drawing() -> None:
    pytest.importorskip("build123d")
    svg = output(HexmoRectangle, HELIX_ENTRY_N + ["--format=svg_3d"])
    assert b"<svg" in svg[:400] and lines(svg) > 10


def test_deck_toggle() -> None:
    pytest.importorskip("build123d")
    open_top = output(HexmoHexagon, HELIX_RING_N["M1"] + ["--format=svg_3d",
                                                         "--step_detail=simple"])
    decked = output(HexmoHexagon, HELIX_RING_N["M1"] + ["--format=svg_3d",
                                                       "--step_detail=simple", "--view_deck=1"])
    # The deck hides most of the inside, so the drawings differ.
    assert open_top != decked


def test_only_cut_parts_are_drawn() -> None:
    # The drawing shows what is cut (the sheet's red lines): no track
    # ribbons or clearance boxes; the deck only when asked for.
    pytest.importorskip("build123d")
    box = HexmoHexagon()
    box.parseArgs(HELIX_RING_N["M6"])
    parts = _hexmo_step.exact_hexmo_parts(box, clearance="all")
    drawn = _hexmo_step._drawn_parts(parts, deck=False)
    assert drawn and all(p.kind not in ("track", "clearance") for p in drawn)
    assert "deck" not in {p.name for p in drawn}
    assert "deck" in {p.name for p in _hexmo_step._drawn_parts(parts, deck=True)}


def test_clear_error_without_the_dependency(monkeypatch) -> None:
    def missing():
        raise ImportError("No module named 'build123d'")

    monkeypatch.setattr(_hexmo_step, "_bd", missing)
    with pytest.raises(ValueError, match=r"pip install \.\[step\]"):
        output(HexmoHexagon, ["--format=svg_3d"])
