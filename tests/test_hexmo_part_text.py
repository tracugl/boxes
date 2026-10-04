"""Tests for ``--part_text``: the descriptive text etched on helper parts.

The helper parts (riser supports, track-guide plates and track templates)
carry text that is handy while assembling but clutters the cut sheet: each
riser support's track height, the guide plate's side arrow ("edge 4 side ->",
"outside of curve ->"), the template's radius/gauge label and its "EDGE" end
marks.  ``--part_text`` (default off) switches all of it on.  The letters that
pair up the cut ends of a split template are kept either way, since they are
needed to put the pieces back together in order.

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

from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle

# Helix ring M1 at h=80 with its riser, a guide plate per route edge and the
# track templates: every kind of helper-part text at once.
M1 = ["--radius=220", "--thickness=3", "--h=80", "--trapezoid=1", "--bottom=spoke",
      "--track_lead_in=26", "--track_width=17", "--support_length=55",
      "--support_edges=4@132,4@30/90", "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
      "--track_openings=3:-17.5:73.6:35,5:35:65.9:35", "--deck_slots=3:-17.5-5:-35/35",
      "--risers=3:-17.5-5:-35~73.6..65.9/35", "--track_guide=1", "--track_template=1"]

# A rectangle with an asymmetric track family, so its guide plate has an arrow.
RECT = ["--radius=220", "--thickness=3", "--h=100", "--num_columns=2", "--num_rows=3",
        "--track_lines=1", "--track_width=17", "--track_lead_in=26", "--track_guide=1",
        "--track_template=1", "--track_center_offset=10"]


def etched_texts(cls, args):
    """Render ``cls`` with ``args``; return every string passed to ``text()``.

    @param cls  - The generator class.
    @param args - Command-line style arguments.
    @returns List of the etched strings, in drawing order.
    """
    box = cls()
    box.parseArgs(args + ["--reference=0"])
    box.metadata["reproducible"] = True
    texts = []
    orig = box.text
    box.text = lambda t, *a, **kw: (texts.append(t), orig(t, *a, **kw))[1]
    box.open()
    box.render()
    box.close()
    return texts


def helper_text(texts):
    """The strings among ``texts`` that ``--part_text`` controls."""
    return [t for t in texts
            if t == "EDGE" or t.endswith("->") or t.startswith("R")
            or t.replace(".", "", 1).isdigit()]


class TestHexagon:

    def test_off_by_default(self) -> None:
        assert helper_text(etched_texts(HexmoHexagon, M1)) == []

    def test_on(self) -> None:
        texts = etched_texts(HexmoHexagon, M1 + ["--part_text=1"])
        assert "edge 4 side ->" in texts
        assert "EDGE" in texts
        assert any(t.startswith("R297 ") for t in texts)
        # One height per riser support, falling along the bed.
        heights = [float(t) for t in texts if t.replace(".", "", 1).isdigit()]
        assert len(heights) == 5 and heights == sorted(heights, reverse=True)

    def test_deck_radius_label_is_not_affected(self) -> None:
        # --track_label's radius on the deck has its own option.
        texts = etched_texts(HexmoHexagon, M1 + ["--track_label=1"])
        assert "297 mm" in texts


class TestRectangle:

    def test_off_by_default(self) -> None:
        assert helper_text(etched_texts(HexmoRectangle, RECT)) == []

    def test_on(self) -> None:
        texts = etched_texts(HexmoRectangle, RECT + ["--part_text=1"])
        assert "outside of curve ->" in texts
        assert "EDGE" in texts


class TestSplitTemplate:

    @pytest.mark.parametrize("on", [False, True])
    def test_joint_letters_are_always_kept(self, on) -> None:
        args = M1 + ["--track_template_segments=3", f"--part_text={int(on)}"]
        texts = etched_texts(HexmoHexagon, args)
        assert texts.count("A") >= 2 and texts.count("B") >= 2
