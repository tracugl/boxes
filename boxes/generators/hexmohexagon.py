"""Hexagon box generator with optional 'spoke' bottom pattern.

The 'spoke' style draws a hexagonal frame (outer and inner hex cut) plus six
identical kite-shaped cutouts arranged symmetrically around the centre.
"""

# Copyright (C) 2025 Travis Cugley
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import copy
import datetime
import math

from boxes import Boxes, edges, boolarg
from boxes.Color import *
from boxes.generators._hexmo_big_holes import HexmoBigHoleMixin
from boxes.generators._hexmo_track_guide import HexmoTrackGuideMixin
from boxes.generators._hexmo_track_template import HexmoTrackTemplateMixin
from boxes.generators._hexmo_under_track import HexmoUnderTrackMixin
from boxes.generators._hexmo_track_openings import (
    SplitJointEdge, parse_track_openings, rect_circle_gap, wall_and_deck_pieces,
)
from boxes.generators._hexmo_track_routes import (
    Arc, Line, RouteSpec, edge_position, expand_routes, offset_segments,
    parse_track_routes, route_geometry, route_template_steps,
    segments_polyline, template_key,
)


class HexmoHexagon(HexmoBigHoleMixin, HexmoTrackGuideMixin, HexmoTrackTemplateMixin,
                   HexmoUnderTrackMixin, Boxes):
    """Box with a regular hexagon or half hexagon as the base. """

    ui_group = "Box"

    # Alignment-hole geometry constants shared by drawAlignmentHoles,
    # drawAlignmentHolesLong, and drawSupports.  Centralising them here
    # means a single change propagates to all three methods.
    _SPACER = 15    # minimum clearance from panel edge to hole edge (mm)
    _R2     = 12.5  # radius of medium alignment-pin receiver holes (mm)
    _R3     = 3     # radius of small registration dot / pilot holes (mm)

    def __init__(self) -> None:
        Boxes.__init__(self)

        # Override the default material thickness to suit typical hex box use.
        defaultgroup = self.argparser._action_groups[1]
        for action in defaultgroup._actions:
            if action.dest == 'thickness':
                action.default = 6.0

        self.addSettingsArgs(edges.FingerJointSettings, finger=5, space=5, surroundingspaces=2, play=0.2)

        self.buildArgParser("h", "outside")
        self.argparser.add_argument(
            "--radius", action="store", type=float, default=500.0,
            help="inner radius of the hexagon (at the corners)")
        self.argparser.add_argument(
            "--top", action="store", type=str, default="closed",
            choices=["closed"],
            help="style of the top")
        self.argparser.add_argument(
            "--bottom", action="store", type=str, default="spoke",
            choices=["spoke", "closed"],
            help="style of the bottom")
        self.argparser.add_argument(
            "--edge_width", action="store", type=float, default=60.0,
            help="Width of the outer hexagonal frame for spoke bottom.")
        self.argparser.add_argument(
            "--spoke_width", action="store", type=float, default=120.0,
            help="Width of the spokes for spoke bottom.")
        self.argparser.add_argument(
            "--support_length", action="store", type=float, default=150.0,
            help="length of the internal supports.")
        self.argparser.add_argument(
            "--supports", action="store", type=boolarg, default=True,
            help="add internal support walls and matching finger-joint slots in the top and bottom panels.")
        self.argparser.add_argument(
            "--corner_holes", action="store", type=str, default="g6",
            choices=["g6", "g2"],
            help="Small-hole cluster around each end registration medium hole.  "
                 "'g6' (default) draws the full group — the medium plus the six "
                 "surrounding Ø6 pilot holes (an L-cluster at each corner plus the "
                 "pair directly above/below the medium).  'g2' keeps only the "
                 "medium and the two pilot holes directly above and below it, "
                 "dropping the six corner holes per end — far fewer laser pierces "
                 "and a much shorter cut time.")
        self.argparser.add_argument(
            "--gap_holes", action="store", type=str, default="g4",
            choices=["g4", "g2"],
            help="Registration cluster filling each gap between the big holes.  "
                 "'g4' (default) draws the full group — two mediums with two Ø6 "
                 "pilot holes each (2 medium + 4 small).  'g2' draws a single "
                 "centred medium with one pilot directly above and below it "
                 "(1 medium + 2 small), mirroring the reduced corner cluster — "
                 "fewer laser pierces and a shorter cut time.")
        self.argparser.add_argument(
            "--big_hole_shape", action="store", type=str, default="circle",
            choices=["circle", "rounded_rect"],
            help="Shape of the large weight-reduction through-holes.  'circle' "
                 "(default) draws them as circles (unchanged behaviour).  "
                 "'rounded_rect' draws each as a square with rounded corners "
                 "occupying the same bounding box as the circle (side = the "
                 "circle diameter), so all fit/clearance checks are unaffected.  "
                 "The small registration and medium fallback holes are never "
                 "changed by this option.")
        self.argparser.add_argument(
            "--big_hole_roundness", action="store", type=float, default=0.3,
            help="Corner rounding for --big_hole_shape=rounded_rect, as a "
                 "fraction of the hole's half-width (0 = square corners, "
                 "1 = fully round, i.e. back to a circle).  Default 0.3 — on the "
                 "Ø70 mm big holes that is a 10.5 mm corner radius.  Values are "
                 "clamped by rectangularHole, so out-of-range numbers are safe.")
        # --big_hole_width / --big_hole_height, shared with HexmoRectangle.
        self._addBigHoleSizeArgs()
        self.argparser.add_argument(
            "--under_track_edges", action="store", type=str, default="",
            help="Under-deck track opening: the edges (comma-separated, numbered "
                 "as for --track_routes) whose side walls get it instead of the "
                 "centre big hole, e.g. '1'.  A lower track can then run under "
                 "the deck through those walls.  Each such wall is labelled with "
                 "its edge.  The trapezoid only has edges 3, 4 and 5.")
        # --under_track_height / --under_track_width, shared with HexmoRectangle.
        self._addUnderTrackArgs()
        self.argparser.add_argument(
            "--track_openings", action="store", type=str, default="",
            help="Openings for tracks that cross a joint below deck level (e.g. a "
                 "descending spur), comma-separated 'edge:position:height[:width]'. "
                 "position: mm along the edge from its midpoint, anticlockwise "
                 "seen from above (to the right, facing the wall from outside). "
                 "height: the track base above the floor panel (the opening's "
                 "bottom).  width: default --under_track_width.  If a 40 mm train "
                 "on that track still fits one thickness under the deck it is a "
                 "closed hole; otherwise a notch open at the top of the wall, "
                 "with the deck's edge left plain over it.  E.g. '5:17.5:92.5:26'.")
        self.argparser.add_argument(
            "--trapezoid", action="store", type=boolarg, default=False,
            help="If true, only draw a half-hexagon.")
        self.argparser.add_argument(
            "--trapezoid_side_supports", action="store", type=boolarg, default=False,
            help="Trapezoid mode only: if true, draw all 3 supports (inherited "
                 "from the full hexagon).  If false (default), draw only the "
                 "single support perpendicular to the long edge — the ±60° "
                 "side supports are omitted and the two kite cutouts are "
                 "widened to take advantage of the extra clearance.")
        self.argparser.add_argument(
            "--track_lines", action="store", type=boolarg, default=True,
            help="Etch the 60° model-railway track curve onto the top (deck) "
                 "panel as an alignment guide.  The curve is the arc a train "
                 "follows as it crosses the module: radius = 1.5 × the hexagon "
                 "radius, entering and leaving at the midpoints of the two "
                 "edges 120° apart.  Rendered as an engrave (etch) pass, not a "
                 "cut.  Only drawn in trapezoid (half-hexagon) mode, where both "
                 "of those edges lie in the same panel.")
        self.argparser.add_argument(
            "--track_line_count", action="store", type=int, default=1,
            help="Number of parallel track guide lines to etch when "
                 "--track_lines is on.  1 draws a single centreline arc.  An "
                 "odd count places one line on the centreline with the rest "
                 "offset symmetrically either side; an even count straddles "
                 "the centreline (its midpoint stays on the centreline).  "
                 "Adjacent lines are spaced by --track_spacing.")
        self.argparser.add_argument(
            "--track_spacing", action="store", type=float, default=80.0,
            help="Radial spacing (mm) between adjacent track guide lines when "
                 "--track_line_count > 1.  Defaults to 80 mm.  Ignored when only "
                 "one line is drawn.")
        self.argparser.add_argument(
            "--track_offset", action="store", type=str, default="centred",
            choices=["centred", "outer", "inner"],
            help="How multiple track lines (--track_line_count > 1) are placed "
                 "relative to the centreline.  'centred' (default) spaces them "
                 "symmetrically about the centreline, so the inner lines have a "
                 "tighter radius than the centreline and the outer lines a wider "
                 "one.  'outer' keeps the centreline as the minimum-radius line "
                 "and steps every additional line outward only (larger radius), "
                 "guaranteeing no track is tighter than the centreline.  'inner' "
                 "is the mirror: the centreline is the maximum-radius line and "
                 "every additional line steps inward only (tighter radius; the "
                 "labels show each one).  No effect when --track_line_count is 1.")
        self.argparser.add_argument(
            "--track_center_offset", action="store", type=float, default=0.0,
            help="Signed radial shift (mm) applied to the reference centreline "
                 "itself before the per-track --track_offset spacing is added.  "
                 "0 (default) is the true geometric centreline.  Positive moves "
                 "it outward (larger radius); negative moves it inward (smaller "
                 "radius).  The whole track family (and its --track_offset "
                 "spacing) shifts with it, so a value of +10 puts the centreline "
                 "10 mm further out.  With --track_line_count 1 this simply "
                 "relocates the single centreline.")
        self.argparser.add_argument(
            "--track_width", action="store", type=float, default=30.0,
            help="Physical width (mm) of the actual model-railway track laid on "
                 "the deck (the roadbed/tie footprint).  Used by --draw_track to "
                 "place a pair of edge lines at ± track_width/2 either side of "
                 "each centreline.  Set to your scale's track width (30 mm HO, "
                 "17 mm N).")
        self.argparser.add_argument(
            "--track_lead_in", action="store", type=float, default=30.0,
            help="Length (mm) of a straight lead-in section where each track "
                 "line meets an edge.  The line runs straight (perpendicular to "
                 "the edge) for this distance from the edge, then the curve "
                 "begins at the inner end.  Because the crossing points stay "
                 "fixed, the arc shortens accordingly (curve radius becomes "
                 "1.5·R − √3·lead_in).  Set to 0 for a pure edge-to-edge arc.")
        self.argparser.add_argument(
            "--track_label", action="store", type=boolarg, default=True,
            help="Etch the resulting curve radius (mm) as text near the apex of "
                 "each track centreline.  One label per --track_line_count "
                 "centreline.  On by default when --track_lines is on.")
        self.argparser.add_argument(
            "--track_crossing", action="store", type=boolarg, default=True,
            help="Etch a short crossing tick (perpendicular to the track) at "
                 "each point where a straight lead-in meets the curve, marking "
                 "the transition.  Only drawn when --track_lead_in > 0.")
        # Full-hexagon route selection.  Edges are numbered as on a flat-top
        # hexagon: 1 top, 2 upper-right, 3 lower-right, 4 bottom, 5 lower-left,
        # 6 upper-left.  Each option draws one possible track route across the
        # module (with lead-ins); any combination may be enabled.  These are
        # ignored in trapezoid mode, which always draws its single lower curve.
        self.argparser.add_argument(
            "--track_left", action="store", type=boolarg, default=False,
            help="Full hexagon: draw the left curve, from edge 4 (bottom) to "
                 "edge 6 (upper-left).")
        self.argparser.add_argument(
            "--track_middle", action="store", type=boolarg, default=False,
            help="Full hexagon: draw the middle straight, from edge 4 (bottom) "
                 "to edge 1 (top) — a diameter through the centre.")
        self.argparser.add_argument(
            "--track_right", action="store", type=boolarg, default=False,
            help="Full hexagon: draw the right curve, from edge 4 (bottom) to "
                 "edge 2 (upper-right).")
        self.argparser.add_argument(
            "--track_top", action="store", type=boolarg, default=False,
            help="Full hexagon: draw the top curve, from edge 6 (upper-left) to "
                 "edge 2 (upper-right).")
        self.argparser.add_argument(
            "--track_routes", action="store", type=str, default="",
            help="Any track routes, replacing --track_left/middle/right/top "
                 "(and the trapezoid's own curve) when set.  Comma-separated "
                 "'A:offset-B:offset' entries, edges numbered as above, e.g. "
                 "'1:-17.5-5:-17.5, 3:-17.5-1:-17.5, 1:-17.5-5:17.5'.  Edges two "
                 "apart get a curve (the largest that keeps --track_lead_in at "
                 "both ends), opposite edges a straight, or an S-curve if the "
                 "two offsets differ; adjacent edges are refused.  On a curve a "
                 "positive offset is towards its outside, on a straight to the "
                 "right of travel from A to B.  Leave the offsets off ('4-6') to "
                 "draw the --track_line_count family.  Routes from the same "
                 "edge and offset share their lead-in, like a turnout.  The "
                 "trapezoid only has edges 3, 4 and 5.")
        self.argparser.add_argument(
            "--draw_center", action="store", type=boolarg, default=False,
            help="When --track_lines is on, etch the track centreline arc(s) "
                 "themselves (the --track_line_count parallel curves).  Off by "
                 "default; --draw_track etches the footprint edges instead, and "
                 "both can be on together.")
        self.argparser.add_argument(
            "--draw_track", action="store", type=boolarg, default=True,
            help="When --track_lines is on, treat each centreline as the middle "
                 "of the track and etch a pair of edge lines offset by "
                 "± track_width/2, showing where the actual track footprint sits."
                 "  Can be combined with --draw_center to show both.")
        # --track_guide / --track_guide_clearance, shared with HexmoRectangle.
        self._addTrackGuideArgs()
        # --track_template, --track_gauge, …, shared with HexmoRectangle.
        self._addTrackTemplateArgs()

        self.n = 6

    def drawSupports(self, isTrapezoid=False):
        """Draw rectangular internal support walls, one per half-spoke.

        A hexagonal spoke bottom has six support walls — one for each of the
        six half-spokes radiating from the centre (two halves per axis across
        the three 60° axes).  In trapezoid mode only the three downward
        half-spokes are present, so only three support walls are needed.
        When `self.trapezoid_side_supports` is False (the default in trapezoid
        mode), the ±60° side spokes are omitted and a single support wall is
        drawn — the one perpendicular to the long top edge.

        All walls are identical rectangles of size support_length × box_height,
        finger-jointed on both long edges ('fefe' pattern), so they can be
        laser-cut from the same template.

        Through-holes are placed along the horizontal centre line (y = h/2),
        distributed across the support length to remove as much material as
        possible while keeping at least _SPACER clearance from both panel ends.
        The hole-count algorithm mirrors drawAlignmentHoles but is transposed:
        holes run along the x-axis (support length) rather than the y-axis.
        In every x-gap between adjacent holes, _drawSupportGapFeatures attempts
        to insert smaller sub-holes near the top and bottom panel edges.

        Hole sizing: r1 = (h − 2·_SPACER) / 2 — identical formula to
        drawAlignmentHoles, so diameters are consistent across all panel types.
        Uses raw self.h (not adjustSize-shrunk) to keep diameters constant
        regardless of whether --outside is set.

        @param isTrapezoid - When True, render 3 support walls instead of 6.
        """
        h = self.h
        if self.outside:
            h = self.adjustSize(h)
        sl = self.support_length

        # Hole radius: same formula as drawAlignmentHoles.  Raw self.h keeps the
        # diameter identical whether or not --outside shrinks the rendered height.
        r1 = (self.h - 2 * self._SPACER) / 2

        MIN_CLEAR = 5.0

        # Number of support walls:
        #   full hexagon                            → 6  (3 axes × 2 half-spokes)
        #   trapezoid, side supports enabled        → 3  (3 downward half-spokes)
        #   trapezoid, side supports disabled       → 1  (only 0° axis spoke)
        if isTrapezoid:
            n_supports = 3 if self.trapezoid_side_supports else 1
        else:
            n_supports = 6

        def draw_holes():
            """Place through-holes on one support panel.

            Preference order:
              1. Big holes (r1): packed along sl when support is wide enough for
                 full _SPACER clearance.  Also fills x-axis gaps with sub-holes.
              2. Medium holes (r2): fallback when big holes don't fit.  Two medium
                 holes replace the single big hole for short supports (e.g. sl=90).
              3. Nothing: support too short even for medium holes.

            Fires at the bottom-left origin (edge 0) of each rectangularWall
            call.  The x-axis runs right along sl and y runs up along h.
            """
            sp = self._SPACER

            # ── Attempt big holes (r1) ──────────────────────────────────────────
            if r1 > 0:
                x_floor = sp + r1
                available = sl - 2 * x_floor

                if available >= 0:
                    # Big holes fit with full _SPACER clearance — use them.
                    n = max(1, 1 + int(available / (2 * r1 + MIN_CLEAR)))
                    if n == 1:
                        big_xs = [sl / 2]
                    else:
                        step = available / (n - 1)
                        big_xs = [x_floor + i * step for i in range(n)]

                    for x in big_xs:
                        self._drawBigHole(x, h / 2, r1)

                    # Fill gaps between big holes with sub-hole pairs.
                    lo_bounds = [sp]                   + [x + r1 for x in big_xs]
                    hi_bounds = [x - r1 for x in big_xs] + [sl - sp]
                    for x_lo, x_hi in zip(lo_bounds, hi_bounds):
                        self._drawSupportGapFeatures(h, x_lo, x_hi)
                    return  # big holes drawn — done

            # ── Fallback: medium holes (r2) ─────────────────────────────────────
            # Reached when r1 ≤ 0 (very short box) or big holes don't fit along sl.
            # Medium holes are smaller so more can fit on a narrow support.
            r2 = self._R2
            x_floor_med = sp + r2
            available_med = sl - 2 * x_floor_med

            if available_med < 0:
                # Support too short even for medium holes — render blank.
                return

            n_med = max(1, 1 + int(available_med / (2 * r2 + MIN_CLEAR)))
            if n_med == 1:
                med_xs = [sl / 2]
            else:
                step = available_med / (n_med - 1)
                med_xs = [x_floor_med + i * step for i in range(n_med)]

            for x in med_xs:
                self.hole(x, h / 2, r2)

            # Medium holes are a reduced-clearance fallback — gaps between them
            # are too small (≈ MIN_CLEAR) to fit any sub-hole groups, so no
            # gap-filling pass is performed here.

        for _ in range(n_supports):
            self.rectangularWall(sl, h, "fefe", callback=[draw_holes], move="right")

    def drawSupportHoles(self, r, isTrapezoid=False):
        """Cut finger-joint slots into the bottom panel for all three spoke axes.

        A hexagonal spoke bottom has three internal support walls, one per spoke
        direction (0°, +60°, and -60° from the vertical axis).  Each spoke gets
        two finger-joint slots placed symmetrically around the hex centre so that
        the rectangular support wall can slot perpendicularly into the panel.

        This callback fires at the start of edge 0 (the bottom-left vertex of the
        flat-top hexagon), NOT at the panel centre.  In that coordinate system the
        panel centre lies at (r/2, H).  To rotate each spoke's slots correctly we
        must first translate the origin to the centre and THEN rotate; rotating
        around (0,0) would pivot around the bottom-left vertex and produce wildly
        misplaced slots.

        moveTo(r/2, H, spoke_angle) achieves the combined translate-then-rotate in
        one call (ctx.translate followed by ctx.rotate).  After that, the two
        fingerHolesAt positions are expressed in centre-relative coordinates:
        (0, ±H/2), so they sit symmetrically on each spoke axis regardless of
        the spoke angle.

        In trapezoid mode the hex centre sits on the long top edge, and only the
        three downward half-spokes fall inside the panel.  The "lower slot" (local
        y < 0, i.e. below centre toward the short bottom edge) is the one that
        stays; the upper slot would land outside the trapezoid and is omitted.
        The coordinate formula for the centre (r/2, H) is unchanged because V0
        (callback origin) is the same bottom-left vertex in both modes.

        When `self.trapezoid_side_supports` is False (the default in trapezoid
        mode), the ±60° spoke slots are also omitted — only the 0° spoke (the
        axis perpendicular to the long top edge) is cut.  This matches the
        single support wall rendered by drawSupports in the same configuration.

        @param r          - Inner corner radius of the hexagon bottom panel.
        @param isTrapezoid - When True, only cut the three lower (inward) slots
                             instead of all six.  Combined with
                             trapezoid_side_supports=False, only the 0° slot
                             is cut.
        """
        sl = self.support_length

        H = r * math.sqrt(3) / 2.0  # apothem — also the y-distance from origin to centre

        # Choose which spoke axes receive slots.  The three axes are 60° apart.
        # In trapezoid mode without side supports, the ±60° axes are skipped
        # so the bottom panel matches the single-wall drawSupports layout.
        if isTrapezoid and not self.trapezoid_side_supports:
            spoke_angles = (0,)
        else:
            spoke_angles = (0, 60, -60)

        # For each spoke axis, shift the coordinate origin to the hex centre
        # and rotate to align with the spoke, then draw the slot(s).
        # saved_context() keeps the transform local so the next spoke starts
        # from the original origin.
        #
        # Both regularPolygonWall (hex) and drawTrapezoidWall (trap) fire the
        # support-holes callback (callback[1]) at y = edges[0].startWidth() + burn
        # = thickness + burn above V0.  From that callback origin, moveTo(r/2, H)
        # places the centre at y = H + thickness + burn from V0 — identical in both
        # modes.  No special trapezoid correction is needed here.

        for spoke_angle in spoke_angles:
            with self.saved_context():
                # Translate to the hex centre then rotate to the spoke axis.
                self.moveTo(r / 2, H, spoke_angle)
                # Lower slot: midpoint at (0, -H/2) in centre-relative coords.
                # This slot falls in the trapezoid's half (below the hex centre)
                # and is always drawn.
                self.fingerHolesAt(0, -H / 2 - sl / 2, sl, angle=90)
                if not isTrapezoid:
                    # Upper slot: midpoint at (0, +H/2) — above the hex centre.
                    # Only present in full-hexagon mode; outside the trapezoid panel.
                    self.fingerHolesAt(0,  H / 2 - sl / 2, sl, angle=90)

    def _drawCornerGroup8(self, s, l):
        """Draw the corner registration clusters shared by all side-panel variants.

        Thin wrapper over :meth:`_cornerGroupHoles`, which holds the layout
        (documented there) so the track guide can reuse a subset of it.

        @param s - Panel height (pre-shrink side0 value), used for y-axis positions.
        @param l - Panel width (slant length), used for x-axis positions.
        """
        for x, y, r in self._cornerGroupHoles(s, l):
            self.hole(x, y, r)

    def _drawGapFeatures(self, l, y_lo, y_hi):
        """Fill the space between two adjacent features with G6 sub-groups.

        Attempts to place, symmetrically within the inner gap [y_lo, y_hi]:
          - Full G6 equivalent (G2-small + G2-medium + G2-small, 6 holes)
            when half-gap ≥ r2 + 2·r3 + 2·MIN_CLEAR  (≈ 28.5 mm)
          - G2-medium pair only (2 holes)
            when half-gap ≥ r2 + MIN_CLEAR             (≈ 17.5 mm)
          - Nothing when the gap is too small

        y_lo and y_hi are **inner** boundaries — the outer edge of the lower
        adjacent feature and the inner edge of the upper adjacent feature
        respectively.  Callers compute them as: corner_inner = 3·sp + r2,
        big_hole top/bottom = centre ± r1.

        The small holes in the G6 are placed at y_mid ± sm_offset where
        sm_offset = r2 + r3 + MIN_CLEAR, guaranteeing MIN_CLEAR clearance
        to both the medium hole and the gap boundaries.

        @param l    - Panel width (for x-position calculations).
        @param y_lo - Inner lower boundary (top edge of the feature below this gap).
        @param y_hi - Inner upper boundary (bottom edge of the feature above this gap).
        """
        r2 = self._R2
        r3 = self._R3
        sp = self._SPACER
        MIN_CLEAR = 5.0

        half_gap = (y_hi - y_lo) / 2
        y_mid    = (y_lo + y_hi) / 2

        # Minimum half-gap for a G2-medium pair to clear both boundaries.
        half_for_G2m = r2 + MIN_CLEAR              # ≈ 17.5 mm

        # Small holes are placed at y_mid ± sm_offset.  The offset must satisfy:
        #   sm_offset ≥ r2 + r3 + MIN_CLEAR   (clear the medium hole edge)
        # And the small must also clear the gap boundary:
        #   sm_offset + r3 + MIN_CLEAR ≤ half_gap
        # Combined minimum half-gap for the full G6 equivalent:
        sm_offset   = r2 + r3 + MIN_CLEAR          # ≈ 20.5 mm
        half_for_G6 = sm_offset + r3 + MIN_CLEAR   # ≈ 28.5 mm

        if self.gap_holes == "g2":
            # G2: mirror the reduced corner cluster — a single centred medium
            # with one pilot directly above and below it (1 medium + 2 small).
            if half_gap >= half_for_G2m:
                self.hole(l / 2,  y_mid, r2)  # centred medium
                self.hole(l - sp, y_mid, r3)  # pilot toward one edge
                self.hole(sp,     y_mid, r3)  # pilot toward the other edge
            return

        if half_gap >= half_for_G6:
            # Full G4 pattern: G2-small · G2-medium · G2-small (symmetric),
            # i.e. two mediums each flanked by a pilot above and below.
            self.hole(l - sp,        y_mid - sm_offset, r3)  # lower small, right side
            self.hole(sp,            y_mid - sm_offset, r3)  # lower small, left side
            self.hole(l - r2/2 - sp, y_mid,             r2)  # medium, right side
            self.hole(sp + r2/2,     y_mid,             r2)  # medium, left side
            self.hole(l - sp,        y_mid + sm_offset, r3)  # upper small, right side
            self.hole(sp,            y_mid + sm_offset, r3)  # upper small, left side

        elif half_gap >= half_for_G2m:
            # Gap too narrow for smalls — place medium pair only.
            self.hole(l - r2/2 - sp, y_mid, r2)
            self.hole(sp + r2/2,     y_mid, r2)

    def _drawSupportGapFeatures(self, h, x_lo, x_hi):
        """Fill the x-axis gap between two support holes with sub-hole pairs.

        Transposed counterpart of _drawGapFeatures: gaps run along x (the
        support-length axis) rather than y, and sub-holes are placed near the
        top and bottom edges of the support panel (y ≈ _SPACER and
        y ≈ h − _SPACER) rather than near the left/right edges.

        Attempts to place, symmetrically within the inner gap [x_lo, x_hi]:
          - Full G6 equivalent (left-small + centre-medium + right-small,
            each repeated at top and bottom): 6 holes total, when
            half-gap ≥ r2 + 2·r3 + 2·MIN_CLEAR  (≈ 28.5 mm).
          - G2-medium pair only (top + bottom): 2 holes, when
            half-gap ≥ r2 + MIN_CLEAR  (≈ 17.5 mm).
          - Nothing when the gap or the panel height is too small.

        Vertical guard: h ≥ 2·_SPACER + 3·r2 + MIN_CLEAR (≈ 72.5 mm) ensures
        the top and bottom medium holes never overlap each other.

        @param h    - Support panel height (raw box height, mm).
        @param x_lo - Inner left boundary of the gap (outer edge of left neighbour).
        @param x_hi - Inner right boundary of the gap (outer edge of right neighbour).
        """
        r2 = self._R2
        r3 = self._R3
        sp = self._SPACER
        MIN_CLEAR = 5.0

        # Vertical guard: binding constraint is top-medium vs bottom-medium overlap.
        # Condition: (h − sp − r2/2) − r2  ≥  (sp + r2/2) + r2 + MIN_CLEAR
        # Rearranges to: h ≥ 2·sp + 3·r2 + MIN_CLEAR ≈ 72.5 mm.
        if h < 2 * sp + 3 * r2 + MIN_CLEAR:
            return

        half_gap = (x_hi - x_lo) / 2
        x_mid    = (x_lo + x_hi) / 2

        # Thresholds mirror _drawGapFeatures — geometry depends only on gap
        # half-width and hole sizes, not on which axis is the gap axis.
        half_for_G2m = r2 + MIN_CLEAR              # ≈ 17.5 mm
        sm_offset    = r2 + r3 + MIN_CLEAR         # ≈ 20.5 mm — guarantees MIN_CLEAR
                                                    # between each small and medium edge
        half_for_G6  = sm_offset + r3 + MIN_CLEAR  # ≈ 28.5 mm

        # Precompute y-positions for readability.
        y_bot_r3 = sp                # small hole centre, near bottom edge
        y_top_r3 = h - sp            # small hole centre, near top edge
        y_bot_r2 = sp + r2 / 2      # medium hole centre, near bottom
        y_top_r2 = h - sp - r2 / 2  # medium hole centre, near top

        if self.gap_holes == "g2":
            # G2: single centred medium with one pilot toward each edge
            # (1 medium + 2 small), the transposed mirror of the reduced corner.
            if half_gap >= half_for_G2m:
                self.hole(x_mid, h / 2,     r2)  # centred medium
                self.hole(x_mid, y_bot_r3,  r3)  # pilot near bottom edge
                self.hole(x_mid, y_top_r3,  r3)  # pilot near top edge
            return

        if half_gap >= half_for_G6:
            # Full G4 pattern: three x-positions × two y-positions (top+bottom).
            self.hole(x_mid - sm_offset, y_bot_r3, r3)  # left-small,    bottom
            self.hole(x_mid - sm_offset, y_top_r3, r3)  # left-small,    top
            self.hole(x_mid,             y_bot_r2, r2)  # centre-medium, bottom
            self.hole(x_mid,             y_top_r2, r2)  # centre-medium, top
            self.hole(x_mid + sm_offset, y_bot_r3, r3)  # right-small,   bottom
            self.hole(x_mid + sm_offset, y_top_r3, r3)  # right-small,   top

        elif half_gap >= half_for_G2m:
            # Gap too narrow for smalls — medium pair top and bottom only.
            self.hole(x_mid, y_bot_r2, r2)  # bottom medium
            self.hole(x_mid, y_top_r2, r2)  # top medium

    def drawAlignmentHoles(self, s, l, text, under_track=False, openings=()):
        """Cut and etch alignment features into a side panel for stacking hexagons.

        The corner group-of-8 clusters at both panel ends are always drawn at
        fixed absolute spacer offsets (invariant to panel height).  The interior
        layout has two layers:

        1. Big holes: up to three, always odd-counted so s/2 (the mandatory
           centre track-pass-through aperture) is included.  A single centred
           hole is used when the wall is too short for three.

        2. Gap filling: every space between adjacent features (corner → BIG,
           BIG → BIG, BIG → corner) is passed to _drawGapFeatures, which
           fills it with a G6-equivalent (G2-small + G2-medium + G2-small)
           or just a G2-medium pair depending on how much room is available.

        At radius=300 this produces corner-8 → G2s → G2m → BIG → G2m → G2s
        → corner-8, matching the intended pattern exactly.

        With ``under_track`` the centre big hole is replaced by the under-deck
        track opening (see :mod:`_hexmo_under_track`).  Any other big hole that
        would come within the minimum clearance of it is dropped too, and the
        gap filling works around the opening as it does around a big hole.

        @param s           - Pre-shrink panel height (original side0, before subtracting 2*t).
        @param l           - Panel width (slant length l from render()).
        @param text        - Unused; kept for API compatibility.
        @param under_track - Cut the under-deck track opening on this wall.
        @param openings    - Track openings (--track_openings) on this wall, as
                             ``((x0, x1, y0, y1), closed)`` in this frame (x up
                             the wall, y along it).  Closed ones are cut here;
                             notches (``closed`` False) are cut by the wall's top
                             edge, but still clear the big holes and gap filling.
        @throws ValueError - From the under-deck and track-opening checks.
        """
        sp = self._SPACER
        r2 = self._R2

        # r1 is sized so the hole fills most of the wall width (l), leaving
        # _SPACER clearance top and bottom of the box height dimension.
        r1 = (self.h - 2 * sp) / 2

        # Minimum edge-to-edge clearance between any two circular features.
        MIN_CLEAR = 5.0

        # Lowest y where a big hole centre can sit without its edge overlapping
        # the corner group's medium hole (at 3·sp, radius r2).
        y_floor = 3 * sp + r2 + r1 + MIN_CLEAR

        # Vertical band available for interior holes, between the two safe floors.
        available = s - 2 * y_floor

        # Compute how many big holes fit without overlapping each other.
        # Each adjacent pair requires at least (2·r1 + MIN_CLEAR) centre-to-centre.
        if available < 0:
            # Wall too short — no interior holes; just the corner groups.
            big_ys = []
        else:
            n = min(3, max(1, 1 + int(available / (2 * r1 + MIN_CLEAR))))
            # Force an odd count so the distribution is always symmetric and
            # s/2 is guaranteed to be a big hole.  The centre hole must remain
            # present at every radius because it acts as a track pass-through
            # aperture for stacked board sections.
            if n % 2 == 0:
                n -= 1
            if n == 1:
                # Single hole centred vertically.
                big_ys = [s / 2]
            else:
                # For odd n ≥ 3, evenly spaced with the middle hole at s/2.
                step = available / (n - 1)
                big_ys = [y_floor + i * step for i in range(n)]

        # Interior features along the wall, as (lower edge, upper edge) spans
        # in y.  Each big hole spans centre ± r1.
        features = [(y - r1, y + r1) for y in big_ys]
        under_rect = None
        if under_track or openings:
            # Validate before drawing anything, so an error never leaves half
            # a wall.  Openings take the place of any big hole they would
            # come too close to (the under-deck one replaces the centre hole).
            if under_track:
                self._checkUnderTrackClearsCorners(s)
                bottom, top = self._underTrackSpan(l)
                half = self.under_track_width / 2
                under_rect = (bottom, top, s / 2 - half, s / 2 + half)
                big_ys = [y for y in big_ys
                          if abs(y - s / 2) >= half + r1 + self._UNDER_TRACK_CLEAR]
            rects = [rect for rect, _ in openings]
            big_ys = [y for y in big_ys
                      if all(rect_circle_gap(rect, (l / 2, y, r1)) >= self._UNDER_TRACK_CLEAR
                             for rect in rects)]
            self._checkTrackOpenings(s, l, rects, under_rect,
                                     [(l / 2, y, r1) for y in big_ys])
            features = sorted([(y - r1, y + r1) for y in big_ys]
                              + [(y0, y1) for _, _, y0, y1 in rects]
                              + ([(under_rect[2], under_rect[3])] if under_rect else []))
            if under_rect:
                self._drawUnderTrackOpening(s / 2, under_rect[0], under_rect[1],
                                            along_x=False)
            for (x0, x1, y0, y1), closed in openings:
                # Notches are cut by the wall's top edge, not here.
                if closed:
                    self.rectangularHole(
                        (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0,
                        r=max(0.0, self.big_hole_roundness) * min(x1 - x0, y1 - y0) / 2,
                        center_x=True, center_y=True)

        # Draw the big through-holes along the vertical centre line.
        for y in big_ys:
            self._drawBigHole(l / 2, y, r1, along_x=False)

        # Fill every gap with sub-groups via _drawGapFeatures.
        # Boundaries: the corner group's inner edge is 3·sp + r2 (top of the
        # medium hole), and each interior feature contributes its outer edges.
        corner_inner = 3 * sp + r2
        lo_bounds = [corner_inner]      + [hi for _, hi in features]
        hi_bounds = [lo for lo, _ in features] + [s - corner_inner]
        for y_lo, y_hi in zip(lo_bounds, hi_bounds):
            self._drawGapFeatures(l, y_lo, y_hi)

        # Corner group-of-8 clusters (see _drawCornerGroup8 for layout details).
        self._drawCornerGroup8(s, l)

    def drawAlignmentHolesLong(self, s, l, text):
        """Cut and etch alignment features into the trapezoid long back wall.

        The long back wall spans two hex-side-lengths (s = 2 * side0_orig).
        Its hole layout is derived from the standard-wall algorithm (see
        drawAlignmentHoles) applied to s_half = s/2, then mirrored symmetrically
        about the centre so that positions near either edge of the long wall match
        exactly the positions on the adjacent standard walls.

        Pattern (bottom → top, n_big=3 case):
            group-of-8
            BIG  G6  BIG  G6  BIG          ← bottom half positions
            BIG  (centre, no G6 on either side — "transition zone")
            BIG  G6  BIG  G6  BIG          ← top half (mirrored)
            group-of-8

        When fewer big holes fit per half (small-radius boards), the pattern
        shrinks proportionally while preserving the corner groups.

        @param s    - Pre-shrink panel height (2 * side0_orig for the long wall).
        @param l    - Panel width (slant length l from render()).
        @param text - Unused; kept for API compatibility.
        """
        sp = self._SPACER
        r2 = self._R2
        r1 = (self.h - 2 * sp) / 2

        # Use the same dynamic algorithm as drawAlignmentHoles, applied to
        # s_half so the bottom-half y-positions match the adjacent standard wall.
        s_half = s / 2
        MIN_CLEAR = 5.0
        y_floor   = 3 * sp + r2 + r1 + MIN_CLEAR
        available = s_half - 2 * y_floor

        if available < 0:
            half_ys = []
        else:
            n = min(3, max(1, 1 + int(available / (2 * r1 + MIN_CLEAR))))
            # Force odd count — see drawAlignmentHoles for the reasoning.
            if n % 2 == 0:
                n -= 1
            if n == 1:
                half_ys = [s_half / 2]
            else:
                step = available / (n - 1)
                half_ys = [y_floor + i * step for i in range(n)]

        # Full list: bottom half + long-wall centre + top half mirrored.
        # The centre hole at s/2 is distinct from any half_ys value (half_ys
        # lives in [y_floor, s_half - y_floor] ⊂ [0, s_half], and y_floor > 0).
        big_ys = half_ys + [s / 2] + [s - y for y in reversed(half_ys)]

        # Draw the big through-holes along the vertical centre line.
        for y in big_ys:
            self._drawBigHole(l / 2, y, r1, along_x=False)

        # Fill every gap with sub-groups via _drawGapFeatures — same logic as
        # drawAlignmentHoles.  The "transition zone" gaps near s/2 are naturally
        # narrow and will produce only G2m or nothing, while the outer gaps
        # (matching the adjacent standard walls) receive the full G6 equivalent.
        corner_inner = 3 * sp + r2
        lo_bounds = [corner_inner]      + [y + r1 for y in big_ys]
        hi_bounds = [y - r1 for y in big_ys] + [s - corner_inner]
        for y_lo, y_hi in zip(lo_bounds, hi_bounds):
            self._drawGapFeatures(l, y_lo, y_hi)

        # Corner group-of-8 clusters — same layout as drawAlignmentHoles.
        self._drawCornerGroup8(s, l)

    def drawKites(self, r, joint_type, isTrapezoid):
        """Draw six kite-shaped cutouts inside the hexagonal spoke bottom panel.

        Each kite is derived from a master shape aligned with the flat-top
        orientation of the outer hexagon, then rotated in 60-degree increments.
        If the frame or spokes would degenerate (non-positive dimensions), the
        method falls back to a plain closed polygon with no cutouts.

        **Kite geometry** — in full-hex and trapezoid-with-side-supports modes
        the master kite has four vertices symmetric about the spoke axis:
        P1 (top, 120° pinned to the inner hex corner), P2 (right 90°, pinned
        to the inner hex edge), P3 (inner tip, 60° interior), and P4 (left
        90°, mirror of P2).  The six per-kite rotations of this master reproduce
        the original full-hex layout byte-for-byte.

        In **trapezoid mode with trapezoid_side_supports=False**, kites 2 and 3
        are redrawn as an L-shaped "right-angle" kite anchored at the inner
        tip rather than the outer apex.  The L-shape has:

          - P3 as the 90° corner at (∓spoke_width/2, −edge_width): the
            intersection of the central-spoke wall and the long-wall inner
            frame.  Both edge clearances are explicit — the long top wall
            carries the same edge_width frame as the natural hex sides.
          - Horizontal edge from P3 running toward the slanted side of the
            trapezoid.  P2 lies on the slanted inner-hex edge at y=−edge_width.
          - Vertical edge from P3 running down.  P4 lies on the bottom
            inner-hex edge at y=−A_inner.
          - P1 at the 240°/300° inner-hex corner, closing P1-P2-P3-P4.

        The L-shaped kite is no longer axially symmetric, so kite 3 is drawn
        as the x-axis mirror of kite 2 rather than a rotation.

        @param r           - Inner corner radius of the hexagon bottom panel.
        @param joint_type  - Two-character edge string (e.g. 'yY') passed
                             through to regularPolygonWall on fallback.
        @param isTrapezoid - When True, only the two kites in the flat half
                             are drawn (half-hexagon / trapezoid mode).  In
                             trapezoid mode with trapezoid_side_supports=False,
                             the L-shape kites replace the rotated masters.
        """
        n = self.n
        edge_width = self.edge_width
        spoke_width = self.spoke_width

        sqrt3 = math.sqrt(3)
        cos30 = sqrt3 / 2.0
        A_outer = r * cos30             # outer apothem of the hex
        A_inner = A_outer - edge_width  # apothem inset by the frame width
        if A_inner <= 0:
            # Frame width consumes the entire panel — fall back to solid hex.
            self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
            return
        R_inner = A_inner / cos30                   # inner corner radius after frame

        widen_kites = isTrapezoid and not self.trapezoid_side_supports

        # Original full-hex s (half the chord length of the kite base).
        s = (A_inner / sqrt3) - (spoke_width / 2.0)
        if s <= 0:
            # Spokes are too wide to fit — fall back to solid hex.
            self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
            return

        if widen_kites:
            # L-shaped kites for trapezoid mode with the side supports removed.
            # The shape is defined directly in the centre frame rather than via
            # a rotated master, because the shape is no longer axially symmetric
            # about the spoke axis.
            #
            # The "inner trapezoid" available for kite cutouts is bounded by:
            #   - central-spoke left/right walls at x = ∓spoke_width/2
            #   - long-wall inner frame at y = -edge_width  (new in this pass —
            #     the long top wall is an edge of the trapezoid panel and must
            #     carry the same edge_width frame as the natural hex sides)
            #   - slanted inner-hex edges from 240°/300° corners toward 180°/0°
            #   - bottom inner-hex edge at y = -A_inner

            # Degenerate guard: frame widths would overlap and leave nothing
            # for the kite cutout.
            if edge_width >= A_inner or spoke_width >= R_inner:
                self.regularPolygonWall(corners=n, r=r, edges=joint_type[1], move="right")
                return

            # P3 at the 90° corner where the central-spoke wall meets the
            # long-wall frame.
            #
            # The long top cut line does not pass through the callback origin
            # (near the hex centre): the V2/V5 miter fixes in drawTrapezoidWall
            # shift the drawn long-top path up by exactly `thickness` in the
            # callback frame (see drawTrapezoidWall: the two forward steps at
            # V1 and V2 in the slant direction each contribute t/2 in y, for
            # a total of thickness).  Measuring the frame from the physical
            # cut therefore places the kite's horizontal edge at
            #     p3_y = thickness − edge_width
            # so the gap between cut line and kite equals edge_width exactly.
            p3_x = -spoke_width / 2.0
            p3_y = self.thickness - edge_width

            # P2: horizontal edge from P3 runs left until it meets the slanted
            # inner-hex edge from the 240° corner toward the 180° corner.
            # Slanted line equation: y = -√3 · (x + R_inner).
            p2_x = -p3_y / sqrt3 - R_inner
            p2_y = p3_y

            # P4: vertical edge from P3 runs down to the bottom inner-hex
            # edge at y = -A_inner.
            p4_x = p3_x
            p4_y = -A_inner

            # P1 at the 240° inner-hex corner, closing the quadrilateral.
            p1_x = -R_inner / 2.0
            p1_y = -A_inner

            kite_2 = [(p1_x, p1_y), (p2_x, p2_y),
                      (p3_x, p3_y), (p4_x, p4_y)]
            # Kite 3 is the y-axis mirror of kite 2 (flip x sign).
            kite_3 = [(-p1_x, p1_y), (-p2_x, p2_y),
                      (-p3_x, p3_y), (-p4_x, p4_y)]

            for kite in (kite_2, kite_3):
                self.ctx.move_to(kite[0][0], kite[0][1])
                for x_, y_ in kite[1:]:
                    self.ctx.line_to(x_, y_)
                self.ctx.line_to(kite[0][0], kite[0][1])
                self.ctx.stroke()
            return

        # ── Original rotation-based kite (full hex + trapezoid with sides) ──
        # Define the master kite with its apex pointing upward (+y direction).
        P1 = (0.0, R_inner)                          # top vertex (120° angle)
        P2 = (s * sqrt3 / 2.0, R_inner - s / 2.0)   # right 90° vertex
        P3 = (0.0, R_inner - 2.0 * s)               # inner 60° vertex
        P4 = (-s * sqrt3 / 2.0, R_inner - s / 2.0)  # left 90° vertex

        def rotate_points(pts, angle_deg):
            """Rotate a list of (x, y) points around the origin by angle_deg."""
            ang = math.radians(angle_deg)
            ca, sa = math.cos(ang), math.sin(ang)
            return [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]

        # Rotate master kite 30° so its edges align with the flat-top hex orientation.
        kite_master = rotate_points([P1, P2, P3, P4], 30)

        # Produce one kite per hex face by rotating the master in 60° steps.
        kites = [rotate_points(kite_master, 60 * i) for i in range(6)]

        for kite_counter, kite in enumerate(kites):
            # In trapezoid mode only kites 2 and 3 are drawn.  The master kite
            # has its apex at +y (upward), so after the 30° alignment rotation:
            #   kite 0 apex → upper-left  (above centre, outside the trapezoid)
            #   kite 1 apex → left        (at centre height)
            #   kite 2 apex → lower-left  (below centre, inside the trapezoid) ✓
            #   kite 3 apex → lower-right (below centre, inside the trapezoid) ✓
            #   kite 4 apex → right       (at centre height)
            #   kite 5 apex → upper-right (above centre, outside the trapezoid)
            # The trapezoid is the bottom half of the hexagon, so only kites 2
            # and 3 fall within its boundary.
            if isTrapezoid and kite_counter not in (2, 3):
                continue

            self.ctx.move_to(kite[0][0], kite[0][1])
            for x_, y_ in kite[1:]:
                self.ctx.line_to(x_, y_)
            self.ctx.line_to(kite[0][0], kite[0][1])
            self.ctx.stroke()

    # Old full-hexagon toggles, as routes (edge numbering: see --track_routes).
    # Each draws the --track_line_count family; the order keeps the drawing
    # (and template) order of the original implementation.
    _TOGGLE_ROUTES = (("track_left", 6, 4), ("track_right", 4, 2),
                      ("track_top", 2, 6), ("track_middle", 4, 1))
    # Edges the trapezoid (lower half-hexagon) actually has.
    _TRAPEZOID_EDGES = {3, 4, 5}

    def _trackRoutes(self, isTrapezoid):
        """The concrete routes this module's track is drawn along.

        --track_routes wins when set.  Otherwise the trapezoid draws its one
        curve (edge 5 → edge 3) and the full hexagon draws whichever of
        --track_left/right/top/middle are on, each as the --track_line_count
        family.

        @param isTrapezoid - True for the half-hexagon deck.
        @returns ``(routes, explicit)``: ``(start, start_offset, end,
                 end_offset)`` tuples, and whether they came from
                 --track_routes (explicit routes must all fit; family routes
                 too tight to draw are skipped, as before).
        @throws ValueError - On a malformed --track_routes, or one using an
                             edge the trapezoid does not have.
        """
        specs = parse_track_routes(self.track_routes)
        explicit = bool(specs)
        if explicit and isTrapezoid:
            missing = sorted({e for s in specs for e in (s.start, s.end)}
                             - self._TRAPEZOID_EDGES)
            if missing:
                raise ValueError(
                    f"--track_routes: the trapezoid has no edge {missing[0]}; it "
                    "only has edges 3, 4 and 5 (and its curve runs 5–3).")
        if not explicit:
            if isTrapezoid:
                specs = [RouteSpec(5, 3, None, None)]
            else:
                specs = [RouteSpec(a, b, None, None)
                         for opt, a, b in self._TOGGLE_ROUTES if getattr(self, opt)]
        return expand_routes(specs, self._trackOffsets()), explicit

    def _trackRouteGeometries(self, r, isTrapezoid):
        """Solve every route for this deck (see :mod:`_hexmo_track_routes`).

        @param r           - Inner hexagon circumradius (the deck's).
        @param isTrapezoid - True for the half-hexagon deck.
        @returns List of :class:`RouteGeometry`, in drawing order.
        @throws ValueError - If an explicit --track_routes entry cannot be
                             drawn (adjacent edges, offsets too large).
        """
        apothem = r * math.sqrt(3.0) / 2.0
        routes, explicit = self._trackRoutes(isTrapezoid)
        geometries = []
        for start, so, end, eo in routes:
            try:
                geometries.append(route_geometry(start, so, end, eo, apothem,
                                                 self.track_lead_in))
            except ValueError:
                if explicit:
                    raise
                # A family offset so far inside that the curve collapses was
                # always silently skipped; keep doing so.
        return geometries

    def drawHexTrackTemplates(self, r, isTrapezoid=False):
        """Cut the --track_template pieces for this module's track routes.

        Each route's template follows its centreline exactly: lead-in, arc
        and lead-out for a curve, the straight for a straight, both arcs of
        an S-curve.  Routes that give the same piece (mirror images or
        reversals, such as the full hexagon's left/right/top curves at one
        offset) share a template, since a template can be turned over or
        round.  A piece too tight to cut (an arc radius within half the
        template width of zero) is skipped.

        @param r           - Inner hexagon circumradius (as for drawTrackLines).
        @param isTrapezoid - True for the half-hexagon deck.
        @throws ValueError - Propagated from the template width checks or an
                             explicit --track_routes entry that cannot be drawn.
        """
        half = self._templateWidth() / 2.0
        gauge = f"{self.track_gauge:g}mm"
        seen = set()
        for geometry in self._trackRouteGeometries(r, isTrapezoid):
            steps = route_template_steps(geometry)
            key = template_key(steps)
            if key in seen:
                continue
            seen.add(key)
            arcs = [st for st in steps if st[0] == "arc"]
            if any(st[2] - half <= 0 for st in arcs):
                continue
            if not arcs:
                label = f"straight {gauge}"
            elif len(arcs) == 1:
                label = f"R{geometry.radius:.0f} {gauge}"
            else:
                label = f"S R{geometry.radius:.0f} {gauge}"
            self.drawTrackTemplate(list(steps), label, move="right")

    def drawTrackLines(self, r, isTrapezoid=False):
        """Etch the model-railway track onto the deck as an alignment guide.

        Six hexagon modules joined edge-to-edge in a ring form one closed loop
        of track; each module carries a 60° arc of that loop.  The loop radius
        is ``1.5 · R`` (R = the hexagon circumradius, ``--radius``; see the
        scale READMEs), with the arc meeting each edge square at its midpoint
        so neighbouring modules join smoothly.

        **Routes.**  Every track drawn is a *route* between two edges (see
        :mod:`boxes.generators._hexmo_track_routes` for the geometry): a
        straight lead-in of ``--track_lead_in`` (L), one 60° arc, and a
        lead-out, for edges two apart; a straight (or S-curve) for opposite
        edges.  The trapezoid's curve is the route edge 5 → edge 3; the full
        hexagon's ``--track_left`` 6→4, ``--track_right`` 4→2, ``--track_top``
        2→6 and ``--track_middle`` 4→1; or ``--track_routes`` lists any
        others, with their own offset at each end.  With equal offsets a curve
        is concentric with the ring: radius ``(A − L)·√3 + offset`` with
        ``A = R·√3/2``, i.e. ``1.5·R − √3·L`` on the centreline.  Unequal
        offsets give the largest arc that keeps L at both ends.

        **Parallel tracks.**  A route given without offsets is drawn once per
        ``--track_line_count`` offset (``--track_spacing``, ``--track_offset``,
        ``--track_center_offset``), so the family stays parallel and each
        track meets the edge at its own offset.

        **What is etched.**  ``--draw_center`` etches each route's centreline;
        ``--draw_track`` etches the two footprint edges ``± --track_width/2``
        either side (the route shifted sideways: lines move, arcs change
        radius about the same centre, so the edges stay parallel).  Both may
        be on together.  A footprint arc that would collapse is skipped.

        **Radius label.**  With ``--track_label``, each curve's radius is
        etched at the middle of its arc (at the join of an S-curve's two
        arcs): millimetres just outside the centreline, inches (1 dp) just
        inside, sized from ``--track_width`` so both sit inside the footprint
        and are hidden once track is laid.

        **Transition ticks.**  With ``--track_crossing``, a short tick across
        the track marks every point where a straight meets an arc.

        **Frame origin.**  Fired from callback[0].  ``regularPolygonWall``
        fires it at the true hexagon centre, but ``drawTrapezoidWall`` fires
        it at the join-edge outer face, one thickness ``t`` below the true
        centre (the kites are built around that frame, so callback[0] itself
        is left alone).  Every edge's fingers are centred on the path-edge
        midpoint, on the edge normal through the *true* centre, so in
        trapezoid mode the origin is shifted up by ``t`` before drawing — the
        same ``apothem + t`` centre that ``drawSupportHoles`` uses.

        Drawn in ``Color.ETCHING`` inside a saved context so the engrave colour
        does not leak into subsequent cut paths.

        @param r           - Inner hexagon circumradius (the deck's), in mm.
        @param isTrapezoid - True for the half-hexagon deck.
        @throws ValueError - If an explicit --track_routes entry cannot be drawn.
        """
        if self.track_line_count < 1:
            return
        geometries = self._trackRouteGeometries(r, isTrapezoid)

        with self.saved_context():
            self.set_source_color(Color.ETCHING)
            if isTrapezoid:
                # drawTrapezoidWall fires callback[0] one thickness below the
                # true hex centre (see "Frame origin" above); lift the origin
                # so the crossings land on each slanted edge's middle finger.
                self.moveTo(0, self.thickness)
            for geometry in geometries:
                self._drawTrackRoute(geometry)

    def _underTrackEdges(self, isTrapezoid):
        """Edges whose side walls get the under-deck track opening.

        @param isTrapezoid - True for the half-hexagon (edges 3, 4, 5 only).
        @returns Sorted list of edge numbers (empty when the option is unset).
        @throws ValueError - On anything but comma-separated edge numbers 1–6,
                             or an edge the trapezoid does not have.
        """
        text = self.under_track_edges.strip()
        if not text:
            return []
        edges = set()
        for item in text.split(","):
            item = item.strip()
            if not item.isdigit() or not 1 <= int(item) <= 6:
                raise ValueError(
                    f"--under_track_edges: {item!r} is not an edge number 1–6.")
            edges.add(int(item))
        if isTrapezoid and not edges <= self._TRAPEZOID_EDGES:
            raise ValueError(
                "--under_track_edges: the trapezoid only has edges 3, 4 and 5 "
                f"(got {', '.join(str(e) for e in sorted(edges))}).")
        return sorted(edges)

    # Deck side index → edge number, in the order the deck panel draws its
    # sides (anticlockwise from the bottom).  The trapezoid's third side is
    # its long join edge, which has no edge number.
    _DECK_SIDE_EDGES = (4, 3, 2, 1, 6, 5)
    _TRAPEZOID_DECK_SIDE_EDGES = (4, 3, None, 5)
    # Minimum solid material between a track opening and any other hole.
    _TRACK_OPENING_CLEAR = 2.0

    def _trackOpeningPlan(self, isTrapezoid, l):
        """Parse and classify --track_openings.

        @param isTrapezoid - True for the half-hexagon (edges 3, 4, 5 only).
        @param l           - Wall body height: floor panel top to deck underside.
        @returns Dict edge → list of ``(opening, notch)``, where ``notch`` is
                 True when a 40 mm train on that track would not fit under
                 one thickness of wall below the deck.
        @throws ValueError - On a malformed entry, an edge the module does not
                             have, or a track height too near the floor or
                             above the deck underside.
        """
        t = self.thickness
        plan = {}
        for opening in parse_track_openings(self.track_openings,
                                            self.under_track_width):
            if isTrapezoid and opening.edge not in self._TRAPEZOID_EDGES:
                raise ValueError(
                    f"--track_openings: the trapezoid has no edge {opening.edge}; "
                    "it only has edges 3, 4 and 5.")
            if opening.height < t:
                raise ValueError(
                    f"--track_openings: a track at {opening.height:g} mm would cut "
                    f"into the floor joint; keep it at least {t:g} mm above the "
                    "floor panel.")
            if opening.height >= l:
                raise ValueError(
                    f"--track_openings: a track at {opening.height:g} mm is not "
                    f"below the deck underside ({l:g} mm above the floor panel).")
            notch = opening.height + self._UNDER_TRACK_ENVELOPE > l - t
            plan.setdefault(opening.edge, []).append((opening, notch))
        return plan

    def _deckEdges(self, char, isTrapezoid, deck_length, wall_length, notches):
        """Deck edge types, split where a wall below is notched.

        @param char        - The deck's joint edge character (e.g. 'Z').
        @param isTrapezoid - Selects the side → edge numbering.
        @param deck_length - Deck side length.
        @param wall_length - Wall top-edge length.
        @param notches     - Edge → list of ``(position, width, depth)``.
        @returns ``char`` when nothing is notched, else one edge per deck side.
        """
        if not notches:
            return char
        sides = self._TRAPEZOID_DECK_SIDE_EDGES if isTrapezoid else self._DECK_SIDE_EDGES
        base = self.edges[char]
        edges = []
        for edge in sides:
            if edge in notches:
                _, deck = wall_and_deck_pieces(wall_length, deck_length, notches[edge])
                edges.append(SplitJointEdge(self, base, deck))
            else:
                edges.append(base)
        return edges

    def _checkTrackOpenings(self, s, l, rects, under_rect, big_holes):
        """Keep every track opening clear of the wall's other holes.

        @param s          - Wall pattern length (the frame of the holes).
        @param l          - Wall body height.
        @param rects      - Track openings, ``(x0, x1, y0, y1)`` in the wall
                            frame (x up the wall, y along it).
        @param under_rect - The under-deck opening's rectangle, or None.
        @param big_holes  - Big holes still to be drawn, ``(x, y, r)``.
        @throws ValueError - If an opening comes within _TRACK_OPENING_CLEAR mm
                             of a corner-group or big hole, another opening, or
                             runs off the wall.
        """
        clear = self._TRACK_OPENING_CLEAR
        holes = [(x, y, r) for x, y, r in self._cornerGroupHoles(s, l)] + list(big_holes)
        others = list(rects) + ([under_rect] if under_rect else [])
        for i, rect in enumerate(rects):
            x0, x1, y0, y1 = rect
            if y0 < clear or y1 > s - clear:
                raise ValueError("--track_openings: an opening runs off the end of the wall.")
            for hole in holes:
                gap = rect_circle_gap(rect, hole)
                if gap < clear:
                    raise ValueError(
                        f"--track_openings: an opening at {y0 + (y1 - y0) / 2 - s / 2:+.1f} mm "
                        f"comes within {gap:.1f} mm of the wall's corner/registration "
                        f"holes (needs {clear:g}); move it or narrow it.")
            for j, other in enumerate(others):
                if j == i:
                    continue
                ox0, ox1, oy0, oy1 = other
                gap = max(oy0 - y1, y0 - oy1, ox0 - x1, x0 - ox1)
                if gap < clear:
                    raise ValueError(
                        "--track_openings: two openings on one wall overlap or come "
                        f"within {clear:g} mm of each other.")

    def drawRouteTrackGuides(self, s, l, r, isTrapezoid):
        """One track-guide plate per edge that --track_routes crosses.

        With --track_routes each edge can carry its own set of tracks at its
        own positions, so one plate no longer fits every wall.  Each plate is
        labelled with its edge.  Its windows sit where the routes cross that
        edge, measured anticlockwise (seen from above) from the edge midpoint.
        Routes that leave from the same point, like a turnout's two routes,
        share a window.  Facing the wall from outside, anticlockwise is to the
        right, so when the windows are not symmetric the plate is etched
        "edge N side ->", naming the neighbouring edge on that side.

        @param s           - Wall reference length (``side_orig``).
        @param l           - Wall body height.
        @param r           - Inner hexagon circumradius (as for drawTrackLines).
        @param isTrapezoid - True for the half-hexagon deck.
        @throws ValueError - From the route geometry or a window that does not fit.
        """
        apothem = r * math.sqrt(3.0) / 2.0
        by_edge = {}
        for geometry in self._trackRouteGeometries(r, isTrapezoid):
            ends = ((geometry.start, geometry.segments[0].p0),
                    (geometry.end, geometry.segments[-1].p1))
            for edge, point in ends:
                # Rounded so that shared starts collapse to one window and a
                # symmetric pair compares as symmetric.
                position = round(edge_position(edge, point, apothem), 6) + 0.0
                by_edge.setdefault(edge, set()).add(position)
        for edge in sorted(by_edge):
            neighbour = 6 if edge == 1 else edge - 1   # anticlockwise neighbour
            self.drawTrackGuide(s, l, move="right", offsets=sorted(by_edge[edge]),
                                label=f"track guide edge {edge}",
                                arrow=f"edge {neighbour} side ->")

    # Polyline steps per arc: plenty for a smooth engraved curve.
    _ARC_STEPS = 64

    def _drawTrackRoute(self, geometry):
        """Etch one route: centreline and/or footprint, ticks and label.

        @param geometry - A solved :class:`RouteGeometry`.
        """
        half_width = self.track_width / 2.0
        visible = self.draw_center or self.draw_track

        def stroke(segments):
            points = segments_polyline(segments, self._ARC_STEPS)
            self.ctx.move_to(*points[0])
            for point in points[1:]:
                self.ctx.line_to(*point)
            self.ctx.stroke()

        if self.draw_center:
            stroke(geometry.segments)
        if self.draw_track:
            for d in (-half_width, half_width):
                shifted = offset_segments(geometry.segments, d)
                if shifted is not None:
                    stroke(shifted)
        if self.track_crossing and visible:
            self._drawTransitionTicks(geometry.segments, half_width)
        if self.track_label and visible and geometry.radius is not None:
            self._drawRadiusLabel(geometry)

    def _drawTransitionTicks(self, segments, half_width):
        """Tick across the track wherever a straight meets an arc.

        The tick runs along the arc's radius there, so it crosses the track
        square.  It spans the footprint (when drawn) plus 6 mm each side.

        @param segments   - The route's pieces.
        @param half_width - Half of --track_width.
        """
        cross_half = (half_width if self.draw_track else 0.0) + 6.0
        for i, seg in enumerate(segments):
            if not isinstance(seg, Arc):
                continue
            before = segments[i - 1] if i > 0 else None
            after = segments[i + 1] if i + 1 < len(segments) else None
            for neighbour, point in ((before, seg.p0), (after, seg.p1)):
                if not (isinstance(neighbour, Line) and neighbour.length > 1e-9):
                    continue
                ux = (point[0] - seg.centre[0]) / seg.radius
                uy = (point[1] - seg.centre[1]) / seg.radius
                r_lo = max(0.0, seg.radius - cross_half)
                r_hi = seg.radius + cross_half
                self.ctx.move_to(seg.centre[0] + r_lo * ux, seg.centre[1] + r_lo * uy)
                self.ctx.line_to(seg.centre[0] + r_hi * ux, seg.centre[1] + r_hi * uy)
                self.ctx.stroke()

    def _drawRadiusLabel(self, geometry):
        """Etch a curve's radius in mm (outside) and inches (inside).

        The label sits at the middle of the arc (the join of an S-curve's two
        arcs), turned to follow the track and kept upright.

        @param geometry - A solved :class:`RouteGeometry` with a radius.
        """
        fontsize = self.track_width * 0.35
        if fontsize <= 0:
            return
        # At 0.35·width, a line centred in each half of the footprint
        # [0, width/2] stays clear of the centreline and the rail edge.
        band = self.track_width / 4.0
        arcs = [seg for seg in geometry.segments if isinstance(seg, Arc)]
        arc = arcs[0]
        angle = arc.start_angle + (arc.sweep / 2.0 if len(arcs) == 1 else arc.sweep)
        apex = arc.point(angle)
        ux, uy = math.cos(angle), math.sin(angle)   # outward, from the arc centre
        # Follow the track (tangent = radius + 90°), normalised to (−90°, 90°].
        text_angle = ((math.degrees(angle) + 180.0) % 180.0) - 90.0
        rho = geometry.radius
        # stroke=True paints the glyph outlines in the ETCHING stroke colour
        # with no fill, so lasers that vector-etch by stroke colour (ignoring
        # fill) still trace these labels.
        for text, sign in ((f"{rho:.0f} mm", 1.0), (f'{rho / 25.4:.1f}"', -1.0)):
            with self.saved_context():
                self.text(text, x=apex[0] + sign * band * ux, y=apex[1] + sign * band * uy,
                          angle=text_angle, align="middle center",
                          fontsize=fontsize, color=Color.ETCHING, stroke=True)

    def drawTrapezoidWall(self, r, edges_char='e', hole=None, callback=None, move=None):
        """Draw a trapezoidal panel — the bottom (or top) half of a regular hexagon.

        The trapezoid is derived by slicing a flat-top hexagon horizontally through
        its centre.  Two trapezoids placed back-to-back on their long edge reform the
        original hexagon.  The four edges, traversed counter-clockwise from the
        bottom-left vertex (V0), are:

          Edge 0 — short bottom edge, length r  (hex side length)
          Edge 1 — right slanted side, length r
          Edge 2 — long top/join edge, length 2r
          Edge 3 — left slanted side, length r

        Exterior turn angles (same as regularPolygonWall convention):
          60° at V1 and V0 (interior angle 120°)
          120° at V2 and V5 (interior angle 60°)

        Callback convention (identical to regularPolygonWall):
          callback[0] — fired at the hexagon centre (r/2 from V0, H above V0)
          callback[1..4] — fired at the start of edges 0..3 respectively

        The bounding box width equals that of the full hexagon (both span 2r
        horizontally), so the layout cursor advances by the same x-amount as a
        corresponding regularPolygonWall call would.

        @param r          - Hexagon circumradius (= hex side length).
        @param edges_char - Edge type character or single-char string for all four
                            sides (default 'e').  One char is replicated to all four
                            edges; a 4-char string assigns each edge individually.
        @param hole       - Diameter of a central circular cutout, or None.
        @param callback   - List/tuple of callables; indexed per the convention above.
        @param move       - Layout direction string ('right', 'up only', etc.).
        """
        # H_geom = r*√3/2 is the apothem of the hexagon (= intended panel height).
        # H is a helper variable used only for the bounding box and callback positions;
        # it does NOT control the actual cut path height.
        #
        # Bounding box height = H + 2*thickness + spacing.  We want this to equal
        # H_geom + spacing, so H = H_geom - 2*thickness.
        #
        # The cut path height is determined by the edge/corner geometry.  A naive
        # edgeCorner(120° exterior) at V2 produces step1 = t*tan(60°) = t√3 in the
        # 60° direction, contributing y = t√3·sin(60°) = 3t/2.  Combined with V1's
        # +t/2 and the per-edge shortfall, the total comes out to H_geom + t — one
        # thickness too tall.
        #
        # The fix: at V2 and V5 the step that lies along the slant direction is drawn
        # as t/√3 (matching the miter used at 60°-exterior hex vertices) rather than
        # t√3.  This brings the join-edge outer face to exactly H_geom, so two
        # trapezoid panels placed back-to-back on their join edges reproduce the full
        # hexagon height.
        H = r * math.sqrt(3) / 2.0 - 2 * self.thickness

        # Resolve the edge character(s) to edge objects.  Replicate a single char
        # across all four sides; otherwise treat as a per-edge sequence.
        if not hasattr(edges_char, "__getitem__") or len(edges_char) == 1:
            edges = [self.edges.get(edges_char, edges_char)] * 4
        else:
            edges = [self.edges.get(e, e) for e in edges_char]
        edges = edges + edges   # duplicate for wrapping corner references

        # Bounding box.  The trapezoid has the same horizontal span as the full
        # hexagon (leftmost point x = -r/2, rightmost x = 3r/2), so we reuse the
        # hex tw formula from regularPolygonWall.  Height:
        #   path_height = H_geom (achieved via the custom V2/V5 corners below)
        #   th = path_height + edges[0].spacing() = H_geom + spacing
        sp = max(edges[i].spacing() for i in range(4))
        tw = 2 * r + 2 * sp / math.sin(math.radians(60))
        th = H + 2 * self.thickness + edges[0].spacing()

        if self.move(tw, th, move, before=True):
            return

        # Position the cursor at V0 — the left end of the short bottom edge.
        # Formula mirrors regularPolygonWall: 0.5*tw - 0.5*side, where side=r.
        self.moveTo(0.5 * tw - 0.5 * r, edges[0].margin())

        # Centre callback (callback[0] for kites) and optional central hole.
        # The hex centre sits at the join-edge outer face level (H_geom from V0).
        # We fire the callback at y = H + 2*thickness + burn = H_geom + burn so
        # that kite paths originate at the join-edge boundary and extend inward
        # (downward in panel coordinates).
        if hole:
            self.hole(r / 2., H + 2 * self.thickness + self.burn, hole / 2.)
        self.cc(callback, 0, r / 2., H + 2 * self.thickness + self.burn)

        # ── Edge 0: short bottom edge (length r) ─────────────────────────────
        self.cc(callback, 1, 0, edges[0].startWidth() + self.burn)
        edges[0](r)
        self.edgeCorner(edges[0], edges[1], 60)    # 60° exterior at V1 (interior 120°)

        # ── Edge 1: right slanted side (length r) ────────────────────────────
        self.cc(callback, 2, 0, edges[1].startWidth() + self.burn)
        edges[1](r)

        # V2 corner (120° exterior, interior 60°): use t/√3 for the slant-direction
        # step instead of the standard t·tan(60°) = t√3.  This is the same miter
        # size used at hexagon vertices (60° exterior) and places the join-edge outer
        # face at exactly H_geom — half the full hexagon path height.
        self.edge(self.thickness / math.sqrt(3.0))
        self.corner(120)
        # step3 at 180°: use 2t/√3 (= 2A) not t·tan(60°)=t√3 (= 3A).
        # The 3A value over-extends the path by A = t/√3 per side, producing a
        # trapezoid that is 2A = 2t/√3 wider than the hexagon.  2A matches the
        # miter geometry needed for the join-edge outer face to align with the
        # corresponding hexagon vertex.
        self.edge(2.0 * self.thickness / math.sqrt(3.0))

        # ── Edge 2: long top/join edge (length 2r) ───────────────────────────
        self.cc(callback, 3, 0, edges[2].startWidth() + self.burn)
        edges[2](2 * r)

        # V5 corner (120° exterior, interior 60°): symmetric reduction of the
        # return step3 (t/√3 instead of t√3) so the path closes correctly after
        # the modified V2 step1.
        # step1 at 180°: symmetric reduction matching the V2 step3 fix above.
        # 2t/√3 instead of t·tan(60°)=t√3 so both corners contribute equally to
        # closing the extra horizontal travel introduced by the modified V2 step1.
        self.edge(2.0 * self.thickness / math.sqrt(3.0))
        self.corner(120)
        self.edge(self.thickness / math.sqrt(3.0))

        # ── Edge 3: left slanted side (length r) ─────────────────────────────
        self.cc(callback, 4, 0, edges[3].startWidth() + self.burn)
        edges[3](r)
        self.edgeCorner(edges[3], edges[0], 60)    # 60° exterior at V0 (interior 120°)

        self.move(tw, th, move)

    def drawReferencePanel(self, move="right"):
        """Render a flat reference panel listing all generator parameters.

        The panel is sized to contain the full parameter list as engraved text
        and uses Color.ETCHING so that laser software routes it as an engrave
        pass rather than a cut pass.  A Color.OUTER_CUT rectangle provides the
        border so the panel can be cut from stock.

        The panel is positioned using the standard boxes ``move`` convention:
        call with ``move="right"`` (default) to advance the layout cursor to
        the right of the panel, or ``move="up only"`` to reserve space only.

        @param move - Direction string passed to self.move() for layout
                      control.  Defaults to "right".
        """
        fontsize = 6          # mm — small but legible on most laser systems
        margin = 5            # mm — clearance between border and text
        line_height = 1.4 * fontsize  # matches boxes text() inter-line spacing
        panel_width = 150     # mm — wide enough for longest expected param lines

        # Gather current parameter values by walking all argparser actions and
        # reading the corresponding attribute off self.  Edge-setting args
        # (e.g. FingerJoint_finger) are also stored on self via setattr after
        # parse_args, so getattr covers them without special-casing.
        # Actions whose dest is SUPPRESS (e.g. --help) have no corresponding
        # attribute and are skipped by the getattr guard.
        params = []
        seen_dests: set[str] = set()
        for action in self.argparser._actions:
            dest = action.dest
            if dest in seen_dests or dest == argparse.SUPPRESS:
                continue
            seen_dests.add(dest)
            val = getattr(self, dest, None)
            if val is None:
                continue
            params.append((dest, val))
        params.sort(key=lambda p: p[0])

        # Build text: generator name + ISO timestamp header, then one param per line.
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        header_lines = [f"{self.__class__.__name__}  {timestamp}", ""]
        param_lines = [f"{dest}: {val}" for dest, val in params]
        lines = header_lines + param_lines

        panel_height = 2 * margin + len(lines) * line_height

        # First call with before=True: reserve layout space; return early if
        # the caller only wants space reservation (e.g. move="up only").
        if self.move(panel_width, panel_height, move, True):
            return

        # Outer cut border so the panel can be laser-separated from stock.
        self.set_source_color(Color.OUTER_CUT)
        self.ctx.rectangle(0, 0, panel_width, panel_height)
        self.ctx.stroke()

        # Render the parameter list as a single multi-line etching block.
        # boxes' text() iterates lines in reverse and moves upward per line,
        # so lines[0] ends up at the top and lines[-1] sits at y=margin.
        self.text(
            "\n".join(lines),
            x=margin,
            y=margin,
            fontsize=fontsize,
            color=Color.ETCHING,
        )

        # Second call: advance the layout cursor past the rendered panel.
        self.move(panel_width, panel_height, move)

    def render(self):
        """Generate all panels and walls that make up the hexagon box.

        Handles outside vs inside measurement modes and all supported
        top/bottom style variants.
        """
        r, h, n, isTrapezoid = self.radius, self.h, self.n, self.trapezoid

        if self.outside:
            # Convert outside measurements to inside by subtracting material thickness.
            r -= self.thickness / math.cos(math.radians(360 / (2 * n)))
            if self.top == "none":
                h = self.adjustSize(h, False)
            elif "lid" in self.top and self.top != "angled lid":
                h = self.adjustSize(h) - self.thickness
            else:
                h = self.adjustSize(h)

        t = self.thickness

        # Top and bottom radii are always equal, so a single regularPolygon call
        # suffices.  The taper scaffold (r0/r1, a, beta, d_top/d_bottom) from the
        # original starter-template geometry reduces to zero-taper constants and
        # has been removed.
        r, _, side = self.regularPolygon(n, radius=r)

        # Capture the original side length before shrinking — used for alignment-hole
        # position ratios and for computing the long trapezoid back-wall width.
        side_orig = side

        # Subtract two thicknesses from each side so finger joints fit flush.
        side -= 2 * t

        # Side-wall height equals box height (no taper — l simplifies from
        # sqrt((r0−r1)²+h²) to h when r0=r1).
        l = h
        # Dihedral correction angle between adjacent side panels (taper angle = 0).
        phi = 180 - 2 * math.degrees(math.asin(math.cos(math.pi / n)))

        # Track openings (--track_openings), parsed and checked before anything
        # is drawn.  Notched ones change both a wall's top edge and the deck
        # edge above it: edge → [(position, width, depth below the deck)].
        opening_plan = self._trackOpeningPlan(isTrapezoid, l)
        notches = {}
        for edge, entries in opening_plan.items():
            cut = [(o.position, o.width, l - o.height) for o, notch in entries if notch]
            if cut:
                notches[edge] = cut

        # Register custom finger-joint edge objects.  Each call mutates self.edges
        # as a side effect; the returned settings object is not used afterwards,
        # so it is assigned to _ to make the write-only pattern explicit.
        _ = copy.deepcopy(self.edges["f"].settings)
        _.setValues(self.thickness, angle=phi)
        _.edgeObjects(self, chars="gGH")

        # Top and bottom panels are parallel (no taper), so both use angle=90.
        _ = copy.deepcopy(self.edges["f"].settings)
        _.setValues(self.thickness, angle=90)
        _.edgeObjects(self, chars="yYH")

        _ = copy.deepcopy(self.edges["f"].settings)
        _.setValues(self.thickness, angle=90)
        _.edgeObjects(self, chars="zZH")

        def deck_edges(joint_type, is_top):
            """The face's edge types: the deck's are split over any notch."""
            if not is_top:
                return joint_type[1]
            return self._deckEdges(joint_type[1], isTrapezoid, side_orig, side, notches)

        def drawTop(r, top_type, joint_type, is_top=False):
            """Render one face (top or bottom) as the appropriate panel style.

            Top is always 'closed'; bottom is 'spoke' or 'closed'.  In
            trapezoid mode the hexagonal panel is replaced by the equivalent
            trapezoidal panel produced by drawTrapezoidWall.

            When bottom='spoke' the support walls have finger joints ('fefe')
            on both ends, so the closed top panel must carry matching support-
            hole slots.  The support-hole callback is placed at index 1 (the
            edge-0-start / V0 position) so that drawSupportHoles can translate
            from V0 to the hex centre with its standard moveTo(r/2, H, angle)
            formula — the same position used by the spoke bottom panel.

            The centre slot (callback[0], fired at the hex centre) carries the
            kite cutouts on a spoke face, or — on the top *deck* in trapezoid
            mode when --track_lines is on — the etched track-curve guide.  These
            never coincide: the top is always 'closed' (never 'spoke') and the
            track guide is only wired onto the top face, so a single callback[0]
            slot serves both without conflict.

            @param r          - Inner corner radius of this face.
            @param top_type   - 'closed' or 'spoke'.
            @param joint_type - Two-character edge string, e.g. 'yY' or 'zZ'.
            @param is_top     - True for the top (deck) face.  Enables the track
                                guide callback; the bottom face never gets it.
            """
            # Build the support-hole callback for closed panels.  Fires at the
            # V0-start slot (index 1); index 0 is None so the kites/centre slot
            # is skipped.  Active whenever self.supports is True, regardless of
            # whether the opposite face is "spoke" or "closed".
            if self.supports:
                support_cb = [None, lambda: self.drawSupportHoles(r=r, isTrapezoid=isTrapezoid)]
            else:
                support_cb = None

            # Track-curve guide: etched onto the top deck.  In trapezoid mode it
            # draws the single lower curve; on the full hexagon it draws the
            # --track_left/middle/right/top routes selected.  It occupies
            # callback[0]; if support slots are present we splice it into the
            # index-0 slot of the existing support callback list.
            if is_top and self.track_lines:
                track_cb = lambda: self.drawTrackLines(r=r, isTrapezoid=isTrapezoid)
                if support_cb is not None:
                    support_cb = [track_cb] + support_cb[1:]
                else:
                    support_cb = [track_cb]

            if isTrapezoid:
                if top_type == "spoke":
                    # Build spoke callbacks; only append drawSupportHoles when
                    # supports are enabled so the slot geometry matches the walls.
                    spoke_cbs = [lambda: self.drawKites(r=r, joint_type=joint_type, isTrapezoid=True)]
                    if self.supports:
                        spoke_cbs.append(lambda: self.drawSupportHoles(r=r, isTrapezoid=True))
                    self.drawTrapezoidWall(
                        r=r, edges_char=joint_type[1], move="right",
                        callback=spoke_cbs)
                else:  # "closed"
                    self.drawTrapezoidWall(r=r, edges_char=deck_edges(joint_type, is_top),
                                           move="right", callback=support_cb)
            else:
                if top_type == "spoke":
                    spoke_cbs = [lambda: self.drawKites(r=r, joint_type=joint_type, isTrapezoid=False)]
                    if self.supports:
                        spoke_cbs.append(lambda: self.drawSupportHoles(r=r))
                    self.regularPolygonWall(
                        corners=n, r=r, edges=joint_type[1], move="right",
                        callback=spoke_cbs)
                else:  # "closed"
                    self.regularPolygonWall(corners=n, r=r, edges=deck_edges(joint_type, is_top),
                                            move="right", callback=support_cb)

        with self.saved_context():
            # Draw bottom panel first, then top (order affects SVG layout).
            drawTop(r, self.bottom, "yY")
            drawTop(r, self.top, "zZ", is_top=True)
            # Support walls must be placed inside this saved_context block so
            # they land after the face panels in the layout stream.  Outside the
            # block the cursor reverts to its pre-block position, causing the
            # walls to overlap whatever is drawn next.
            if self.supports:
                self.drawSupports(isTrapezoid=isTrapezoid)

        # Invisible up-only move reserves vertical space for the panels above.
        # In trapezoid mode the panel is half-height, so use the trapezoid wall
        # for space reservation to avoid excess vertical whitespace in the layout.
        if isTrapezoid:
            self.drawTrapezoidWall(r=r, edges_char='F', move="up only")
        else:
            self.regularPolygonWall(corners=n, r=r, edges='F', move="up only")

        fingers_top = self.top in ("closed", "hole", "angled hole",
                                   "round lid", "angled lid2", "bayonet mount")
        fingers_bottom = self.bottom in ("closed", "hole", "angled hole",
                                         "round lid", "angled lid2", "spoke")

        t_ = self.edges["G"].startWidth()
        bottom_edge = ('y' if fingers_bottom else 'e')
        top_edge = ('z' if fingers_top else 'e')
        # No taper: d_top = d_bottom = 0, so l is unchanged after this point.

        # Alignment-hole callback shared by all hex side panels.
        # moveTo(0, -t) compensates for the 2*t trimming of side: the natural
        # callback origin sits t to the left of where it was before trimming,
        # so shifting t rightward (−y in local coords) restores centre alignment
        # when new and old panels are stacked and centred.
        def draw_aligned_holes(under_track=False, openings=()):
            self.moveTo(0, -self.thickness)
            if under_track or openings:
                self.drawAlignmentHoles(side_orig, l, "A", under_track=under_track,
                                        openings=openings)
            else:
                # The plain call, unchanged, so wrappers of drawAlignmentHoles
                # with the original signature (e.g. test spies) keep working.
                self.drawAlignmentHoles(side_orig, l, "A")

        # Standard walls in drawing order, as (edge, under_track): the walls
        # with an under-deck or track opening first (labelled with their edge,
        # since they are no longer interchangeable), then plain ones.
        under_edges = self._underTrackEdges(isTrapezoid)
        feature_edges = sorted(set(under_edges) | set(opening_plan))
        n_standard = 3 if isTrapezoid else n
        standard_walls = ([(e, e in under_edges) for e in feature_edges]
                          + [(None, False)] * (n_standard - len(feature_edges)))

        def wall_openings(edge):
            """This edge's track openings in the wall-hole frame.

            Positions are along the wall's top edge in its drawing direction;
            fitted with that direction anticlockwise, they match the deck.
            """
            rects = []
            for o, notch in opening_plan.get(edge, []):
                centre = side_orig / 2 + o.position
                top = l if notch else l - self.thickness
                rects.append(((o.height, top, centre - o.width / 2, centre + o.width / 2),
                              not notch))
            return rects

        def draw_standard_wall(edge, under_track):
            wall_edges = e0
            if edge in notches:
                # Segment 6 of borders0 is the top (deck) edge; split it round
                # the notches, keeping every other segment's edge type.
                wall_edges = [e0[i % 4] for i in range(len(borders0) // 2)]
                pieces, _ = wall_and_deck_pieces(side, side_orig, notches[edge])
                wall_edges[6] = SplitJointEdge(self, self.edges[top_edge], pieces)
            openings = wall_openings(edge)
            self.polygonWall(borders0, edge=wall_edges, correct_corners=False, move="right",
                             callback=[None, lambda: draw_aligned_holes(under_track, openings)],
                             label=f"edge {edge}" if edge is not None else "")

        # Alignment-hole callback for the trapezoid long back wall.
        # The hole pattern is always laid over the full 2*side_orig reference and
        # is symmetric about its own centre, so it is independent of how much the
        # drawn panel (side_long) has been trimmed.  To keep it centred on — and
        # therefore fixed relative to the centre of — the panel, the callback
        # origin (the bottom-right corner, at side_long/2 right of the panel
        # centre) is shifted by m = side_long/2 - side_orig.  For the historic
        # side_long = 2*side_orig - 2t this is -t; for the shortened
        # side_long = 2*side_orig - 3t it is -1.5t.  Deriving m from side_long
        # means the holes never move when the trim changes.
        def draw_aligned_holes_long():
            self.moveTo(0, side_long / 2 - side_orig)
            self.drawAlignmentHolesLong(2 * side_orig, l, "A")

        # Standard stepped-tab side-panel border.  With no taper, d_top = d_bottom = 0
        # and angle a = 0, so the border reduces to right-angle turns and the two
        # inset steps are zero-length.  The shape is still defined explicitly (rather
        # than a plain rectangle) so that the E-edge finger-joint tabs are placed
        # correctly by polygonWall.
        borders0 = [side, 90,
                    0, -90, t_, 90, l, 90, t_, -90, 0,
                    90, side, 90,
                    0, -90, t_, 90, l, 90, t_, -90, 0, 90]
        e0 = bottom_edge + 'E' + top_edge + 'E'

        if isTrapezoid:
            # Trapezoid side walls: 4 panels instead of 6.
            #
            #   1 × long back wall  — spans the join edge (length 2r)
            #   3 × standard walls  — one each for right slant, short front, left slant
            #

            # Long back-wall border.  The panel spans two hex-side-lengths with
            # finger-joint notches only at the two outer ends (no junction at the
            # midpoint in a trapezoid box).  It is trimmed by a further material
            # thickness (t/2 off each end, symmetric) beyond the 2*side_orig − 2*t
            # nominal: at full width the long wall butts into the two slanted side
            # walls when assembled and needs sanding, so the extra t of clearance
            # lets it drop in.  Because the trim is symmetric the panel centre is
            # unchanged, and the alignment-hole callback re-centres on side_long
            # (see draw_aligned_holes_long) so every hole keeps its position.
            side_long = 2 * side_orig - 3 * t
            borders_long = [side_long, 90,
                            0, -90, t_, 90, l, 90, t_, -90, 0,
                            90, side_long, 90,
                            0, -90, t_, 90, l, 90, t_, -90, 0, 90]

            # Long back wall (1 panel).  callback[1] fires at the first stepped-tab
            # segment where the alignment holes are drawn; callback[0] is None
            # (the former drawMarkers2 stub has been removed).
            self.polygonWall(borders_long, edge=e0, correct_corners=False, move="right",
                             callback=[None, draw_aligned_holes_long])

            # Three standard-width walls (right slant, front short, left slant).
            for edge, under_track in standard_walls:
                draw_standard_wall(edge, under_track)

        else:
            # Even number of sides (n=6): all panels use the stepped-tab profile.
            for edge, under_track in standard_walls:
                draw_standard_wall(edge, under_track)

        # Optional track-laying jig.  It fits any standard wall, so it takes
        # the standard-wall hole frame (side_orig, l), never the trapezoid
        # long wall's.
        if self.track_guide:
            if parse_track_routes(self.track_routes):
                self.drawRouteTrackGuides(side_orig, l, r, isTrapezoid)
            else:
                self.drawTrackGuide(side_orig, l, move="right")

        # Optional Tracksetta-style templates that follow the etched track.
        if self.track_template:
            self.drawHexTrackTemplates(r, isTrapezoid)

        # Append a reference panel that engraves all parameter values onto a
        # flat piece of stock — useful for reproducing or identifying a cut job.
        self.drawReferencePanel(move="right")
