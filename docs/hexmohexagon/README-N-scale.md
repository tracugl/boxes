# HexmoHexagon — N Scale Reference

Settings for cutting **N-scale** hexagonal layout modules with the `HexmoHexagon`
generator ([boxes/generators/hexmohexagon.py](../../boxes/generators/hexmohexagon.py)).

> Companion file: [README-HO-scale.md](./README-HO-scale.md) — same system, HO numbers.

---

## What this is

`HexmoHexagon` cuts a hexagonal box that doubles as a modular model-railroad
board section. Six modules joined edge-to-edge in a **ring** (sharing edges
around a central void) form one closed loop of track — a full circle.

Each module contributes a **60° arc** (6 × 60° = 360°). The track crosses each
hexagon between two edges that are **120° apart** around the hexagon centre,
perpendicular to each edge so neighbouring modules join smoothly.

```
        ___                The 6 module centres form a hexagon.
       /   \               Each module carries a 60° arc; the arcs
   ___/     \___           join into one circle centred on the ring's
  /   \     /   \          middle. Track-circle radius = 1.5 x R.
  \   /     \   /
   \_/  HOLE  \_/
   / \       / \
  /   \     /   \
  \___/     \___/
      \     /
       \___/
```

---

## The one relationship to remember

> **track curve radius = 1.5 × R**
>
> where **R** is the hexagon circumradius — the generator's `--radius`
> (measured "at the corners").

Rearranged to size a module for a target curve:

```
R = track_radius / 1.5
```

Two independent derivations (the single-module arc, and the distance from the
ring centre to the shared-edge midpoints) both give the same 1.5× factor, so it
holds exactly.

---

## N-scale target: 280 mm curve

280 mm is essentially the standard N set-track curve (e.g. Kato R282).

```
R = 280 / 1.5 = 186.7 mm
```

| Parameter | Value | Why |
|---|---|---|
| `--radius` | **186.7** | set directly by the 280 mm track radius |
| `--edge_width` | **22** | outer frame width, scaled from HO by ~0.37 |
| `--spoke_width` | **45** | keeps the kite cutouts non-degenerate (s ≈ 58 mm > 0) |
| `--support_length` | **56** | internal support walls |
| `--h` (height) | your call | module/board depth — independent of track radius |
| `--thickness` | 3 (or 6) | material choice; 3 mm ply suits the lighter N module |
| `--FingerJoint_play` | 0.3 (default 0.2) | looser finger-joint fit suits 3 mm ply; drop to 0.2 for a tighter fit |


**Why the spoke/frame/support values must shrink:** the defaults were tuned for
the 500 mm HO hexagon. Left at HO sizes on a 187 mm hexagon, the kite cutouts
go degenerate and the generator silently falls back to a **solid** hex (no spoke
pattern). The values above were scaled by the radius ratio 187/500 ≈ 0.37 and
verified to keep the spokes intact.

---

## Example render command

The app runs via Docker Compose on port **4455**:

```bash
docker compose up        # start the server
```

```bash
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=186.7\
&edge_width=22\
&spoke_width=45\
&support_length=56\
&bottom=spoke&top=closed&thickness=6" -o hexmo_n.svg
```

---

## Track-curve guide

You can etch the track curve onto the top (deck) panel as a lay-out guide. It is
engraved, not cut, and follows the exact `1.5 × R` curve: it enters and leaves at
the midpoints of edges 120° apart, meeting each perpendicularly so neighbouring
modules join smoothly. This works on both the half-hexagon (trapezoid) and the
full hexagon — see **Trapezoid vs. full hexagon** below.

| Parameter | Meaning | N suggestion |
|---|---|---|
| `--track_lines` | master switch: turn the guide on | `1` |
| `--track_line_count` | number of parallel track centrelines | `1`, or `2` for a double-track module |
| `--track_spacing` | radial spacing between adjacent centrelines (mm) | `80` (track-centre to track-centre) |
| `--draw_center` | etch the centreline arc(s) themselves | `1` (on by default) |
| `--draw_track` | etch the two track-footprint edges at ± `track_width`/2 | `1` |
| `--track_width` | physical width of the laid track/roadbed (mm) | `~20` (N) |
| `--track_lead_in` | straight lead-in length at each edge (mm) | `30` (default) |
| `--track_label` | etch each curve's resulting radius as text | `1` (on by default) |
| `--track_crossing` | etch a tick where each lead-in meets the curve | `1` (on by default) |
| `--track_left` | full hexagon: curve edge 4 → 6 | `1` to draw it |
| `--track_middle` | full hexagon: straight edge 4 → 1 (diameter) | `1` to draw it |
| `--track_right` | full hexagon: curve edge 4 → 2 | `1` to draw it |
| `--track_top` | full hexagon: curve edge 6 → 2 | `1` to draw it |

