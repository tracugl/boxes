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
curl "http://localhost:4455/HexagonBox?render=1&top=closed&bottom=spoke"
```

Replace `HexagonBox` with any generator class name. `render=1` triggers SVG output; omitting it returns the HTML form page.

### Rebuilding the image

When the image needs a full rebuild (e.g. after changing `requirements.txt` or `scripts/Dockerfile`):

```bash
docker compose down -v            # -v removes the anonymous /app/env volume
docker compose build --no-cache
docker compose up
```

The `-v` flag is critical — without it the old venv volume is reused and dependency changes in the new image are silently ignored.
