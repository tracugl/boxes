"""Tests for --sheets: packing Hexmo parts onto laser blanks (_hexmo_nest).

The blanks one full sheet is cut into (e.g. two 1200 × 900 and one 600 × 900
from a 2400 × 1200 sheet) are filled with the parts' true shapes, holes
included, turned where that fits better, on as few full sheets as will take
them.

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

import copy

import numpy as np

from boxes.drawing import Part, Path as DrawPath
from boxes.generators import _hexmo_nest as N
from boxes.generators import _hexmo_nest_shape as S
from boxes.generators.hexmohexagon import HexmoHexagon

SIZES = N.parse_sheets(N.DEFAULT_SHEETS)
# An N trapezoid module (the dogbone's), small and quick to render.
N_TRAPEZOID = ["--radius=250", "--thickness=3", "--h=80", "--edge_width=22", "--spoke_width=60",
               "--support_length=55", "--track_lead_in=20", "--track_width=17",
               "--trapezoid=1", "--track_routes=3:25-5:25,3:-15-5:-15", "--labels=0",
               "--reference=0"]


def ring(points, colour=(1, 0, 0)):
    """A closed drawing Path through the points."""
    cmds = [["M", *points[0]]] + [["L", *pt] for pt in points[1:]] + [["L", *points[0]]]
    return DrawPath(cmds, {"rgb": colour, "lw": 0.1})


def rect_points(w, h, x=0.0, y=0.0):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def rect_part(w, h, x=0.0, y=0.0):
    """A drawing Part holding one w × h rectangle at (x, y)."""
    part = Part("test")
    part.pathes.append(ring(rect_points(w, h, x, y)))
    return part


def frame_part(w, h, border):
    """A w × h rectangle with a hole leaving a ``border`` wide frame."""
    part = rect_part(w, h)
    part.pathes.append(ring(rect_points(w - 2 * border, h - 2 * border, border, border)))
    return part


def placed(part, matrix):
    """A copy of the part moved onto its blank."""
    q = copy.deepcopy(part)
    N._place(q, matrix)
    return q


class TestParse:

    def test_default(self) -> None:
        assert SIZES == [N.BlankSize(1200, 900, 2), N.BlankSize(600, 900, 1)]

    def test_blank_is_none(self) -> None:
        assert N.parse_sheets("") == []

    @pytest.mark.parametrize("text", ["1200", "1200x", "x900", "0x900", "1200x900:0", "a x b"])
    def test_bad(self, text) -> None:
        with pytest.raises(ValueError, match="--sheets"):
            N.parse_sheets(text)

    def test_target(self) -> None:
        count, name, args = N.parse_target(
            "10@http://localhost:4455/HexmoHexagon?radius=250&trapezoid=1&render=1")
        assert (count, name, args) == (10, "HexmoHexagon", ["--radius=250", "--trapezoid=1"])


class TestPack:

    def test_fewest_full_sheets(self) -> None:
        # Three 1100 × 800 parts: one per 1200 × 900 blank, so two full sheets
        # (each gives two such blanks).
        blanks, sheets = N.pack([rect_part(1100, 800) for _ in range(3)], SIZES)
        assert sheets == 2
        assert [b.size.name for b in blanks] == ["1200x900"] * 3

    def test_small_parts_share_a_blank(self) -> None:
        blanks, sheets = N.pack([rect_part(100, 100) for _ in range(20)], SIZES)
        assert (len(blanks), sheets) == (1, 1)

    def test_turned_to_fit(self) -> None:
        # 850 wide × 500 high only fits the 600 × 900 blank turned on its side.
        blanks, _ = N.pack([rect_part(850, 500)], [N.BlankSize(600, 900)])
        (part, matrix), = blanks[0].parts
        assert abs(matrix.b) > 0.5  # a quarter turn
        e = placed(part, matrix).extents()
        assert (round(e.xmax - e.xmin), round(e.ymax - e.ymin)) == (500, 850)

    def test_too_big_is_refused(self) -> None:
        with pytest.raises(ValueError, match="fits none of the blanks"):
            N.pack([rect_part(1250, 500)], SIZES)

    def test_parts_stay_apart_and_inside(self) -> None:
        parts = [rect_part(300 + 7 * k, 200 + 5 * k, x=1000 * k, y=-50 * k) for k in range(12)]
        blanks, _ = N.pack(parts, SIZES, spacing=4, margin=5)
        for blank in blanks:
            boxes_ = []
            for part, matrix in blank.parts:
                e = placed(part, matrix).extents()
                assert e.xmin >= 5 - 1e-6 and e.ymin >= 5 - 1e-6
                assert e.xmax <= blank.size.width - 5 + 1e-6
                assert e.ymax <= blank.size.height - 5 + 1e-6
                boxes_.append(e)
            for i, a in enumerate(boxes_):
                for b in boxes_[i + 1:]:
                    apart = (a.xmax + 4 - 1e-6 <= b.xmin or b.xmax + 4 - 1e-6 <= a.xmin or
                             a.ymax + 4 - 1e-6 <= b.ymin or b.ymax + 4 - 1e-6 <= a.ymin)
                    assert apart


class TestNest:
    """True shapes: holes and the room beside slanted sides take other parts."""

    def test_small_parts_go_in_a_hole(self) -> None:
        # A 1100 × 800 frame fills a big blank by bounding box; the small
        # parts fit only in its 900 × 600 hole.
        parts = [frame_part(1100, 800, 100)] + [rect_part(200, 150) for _ in range(6)]
        blanks, sheets = N.pack(parts, SIZES)
        assert (len(blanks), sheets) == (1, 1)
        frame = placed(*blanks[0].parts[0]).extents()
        for part, matrix in blanks[0].parts[1:]:
            e = placed(part, matrix).extents()
            assert frame.xmin + 104 - 1e-6 <= e.xmin and e.xmax <= frame.xmax - 104 + 1e-6
            assert frame.ymin + 104 - 1e-6 <= e.ymin and e.ymax <= frame.ymax - 104 + 1e-6

    def test_triangles_pair_up(self) -> None:
        # Two right triangles, 1100 × 800: their bounding boxes need two big
        # blanks; turned to face each other they share one.
        tri = [(0, 0), (1100, 0), (0, 800)]
        parts = []
        for _ in range(2):
            part = Part("test")
            part.pathes.append(ring(tri))
            parts.append(part)
        blanks, _ = N.pack(parts, [N.BlankSize(1200, 900, 2)])
        assert len(blanks) == 1

    def test_small_blank_before_another_sheet(self) -> None:
        # Two 1100 × 800 parts fill the sheet's two big blanks; a 500 × 800
        # one goes on its small blank, not on another sheet.
        parts = [rect_part(1100, 800), rect_part(1100, 800), rect_part(500, 800)]
        blanks, sheets = N.pack(parts, SIZES)
        assert sheets == 1
        assert [b.size.name for b in blanks] == ["1200x900", "1200x900", "600x900"]

    def test_spill_goes_on_a_spare_small_blank(self) -> None:
        # Three 1100 × 800 parts need two sheets (four big blanks, two small);
        # a 300 × 300 part fits beside none of them, and goes on a spare
        # small blank rather than the fourth big one.
        parts = [rect_part(1100, 800) for _ in range(3)] + [rect_part(300, 300)]
        blanks, sheets = N.pack(parts, SIZES)
        assert sheets == 2
        assert [b.size.name for b in blanks] == ["1200x900"] * 3 + ["600x900"]


class TestShape:
    """A part's cells: material occupied, holes free, rounded outwards."""

    def test_hole_is_free(self) -> None:
        shape = S.shape_of(frame_part(100, 60, 10))
        # One cell over: a line on the box's far edge still lands in the grid.
        assert shape.cells.shape == (51, 31)
        assert shape.cells[0, 0] and shape.cells[-1, -1]
        assert not shape.cells[25, 15]
        assert shape.area == pytest.approx(100 * 60 - 80 * 40, rel=0.05)

    def test_open_outline_takes_the_whole_box(self) -> None:
        part = Part("test")
        pts = rect_points(100, 60)
        part.pathes.append(DrawPath([["M", *pts[0]]] + [["L", *pt] for pt in pts[1:]],
                                    {"rgb": (1, 0, 0), "lw": 0.1}))
        assert S.shape_of(part).cells.all()

    def test_lines_drawn_end_to_end_close(self) -> None:
        # The outline in four separate pieces, as a generator may draw it.
        part = Part("test")
        pts = rect_points(100, 60) + [(0, 0)]
        for a, b in zip(pts, pts[1:]):
            part.pathes.append(DrawPath([["M", *a], ["L", *b]], {"rgb": (1, 0, 0), "lw": 0.1}))
        part.pathes.append(ring(rect_points(80, 40, 10, 10)))
        assert not S.shape_of(part).cells[25, 15]

    @pytest.mark.parametrize("quarter", range(4))
    def test_turned_cells_match_the_placed_part(self, quarter) -> None:
        # An L: points inside it land on taken cells of its turned grid once
        # the part is moved, and a point in the crook of the L on a free one.
        part = Part("test")
        part.pathes.append(ring([(10, 20), (70, 20), (70, 40), (30, 40), (30, 120), (10, 120)]))
        shape = S.shape_of(part)
        grid = (shape.cells.shape[0] * S.CELL, shape.cells.shape[1] * S.CELL)
        m = (S.place_matrix(grid, quarter, 0.0, 0.0)
             * N.Affine.translation(-shape.origin[0], -shape.origin[1]))
        turned = shape.turned(quarter)
        for point, taken in (((20, 100), True), ((60, 30), True), ((55, 90), False)):
            x, y = m * point
            assert turned[int(x // S.CELL), int(y // S.CELL)] == taken


def helper(kind, w, h, x=0.0, y=0.0):
    """A rectangle part marked as a helper (``template`` or ``guide``)."""
    part = rect_part(w, h, x, y)
    part.helper = kind
    return part


class TestHelpers:
    """An order keeps at most 2 of each different track template piece and 3
    of each different guide plate, told apart by shape."""

    def test_same_shape_anywhere_is_one_design(self) -> None:
        parts = [helper("template", 300, 40, x=100 * k, y=7 * k) for k in range(5)]
        assert len(N.cap_helpers(parts, N.HELPER_LIMITS)) == 2

    def test_different_shapes_each_keep_their_own(self) -> None:
        parts = ([helper("template", 300, 40) for _ in range(3)]
                 + [helper("template", 310, 40) for _ in range(3)]
                 + [helper("guide", 120, 90) for _ in range(5)])
        kept = N.cap_helpers(parts, N.HELPER_LIMITS)
        assert sum(p.helper == "template" for p in kept) == 4
        assert sum(p.helper == "guide" for p in kept) == 3

    def test_other_parts_are_never_dropped(self) -> None:
        parts = [rect_part(300, 40) for _ in range(6)]
        assert len(N.cap_helpers(parts, N.HELPER_LIMITS)) == 6

    def test_counted_across_the_whole_order(self) -> None:
        seen = {}
        first = N.cap_helpers([helper("guide", 120, 90) for _ in range(2)], N.HELPER_LIMITS, seen)
        second = N.cap_helpers([helper("guide", 120, 90) for _ in range(2)], N.HELPER_LIMITS, seen)
        assert (len(first), len(second)) == (2, 1)

    def test_the_generators_mark_them(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(N_TRAPEZOID + ["--track_guide=1", "--track_template=1"])
        box.open()
        box.render()
        box.ctx.stroke()
        kinds = {getattr(p, "helper", None) for p in box.surface.parts}
        assert {"template", "guide"} <= kinds


class TestGenerator:

    def render(self, extra):
        box = HexmoHexagon()
        box.parseArgs(N_TRAPEZOID + extra)
        box.metadata["reproducible"] = True
        box.open()
        box.render()
        return box, box.close().getvalue().decode()

    def test_off_by_default(self) -> None:
        box, svg = self.render([])
        assert "Blank 1 of" not in svg
        assert not hasattr(box, "sheets_used")

    def test_labelled_blanks(self) -> None:
        box, svg = self.render(["--sheets=" + N.DEFAULT_SHEETS])
        blanks, sheets = box.sheets_used
        assert sheets == 1
        first = blanks[0].size
        assert f"Blank 1 of {len(blanks)}: {first.width:g} × {first.height:g}" in svg

    def test_every_part_on_its_blank(self) -> None:
        # Laid out before the drawing is finished (which moves everything
        # into page coordinates), as close() does.
        box = HexmoHexagon()
        box.parseArgs(N_TRAPEZOID)
        box.open()
        box.render()
        box.ctx.stroke()
        blanks, _ = N.pack(box.surface.parts, SIZES)
        N.lay_out(box.surface, blanks)
        # In a row: each blank starts where the last ended, plus a gap.
        x0 = 0.0
        for blank in blanks:
            for part, _ in blank.parts:
                e = part.extents()
                assert x0 - 1e-6 <= e.xmin and e.xmax <= x0 + blank.size.width + 1e-6
                assert -1e-6 <= e.ymin and e.ymax <= blank.size.height + 1e-6
            x0 += blank.size.width + N._BLANK_GAP

    def test_settings_tag_beside_the_blanks_not_on_them(self) -> None:
        box = HexmoHexagon()
        box.parseArgs(N_TRAPEZOID)
        box.open()
        box.render()
        box.ctx.stroke()
        blanks, _ = N.pack(box.surface.parts, SIZES)
        assert not any(N.is_settings_tag(p) for b in blanks for p, _ in b.parts)
        N.lay_out(box.surface, blanks)
        tag, = [p for p in box.surface.parts if N.is_settings_tag(p)]
        end = sum(b.size.width + N._BLANK_GAP for b in blanks)
        assert tag.extents().xmin >= end - 1e-6
        assert all(path.params["rgb"] == N.Color.ANNOTATIONS for path in tag.pathes)

    def test_step_format_ignores_sheets(self) -> None:
        pytest.importorskip("build123d")
        box = HexmoHexagon()
        box.parseArgs(N_TRAPEZOID + ["--sheets=" + N.DEFAULT_SHEETS, "--format=step"])
        box.open()
        box.render()
        box.close()
        assert not hasattr(box, "sheets_used")


def test_command_line_settings_tag_is_a_separate_reference(tmp_path) -> None:
    url = "http://localhost:4455/HexmoHexagon?" + "&".join(a[2:] for a in N_TRAPEZOID)
    assert N.main([str(tmp_path), f"3@{url}"]) == 0
    files = sorted(tmp_path.glob("blank-*.svg"))
    assert files
    # The parameter list is on none of the blanks…
    assert "FingerJoint_bottom_lip" not in "".join(f.read_text() for f in files)
    # …but in its own reference file, once, in the annotation colour (cyan).
    tag = (tmp_path / "01-HexmoHexagon-settings.svg").read_text()
    assert tag.count("FingerJoint_bottom_lip") == 1
    assert "rgb(255,0,0)" not in tag and "#ff0000" not in tag.lower()
    # A second, smaller run clears the first's files.
    assert N.main([str(tmp_path), url]) == 0
    assert len(sorted(tmp_path.glob("blank-*.svg"))) <= len(files)
