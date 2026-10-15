"""The Hexmo generators' defaults: the HO settings (see README-HO-scale.md).

HexmoHexagon and HexmoRectangle open with these, so a module with no options
is an HO module cut the way the HO README recommends.  Most are the
generators' own options; ``labels`` and ``reference`` belong to the boxes
core (every generator has them) and are changed for these two only.

Applied with ``argparse``'s ``set_defaults`` after every option is added
(:func:`apply_ho_defaults`), which also updates each option's shown default,
so the web form and ``--help`` show these values.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

# The HO README's cut settings that every HO module shares (its per-module
# track routes, openings and so on are left to each module).
HO_DEFAULTS = {
    # Fewer, simpler holes: shorter laser cut time (README "Reducing laser cut
    # time").
    "corner_holes": "g2",
    "gap_holes": "g2",
    "big_hole_shape": "rounded_rect",
    # A snug finger-joint fit in 6 mm MDF.
    "FingerJoint_play": 0.1,
    "FingerJoint_extra_length": 0.05,
    # The lower level runs on the floor: one thickness up.
    "under_track_height": 6.0,
    # The track-laying jigs come with every module.
    "track_guide": True,
    "track_template": True,
    # No part labels or reference bar on the cut sheets.
    "labels": False,
    "reference": 0.0,
}

# HexmoRectangle's extra: three compartments along the long axis (the HO entry).
HO_RECTANGLE_DEFAULTS = {"num_columns": 3}


def apply_ho_defaults(generator, rectangle=False):
    """Make the HO settings a generator's defaults.

    @param generator - A HexmoHexagon or HexmoRectangle, after every option
                       has been added to its argument parser.
    @param rectangle - Add HexmoRectangle's own (:data:`HO_RECTANGLE_DEFAULTS`).
    @throws ValueError - If an option is missing (a renamed option would
                         otherwise be ignored silently).
    """
    # Read at call time, so the feature tests can run against the
    # generators' original defaults (tests/conftest.py empties these).
    defaults = {**HO_DEFAULTS, **(HO_RECTANGLE_DEFAULTS if rectangle else {})}
    known = {action.dest for action in generator.argparser._actions}
    missing = sorted(set(defaults) - known)
    if missing:
        raise ValueError(f"{type(generator).__name__} has no option(s) {', '.join(missing)}")
    generator.argparser.set_defaults(**defaults)
