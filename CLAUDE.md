# Boxes — Claude Instructions

## Repository

This is a personal fork of `florianfesti/boxes`, maintained independently at `https://github.com/tracugl/boxes`.

## Pull Requests

**NEVER open a PR targeting `florianfesti/boxes`.** All PRs must target this repo (`tracugl/boxes`) only.

When creating a PR, always explicitly pass `--repo tracugl/boxes` to the `gh` CLI to prevent accidental upstream targeting:

```bash
gh pr create --repo tracugl/boxes --base master
```

The upstream remote exists solely for fetching changes into this fork. Nothing is ever pushed or PR'd back to it.

## Testing with Docker

The app runs via Docker Compose on port **4455** (mapped from 8000 inside the container).

```bash
docker compose up        # start the server
docker compose down      # stop
```

To smoke-test a generator, hit the render endpoint directly:

```bash
curl "http://localhost:4455/HexagonBox?render=1&top=closed&bottom=spoke&radius=100&thickness=6"
```

Replace `HexagonBox` with any generator class name. `render=1` triggers SVG output; omitting it returns the HTML form page.

**HexagonBox parameter names**: use `radius=...` directly — the generator exposes a single `radius` parameter.

### Measuring SVG panel dimensions

SVG coordinates are in mm (1 viewBox unit = 1 mm). To measure a panel's bounding box, parse path commands properly — naive alternating-x/y splitting breaks on `H` (horizontal) and `V` (vertical) commands:

```python
import re

def parse_path_d(d):
    tokens = re.findall(r'[MLHVCSQTAZmlhvcsqtaz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    coords, cmd, cx, cy = [], 'M', 0.0, 0.0
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t; i += 1; continue
        if cmd in ('M','m'):
            x,y = float(tokens[i]),float(tokens[i+1])
            if cmd=='m': x,y = cx+x,cy+y
            cx,cy = x,y; coords.append((cx,cy)); i+=2; cmd='L' if cmd=='M' else 'l'
        elif cmd in ('L','l'):
            x,y = float(tokens[i]),float(tokens[i+1])
            if cmd=='l': x,y = cx+x,cy+y
            cx,cy = x,y; coords.append((cx,cy)); i+=2
        elif cmd in ('H','h'):
            x=float(tokens[i]); cx=x if cmd=='H' else cx+x; coords.append((cx,cy)); i+=1
        elif cmd in ('V','v'):
            y=float(tokens[i]); cy=y if cmd=='V' else cy+y; coords.append((cx,cy)); i+=1
        elif cmd in ('Z','z'): break
        else: i+=2
    return coords
```

Use the path with the highest point count for panels with finger joints (many small segments = the cut outline).

### `edgeCorner` miter geometry

`edgeCorner(edge1, edge2, angle)` draws:
1. `edge2.startWidth() * tan(angle/2)` forward (step into corner)
2. `corner(angle)` turn
3. `edge1.endWidth() * tan(angle/2)` forward (step out of corner)

For `FingerJointEdge 'Y'` (female): `startWidth() = endWidth() = thickness`, so each step = `thickness * tan(angle/2)`.

At a 60° exterior corner: step = `t * tan(30°)` = `t/√3`.
At a 120° exterior corner: step = `t * tan(60°)` = `t√3`.

The 120° miter (`t√3`) is often too large for trapezoid/half-hex panels — use `t/√3` instead to match the hex-vertex miter size.

### Rebuilding the image

When the image needs a full rebuild (e.g. after changing `requirements.txt` or `scripts/Dockerfile`):

```bash
docker compose down -v            # -v removes the anonymous /app/env volume
docker compose build --no-cache
docker compose up
```

The `-v` flag is critical — without it the old venv volume is reused and dependency changes in the new image are silently ignored.
