#!/usr/bin/env bash
# Hexmo sheets: pack Hexmo modules' parts onto laser blanks, one SVG per blank.
#
#   scripts/hexmo-sheets.sh OUTDIR [--sheets=1200x900:2,600x900] [N@]EDIT_URL ...
#
# Each EDIT_URL is a HexmoHexagon / HexmoRectangle edit link (quote it); put
# N@ in front for N of that module, packed together.  The default blanks are
# a 2400 x 1200 sheet cut at 900: two 1200 x 900 and one 600 x 900, for a
# 1300 x 900 laser bed.  --sheet_spacing and --sheet_margin (mm) set the gaps.
# Writes OUTDIR/NN-<generator>-blank-KK-<w>x<h>.svg and prints how many full
# sheets to buy.  OUTDIR must be inside the repository (the container sees it
# as /app); it runs in the Docker container, as you, so the files are yours.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -lt 2 ]]; then
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
docker compose exec -T -u "$(id -u):$(id -g)" web \
  env PYTHONPATH=/app /app/env/bin/python -W ignore -m boxes.generators._hexmo_nest "$@"
