"""Tests for ``--format step`` on the Hexmo generators.

HexmoHexagon and HexmoRectangle offer ``step`` as an output format, next to
the usual laser formats: the generator renders as normal (so every check
still runs), then returns the module's 3D assembly as a STEP file instead of
the SVG.  The web form's Format menu lists it, and the server sends any
non-SVG format as a download, so it needs no server changes.  Without the
optional ``step`` dependency it fails with a clear message, and the laser
formats are unaffected.

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

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators import _hexmo_step
from boxes.generators._hexmo_helix_ring import HELIX_ENTRY_N, HELIX_RING_N
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle


def format_choices(cls):
    box = cls()
    return next(a.choices for a in box.argparser._actions if a.dest == "format")


def output(cls, args):
    """Run a generator the way the web server does; return the output bytes."""
    box = cls()
    box.parseArgs(args)
    box.metadata["reproducible"] = True
    box.open()
    box.render()
    return box.close().getvalue()


class TestChoice:

    @pytest.mark.parametrize("cls", [HexmoHexagon, HexmoRectangle])
    def test_offered_by_the_hexmo_generators(self, cls) -> None:
        assert "step" in format_choices(cls)

    def test_not_added_to_other_generators(self) -> None:
        from boxes.generators.closedbox import ClosedBox
        assert "step" not in format_choices(ClosedBox)


class TestOutput:

    def test_hexagon(self) -> None:
        pytest.importorskip("build123d")
        data = output(HexmoHexagon, HELIX_RING_N["M6"] + ["--format=step"])
        assert data.startswith(b"ISO-10303-21")
        assert b"riser bed" in data and b"clearance" in data

    def test_rectangle(self) -> None:
        pytest.importorskip("build123d")
        data = output(HexmoRectangle, HELIX_ENTRY_N + ["--format=step"])
        assert data.startswith(b"ISO-10303-21")
        assert b"long support" in data

    def test_clearance_option(self) -> None:
        pytest.importorskip("build123d")
        data = output(HexmoHexagon, HELIX_RING_N["M6"] + ["--format=step",
                                                         "--step_clearance=none"])
        assert b"clearance" not in data

    def test_settings_that_refuse_to_render_refuse_to_export(self) -> None:
        with pytest.raises(ValueError):
            output(HexmoHexagon, ["--format=step", "--risers=3-5~999..1"])

    def test_svg_unaffected(self) -> None:
        assert output(HexmoHexagon, []).lstrip().startswith(b"<?xml")


def test_clear_error_without_the_dependency(monkeypatch) -> None:
    def missing():
        raise ImportError("No module named 'build123d'")

    monkeypatch.setattr(_hexmo_step, "_bd", missing)
    with pytest.raises(ValueError, match=r"pip install \.\[step\]"):
        output(HexmoHexagon, ["--format=step"])
