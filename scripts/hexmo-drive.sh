#!/usr/bin/env bash
# Hexmo Drive: export helix-ring layouts and serve the drivable 3D preview.
#
#   scripts/hexmo-drive.sh                  serve (exports every layout first if none are)
#   scripts/hexmo-drive.sh LAYOUT ...       re-export those layouts, then serve
#   scripts/hexmo-drive.sh --all            re-export every layout, then serve
#
# Layouts: N250-dogbone, N250-dual-dogbone, HO-dual-dogbone and HO-ground-HO (one
# ring opened up for scenery, one plain); and the helix rings N250,
# N250-ground, HO, HO-ground, each alone or as a joined pair (append -x2,
# e.g. HO-ground-x2).  The export runs in the Docker container
# (it needs build123d); the web server runs here, on every interface, so
# other machines on the network can open it too.  PORT overrides 4456.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-4456}"
DIR=docs/hexmohexagon/drive

if [[ $# -gt 0 || ! -f "$DIR/layouts.json" ]]; then
  layouts="${*:---all}"
  docker compose exec -T web sh -c \
    "cd /app && PYTHONPATH=/app /app/env/bin/python -W ignore -m boxes.generators._hexmo_drive $layouts"
fi

echo "Hexmo Drive: http://$(hostname):$PORT/  (Ctrl+C to stop)"
# Python's static file server, on every interface, telling browsers to check
# for a newer copy of every file each time (Cache-Control: no-cache; an
# unchanged file comes back as a quick "not modified").  Without it a browser
# may reuse an old export's track or model after a re-export.
exec python3 - "$PORT" "$DIR" <<'PY'
import functools
import http.server
import sys


class NoCache(http.server.SimpleHTTPRequestHandler):
    """Serve files as usual, marked to be revalidated on every use."""

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


port, root = int(sys.argv[1]), sys.argv[2]
handler = functools.partial(NoCache, directory=root)
http.server.ThreadingHTTPServer(("", port), handler).serve_forever()
PY
