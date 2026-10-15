"""Tests for the Hexmo generators' defaults: the HO README's settings.

HexmoHexagon and HexmoRectangle with no options are HO modules cut as the HO
README recommends (_hexmo_defaults); other generators keep the boxes defaults.

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

pytestmark = [IGNORE_CORE_MATMUL, pytest.mark.ho_defaults]

from boxes.generators._hexmo_defaults import HO_DEFAULTS, apply_ho_defaults
from boxes.generators._hexmo_helix_ring import _HO_COMMON, helix_entry_ho
from boxes.generators.hexmohexagon import HexmoHexagon
from boxes.generators.hexmorectangle import HexmoRectangle
from boxes.generators.universalbox import UniversalBox

# The HO presets' options that belong to one module (its track and openings),
# not to every HO module.
_PER_MODULE = ("--trapezoid", "--track_routes", "--track_openings", "--deck_slots",
               "--risers", "--under_track_edges", "--turnouts", "--under_track=",
               "--subway=")


def parsed(cls, args=()):
    box = cls()
    box.parseArgs(list(args))
    return box


def preset(args):
    """``{option: value}`` of a preset's shared settings, as the parser reads them."""
    return {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in args
            if not a.startswith(_PER_MODULE)}


@pytest.mark.parametrize("cls, args", [(HexmoHexagon, _HO_COMMON),
                                       (HexmoRectangle, helix_entry_ho())])
def test_no_options_is_the_ho_preset(cls, args) -> None:
    # Every shared setting of the HO README's preset is already the default:
    # parsing the preset changes nothing.
    plain, ho = parsed(cls), parsed(cls, [f"--{k}={v}" for k, v in preset(args).items()])
    changed = {k: (getattr(plain, k), getattr(ho, k)) for k in preset(args)
               if getattr(plain, k) != getattr(ho, k)}
    assert changed == {}


def test_rectangle_has_three_columns() -> None:
    assert parsed(HexmoRectangle).num_columns == 3


def test_other_generators_keep_the_boxes_defaults() -> None:
    box = parsed(UniversalBox)
    assert box.labels is True and box.reference == 100.0


def test_the_form_shows_the_ho_defaults() -> None:
    # The web form and --help read each option's own default.
    actions = {a.dest: a for a in HexmoHexagon().argparser._actions}
    for name, value in HO_DEFAULTS.items():
        assert actions[name].default == value


def test_a_missing_option_is_refused() -> None:
    box = UniversalBox()
    with pytest.raises(ValueError, match="no option"):
        apply_ho_defaults(box)


@pytest.mark.parametrize("cls", [HexmoHexagon, HexmoRectangle])
def test_renders_with_no_options(cls) -> None:
    # What the web form draws first: every default together.
    box = parsed(cls)
    box.open()
    box.render()
    svg = box.close().getvalue().decode()
    assert "<path" in svg
