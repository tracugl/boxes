# Hexmo Drive: drive a train round a helix layout

A 3D preview, in the browser, of a Hexmo helix layout built from the real cut
parts, with a train you drive round it. The cars' bogies follow the track, so
their swing-out on curves and their tilt on the grades are true to scale. The
page warns when a car touches or comes close to any part of the layout.

## Running it

From the repository root, with the Docker container up (`docker compose up`):

```bash
scripts/hexmo-drive
```

Then open `http://<this machine's name>:4456/`; the script prints the address.
The first run exports every layout, which takes a few minutes. After that the
script only serves the files, so start-up is instant. Ctrl+C stops it.

After a change to the generators or the ring presets, re-export:

```bash
scripts/hexmo-drive --all                        # every layout
scripts/hexmo-drive N250-ground-x2 HO-ground-x2  # just these
```

`PORT=8080 scripts/hexmo-drive` serves on another port. The export runs in the
container (it needs the optional `step` dependency, build123d, which the
image installs). The web server runs on the host and listens on every
interface, so other machines on the network can open the page.

## Layouts

| Layout | What it is |
|---|---|
| `N250`, `HO` | One helix ring, with 1.5 m staging tracks added off the entry's two dead ends (upper line and lower level). |
| `N250-ground`, `HO-ground` | The same, opened up for scenery (`--lower_ground`). |
| `…-x2` (e.g. `N250-ground-x2`) | Two rings joined entry rectangle to entry rectangle, the second turned 180°. With every turnout on "through" this is one continuous loop: down one helix, along the lower level, up the other and back along the upper level. |

Pick a layout from the menu at the top of the page, or with `?layout=HO-ground-x2`
in the address.

## Driving

| Control | Does |
|---|---|
| **W** / **↑** | Throttle up (forward) |
| **S** / **↓** | Throttle down, then reverse |
| **Space** | Stop |
| **C** | Next camera: chase, cab, orbit |
| **1–4** or click a post | Throw a turnout (not while the train is on it) |
| Drag | Look around: swing the chase camera, turn your head in the cab, rotate in orbit |
| Wheel | Zoom (chase and orbit) |
| Double-click | Reset the chase or cab view |

Full throttle is 100 scale km/h. A turnout set to "diverging" sends the train
round its helix's reversing loop. Approaching a turnout from one of its two
roads (trailing), the train runs through it and sets it to match, like spring
points.

## Clearance warnings

Every frame, each car body is tested against every part of the layout except
the track strips it rides on, and the gap between them is measured. The panel
shows **Clear**, the gap when a car is within the alarm distance ("autorack 1
is 1.6 mm from A M6 deck"), or **touches**. It also keeps a list of every part
touched or come close to.

While the alarm is on, what set it off is highlighted, amber when within the
alarm distance and red when touching, and pulsing:

- **the car**;
- **the part**, drawn over the layout;
- **the spot**: a ball on the part where the car comes nearest, with a line to
  the car. It shows through walls and decks.

If several cars are close to different parts, each is shown.

- **Alarm within … mm** sets the alarm distance (0–30 mm, default 2). `?margin=5`
  in the address sets it too. Changing it clears the list.
- **Stop the train on an alarm** (on by default) stops the train the moment a
  car first comes within the alarm distance. While the alarm stays on you can
  drive on through or back out without it stopping again. It re-arms once every
  car is clear.

Both settings are remembered in this browser.

The model is the layout **as built**. A deck slot that runs out at a module
edge is cut with a narrow strip of deck left across its mouth, over the wall,
to hold the deck in one piece; you cut that strip away once the deck is in
place. The preview's decks have those strips removed, where the cut sheets and
the STEP export keep them.

## How it works

- `boxes/generators/_hexmo_drive.py` exports each layout:
  - `<layout>.glb`: the parts, a binary glTF;
  - `<layout>.track.json`: the track as a graph of centreline polylines, joined at module edges, riser hand-overs and turnouts;
  - `layouts.json`: the list for the menu.

  These generated files are ignored by git.
- `layout.js` merges the model at load: one mesh per colour to draw (the
  export has one mesh per face of every part, tens of thousands of draw calls
  otherwise) and one shape per part for the clearance tests.
- `track.js` runs the train on the graph; `clearance.js` does the collision
  tests (three-mesh-bvh); `index.html` is the page. three.js and three-mesh-bvh
  load from a CDN, so the page needs internet access the first time.
