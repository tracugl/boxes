"""Tracksetta-style track-laying templates shared by HexmoHexagon and HexmoRectangle.

A template is a flat strip that sits *between the rails*: flexible track is
pushed against both edges and holds the template's exact curve while it is
pinned down.  Commercial templates come in fixed radii that don't match the
Hexmo modules, so the generators cut their own.  Each one follows a module's
etched track centreline exactly, at the same radius, arc and lead-ins.

**Width.**  ``--track_gauge`` is the distance between the inside faces of the
rails (16.5 mm HO, 9 mm N), less an optional ``--track_template_clearance``
so the strip lifts out of laid track easily.  The outline is drawn with
``edge``/``corner``, whose burn compensation keeps the cut piece true-size.

**Routes.**  A route is a list of centreline steps, in order:
``("line", length)`` or ``("arc", degrees, radius)``.  Positive degrees turn
left; the steps join tangentially.  A HexmoHexagon curve is
``lead-in + 60° arc + lead-in``; a straight is a single line.
``--track_template_segments`` splits a route into equal-length pieces, each
cut as its own part, and ``piece i/N`` is etched on it.

The module name starts with an underscore, so generator discovery
(``getAllBoxGenerators``) skips it.  This mixin is not a generator.
"""
from __future__ import annotations

import math

from boxes import boolarg
from boxes.Color import Color


