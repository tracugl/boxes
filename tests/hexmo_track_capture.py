"""Capture the etched track centreline/footprint paths a Hexmo generator draws.

Shared helper for the track-route tests (not itself a test module).  It spies
on the drawing context while ``drawTrackLines`` runs and records every stroked
polyline in sheet coordinates, so two implementations of the track drawing
can be compared point for point, whatever order or direction they draw in.
"""
from __future__ import annotations

from hexmo_testutil import apply


def etched_track_paths(box):
    """Render ``box`` and return the polylines etched by ``drawTrackLines``.

    @param box - A parsed (not yet rendered) HexmoHexagon.
    @returns Sorted list of polylines; each is a tuple of ``(x, y)`` points
             rounded to 1e-4 mm and oriented so its smaller end comes first,
             which makes the comparison independent of drawing direction.
    """
    paths, current = [], []
    active = [False]
    original_draw = box.drawTrackLines

    def draw_spy(*args, **kwargs):
        active[0] = True
        try:
            return original_draw(*args, **kwargs)
        finally:
            active[0] = False

    box.drawTrackLines = draw_spy
    box.open()
    ctx = box.ctx
    move_to, line_to, stroke = ctx.move_to, ctx.line_to, ctx.stroke

    def point(x, y):
        px, py = apply(ctx._m, (x, y))
        return (round(px, 4) + 0.0, round(py, 4) + 0.0)

    def move_spy(x, y):
        if active[0]:
            current[:] = [point(x, y)]
        return move_to(x, y)

    def line_spy(x, y):
        if active[0]:
            current.append(point(x, y))
        return line_to(x, y)

    def stroke_spy(*args, **kwargs):
        if active[0] and len(current) > 1:
            path = tuple(current)
            paths.append(min(path, path[::-1]))
            current.clear()
        return stroke(*args, **kwargs)

    ctx.move_to, ctx.line_to, ctx.stroke = move_spy, line_spy, stroke_spy
    box.render()
    box.close()
    return sorted(paths)
