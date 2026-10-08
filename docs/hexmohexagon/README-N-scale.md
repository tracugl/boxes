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

## N-scale target: 280 mm curve

280 mm is essentially the standard N set-track curve (Kato Unitrack R282).

```
radius = (280 + √3 × 26) / 1.5 + 3 / cos 30°
       = 216.7 + 3.5  ≈  220.2 mm  →  radius = 220
```

With `radius=220`, `thickness=3` and `track_lead_in=26`, the inner corner radius is
216.5 mm and the etched curve is `1.5 × 216.5 − √3 × 26 = 279.8 mm`; the
`--track_label` on the deck reads **280 mm**. These are the preferred N-scale
settings used throughout this file and by the ready-made URLs below:

| Parameter | Value | Why |
|---|---|---|
| `--radius` | **220** | outside corner radius for the 280 mm curve (see above) |
| `--h` (height) | **100** | module/board depth; independent of track radius |
| `--thickness` | **3** | 3 mm ply suits the lighter N module |
| `--outside` | **on** (default) | `radius` is the outside measurement |
| `--edge_width` | **22** | outer frame width of the spoke bottom |
| `--spoke_width` | **60** | keeps the kite cutouts non-degenerate (s ≈ 66 mm > 0) |
| `--support_length` | **60** | internal support walls |
| `--trapezoid` | **1** | half-hexagon module |
| `--corner_holes` | **g2** | fewer pierces, see [Reducing laser cut time](#reducing-laser-cut-time) |
| `--gap_holes` | **g4** (default) on the hexagon, **g2** on the rectangle | full gap-fill clusters on the hexagon's walls; the rectangle's reduced set saves pierces |
| `--big_hole_shape` | **rounded_rect** | roundness `0.3` (default), see [Big-hole shape](#big-hole-shape) |
| `--big_hole_width` × `--big_hole_height` | **50 × 70** | the under-board train pass-through, narrowed so it fits between a 3-lane HexmoRectangle's long supports (see [Straight modules](#straight-modules-hexmorectangle)); the same size on every module so the holes line up |
| `--FingerJoint_play` | **0.2** (default) | finger-joint clearance, a multiple of thickness (0.6 mm at 3 mm) |
| `--FingerJoint_extra_length` | **0.1** | fingers stand 0.3 mm proud, to sand flush |
| `--track_width` | **17** | N track footprint |
| `--track_lead_in` | **26** | straight run at each edge crossing |
| `--track_spacing` | **35** | centre-to-centre, if you add a second track |
| `--track_guide` | **1** | the track-laying guide plate (clearance 30, the default) |
| `--labels` / `--reference` | **0** / **0** | no part-name annotations and no 100 mm scale-reference bar in the SVG (the track labels stay on) |

The track-guide extras stay at their defaults: `--track_lines`, `--draw_track`,
`--track_label` and `--track_crossing` on, plus `--draw_center=1` to etch the
centreline too.

**Why the spoke/frame/support values must shrink:** the defaults were tuned for
the 500 mm HO hexagon. Left at HO sizes on a 220 mm hexagon, the kite cutouts
go degenerate and the generator silently falls back to a **solid** hex (no spoke
pattern). The values above keep the spokes intact (kite size s ≈ 66 mm, see
[Gotchas](#gotchas)).

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
&radius=220&h=100&thickness=3\
&edge_width=22&spoke_width=60&support_length=60\
&bottom=spoke&top=closed&trapezoid=1\
&corner_holes=g2&big_hole_shape=rounded_rect&FingerJoint_extra_length=0.1\
&gap_holes=g4&big_hole_width=50&big_hole_height=70\
&track_width=17&track_lead_in=26" -o hexmo_n.svg
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
http://localhost:4455/HexmoHexagon?radius=220&h=100&thickness=3&edge_width=22&spoke_width=60&support_length=60&bottom=spoke&top=closed&trapezoid=1&corner_holes=g2&gap_holes=g4&big_hole_shape=rounded_rect&big_hole_width=50&big_hole_height=70&FingerJoint_extra_length=0.1&track_lines=1&draw_center=1&draw_track=1&track_width=17&track_lead_in=26&track_spacing=35&track_guide=1&labels=0&reference=0
```

**N-scale HexmoRectangle** — the shared mating dimensions, track settings and
50 × 70 mm pass-through, with 3 lanes and 2 compartments (`num_rows=3`,
`num_columns=2`, see [Straight modules](#straight-modules-hexmorectangle)):

```
http://localhost:4455/HexmoRectangle?radius=220&h=100&thickness=3&spoke_width=120&slot_tolerance=1&num_columns=2&num_rows=3&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&big_hole_width=50&big_hole_height=70&FingerJoint_extra_length=0.1&track_lines=1&draw_track=1&track_width=17&track_lead_in=26&track_spacing=35&track_guide=1&labels=0&reference=0
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
engraved, not cut, and follows the curve from
[The one relationship](#the-one-relationship-to-remember): it enters and leaves at
the midpoints of edges 120° apart, meeting each perpendicularly so neighbouring
modules join smoothly. This works on both the half-hexagon (trapezoid) and the
full hexagon — see **Trapezoid vs. full hexagon** below.

| Parameter | Meaning | N suggestion |
|---|---|---|
| `--track_lines` | master switch: turn the guide on | `1` |
| `--track_line_count` | number of parallel track centrelines | `1`, or `2` for a double-track module |
| `--track_spacing` | radial spacing between adjacent centrelines (mm) | `35` (track-centre to track-centre) |
| `--track_offset` | `centred` (extras straddle the centreline), `outer` (centreline = minimum radius, extras step outward only) or `inner` (centreline = maximum radius, extras step inward only) | `outer` to guarantee no track tighter than the centreline |
| `--track_center_offset` | signed shift (mm) of the reference centreline itself: `+` = outward (larger radius), `−` = inward | `0` (true centreline); `+15` to bias the whole family 15 mm out |
| `--draw_center` | etch the centreline arc(s) themselves | `1` (off by default) |
| `--draw_track` | etch the two track-footprint edges at ± `track_width`/2 | `1` |
| `--track_width` | physical width of the laid track/roadbed (mm) | `17` |
| `--track_lead_in` | straight lead-in length at each edge (mm) | `26` (default `30`) |
| `--track_label` | etch each curve's resulting radius as text | `1` (on by default) |
| `--track_crossing` | etch a tick where each lead-in meets the curve | `1` (on by default) |
| `--track_left` | full hexagon: curve edge 4 → 6 | `1` to draw it |
| `--track_middle` | full hexagon: straight edge 4 → 1 (diameter) | `1` to draw it |
| `--track_right` | full hexagon: curve edge 4 → 2 | `1` to draw it |
| `--track_top` | full hexagon: curve edge 6 → 2 | `1` to draw it |
| `--track_routes` | any routes, each with its own offset at each end (replaces the four above) | e.g. `1:-17.5-5:17.5` |

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
N-scale settings (`R` = 216.5, lead-in 26) that is the 279.8 mm (280 mm) curve. Set it
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
&radius=220&h=100&thickness=3&edge_width=22&spoke_width=60&support_length=60\
&bottom=spoke&top=closed&corner_holes=g2&big_hole_shape=rounded_rect\
&trapezoid=1&track_lines=1&track_line_count=1\
&draw_center=1&draw_track=1&track_width=17&track_lead_in=26" -o hexmo_n_half.svg
```

```bash
# Full hexagon: left + right + middle routes (N-scale params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=220&h=100&thickness=3&edge_width=22&spoke_width=60&support_length=60\
&bottom=spoke&top=closed&corner_holes=g2&big_hole_shape=rounded_rect\
&track_lines=1&draw_center=1&draw_track=1&track_width=17&track_lead_in=26\
&track_left=1&track_right=1&track_middle=1" -o hexmo_n_full.svg
```

### Any route: `--track_routes`

The four toggles above only cover the routes from edge 4 plus the top curve.
`--track_routes` draws any set of routes instead (it replaces the toggles, and
the trapezoid's own curve, when set). Each entry is `A:offset-B:offset`,
comma-separated:

- **Edges two apart** (e.g. `1-5`) get a curve: a straight lead-in, one 60° arc
  and a lead-out. With equal offsets it is the usual concentric curve
  (`279.8 + offset`). With different offsets it is the largest arc that still
  keeps `--track_lead_in` straight at both ends; the shorter end gets exactly the
  lead-in and the other end a longer straight. The etched label gives the radius.
- **Opposite edges** (e.g. `4-1`) get a straight, or an S-curve between the two
  lead-ins if the offsets differ.
- **Adjacent edges** are refused: the curve would be far too tight.

On a curve a positive offset is towards the outside of that curve; on a straight
it is to the right of travel from `A` to `B`. Leave the offsets off (`4-6`) to
draw the `--track_line_count` family along that route. Give one offset and it
applies to both ends. Routes that start at the same edge and offset share their
lead-in, so the second one is drawn as a turnout's diverging route. On the
trapezoid only edges 3, 4 and 5 exist, so its routes all run `3-5` (edge 4 is
next to both), but each can still have its own offset at each end. The helix
ring's M1 carries the main line 17.5 mm out and a spur that moves in from 17.5 to
35 mm inside, `3:17.5-5:17.5,3:-17.5-5:-35` (R297 and R227); M2–M5 carry the
same main line and the spur at a steady 35 mm in, `3:17.5-5:17.5,3:-35-5:-35`.

With `--track_guide=1`, each edge the routes cross gets its own plate, labelled
`track guide edge N`. Its windows sit where the routes cross that edge, in mm
anticlockwise from the edge midpoint. Facing the wall from outside, anticlockwise
is to the right, so with `--part_text=1` an asymmetric plate is etched
`edge M side ->`, naming the neighbour on that side. With `--track_template=1` each different route gets a
template; mirror images and reversals share one.

**Example: the helix ring's M6.** Three tracks enter at edge 1, 35 mm apart. The
outer two (35 mm either side of the centre) are the legs of a reversing loop,
curving to edge 5 or edge 3 and ending 17.5 mm on the inside of their curve
(R227). The spur runs on the centre line and ends 17.5 mm on the outside of the
edge 1 → 5 leg at edge 5 (R262). Every pair stays 35 mm apart, and there is no
edge 3 → 5 track. The turnouts that split the entry line into these three tracks
can't fit on M6: a Peco turnout is a 124–160 mm straight, and M6's tracks start
curving 26 mm in. They sit on a HexmoRectangle joined to edge 1 instead (see
**Turnouts** under [Straight modules](#straight-modules-hexmorectangle)).

```bash
# Full hexagon: helix-ring M6 (N-scale params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=220&h=100&thickness=3&edge_width=22&spoke_width=60&support_length=60\
&bottom=spoke&top=closed&corner_holes=g2&big_hole_shape=rounded_rect\
&track_lines=1&draw_track=1&track_width=17&track_lead_in=26&track_gauge=9\
&track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5" -o hexmo_n_m6.svg
```

### Track-laying guide plate

The etching shows where the track goes; `--track_guide=1` adds a jig that
**holds** it there while you mark and cut. It is one extra flat plate that you
dowel to the outer face of any side wall, through two small pilot holes: the
pin directly above each end's medium hole, in the row nearest the deck. No
medium holes are cut. The plate is only as big as it needs to be, with 15 mm of
solid material around the pins and windows (156.5 × 75 mm with the N-scale settings). It
stands above the deck with one rectangular window per track:

- **Width:** exactly `--track_width`, so the track can't move sideways.
- **Height:** `--track_guide_clearance` (default 30 mm), so there's room for
  roadbed, risers and scenery. The window floor starts one material thickness
  below the deck surface, level with the deck's underside, so the plate never
  lifts the track even if it sits slightly high on its dowels.

Every track crosses a wall at a right angle, at the wall's centre, offset along
the wall by `--track_spacing`, `--track_offset` and `--track_center_offset`. So
one plate fits every standard wall. The windows use the same offsets as the
etching, so the two always agree. The pins come from the same code as the wall's
corner groups, so they match exactly. Both `--corner_holes` options have them,
so the guide is the same either way. A wider track family makes the plate wider
to keep the margin round the outer windows.

If the tracks aren't symmetric about the centre (`--track_offset=outer` or `inner`, or a
non-zero `--track_center_offset`), the plate can be etched with
`outside of curve ->` (`--part_text=1`). The other end of a curve is its mirror image, so flip the
plate over for that end. The hole pattern is symmetric, so it still fits.

| Parameter | Meaning | N suggestion |
|---|---|---|
| `--track_guide` | add the guide plate | `1` |
| `--track_guide_clearance` | window height above the deck (mm) | `30` |

```bash
# Half-hexagon with its track guide (N-scale params)
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=220&h=100&thickness=3&edge_width=22&spoke_width=60&support_length=60\
&bottom=spoke&top=closed&corner_holes=g2&big_hole_shape=rounded_rect\
&trapezoid=1&track_lines=1&track_line_count=1\
&draw_center=1&draw_track=1&track_width=17&track_lead_in=26\
&track_guide=1&track_guide_clearance=30" -o hexmo_n_half_guide.svg
```

If a window wouldn't fit on the plate (for example a very wide `--track_spacing`),
the generator stops with an error instead of drawing a guide that falls apart.

### Track-laying template (Tracksetta-style)

Commercial track-setting templates come in fixed radii that don't match these
modules, so the generators cut their own. `--track_template=1` adds a flat strip
exactly `--track_gauge` wide that sits **between the rails**. Push flexible track
against both edges and it holds the module's exact curve while you pin it down.

- **Shape:** it follows the etched track centreline: lead-in straight, the 60°
  curve, lead-in straight. Its ends sit where the track crosses the module
  edges. With the N-scale settings it is the 280 mm curve, 345 mm long (centreline) in one piece.
- **One per track:** a double-track module gets one template per track, at each
  track's radius. On the full hexagon every curve route (left/right/top) shares
  the same radii, so one set covers them; `--track_middle` adds a straight.
  HexmoRectangle cuts one straight the length of its track.
- **Width:** `--track_gauge` is the distance between the inside faces of the rails,
  **9 mm** for N (`--track_width` is the sleeper footprint, not the
  gauge). `--track_template_clearance` (default 0) narrows it slightly so it
  lifts out of laid track easily. Laser burn is compensated, so the strip is cut
  true to size.
- **Segments:** `--track_template_segments` (default 1) splits each template into
  equal-length pieces, e.g. to fit a smaller laser bed. Each piece is etched
  with its radius, the gauge and `i/N`, plus a mark at each end: **EDGE** on the
  two ends that sit at the module edges, and a matching letter on both sides of
  every cut. With 3 pieces that reads `EDGE … 1/3 … A`, `A … 2/3 … B`,
  `B … 3/3 … EDGE`, so matching letters go together. The radius label and the
  **EDGE** marks are only etched with `--part_text=1` (see below); the letters
  always are.
- It is cut from the module's own `--thickness`, with no handle.

| Parameter | Meaning | N suggestion |
|---|---|---|
| `--track_template` | add the template(s) | `1` |
| `--track_gauge` | rail gauge, inside faces (mm) | `9` |
| `--track_template_clearance` | taken off the width (mm) | `0` |
| `--track_template_segments` | pieces per template | `1` (or `2`–`3` for a small bed) |

```bash
curl "http://localhost:4455/HexmoHexagon?render=1\
&radius=220&h=100&thickness=3&edge_width=22&spoke_width=60&support_length=60\
&trapezoid=1&track_width=17&track_lead_in=26\
&track_template=1&track_gauge=9" -o hexmo_n_template.svg
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
&radius=220&h=100&thickness=3&num_rows=3&num_columns=2\
&big_hole_shape=rounded_rect&big_hole_width=50&big_hole_height=70\
&track_lines=1&draw_track=1&track_width=17&track_lead_in=26" -o hexmo_rect_track.svg
```

`--track_guide=1` (and `--track_guide_clearance`) works here too, for the two
short end walls. The rectangle cuts **exactly the same plate** as HexmoHexagon
with the same settings, so one guide fits a hex side wall, a trapezoid side wall
or a rectangle end wall. It holds the track at the same place on either side
of a joint. (Its end-wall pins are placed from the hexagon's wall geometry, so
the dowels line up.)

```bash
curl "http://localhost:4455/HexmoRectangle?render=1\
&radius=220&h=100&thickness=3&num_rows=3&num_columns=2\
&big_hole_shape=rounded_rect&big_hole_width=50&big_hole_height=70\
&track_lines=1&draw_track=1&track_width=17&track_lead_in=26\
&track_guide=1" -o hexmo_rect_guide.svg
```

**Internal layout.** Two options set the rectangle's internal grid:

| Parameter | Meaning | N suggestion |
|---|---|---|
| `--num_columns` | compartments along the long axis; N compartments need N−1 short dividers. `0` = auto from radius | `2` |
| `--num_rows` | lanes across the short axis; N lanes need N−1 long internal supports running the full length. Default `3` | `3`, with the 50 mm-wide pass-through (below) |

The preferred N rectangle keeps 3 lanes (two long supports, at ±35.2 mm) and
narrows the big holes to 50 × 70 mm so the pass-through fits between them, on
the end walls and the short dividers. `num_rows=1` is the alternative: no long
supports at all, so even a full-size 70 mm hole fits. The centre spoke runs down
the middle lane, so an even `num_rows` needs `spoke_width=0`; otherwise the
generator stops with an error.

The short internal dividers cut **the same big holes as the end walls**, at the
same positions and height, so they line up along the module (handy as a wiring
run). A big hole that would cross a long-support slot is left out of both, so
with 3 rows at `radius=220` the full-size 70 mm centre hole is dropped rather
than cut through the joint. To keep 3 rows *and* the pass-through, narrow it
with `--big_hole_shape=rounded_rect` and `--big_hole_width` of up to **57 mm**
(the supports sit at ±35.2 mm); the hole stays centred and keeps its 70 mm
height.

**Turnouts (`--turnouts`).** A rectangle is the place for turnouts: they are
straight-bodied, 124–160 mm long in N, and a hexagon's tracks start curving 26 mm
in. Each comma-separated entry `toe:from:to` etches one turnout's diverging leg.
Its toe is `toe` mm along the deck, on the straight track at lateral offset
`from` (the track lines' own offsets, `+` towards `+y`). The leg curves off and
settles at offset `to`, keeping it to the end of the deck. The sign of `to −
from` gives the hand, and every turnout faces the same end, so fit that end to
the module the tracks fan out into. The through road is the deck's ordinary
straight line.

The leg follows the turnout's own diverging road, a `--turnout_radius` curve to
the `--turnout_angle` crossing angle, straight on past the heel
(`--turnout_length` after the toe), then flexible track: a
`--turnout_reverse_radius` curve back to parallel. The defaults are Peco's N
medium turnout (SL-E395/396: 123.7 mm, R457, 14°) and a 300 mm reverse curve,
which puts the leg 16.9 mm off the through road at the heel and back parallel
35 mm out about 233 mm after the toe. A tick marks each toe, and with
`--track_crossing` each leg gets the usual end tick. The generator stops with an
error if a leg can't spread that far, isn't back parallel before the end of the
deck, or runs off it.

**The helix ring's entry rectangle** joins M6 edge 1 and splits the entry line
into M6's three deck tracks. T1 (toe 10 mm in) sends loop A to −35, and T2 (toe
at T1's heel, 133.7) sends loop B to +35. The centre line runs on as the spur,
and T2's leg is parallel 367 mm along the 375 mm deck. The lower level passes
under the deck on the centre line, through both end walls and the short divider
(`--under_track`, at the same 27.8 mm and 35 mm as M6's edge 1 opening). The two
long supports sit at ±35.2 mm, right under the loop tracks, and the centre lane
under both toes is clear for point motors. For a guide plate at the M6 joint,
use M6's own edge-1 plate: it has windows for all three tracks.

```bash
# Helix ring entry (N, h=80): two Peco medium turnouts, the lower level underneath.
curl "http://localhost:4455/HexmoRectangle?render=1&radius=220&thickness=3&h=80\
&num_rows=3&num_columns=2&big_hole_shape=rounded_rect&big_hole_width=50&big_hole_height=50\
&track_lines=1&draw_track=1&track_width=17&track_lead_in=26\
&under_track=1&under_track_height=27.8&under_track_width=35\
&turnouts=10:0:-35,133.7:0:35" -o hexmo_n_helix_entry.svg
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

### Under-deck track opening

The centre big hole sits halfway up the wall, which suits a train on the floor.
For a lower track that runs just *under the deck* (the helix ring's descending
spur), chosen walls get a rectangular opening instead, on the wall's centre line:

- its **top** is one material thickness under the deck underside;
- its **bottom** is the track height, `--under_track_height` mm above the floor
  panel. `0` (default) puts it as high as still leaves 43 mm for the track and a
  40 mm train, i.e. 46 mm under the deck;
- its **width** along the wall is `--under_track_width` (default `30`).

On HexmoHexagon, `--under_track_edges` lists the edges whose side walls get it
(e.g. `1`; the trapezoid only has edges 3, 4 and 5). Those walls are labelled
with their edge, since they are no longer interchangeable. On HexmoRectangle,
`--under_track=1` cuts it through both end walls and every short divider, so the
track can run from end to end. Both measure from the deck, so the openings of
joined modules line up. The opening keeps 5 mm clear of every other hole; other
big holes that would come closer are left out. A width that reaches the corner
hole groups, a track height too close to the floor or under the deck, or a long
support crossing the opening (HexmoRectangle with an even `--num_rows`) is
refused with an error.

### Track openings at a joint (`--track_openings`)

A track that crosses a joint below deck level but off the centre line (the helix
ring's descending spur) needs its own opening in the wall at that edge. Each entry
is `edge:position:height[:width]`:

- `position` — mm along the edge from its midpoint, anticlockwise seen from above
  (to the right, facing the wall from outside), as for the per-edge track guides;
- `height` — the track base above the floor panel, the opening's bottom edge;
- `width` — along the wall, default `--under_track_width`.

If a 40 mm train on that track still fits one thickness under the deck, the
opening is a closed hole up to one thickness under the deck. Otherwise it is a
**notch** open at the top of the wall, and the deck edge above it is left plain
(no finger slots) across the notch. The wall's top joint and the deck edge are
both split round it, so they still mate finger for finger. The deck itself stays
closed until the deck slot along the track is cut. A notched or holed wall is
labelled with its edge; fit it with the opening over the track. Openings keep
2 mm clear of the wall's other holes. Big holes, and the 25 mm medium (cable)
holes at each end of the wall, that would come closer are left out instead; both
walls at a joint lose the same one, so they still match. A track exactly at the deck underside
(74 mm at h=80) rests on the wall top: nothing is cut from the wall, its top edge
and the deck edge just go plain across the opening, so a deck slot can still run
out over the joint. An opening is refused if it reaches a small pin hole, overlaps
another opening, or puts the track too near the floor or above the deck underside.

```bash
# Helix ring M1 at h=80.  Trains run edge 3 → edge 5 through every ring module,
# so the spur enters at edge 3 (from M6, 17.5 mm towards edge 4) on the wall top
# (a flush opening) and leaves at edge 5 (to M2, 35 mm towards edge 4) in a notch.
curl "http://localhost:4455/HexmoHexagon?render=1&radius=220&thickness=3&h=80\
&trapezoid=1&track_openings=3:-17.5:74:35,5:35:66.1:35" -o hexmo_n_m1.svg
```

### Deck slots along a descending track (`--deck_slots`)

A track that drops away from the deck runs in an open slot cut through it.
Each entry is `route[@from..to][/width]`:

- `route` — as in `--track_routes` (`A:offset-B:offset`; offsets default to 0);
- `@from..to` — the stretch, in mm along the route from its start; leave either
  end off for the route's end (`@169..`, `@..186`). Default: the whole route;
- `/width` — default `--under_track_width`.

A slot that reaches a deck edge runs 1 mm past the wall's inner face, where the
route ends. The deck reaches one thickness further, out over the wall, so a
narrow strip of deck (2 mm at 3 mm stock) is left across the slot's mouth on
purpose. A slot from edge to edge (M1–M5 of the helix ring) would otherwise cut
the deck in two; the strip keeps it in one piece until it is fitted, then cut it
away with a knife. The wall
below must have a `--track_openings` notch there at least as wide as the slot,
which also leaves that deck edge plain; otherwise it is refused. A slot that
crosses a support slot is refused too, because the support wall would block the
track underneath; see the next section. The outline is cut with the same burn
compensation as other holes.

### Choosing and placing supports (`--support_edges`, `--support_position`)

The support walls stand under the deck, floor to deck, one per half-spoke (the
line from the centre to an edge's midpoint), centred half the apothem out. A
track running below the deck must not pass through one.

- `--support_edges` — which half-spokes get a support, by the edge each points
  to, e.g. `2,4,6`. Default: all of them (1–6 on the hexagon; 4, or 3, 4, 5 with
  `--trapezoid_side_supports`, on the trapezoid). When set it overrides
  `--trapezoid_side_supports`. Each entry can also give its own position and a
  quarter turn, `E[@position][/90]`: `4@30/90` is a support on the edge-4
  half-spoke, centred 30 mm out, turned to run across the half-spoke instead of
  along it. An edge can be listed more than once.
- `--support_position` — distance (mm) from the centre to the middle of every
  support. Default: half the apothem (about 94 mm). Refused if a support would
  reach the centre or the side wall.

The support walls and their slots in the deck and bottom panel all follow both,
so they still fit. A support that would reach the centre, a side wall, the
trapezoid's long wall or another support is refused, and so is one whose slot
would stand over a kite on a spoke floor (it must be on a spoke or the rim).

For the helix ring: the trapezoids (M1–M5) use `--support_edges 4@132,4@30/90`.
The support at 132 mm sits past the spur's 35 mm slot (and clear of the riser
support standing on the same line mid-module), under the inner part of the deck. The turned one at 30 mm sits right under the main line (on M1 the spur
runs closer to the centre, so with a 35 mm slot it must be within about 44 mm),
and on a spoke floor its slot lands on the centre spoke. M6 keeps the three supports clear
of its spur, `--support_edges 2,4,6`.

### Riser boards (`--risers`)

Under a descending track, a riser holds the track up at the right height. It is
a **track bed** (one flat strip following the track's path, flexed very slightly
to the slope) and **supports** (small boards standing across the track, each cut
to the bed's height there). The supports' bottom tabs drop into slots in the
floor panel and their top tabs into slots in the bed, so everything locates
exactly. Each entry is `route[@from..to]~h0..h1[/width]`:

- `route` and `@from..to` — as for `--deck_slots`;
- `~h0..h1` — the track height (the bed's top) above the floor panel at the
  stretch's start and end, falling (or rising) evenly. It is `~`, not `=`,
  because the web server splits each URL parameter on `=`;
- `/width` — the bed width, default `--track_width`.

Supports stand 15 mm in from each end of the bed and evenly between, at most
`--riser_spacing` (default 80) apart; with `--part_text=1` each has its height etched on it. Fit the
floor panel with its slots under the bed. On a spoke floor (`--bottom spoke`)
the kite cut-outs would leave nothing for a support to slot into, so a solid
**spine** is left along each riser's path: a band following the track, the bed's
width plus 6 mm each side wide. The kites keep their full size apart from that
band, cut as the openings either side of it, so supports can stand anywhere along
the track. Pieces narrower than 15 mm are left solid. Where a riser stops inside a
kite, the spine runs straight on to that kite's edge. Kites the spine misses, and
the spoke floor without risers, are unchanged. `--bottom closed` works too. A
support that would stand in another riser's track, on a support wall's slot, or
against a side wall is refused, and so is a bed wider than the wall notch it
passes through or the deck slot on its route.

**The deck slot's cut-out is the bed.** When a riser runs along exactly the same
route, stretch and width as a `--deck_slots` entry, the strip that falls out of
the slot *is* the bed, so no separate bed part is cut. The bed's support slots
are cut in the deck inside the slot outline (before it, so the strip doesn't drop
out first), and the slot stops at the wall's
inner face so the strip fits between the walls (the deck left over the wall is
then one full thickness, cut away once fitted, as before). Make the two entries
match to use it, e.g. `--deck_slots 3:-17.5-5:-35/35` with
`--risers 3:-17.5-5:-35~74..66.1/35`. Where a track carries on under the deck
past the end of its slot (M6's return), give that stretch its own riser entry;
it gets a separate bed.

For the helix ring the notches, the deck slot and the bed are all 35 mm, which
leaves room for long N coaches overhanging on the R227–R262 spur curves (about
34 mm swept). At h=80 the spur heights are 74.0 (M6/M1), 66.1, 58.5, 50.8, 43.2
and 35.6 (M5/M6), 31.0 where its return slot ends under M6's deck and 27.8 at M6
edge 1. On M6 the spur leaves the deck at 169 mm along its route, as soon as it
is clear of the return running below it. It falls gently (1.6 %) from 77 (deck
level) to 74 at edge 5, so it crosses the M6/M1 joint resting on the wall tops:
the openings there are flush, with nothing cut from either wall. From there it is
a steady 2.47 % to the end of the return slot, then 1.75 % to edge 1. The
return's slot stops at 186 mm. That leaves the deck whole under the spur's first
stretch, and a 10 mm web of deck between the two slots. Past the slot the return
runs under the deck, so it must be down to 31.0 by then (the 74 mm deck underside
less a 43 mm train). The slots are `1:0-5:17.5@169..` and `3:35-1:0@..186`.

#### The ring at radius 250

At `radius=250`, with a 20 mm lead-in (`--track_lead_in 20`) where each track
crosses a joint, the curves are bigger: the deck curve is R335, the main line
R353 and the spur R300, instead of R280, R297 and R245 at 220 (with 26 mm
lead-ins). The ring is 1.30 m across the flats, instead of 1.14 m. The same
rules give its numbers (the presets in `_hexmo_helix_ring.py` are built from
them):

- **Heights:** its longer run lets the spur end lower than at 220, leaving
  spare headroom at both tight spots. One steady grade, 2.28 %, runs from 74
  at M6/M1 to 28.0 where the return's slot ends under M6's deck: 46 mm under
  the 74 mm deck underside, 3 more than a 43 mm train needs. It carries on at
  the same grade to **23.8** at M6 edge 1, which leaves 47.2 mm under the entry
  rectangle's deck. The joint heights are 74, 65.6, 57.6, 49.5, 41.4 and 33.3
  (M5/M6). The lower level leaves the helix at 23.8 (`--under_track_height`
  on M6 and the entry), and the scenery ring's lower ground is at 23.8 too.
- **On M6:** the spur leaves the deck at 178 mm, the earliest point where its
  first riser support is clear of the return below. The return's slot ends at
  233 mm, leaving a 10 mm web of deck between the two slots.
- **Trapezoid supports:** `4@140,4@38/90`. As at 220, the radial support stands
  just past the spur's slot, and the turned one just inside the main line,
  which runs 34.3 mm out at mid-module.

The 220 ring's numbers above are hand-worked and leave a 15.7 mm web on M6.

```bash
# Helix ring M6 at h=80: three deck tracks at edge 1 (loop legs at ±35, spur on
# the centre line), the spur's slot and riser, the lower-level return under the
# deck to edge 1, and three supports clear of both.
curl "http://localhost:4455/HexmoHexagon?render=1&radius=220&thickness=3&h=80\
&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&support_edges=2,4,6\
&track_lead_in=26&track_width=17\
&track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5\
&under_track_edges=1&under_track_height=27.8&under_track_width=35\
&track_openings=5:17.5:74:35,3:-35:35.6:35\
&deck_slots=1:0-5:17.5@169../35,3:35-1:0@..186/35\
&risers=1:0-5:17.5@169..~77..74/35,3:35-1:0@..186~35.6..31/35,3:35-1:0@186..~31..27.8/35" \
  -o hexmo_n_m6_riser.svg
```

```bash
# Helix ring M1 at h=80, with the spur's riser (74 at edge 3, on the wall top, to 66.1 at edge 5),
# all 35 mm wide.
curl "http://localhost:4455/HexmoHexagon?render=1&radius=220&thickness=3&h=80\
&trapezoid=1&bottom=spoke&support_length=55&support_edges=4@132,4@30/90\
&track_lead_in=26&track_width=17\
&track_routes=3:17.5-5:17.5,3:-17.5-5:-35\
&track_openings=3:-17.5:74:35,5:35:66.1:35&deck_slots=3:-17.5-5:-35/35\
&risers=3:-17.5-5:-35~74..66.1/35" -o hexmo_n_m1_riser.svg
```

```bash
# Helix ring M1 at h=80: main line 17.5 mm out, the spur moving in from 17.5 to
# 35 mm inside, its notches and its slot, with the support moved out past it.
curl "http://localhost:4455/HexmoHexagon?render=1&radius=220&thickness=3&h=80\
&trapezoid=1&support_length=55&support_edges=4@132,4@30/90\
&track_lead_in=26&track_width=17\
&track_routes=3:17.5-5:17.5,3:-17.5-5:-35\
&track_openings=3:-17.5:74:35,5:35:66.1:35\
&deck_slots=3:-17.5-5:-35/35" -o hexmo_n_m1_slot.svg
```

### Helper-part text (`--part_text`)

The helper parts can carry descriptive text: each riser support's track height,
the track guide's side arrow (`edge M side ->`, `outside of curve ->`), and the
track template's radius label and **EDGE** end marks. It clutters the cut sheet,
so it is **off** by default; set `--part_text=1` to etch it. The letters that pair
up the cut ends of a split template are always etched, since they are needed to
reassemble it. Part labels (e.g. `riser 73.2`, `track guide edge 3`) follow the
standard `--labels` option, and the deck's radius label follows `--track_label`.

### Scenery: upper and lower ground (`--lower_ground`)

For scenery on the helix, the inner side of each trapezoid (towards the ring
centre) can be opened up into two levels, with the spur descending between
them:

- **Upper ground** is the deck at 74, carrying the main line. It's cut back to
  the outer edge of the spur's deck slot.
- **Lower ground** is a new plate whose top is `--lower_ground` mm above the
  floor panel. It runs from the edge-4 wall out to the slot's inner edge. At
  **27.8** it's flush with the lower level where it leaves M6 under the entry,
  so it's level all the way round the ring.
- **The strip under the spur** (the slot's 35 mm) stays open down to the box
  floor. The spur, its bed and its riser supports are exactly as before.

The slope between the levels is yours to build; there's no cliff wall.

The walls follow:

- **Edge-4 wall:** lowered all along, under the lower plate.
- **Side walls (edges 3 and 5):** lowered from edge 4 to the spur. Across the
  spur they keep its `--track_openings` opening, cut from the top, so its bottom
  edge still carries the bed end at the joint. From there out they're full
  height under the deck.
- **Holes:** any hole the lowered part would cut through is left out. The rule
  is the same on both sides of a joint, so the pins still line up.
- **Supports:** any support under the lower plate is shortened to fit; the ones
  under the deck stay as they are.

On the **full hexagon (M6)** only the walls on edges 3 and 5 step down, to meet
M5 and M1. M6's deck edge goes plain over the lowered part; you cut the deck
back by hand.

It needs the spur's deck slot (a `--deck_slots` entry from edge 3 to edge 5)
and its wall openings on edges 3 and 5, as the helix modules already have. The
deck's cut-back edge follows the slot. Set **`--upper_edge_gap`** to keep less
deck instead: the edge then runs that many mm inside the main line's rail edge,
so there's nothing to sand away. It never comes inside the spur's slot; in M1
the spur swings to within 9 mm of the main line near edge 3, so a bigger gap
stays at the slot's edge there. Give M6 the same `--upper_edge_gap`: its deck stays
whole, but its stepped walls then start their deck joints where the trapezoids'
do, so the fingers of the two walls at each joint line up.

Edit links for the ring at **radius 250** (see [The ring at radius 250](#the-ring-at-radius-250)),
with its settings: g2 hole groups, rounded-rectangle big holes, the track guide
and template, no labels or reference rectangle, and the trapezoids' decks
stopping 15 mm inside the main line (`upper_edge_gap=15`). Each opens the form
pre-filled:

- **M1:**
  http://localhost:4455/HexmoHexagon?radius=250&thickness=3&h=80&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&track_lead_in=20&track_width=17&under_track_width=35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&trapezoid=1&support_edges=4@140,4@38/90&access_openings=1&track_routes=3:17.5-5:17.5,3:-17.5-5:-35&track_openings=3:-17.5:74:35,5:35:65.6:35&deck_slots=3:-17.5-5:-35/35&risers=3:-17.5-5:-35~74..65.6/35&lower_ground=23.8&upper_edge_gap=15
- **M2:**
  http://localhost:4455/HexmoHexagon?radius=250&thickness=3&h=80&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&track_lead_in=20&track_width=17&under_track_width=35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&trapezoid=1&support_edges=4@140,4@38/90&access_openings=1&track_routes=3:17.5-5:17.5,3:-35-5:-35&track_openings=3:-35:65.6:35,5:35:57.6:35&deck_slots=3:-35-5:-35/35&risers=3:-35-5:-35~65.6..57.6/35&lower_ground=23.8&upper_edge_gap=15
- **M3:**
  http://localhost:4455/HexmoHexagon?radius=250&thickness=3&h=80&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&track_lead_in=20&track_width=17&under_track_width=35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&trapezoid=1&support_edges=4@140,4@38/90&access_openings=1&track_routes=3:17.5-5:17.5,3:-35-5:-35&track_openings=3:-35:57.6:35,5:35:49.5:35&deck_slots=3:-35-5:-35/35&risers=3:-35-5:-35~57.6..49.5/35&lower_ground=23.8&upper_edge_gap=15
- **M4:**
  http://localhost:4455/HexmoHexagon?radius=250&thickness=3&h=80&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&track_lead_in=20&track_width=17&under_track_width=35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&trapezoid=1&support_edges=4@140,4@38/90&access_openings=1&track_routes=3:17.5-5:17.5,3:-35-5:-35&track_openings=3:-35:49.5:35,5:35:41.4:35&deck_slots=3:-35-5:-35/35&risers=3:-35-5:-35~49.5..41.4/35&lower_ground=23.8&upper_edge_gap=15
- **M5:**
  http://localhost:4455/HexmoHexagon?radius=250&thickness=3&h=80&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&track_lead_in=20&track_width=17&under_track_width=35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&trapezoid=1&support_edges=4@140,4@38/90&access_openings=1&track_routes=3:17.5-5:17.5,3:-35-5:-35&track_openings=3:-35:41.4:35,5:35:33.3:35&deck_slots=3:-35-5:-35/35&risers=3:-35-5:-35~41.4..33.3/35&lower_ground=23.8&upper_edge_gap=15
- **M6:**
  http://localhost:4455/HexmoHexagon?radius=250&thickness=3&h=80&edge_width=22&spoke_width=60&bottom=spoke&support_length=55&track_lead_in=20&track_width=17&under_track_width=35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&access_openings=1&access_edges=2,4,6&support_edges=2,4,6&track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5&under_track_edges=1&under_track_height=23.8&track_openings=5:17.5:74:35,3:-35:33.3:35&deck_slots=1:0-5:17.5@178../35,3:35-1:0@..233/35&risers=1:0-5:17.5@178..~77..74/35,3:35-1:0@..233~33.3..28/35,3:35-1:0@233..~28..23.8/35&lower_ground=23.8&upper_edge_gap=15
- **Entry rectangle** (at M6 edge 1, with the lower level on a subway):
  http://localhost:4455/HexmoRectangle?radius=250&thickness=3&h=80&num_rows=3&num_columns=2&track_width=17&track_lead_in=20&under_track=1&under_track_height=23.8&under_track_width=35&turnouts=10:0:-35,133.7:0:35&corner_holes=g2&gap_holes=g2&big_hole_shape=rounded_rect&track_guide=1&track_template=1&labels=0&reference=0&subway=23.8&access_openings=1

The 3D export shows it all (exact parts only), and `--ring=N250-ground`
exports the whole ring opened up this way, with these settings (see below).
`--ring=N-ground` is the same at radius 220.

### Subway: a level track under the deck (`--subway`)

The helix's lower level leaves M6 under the entry rectangle and carries on under
the deck of whatever module comes next. Under a deck a track needs its own bed
and supports, and an opening in every wall it crosses. One `--subway` setting
gives all of that, on every Hexmo module:

- **HexmoHexagon (full or trapezoid):** `A:offset-B:offset~HEIGHT[/WIDTH]`, a
  route as for `--track_routes`, the track height (its base, mm above the floor
  panel) and the bed width (default `--under_track_width`), e.g.
  `--subway 4:0-1:0~23.8`. It adds the wall openings at both ends of the route
  (as `--track_openings` would) and a level riser along it (as `--risers` would):
  a bed, and supports slotted into the floor. Straight or curved; several may be
  given, comma-separated.
- **HexmoRectangle:** `HEIGHT[/WIDTH]`, e.g. `--subway 23.8`. The track runs down
  the centre line from end wall to end wall, through the under-deck openings
  (`--under_track`, turned on at the subway's height and width). Each cell
  between the end walls and short dividers gets a level bed, its top at the
  track height, whose supports slot into the floor strip down the middle lane
  (the spoke). The strip's weight-saving holes give way to the slots. The track
  crosses each wall on its opening's bottom edge, as the helix spur does at its
  joints. Supports stand 15 mm in from each end of a bed and at most
  `--riser_spacing` (default 80) apart.

**Subway-ready walls (`--subway_ports`):** every wall that joins another module
gets the under-deck opening in its middle (where the spoke meets it), at
`--under_track_height` and `--under_track_width`, with a 30 × 14 mm cable slot
under it, centred between the opening and the floor. A subway can then carry on
through any joint, and wiring can follow it. HexmoRectangle: the end walls and
short dividers. Trapezoid: its short walls (3, 4 and 5). Full hexagon: all six.
Walls with `--access_openings` (the trapezoid's long wall, the hexagon's
`--access_edges`) get theirs in the spoke-wide middle post between their two
openings, with 12.5 mm of wood either side at the usual 60 mm spoke and 35 mm
opening. A wall whose middle already has a track or spur opening too close, or
a lowered `--lower_ground` wall, is left as it is. The slot needs about 22 mm under the opening; set
`--under_track_height` to the subway's height (23.8 on the 250 ring).

**Access for re-railing (`--access_openings`):** a wall that joins no other
module needs no medium registration holes, so it can carry large rounded-
rectangle openings instead, for a hand to reach a derailed train under the
deck. Each leaves 12 mm of wood above and below and 15 mm at each end. The
wall keeps some of its Ø6 dowel holes, at their usual places: in each opening,
the pairs nearest its two ends stay (5 mm clear of it) and the opening shrinks
between them; any pairs in between go. Where the pairs are too close together
for that, the pair beside the middle post goes instead and the opening runs to
the post.

- **HexmoRectangle:** each long wall gets one opening per cell, about
  132 × 50 mm at radius 250 and h=80, with four dowel pairs. The long supports
  get the same openings, lined up, so you can reach through the outer lanes into
  the subway in the middle lane.
- **Trapezoid:** its long wall gets two, either side of a middle post as wide as
  `--spoke_width` (over the floor's spoke): about 124 × 50 mm each, with four
  dowel pairs.
- **Full hexagon:** the walls listed in `--access_edges` (default `1,3,5`) get
  two each, either side of the spoke-wide post: about 40 × 50 mm, for fingers,
  with a dowel pair at each end. Pick walls that join no other module; a wall
  with a track or under-deck opening, or a `--lower_ground` step, is refused.

An opening too small (under about 70 × 40 before the dowels are kept) is
refused.

The 250 ring's presets use them on every wall that joins nothing: the
trapezoids' long walls (the ring's outside), M6's edges 2, 4 and 6, and the
entry rectangle's long walls and supports.

The ring at radius 250's entry rectangle carries the lower level this way, at
23.8, with the access openings (the link above). A hexagon or trapezoid that continues it gives its own
`--subway` at the same height, starting where the rectangle's track leaves
(the centre of the end wall it joins).

## 3D model for CAD (`--format step`)

HexmoHexagon and HexmoRectangle can output the module **assembled in 3D**, as
a STEP file you can open in Onshape, FreeCAD, Fusion and so on, instead of the
laser parts. It's for checking a design before cutting: orbit it, take a section
through a joint, measure a clearance.

In the web form choose **Format → step** and **Generate**, and the browser
downloads `HexmoHexagon.step` (or `HexmoRectangle.step`). Every setting is
checked exactly as for the laser output.

By default each part is **exact**: its real cut outline, the same one the
laser cuts, with the finger joints, pin holes, big holes, kites, notches and
slots. It's at nominal size (no burn), extruded to `--thickness` and placed where
it sits once built, so you can check how the parts fit before cutting. Tabs sit
in their slots, and the tests check that joined parts don't overlap. Riser beds
are smooth solids sloping as set, with their support slots cut. Every part is
named in the CAD part list:

- `floor`, `deck`, `wall edge N` (and the trapezoid's `long wall`),
  `support edge N`; on a rectangle `long wall`, `end wall`, `long support`,
  `divider`, `spoke`;
- `riser bed …` and `riser support …`;
- `track …`: each track as a 3 mm ribbon on the deck or its bed;
- `clearance …`: a translucent train envelope (`--train_envelope` high,
  `--under_track_width` wide). `--step_clearance` sets where: `under` (default)
  over the tracks on risers, the ones that pass under or through the deck;
  `all`; or `none`.

`--step_detail=simple` gives plain slabs instead (no joints or holes), which is
quicker and much lighter. The exact M6 is about 11 MB and takes about 5 s; the
simple one is 1.5 MB.

Heights are measured as everywhere else, from the top of the floor panel.

**A 3D drawing instead:** choose **Format → svg_3d** for the assembled module
drawn in 3D: an SVG line drawing seen from the front right, above, with hidden
lines removed, at 1:1 in mm. It's a quick look at the built module without CAD.
**view_deck** adds the deck. It's off by default, so the drawing shows inside:
walls, supports and risers. Only the cut parts are drawn (the cut sheet's red
lines), so the track ribbons and clearance boxes are left out. `--step_detail`
applies here too.

**The whole helix ring** (six modules round their centre, plus the entry
rectangle with its turnouts) exports as one file from the command line:

```bash
python -m boxes.generators._hexmo_step helix-ring.step --ring=N
# plain slabs instead of the exact parts (about 6 MB instead of 64 MB):
python -m boxes.generators._hexmo_step helix-ring.step --ring=N --detail=simple
# a 3D line drawing of the ring (add --deck for the decks):
python -m boxes.generators._hexmo_step helix-ring.svg --ring=N
# the ring at radius 250 (--ring=N250), opened up for scenery (exact parts only):
python -m boxes.generators._hexmo_step helix-ring-ground.step --ring=N250-ground
# the same at radius 220:
python -m boxes.generators._hexmo_step helix-ring-ground.step --ring=N-ground
# or a single module, with any generator options:
python -m boxes.generators._hexmo_step m6.step --radius=220 --h=80 …
```

The ring's tracks meet at every joint, same place and same height (the tests
check this), so following the spur round the ring shows the whole descent.

**Opening it in Onshape:**

1. **Create → Import**, pick the `.step` file.
2. Choose **Import to a single document**, keep **Import appearances** on, and
   turn **Orient imported models with Y Axis Up** *off* (the file is Z-up, as
   Onshape is; with it on, the module lies on its side). Leave composite parts
   and joining surfaces off.
3. The result is in the **CAD Imports** folder tab: an assembly with every part
   named, and a Part Studio. Hide the `deck`s and `clearance`s (filter the list
   by name) to see underneath, or use **Section view** across a joint.
4. When the design changes, import the new file fresh. **Update** only keeps
   parts whose shape is unchanged, so rebuilt beds and tracks fail to resolve.

The free Onshape plan makes documents public.

**Installing:** the 3D export needs the optional `step` dependency (build123d
and the OpenCascade kernel, 100+ MB): `pip install .[step]`. The Docker image
includes it when built with `WITH_STEP=1`, as this fork's `docker-compose.yml`
does; on a slim image it also needs the system OpenGL libraries (`libgl1`).
Without it, `--format step` stops with a message saying what to install, and
the laser formats are unaffected.

---

## Gotchas

- **`--outside`**: it is **on** by default in both HexmoHexagon and
  HexmoRectangle, and that is the intended setting, so leave it on. `radius`
  is then the outside corner radius, and the inside is shrunk by one thickness
  (inner corner radius = `radius − t / cos 30°`). The etched track is built from
  that inner radius, and `--track_label` etches the radius you actually get. Both
  generators must use the same setting, or their walls won't line up.
- **Solid-hex fallback**: if you change `edge_width`/`spoke_width` and the spoke
  pattern disappears, the kites went degenerate. Keep
  `edge_width < A_inner` and `spoke_width` small enough that
  `s = A_inner/√3 − spoke_width/2 > 0`, where `A_inner = R·cos30° − edge_width` and
  `R` is the inner corner radius (`radius − t / cos 30°` with `--outside` on). At the
  N-scale settings: `A_inner = 216.5·cos30° − 22 = 165.5`, so `s ≈ 95.6 − 30 = 65.6 mm`.
- The **height** and **thickness** are build choices, not track geometry. Scale
  height by ~0.54 (the N:HO linear ratio) if you want it visually proportional
  to an HO module.
