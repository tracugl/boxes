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

## N-scale target: ~280 mm curve

280 mm is essentially the standard N set-track curve (e.g. Kato R282).

```
R = 280 / 1.5 = 186.7 mm  →  rounded to radius = 190
```

`radius=190` is the round-number choice used throughout this file (and by the
ready-made N-scale URL, below). It yields a track curve of `190 × 1.5 = 285 mm` —
within a few millimetres of the R282 standard, and comfortably in the broad-curve
range.

| Parameter | Value | Why |
|---|---|---|
| `--radius` | **190** | set directly by the 280 mm track radius |
| `--edge_width` | **22** | outer frame width, scaled from HO by ~0.37 |
| `--spoke_width` | **45** | keeps the kite cutouts non-degenerate (s ≈ 58 mm > 0) |
| `--support_length` | **55** | internal support walls |
| `--h` (height) | your call | module/board depth — independent of track radius |
| `--thickness` | 3 (or 6) | material choice; 3 mm ply suits the lighter N module |
| `--FingerJoint_play` | 0.3 (default 0.2) | looser finger-joint fit suits 3 mm ply; drop to 0.2 for a tighter fit |


**Why the spoke/frame/support values must shrink:** the defaults were tuned for
the 500 mm HO hexagon. Left at HO sizes on a 190 mm hexagon, the kite cutouts
go degenerate and the generator silently falls back to a **solid** hex (no spoke
pattern). The values above were scaled by the radius ratio 190/500 ≈ 0.38 and
verified to keep the spokes intact.

> **Shortcut:** you don't have to type these values field-by-field — open the
> ready-made N-scale URL and the whole form arrives pre-filled. See
> [Scale presets (bookmarkable URLs)](#scale-presets-bookmarkable-urls) below.

---

## Example render command

The app runs via Docker Compose on port **4455**:

```bash
docker compose up        # start the server
```

```bash
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=190\
&edge_width=22\
&spoke_width=45\
&support_length=55\
&bottom=spoke&top=closed&thickness=3" -o hexmo_n.svg
```

---

## Scale presets (bookmarkable URLs)

The generator form pre-fills **every field straight from the URL query string** —
this is built-in boxes behaviour, no special option required. So a "scale preset"
is just a URL you save: open it and the whole form arrives populated with the
N-scale values, ready to review, tweak, or render.

**N-scale HexmoHexagon** — open this to load the form pre-filled (append
`&render=1` to jump straight to the SVG):

```
http://localhost:4455/HexmoHexagon?radius=190&edge_width=22&spoke_width=45&support_length=55&thickness=3&FingerJoint_play=0.3&bottom=spoke&top=closed
```

**N-scale HexmoRectangle** — only the shared mating dimensions differ from
default (a straight module has no frame/spoke/support geometry, and its column
count auto-selects from the radius):

```
http://localhost:4455/HexmoRectangle?radius=190&thickness=3&FingerJoint_play=0.3
```

How to use it:

1. **Bookmark** each URL (or keep them in a notes file). The browser bookmark
   *is* the preset.
2. **Open** it — the form loads with the N values already in every box.
3. **Tweak** anything you like (a different height, a tighter radius) directly in
   the form, then hit **Render**. Because you are editing real form fields, every
   change is visible on the page before you render.

The HO-scale equivalents are just the generator defaults, so the bare
`http://localhost:4455/HexmoHexagon` form already starts at HO — see
[README-HO-scale.md](./README-HO-scale.md#scale-presets-bookmarkable-urls).

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
| `--track_offset` | `centred` (extras straddle the centreline) or `outer` (centreline = minimum radius, extras step outward only) | `outer` to guarantee no track tighter than the centreline |
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
edges. With the default `--track_offset centred`, an odd `--track_line_count`
lands one centreline on the exact curve with the rest paired either side, and an
even count straddles it. Switch to `--track_offset outer` and the design
centreline becomes the *minimum* radius: every extra track steps outward (larger
radius) only, so no track is ever drawn tighter than the centreline. Use this
when the centreline is your minimum-radius constraint and additional tracks may
only bow out — it also keeps the hexagon's outward tracks on the same side as a
mating straight (HexmoRectangle) module's outward tracks.

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
# Half-hexagon: the single lower curve (N-scale params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=190&edge_width=22&spoke_width=45&support_length=55&thickness=3\
&bottom=spoke&top=closed\
&trapezoid=1&track_lines=1&track_line_count=1\
&draw_center=1&draw_track=1&track_width=20&track_lead_in=30" -o hexmo_n_half.svg
```

```bash
# Full hexagon: left + right + middle routes (N-scale params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=190&edge_width=22&spoke_width=45&support_length=55&thickness=3\
&bottom=spoke&top=closed\
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
&radius=190&thickness=3\
&track_lines=1&draw_center=1&draw_track=1&track_width=20&track_lead_in=30" -o hexmo_rect_track.svg
```

---

## Reducing laser cut time

Most of the cut *time* on these panels is pierces, and the small Ø6 registration
pilot holes dominate the count. The biggest lever is the corner cluster at each
end of every side panel:

- `--corner_holes=g6` (default) — full cluster: the medium hole plus the six
  surrounding Ø6 pilot holes.
- `--corner_holes=g2` — keeps only the medium and the two pilot holes directly
  above/below it, dropping the six corner holes per end. Big pierce savings
  (≈48 fewer holes on a trapezoid, 12 per side panel), keeping enough for
  registration. Same option on both generators.

The mid-panel gap-fill clusters (between the big holes) have a matching toggle:

- `--gap_holes=g4` (default) — full cluster: two mediums each with a pilot above
  and below (2 medium + 4 small per gap).
- `--gap_holes=g2` — a single centred medium with one pilot above and below
  (1 medium + 2 small per gap), mirroring the reduced corner cluster. ~6 fewer
  holes per side panel. Same option on both generators.

Other levers: `--supports=0` (no internal support walls), `bottom=closed`
instead of `spoke`, and the track-guide extras (`--track_label=0`,
`--track_crossing=0`).

---

## Big-hole shape

The large weight-reduction through-holes are circles by default. `--big_hole_shape`
lets you draw them as rounded-corner squares instead — purely a look/material
choice, applied to every big hole on both generators.

- `--big_hole_shape=circle` (default) — circular holes (unchanged output).
- `--big_hole_shape=rounded_rect` — each big hole becomes a square with rounded
  corners occupying the **same bounding box** as the circle (side = the circle
  diameter), so every hole-fit and clearance check is unaffected and the count
  and positions are identical. The small registration and medium fallback holes
  are never changed.
- `--big_hole_roundness` (default `0.5`) — corner rounding for `rounded_rect`, as
  a fraction of the hole's half-width: `0` = square corners, `1` = fully round
  (back to a circle). At the default `0.5`, the Ø70 mm big holes get a 17.5 mm
  corner radius. Out-of-range values are clamped, so they never error.

---

## Gotchas

- **`--outside`**: leave it **off** (the default). With it on, `radius` is treated
  as an outside measurement and the inside is shrunk by one thickness — but the
  track geometry needs the *inside corners* at 190 mm.
- **Solid-hex fallback**: if you change `edge_width`/`spoke_width` and the spoke
  pattern disappears, the kites went degenerate. Keep
  `edge_width < A_inner` and `spoke_width` small enough that
  `s = A_inner/√3 − spoke_width/2 > 0`, where `A_inner = radius·cos30° − edge_width`.
- The **height** and **thickness** are build choices, not track geometry. Scale
  height by ~0.54 (the N:HO linear ratio) if you want it visually proportional
  to an HO module.