`--track_lines` is the master switch. With it on, `--draw_center` etches the bare
centreline(s) and `--draw_track` etches where the actual track footprint sits
(centreline ± `track_width`/2); enable both to see the centreline *and* its
edges. For an odd `--track_line_count` one centreline lands on the exact curve
with the rest paired either side; an even count straddles it.

**Trapezoid vs. full hexagon.** In trapezoid (half-hexagon) mode the guide is the
single lower curve. On the **full hexagon** you choose which route(s) to draw
with `--track_left/middle/right/top` (any combination). Edges are numbered as on
a flat-top hexagon — 1 top, 2 upper-right, 3 lower-right, 4 bottom, 5 lower-left,
6 upper-left:

```
                  1
              /------\
           6 /        \ 2
            /          \
            \          /
           5 \        / 3
              \------/
                  4
```

- `--track_left` — curve from edge 4 to edge 6
- `--track_right` — curve from edge 4 to edge 2
- `--track_top` — curve from edge 6 to edge 2
- `--track_middle` — straight diameter from edge 4 to edge 1 (no radius label or
  transition tick, since a straight has no finite radius)

`--track_lead_in` adds a straight run where each line meets an edge: the line is
straight (perpendicular to the edge) for that distance, then the curve begins.
The crossing points stay pinned to the edge midpoints, so the arc shortens to
keep everything joined — the curve radius becomes `1.5·R − √3·lead_in`. Set it
to `0` for a pure edge-to-edge arc.

`--track_label` etches that resulting radius at each centreline apex —
millimetres just outside the centreline, inches (1 dp) just inside — with the
font sized from `--track_width` so both lines stay inside the track footprint
and are hidden once track is laid. `--track_crossing` etches a short tick across
the track at each point where a lead-in meets the curve, marking the
straight/curve transition.

```bash
# Half-hexagon: the single lower curve
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=186.7&edge_width=22&spoke_width=45&support_length=56\
&bottom=spoke&top=closed&thickness=3\
&trapezoid=1&track_lines=1&track_line_count=1\
&draw_center=1&draw_track=1&track_width=20&track_lead_in=30" -o hexmo_n_half.svg
```

```bash
# Full hexagon: left + right + middle routes
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=186.7&edge_width=22&spoke_width=45&support_length=56\
&bottom=spoke&top=closed&thickness=3\
&track_lines=1&draw_center=1&draw_track=1&track_width=20&track_lead_in=30\
&track_left=1&track_right=1&track_middle=1" -o hexmo_n_full.svg
```

### Straight modules (HexmoRectangle)

The companion `HexmoRectangle` straight module carries the same track markings on
its **base plate**, running the full long (H) axis: `--track_lines`,
`--track_line_count`, `--track_spacing`, `--draw_center`, `--draw_track`,
`--track_width`. Because the run is straight there is no radius label; instead
`--track_crossing` (offset by `--track_lead_in`) draws a tick at each end marking
where the track enters/leaves the module.

```bash
curl "http://localhost:4455/HexmoRectangle?render=1\
&radius=186.7&thickness=3\
&track_lines=1&draw_center=1&draw_track=1&track_width=20&track_lead_in=30" -o hexmo_rect_track.svg
```

---

## Gotchas

- **`--outside`**: leave it **off** (the default). With it on, `radius` is treated
  as an outside measurement and the inside is shrunk by one thickness — but the
  track geometry needs the *inside corners* at 186.7 mm.
- **Solid-hex fallback**: if you change `edge_width`/`spoke_width` and the spoke
  pattern disappears, the kites went degenerate. Keep
  `edge_width < A_inner` and `spoke_width` small enough that
  `s = A_inner/√3 − spoke_width/2 > 0`, where `A_inner = radius·cos30° − edge_width`.
- The **height** and **thickness** are build choices, not track geometry. Scale
  height by ~0.54 (the N:HO linear ratio) if you want it visually proportional
  to an HO module.
