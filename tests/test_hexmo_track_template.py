"""Tests for the Tracksetta-style track-laying template (--track_template).

The template is a strip exactly ``--track_gauge`` wide (less any
``--track_template_clearance``) that sits between the rails and follows the
module's etched centreline route.  On a curve that route is a straight lead-in,
a 60° arc at the etched radius, and another lead-in.  ``--track_template_segments``
splits the route into equal-length pieces.

The geometry is tested on the template's centreline route and band outline
(true dimensions; boxes' edge/corner burn compensation keeps the cut
true-size).  The render tests check which templates each generator adds.

These tests avoid lxml, so they run in the Docker image.
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

# Silence only the matmul deprecation raised by upstream's boxes/drawing.py
# (see hexmo_testutil); every other warning still shows.
pytestmark = IGNORE_CORE_MATMUL

from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

# Preferred settings (docs/hexmohexagon/README-*-scale.md).
N_HEX = ["--radius=220", "--thickness=3", "--h=100", "--trapezoid=1",
         "--track_lead_in=26", "--track_gauge=9", "--track_template=1"]
HO_HEX = ["--radius=500", "--thickness=6", "--h=100", "--trapezoid=1",
          "--track_lead_in=23", "--track_line_count=2", "--track_spacing=80",
          "--track_gauge=16.5", "--track_template=1"]


def parsed(cls, args):
    box = cls()
    box.parseArgs(args)
    return box


def route_length(route):
    """Centreline length of a route of ('line', L) / ('arc', deg, r) steps."""
    return sum(s[1] if s[0] == "line" else abs(math.radians(s[1])) * s[2] for s in route)


def record_templates(cls, args):
    """Render and record every drawTrackTemplate call: (route, label)."""
    box = parsed(cls, args)
    box.open()
    calls = []
    orig = box.drawTrackTemplate

    def spy(route, label, *a, **kw):
        calls.append((route, label))
        return orig(route, label, *a, **kw)

    box.drawTrackTemplate = spy
    box.render()
    box.close()
    return box, calls


class TestRoutes:

    def test_n_curve_route_matches_the_etched_track(self) -> None:
        box, calls = record_templates(HexmoHexagon, N_HEX)
        (route, label), = calls
        r_in = 220 - 3 / math.cos(math.radians(30))
        rho = (r_in * math.sqrt(3) / 2 - 26) * math.sqrt(3)
        assert [s[0] for s in route] == ["line", "arc", "line"]
        assert route[0][1] == route[2][1] == pytest.approx(26)
        assert abs(route[1][1]) == pytest.approx(60)
        assert route[1][2] == pytest.approx(rho)          # 279.8 mm
        assert "R280" in label and "9" in label

    def test_one_curve_template_per_track(self) -> None:
        _, calls = record_templates(HexmoHexagon, HO_HEX)
        radii = sorted(round(route[1][2]) for route, _ in calls)
        assert radii == [660, 740]

    def test_full_hex_curves_share_one_template_per_track_plus_a_straight(self) -> None:
        args = [a for a in HO_HEX if a != "--trapezoid=1"] + [
            "--track_left=1", "--track_right=1", "--track_middle=1"]
        box, calls = record_templates(HexmoHexagon, args)
        curves = [r for r, _ in calls if len(r) == 3]
        straights = [r for r, _ in calls if len(r) == 1]
        assert sorted(round(r[1][2]) for r in curves) == [660, 740]
        # The middle straight runs apothem to apothem: 2·A of the inner hex.
        r_in = 500 - 6 / math.cos(math.radians(30))
        (straight,), = straights
        assert straight == ("line", pytest.approx(r_in * math.sqrt(3)))

    def test_full_hex_without_routes_has_no_templates(self) -> None:
        _, calls = record_templates(HexmoHexagon, [a for a in HO_HEX if a != "--trapezoid=1"])
        assert calls == []

    def test_rectangle_gets_one_straight_of_the_track_length(self) -> None:
        box, calls = record_templates(HexmoRectangle, [
            "--radius=500", "--thickness=6", "--track_line_count=2",
            "--track_gauge=16.5", "--track_template=1"])
        (route, label), = calls
        # The etched track's length H, end wall to end wall: the inner long
        # axis, which with --outside on uses the inner radius (as the hex does).
        r_in = 500 - 6 / math.cos(math.radians(30))
        assert route == [("line", pytest.approx(r_in * math.sqrt(3)))]
        assert label == "straight 16.5mm"

    def test_flag_off_draws_no_template(self) -> None:
        for cls, args in ((HexmoHexagon, N_HEX), (HexmoRectangle, ["--radius=220"])):
            _, calls = record_templates(cls, [a for a in args if a != "--track_template=1"])
            assert calls == []


class TestPiecesAndOutline:

    ROUTE = [("line", 26.0), ("arc", -60.0, 279.77), ("line", 26.0)]

    @pytest.mark.parametrize("n", [1, 2, 3, 5])
    def test_segments_split_into_equal_lengths(self, n) -> None:
        box = parsed(HexmoHexagon, N_HEX + [f"--track_template_segments={n}"])
        pieces = box._templatePieces(self.ROUTE)
        assert len(pieces) == n
        total = route_length(self.ROUTE)
        for p in pieces:
            assert route_length(p) == pytest.approx(total / n)
        # Arc angle is conserved across the pieces.
        assert sum(abs(s[1]) for p in pieces for s in p if s[0] == "arc") == pytest.approx(60)

    @pytest.mark.parametrize("gauge, clearance", [(9, 0), (16.5, 0), (16.5, 0.3)])
    def test_band_width_is_gauge_less_clearance(self, gauge, clearance) -> None:
        box = parsed(HexmoHexagon, N_HEX + [f"--track_gauge={gauge}",
                                            f"--track_template_clearance={clearance}"])
        ops = box._templateOutline(self.ROUTE)
        w = gauge - clearance
        caps = [op[1] for op in ops if op[0] == "edge" and op[1] == pytest.approx(w)]
        assert len(caps) == 2
        arcs = sorted(op[2] for op in ops if op[0] == "corner" and op[2] > 0)
        assert arcs == pytest.approx([279.77 - w / 2, 279.77 + w / 2])
        # A closed counter-clockwise outline turns through +360° in total.
        assert sum(op[1] for op in ops if op[0] == "corner") == pytest.approx(360)

    def test_outline_closes(self) -> None:
        box = parsed(HexmoHexagon, N_HEX)
        for piece in box._templatePieces(self.ROUTE) + [[("line", 300.0)]]:
            pts = box._templateTrace(box._templateOutline(piece))
            assert pts[-1] == pytest.approx(pts[0], abs=1e-6)


class TestValidation:

    @pytest.mark.parametrize("opt, match", [
        ("--track_gauge=0", "track_gauge"),
        ("--track_template_clearance=-1", "clearance"),
        ("--track_template_clearance=9", "clearance"),
        ("--track_template_segments=0", "segments"),
    ])
    def test_bad_values_are_refused(self, opt, match) -> None:
        box = parsed(HexmoHexagon, N_HEX + [opt])
        box.open()
        with pytest.raises(ValueError, match=match):
            box.render()


class TestPieceMarks:
    """With segments, matching end marks show which pieces join, and how."""

    def test_end_marks(self) -> None:
        marks = HexmoHexagon._templateEndMarks
        assert [marks(i, 1) for i in range(1)] == [("EDGE", "EDGE")]
        assert [marks(i, 3) for i in range(3)] == [("EDGE", "A"), ("A", "B"), ("B", "EDGE")]

    @staticmethod
    def _etched_per_piece(args):
        """Render and group the etched template texts by piece."""
        box = parsed(HexmoHexagon, args)
        box.open()
        pieces, inside = [], [False]
        o_text, o_move, o_tmpl = box.text, box.move, box.drawTrackTemplate

        def text(t, *a, **kw):
            if inside[0]:
                pieces[-1].append(t)
            return o_text(t, *a, **kw)

        def move(x, y, where, before=False, label=""):
            if inside[0] and before:
                pieces.append([])
            return o_move(x, y, where, before=before, label=label)

        def tmpl(*a, **kw):
            inside[0] = True
            try:
                return o_tmpl(*a, **kw)
            finally:
                inside[0] = False

        box.text, box.move, box.drawTrackTemplate = text, move, tmpl
        box.render()
        return pieces

    def test_three_pieces_are_etched_with_matching_joints(self) -> None:
        pieces = self._etched_per_piece(N_HEX + ["--track_template_segments=3"])
        assert [sorted(p) for p in pieces] == [
            sorted(["EDGE", "R280 9mm  1/3", "A"]),
            sorted(["A", "R280 9mm  2/3", "B"]),
            sorted(["B", "R280 9mm  3/3", "EDGE"]),
        ]

    def test_single_piece_has_edge_at_both_ends(self) -> None:
        (piece,) = self._etched_per_piece(N_HEX)
        assert sorted(piece) == sorted(["EDGE", "R280 9mm", "EDGE"])