class HexmoTrackTemplateMixin:
    """Track-template geometry and drawing, mixed into both Hexmo generators."""

    _TEMPLATE_ARC_STEP = 2.0  # degrees per sample when tracing arcs (bounding boxes)

    def _addTrackTemplateArgs(self):
        """Register the --track_template options.

        Called from each generator's ``__init__`` with its other track
        options, so names, defaults and help text are identical in both.
        """
        self.argparser.add_argument(
            "--track_template", action="store", type=boolarg, default=False,
            help="Add Tracksetta-style track-laying template(s): strips exactly "
                 "--track_gauge wide that sit between the rails and follow this "
                 "module's track centreline (lead-ins and curve), one per track.  "
                 "Push flexible track against both edges to hold the exact curve "
                 "while pinning it.  Cut from the module's own --thickness.")
        self.argparser.add_argument(
            "--track_gauge", action="store", type=float, default=16.5,
            help="Track gauge (mm): the distance between the inside faces of the "
                 "rails, which is the template width.  16.5 for HO (default), "
                 "9 for N.  Not the same as --track_width, the sleeper/roadbed "
                 "footprint.")
        self.argparser.add_argument(
            "--track_template_clearance", action="store", type=float, default=0.0,
            help="Amount (mm) taken off the template width so it lifts out of "
                 "laid track easily.  0 (default) is exactly --track_gauge.")
        self.argparser.add_argument(
            "--track_template_segments", action="store", type=int, default=1,
            help="Split each track template into this many equal-length pieces, "
                 "e.g. to fit a smaller laser bed.  1 (default) cuts it whole.")

    # ---------------------------------------------------------------- geometry

    def _templateWidth(self):
        """Validated template width (mm): gauge less clearance.

        @throws ValueError - On a non-positive gauge, a clearance outside
                             [0, gauge), or fewer than one segment.
        """
        gauge, clear = self.track_gauge, self.track_template_clearance
        if gauge <= 0:
            raise ValueError(f"--track_gauge must be positive (got {gauge:g}).")
        if not 0 <= clear < gauge:
            raise ValueError(
                f"--track_template_clearance must be at least 0 and less than "
                f"--track_gauge {gauge:g} (got {clear:g}).")
        if self.track_template_segments < 1:
            raise ValueError(
                f"--track_template_segments must be at least 1 "
                f"(got {self.track_template_segments}).")
        return gauge - clear

    @staticmethod
    def _stepLength(step):
        """Centreline length of one route step."""
        if step[0] == "line":
            return step[1]
        return abs(math.radians(step[1])) * step[2]

    def _templatePieces(self, route):
        """Split ``route`` into --track_template_segments equal-length pieces.

        A cut may fall inside a line or an arc; the parts keep the arc's
        radius and turning direction, so the pieces join seamlessly.

        @param route - Centreline steps (see module docstring).
        @returns List of routes, one per piece, in order along the track.
        """
        n = max(1, self.track_template_segments)
        total = sum(self._stepLength(s) for s in route)
        cuts = [total * k / n for k in range(n + 1)]
        pieces = []
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            piece, pos = [], 0.0
            for step in route:
                length = self._stepLength(step)
                a, b = max(lo, pos), min(hi, pos + length)
                if b - a > 1e-9:
                    frac = (b - a) / length
                    if step[0] == "line":
                        piece.append(("line", b - a))
                    else:
                        piece.append(("arc", step[1] * frac, step[2]))
                pos += length
            pieces.append(piece)
        return pieces

    def _templateOutline(self, piece):
        """Counter-clockwise band outline of one piece, as edge/corner ops.

        Runs along the right-hand rail edge forwards, squares across the end,
        returns along the left-hand edge, and squares across the start.  On
        a left turn the right edge is the outer one (radius r + w/2), and on a
        right turn the inner one (r − w/2).  Traversed backwards, an arc turns
        the opposite way about the same centre.

        @param piece - Centreline steps of one piece.
        @returns ``[("edge", length) | ("corner", degrees, radius)]`` in true
                 dimensions; radius 0 is a sharp corner.
        """
        w = self._templateWidth()
        half = w / 2.0
        ops = []
        for step in piece:
            if step[0] == "line":
                ops.append(("edge", step[1]))
            else:
                deg, r = step[1], step[2]
                ops.append(("corner", deg, r + half if deg > 0 else r - half))
        ops += [("corner", 90.0, 0.0), ("edge", w), ("corner", 90.0, 0.0)]
        for step in reversed(piece):
            if step[0] == "line":
                ops.append(("edge", step[1]))
            else:
                deg, r = step[1], step[2]
                ops.append(("corner", -deg, r - half if deg > 0 else r + half))
        ops += [("corner", 90.0, 0.0), ("edge", w), ("corner", 90.0, 0.0)]
        return ops

    def _templateTrace(self, ops, start=(0.0, 0.0), heading=0.0):
        """Trace ops (or centreline steps) as points, ignoring burn.

        Used for the part's bounding box and the label position.  Accepts
        outline ops (``edge``/``corner``) or route steps (``line``/``arc``).

        @returns List of ``(x, y)`` points, starting at ``start``.
        """
        x, y = start
        h = heading
        pts = [(x, y)]
        for op in ops:
            if op[0] in ("edge", "line"):
                x += op[1] * math.cos(math.radians(h))
                y += op[1] * math.sin(math.radians(h))
                pts.append((x, y))
                continue
            deg, r = op[1], op[2]
            if r <= 0:
                h += deg
                continue
            side = 90.0 if deg > 0 else -90.0
            cx = x + r * math.cos(math.radians(h + side))
            cy = y + r * math.sin(math.radians(h + side))
            steps = max(1, int(math.ceil(abs(deg) / self._TEMPLATE_ARC_STEP)))
            a0 = math.atan2(y - cy, x - cx)
            for k in range(1, steps + 1):
                a = a0 + math.radians(deg) * k / steps
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            x, y = pts[-1]
            h += deg
        return pts

    def _templatePointAt(self, piece, distance, start, heading):
        """Point and heading at ``distance`` along a piece's centreline."""
        x, y = start
        h = heading
        for step in piece:
            length = self._stepLength(step)
            take = min(distance, length)
            if step[0] == "line":
                x += take * math.cos(math.radians(h))
                y += take * math.sin(math.radians(h))
            else:
                deg = step[1] * take / length
                (x, y), = self._templateTrace([("corner", deg, step[2])], (x, y), h)[-1:]
                h += deg
            distance -= take
            if distance <= 1e-9:
                break
        return x, y, h

    @staticmethod
    def _templateEndMarks(i, n):
        """Etched marks for the two ends of piece ``i`` (0-based) of ``n``.

        The ends that meet the module edges read ``EDGE``.  Each internal cut
        gets a letter (A, B, …) etched on *both* pieces that meet there, so
        matching letters show which ends join, in which order, and which way
        round each piece goes.

        @returns ``(start_mark, end_mark)``.
        """
        def joint(k):
            return chr(ord("A") + k) if k < 26 else f"J{k + 1}"
        start = "EDGE" if i == 0 else joint(i - 1)
        end = "EDGE" if i == n - 1 else joint(i)
        return start, end

    # ----------------------------------------------------------------- drawing

    def drawTrackTemplate(self, route, label, move="right"):
        """Cut one track template, split into --track_template_segments pieces.

        Each piece is its own part, rotated so its end-to-end chord lies
        horizontal (compact on the bed), with ``label`` etched along its
        centreline middle.  ``piece i/N`` is added when there is more than one
        piece.  Each end is marked (see :meth:`_templateEndMarks`): ``EDGE`` at
        the module edges, and a matching letter on both sides of every cut.
        The label and the ``EDGE`` marks are etched only with --part_text; the
        letters always are.

        @param route - Centreline steps of the whole template.
        @param label - Text etched on each piece (radius, gauge).
        @param move  - Layout direction for each piece.
        @throws ValueError - Propagated from :meth:`_templateWidth`.
        """
        w = self._templateWidth()
        pieces = self._templatePieces(route)
        for i, piece in enumerate(pieces):
            # Lay the piece out with its chord horizontal.
            centre = self._templateTrace(piece)
            heading = -math.degrees(math.atan2(centre[-1][1] - centre[0][1],
                                               centre[-1][0] - centre[0][0]))
            ops = self._templateOutline(piece)
            # The outline starts on the right-hand edge, half a width to the
            # right of the centreline start.
            hr = math.radians(heading - 90.0)
            start = (w / 2 * math.cos(hr), w / 2 * math.sin(hr))
            pts = self._templateTrace(ops, start, heading)
            minx = min(p[0] for p in pts)
            miny = min(p[1] for p in pts)
            tw = max(p[0] for p in pts) - minx
            th = max(p[1] for p in pts) - miny
            if self.move(tw, th, move, before=True):
                continue
            with self.saved_context():
                self.moveTo(start[0] - minx, start[1] - miny, heading)
                for op in ops:
                    if op[0] == "edge":
                        self.edge(op[1])
                    else:
                        self.corner(op[1], op[2])
                self.ctx.stroke()
            text = label if len(pieces) == 1 else f"{label}  {i + 1}/{len(pieces)}"
            fontsize = min(0.55 * w, 6.0)
            length = sum(self._stepLength(s) for s in piece)
            # Rough etched-text width: ~0.6 × font size per character.
            width_of = lambda t: 0.6 * fontsize * len(t)
            gap = 2.0   # mm between a mark and the piece end / the label
            marks = self._templateEndMarks(i, len(pieces))
            etch = []
            room = length - 2 * gap
            if room >= width_of(marks[0]) + width_of(marks[1]) + gap:
                # End marks first: they are what shows the assembly order.
                etch += [(marks[0], gap + width_of(marks[0]) / 2),
                         (marks[1], length - gap - width_of(marks[1]) / 2)]
                room -= width_of(marks[0]) + width_of(marks[1]) + 2 * gap
            if not etch or room >= width_of(text):
                etch.append((text, length / 2))
            if not self.part_text:
                # Keep only the joint letters: they are needed to reassemble a
                # split template, while the label and EDGE marks are optional.
                etch = [(t, at) for t, at in etch if t not in (text, "EDGE")]
            for t, at in etch:
                mx, my, mh = self._templatePointAt(piece, at, (-minx, -miny), heading)
                angle = ((mh + 90.0) % 180.0) - 90.0   # keep the text upright
                with self.saved_context():
                    # stroke=True so lasers that vector-etch by stroke colour
                    # still trace the label.
                    self.text(t, x=mx, y=my, angle=angle, align="middle center",
                              fontsize=fontsize, color=Color.ETCHING, stroke=True)
            self.move(tw, th, move)
