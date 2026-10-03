# HexmoHexagon — HO Scale Reference

Settings for cutting **HO-scale** hexagonal layout modules with the `HexmoHexagon`
generator ([boxes/generators/hexmohexagon.py](../../boxes/generators/hexmohexagon.py)).

> Companion file: [README-N-scale.md](./README-N-scale.md) — same system, N numbers.

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
  /   \     /   \          middle. Curve radius = 1.5 x R, less the lead-in term.
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

> **track curve radius = 1.5 × R − √3 × L**
>
> where **R** is the hexagon's *inner* corner radius and **L** is
> `--track_lead_in`, the straight run where the track crosses each edge.

With `--outside` on (the default, and the intended setting) the generator's
`--radius` is the **outside** corner radius, so the inner one is one thickness
smaller:

```
R = radius − t / cos 30°
```

With no lead-in (`L = 0`) the curve is exactly `1.5 × R`. Two independent
derivations (the single-module arc, and the distance from the ring centre to the
shared-edge midpoints) both give that 1.5× factor. A lead-in keeps the edge
crossings where they are and tightens the arc by `√3 × L` (see
[Track-curve guide](#track-curve-guide)).

Rearranged to size a module for a target curve:

```
radius = (track_radius + √3 × L) / 1.5 + t / cos 30°
```

---

## HO-scale preferred: 700 mm curve

The preferred HO module keeps the generator's `radius=500` but uses a 23 mm
lead-in on 6 mm stock:

```
R     = 500 − 6 / cos 30°        = 493.1 mm
curve = 1.5 × 493.1 − √3 × 23    = 699.8 mm   (≈ 27.5" HO curve)
```

The deck's `--track_label` reads **700 mm**. With the preferred double track
(80 mm apart, `centred`) the two etched curves are labelled **660 mm** and
**740 mm**. These are the preferred HO settings used throughout this file and
by the ready-made URLs below:

| Parameter | Value | Why |
|---|---|---|
| `--radius` | **500** | outside corner radius for the 700 mm curve (see above) |
| `--h` (height) | **100** | module/board depth; independent of track radius |
| `--thickness` | **6** | material thickness (default) |
| `--outside` | **on** (default) | `radius` is the outside measurement |
| `--edge_width` | **60** | outer frame width of the spoke bottom |
| `--spoke_width` | **120** | spoke pattern width (kite size s ≈ 152 mm) |
| `--support_length` | **150** | internal support walls |
| `--trapezoid` | **1** | half-hexagon module |
| `--corner_holes` | **g2** | fewer pierces, see [Reducing laser cut time](#reducing-laser-cut-time) |
| `--gap_holes` | **g2** | fewer pierces in the gap-fill clusters too |
| `--big_hole_shape` | **rounded_rect** | roundness `0.3` (default), see [Big-hole shape](#big-hole-shape) |
| `--FingerJoint_play` | **0.1** | finger-joint clearance, a multiple of thickness (0.6 mm at 6 mm) |
| `--FingerJoint_extra_length` | **0.05** | fingers stand 0.3 mm proud, to sand flush |
| `--track_line_count` | **2** | double-track module |
| `--track_spacing` | **80** | track-centre to track-centre |
| `--track_offset` | **centred** (default) | the two tracks straddle the 700 mm centreline |
| `--track_width` | **30** | HO track footprint |
| `--track_lead_in` | **23** | straight run at each edge crossing (default 30) |
| `--track_guide` | **1** | the track-laying guide plate (clearance 30, the default) |
| `--labels` / `--reference` | **0** / **0** | no part-name annotations and no 100 mm scale-reference bar in the SVG (the track labels stay on) |

The other track-guide extras stay at their defaults: `--track_lines`,
`--draw_track`, `--track_label` and `--track_crossing` on, `--draw_center` off.

**To target a different HO curve**, use the sizing formula above. With the 23 mm
lead-in on 6 mm stock that is `radius = (curve + 39.8) / 1.5 + 6.9`. For example:

| Desired HO curve | `--radius` | Label you get |
|---|---|---|
| 457 mm (18", set-track) | 338 | 457 mm |
| 559 mm (22") | 406 | 559 mm |
| 610 mm (24") | 440 | 610 mm |
| 700 mm (preferred) | 500 | 700 mm |
| 762 mm (30", broad) | 541 | 761 mm |

When you change `radius`, scale `edge_width`, `spoke_width` and
`support_length` proportionally from the `radius=500` values (multiply each by
`radius/500`) so the spoke pattern stays intact — see the gotcha below.

---

## Example render command

The app runs via Docker Compose on port **4455**:

```bash
docker compose up        # start the server
```

```bash
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=500&h=100&thickness=6\
&edge_width=60&spoke_width=120&support_length=150\
&bottom=spoke&top=closed&trapezoid=1\
&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect\
&FingerJoint_play=0.1&FingerJoint_extra_length=0.05\
&track_line_count=2&track_spacing=80&track_width=30&track_lead_in=23" -o hexmo_ho.svg
```

---

## Scale presets (bookmarkable URLs)

The generator form pre-fills **every field straight from the URL query string** —
this is built-in boxes behaviour, no special option required. So a "scale preset"
is just a URL you save: open it and the whole form arrives populated, ready to
review, tweak, or render.

The generator defaults are HO-sized (`radius=500`, 6 mm), but the preferred HO
settings differ from them in a few places (lead-in, double track, hole options,
finger fit), so use the preset rather than the bare form.

**HO HexmoHexagon** — open this to load the form pre-filled (append
`&render=1` to jump straight to the SVG):

```
http://localhost:4455/HexmoHexagon?radius=500&h=100&thickness=6&edge_width=60&spoke_width=120&support_length=150&bottom=spoke&top=closed&trapezoid=1&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&FingerJoint_play=0.1&FingerJoint_extra_length=0.05&track_lines=1&track_line_count=2&track_spacing=80&draw_track=1&track_width=30&track_lead_in=23&track_guide=1&labels=0&reference=0
```

**HO HexmoRectangle** — the shared mating dimensions and track settings, with
3 lanes and 3 compartments:

```
http://localhost:4455/HexmoRectangle?radius=500&h=100&thickness=6&spoke_width=120&slot_tolerance=1&num_columns=3&num_rows=3&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&FingerJoint_play=0.1&FingerJoint_extra_length=0.05&track_lines=1&track_line_count=2&track_spacing=80&draw_track=1&track_width=30&track_lead_in=23&track_guide=1&labels=0&reference=0
```

For the **N-scale** bookmark (radius 220, the shrunk frame/spoke/support values
and the R282 track settings), see
[README-N-scale.md → Scale presets](./README-N-scale.md#scale-presets-bookmarkable-urls).

How to use it:

1. **Bookmark** the URL you want (or keep it in a notes file). The bookmark
   *is* the preset.
2. **Open** it — the form loads with those values already in every box (append
   `&render=1` to jump straight to the SVG instead).
3. **Tweak** anything directly in the form — e.g. a tighter 610 mm (24") curve is
   just `radius=440` (with the frame values scaled, see above) — then hit
   **Render**. Every change is visible on the page before you render.

---

## Track-curve guide

You can etch the track curve onto the top (deck) panel as a lay-out guide. It is
engraved, not cut, and follows the curve from
[The one relationship](#the-one-relationship-to-remember): it enters and leaves at
the midpoints of edges 120° apart, meeting each perpendicularly so neighbouring
modules join smoothly. This works on both the half-hexagon (trapezoid) and the
full hexagon — see **Trapezoid vs. full hexagon** below.

| Parameter | Meaning | HO suggestion |
|---|---|---|
| `--track_lines` | master switch: turn the guide on | `1` |
| `--track_line_count` | number of parallel track centrelines | `2` (double track), or `1` |
| `--track_spacing` | radial spacing between adjacent centrelines (mm) | `80` (track-centre to track-centre) |
| `--track_offset` | `centred` (extras straddle the centreline), `outer` (centreline = minimum radius, extras step outward only) or `inner` (centreline = maximum radius, extras step inward only) | `centred` (660 / 740 mm); `outer` to keep no track tighter than the centreline |
| `--track_center_offset` | signed shift (mm) of the reference centreline itself: `+` = outward (larger radius), `−` = inward | `0` (true centreline); `+15` to bias the whole family 15 mm out |
| `--draw_center` | etch the centreline arc(s) themselves | `0` (off by default) |
| `--draw_track` | etch the two track-footprint edges at ± `track_width`/2 | `1` |
| `--track_width` | physical width of the laid track/roadbed (mm) | `30` |
| `--track_lead_in` | straight lead-in length at each edge (mm) | `23` (default `30`) |
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
mating straight (HexmoRectangle) module's outward tracks. `--track_offset inner`
is the mirror image: the centreline becomes the *maximum* radius and every extra
track steps inward (tighter). Use it when the centreline is your outermost line,
e.g. against the deck edge, and check each inner track's etched radius label
against your minimum curve. On a HexmoRectangle the extras go to the same
side as the hexagon's inner tracks, so they still line up across a joint.

`--track_center_offset` is a separate, additive knob that moves the *reference
centreline itself* by a signed millimetre amount before the `--track_offset`
spacing is applied. `0` (default) is the true geometric centreline; a positive
value shifts the whole family outward (larger radius) and a negative value inward.
It composes with `--track_offset` — in `outer` mode the *shifted* centreline
becomes the minimum-radius track (in `inner` mode, the maximum-radius one) — and it works with a single track
(`--track_line_count 1`) to place one centreline off the geometric centre. The
same sign convention as `outer` (positive = larger radius, matching
HexmoRectangle's `+y`) keeps a shifted hex curve aligned with a shifted straight
across a joint. Note the hexagon arc is not clipped to the deck, so keep the
shift (plus any `outer` spread) within the deck depth.

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
keep everything joined — the curve radius becomes `1.5·R − √3·lead_in`. With the
HO settings (`R` = 493.1, lead-in 23) that is the 699.8 mm (700 mm) curve. Set it
to `0` for a pure edge-to-edge arc.

`--track_label` etches that resulting radius at each centreline apex —
millimetres just outside the centreline, inches (1 dp) just inside — with the
font sized from `--track_width` so both lines stay inside the track footprint
and are hidden once track is laid. `--track_crossing` etches a short tick across
the track at each point where a lead-in meets the curve, marking the
straight/curve transition.

```bash
# Half-hexagon: the double-track lower curve (HO params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=500&h=100&thickness=6&bottom=spoke&top=closed\
&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect\
&trapezoid=1&track_lines=1&track_line_count=2&track_spacing=80\
&draw_track=1&track_width=30&track_lead_in=23" -o hexmo_ho_half.svg
```

```bash
# Full hexagon: left + right + middle routes (HO params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=500&h=100&thickness=6&bottom=spoke&top=closed\
&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect\
&track_lines=1&track_line_count=2&track_spacing=80\
&draw_track=1&track_width=30&track_lead_in=23\
&track_left=1&track_right=1&track_middle=1" -o hexmo_ho_full.svg
```

### Track-laying guide plate

`--track_guide=1` adds a jig that holds the track in place while you mark and
cut. It is a flat plate dowelled to the outer face of any side wall through two
small pilot holes, with one window per track, exactly `--track_width` wide. With
the HO settings it is **433 × 75 mm**, with windows at ±40 mm for the two tracks.
HexmoRectangle cuts the identical plate, so one guide fits a hex side wall, a
trapezoid side wall or a rectangle end wall. See
[README-N-scale.md → Track-laying guide plate](./README-N-scale.md#track-laying-guide-plate)
for how it works.

| Parameter | Meaning | HO suggestion |
|---|---|---|
| `--track_guide` | add the guide plate | `1` |
| `--track_guide_clearance` | window height above the deck (mm) | `30` |

### Straight modules (HexmoRectangle)

The companion `HexmoRectangle` straight module carries the same track markings on
its **base plate**, running the full long (H) axis: `--track_lines`,
`--track_line_count`, `--track_spacing`, `--draw_center`, `--draw_track`,
`--track_width`. Because the run is straight there is no radius label; instead
`--track_crossing` (offset by `--track_lead_in`) draws a tick at each end marking
where the track enters/leaves the module.

```bash
curl "http://localhost:4455/HexmoRectangle?render=1\
&radius=500&h=100&thickness=6&num_columns=3&num_rows=3\
&track_lines=1&track_line_count=2&track_spacing=80\
&draw_track=1&track_width=30&track_lead_in=23&track_guide=1" -o hexmo_rect_track.svg
```

**Internal layout.** `--num_columns` sets the compartments along the long axis
(N compartments, N−1 short dividers) and `--num_rows` the lanes across it (N
lanes, N−1 long internal supports). The HO preference is `num_columns=3` and
`num_rows=3`. With the double track at ±40 mm, the two long supports sit at
±80.3 mm (centreline). That leaves about 22 mm between the edge of each track's
footprint (±55 mm) and the face of the support beside it. Check that this is enough
room for your under-board turnout motors. Check that clearance if
you move the tracks with `--track_spacing` or `--track_center_offset`.

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
- `--big_hole_roundness` (default `0.3`) — corner rounding for `rounded_rect`, as
  a fraction of the hole's half-width: `0` = square corners, `1` = fully round
  (back to a circle). At the default `0.3`, the Ø70 mm big holes of a `h=100`
  box get a 10.5 mm corner radius. Out-of-range values are clamped, so they never
  error.
- `--big_hole_width` / `--big_hole_height` (default `0` = automatic) — for
  `rounded_rect`, the hole's width (along the wall) and height (up the wall) in
  mm. A value shrinks **every** big hole around its own centre, on both
  generators, so the holes still line up module to module. They double as the
  under-board train pass-through, so size them to your trains. Positions and
  counts never change. A narrower hole can fit where the full-size one is
  dropped, e.g. between a HexmoRectangle's long supports. Values above the
  automatic size are refused with an error.

The big-hole **size** follows the box height: diameter = `h − 30` mm (Ø70 at the
default `h=100`), identical on HexmoHexagon and HexmoRectangle, so the holes on
mating walls line up at any height.

---

## Gotchas

- **`--outside`**: it is **on** by default in both HexmoHexagon and
  HexmoRectangle, and that is the intended setting, so leave it on. `radius`
  is then the outside corner radius, and the inside is shrunk by one thickness
  (inner corner radius = `radius − t / cos 30°`). The etched track is built from
  that inner radius, and `--track_label` etches the radius you actually get. Both
  generators must use the same setting, or their walls won't line up.
- **Solid-hex fallback**: if you shrink `radius` for a tighter curve but leave the
  HO frame/spoke sizes, the kite cutouts go degenerate and the spoke pattern
  silently disappears (you get a solid hex). Keep `edge_width < A_inner` and
  `spoke_width` small enough that
  `s = A_inner/√3 − spoke_width/2 > 0`, where `A_inner = R·cos30° − edge_width` and
  `R` is the inner corner radius (`radius − t / cos 30°` with `--outside` on). At the
  HO settings: `A_inner = 493.1·cos30° − 60 = 367.0`, so `s ≈ 211.9 − 60 = 151.9 mm`.
- The **height** and **thickness** are build choices, not track geometry.
