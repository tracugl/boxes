"""Settings for the N-scale helix ring, as used by the 3D (STEP) export.

The helix ring is six modules round a centre, M1–M5 trapezoids and M6 a full
hexagon, plus a HexmoRectangle at M6 edge 1 carrying the turnouts.  Trains
run edge 3 → edge 5 through every module, so M(n)'s edge 5 meets M(n+1)'s edge
3, and M6's edge 5 meets M1's edge 3.  The spur descends a full turn from M6's
deck to the lower level, which leaves under M6's deck at edge 1.  The README's
"Riser boards" section explains the numbers; these are the same settings, at
h=80.

Each entry is the generator's own command-line options.

The module name starts with an underscore, so generator discovery skips it.
"""
from __future__ import annotations

# Shared by every N ring module.
_N_COMMON = ["--radius=220", "--thickness=3", "--h=80", "--edge_width=22", "--spoke_width=60",
             "--bottom=spoke", "--support_length=55", "--track_lead_in=26", "--track_width=17",
             "--under_track_width=35"]
_N_TRAPEZOID = _N_COMMON + ["--trapezoid=1", "--support_edges=4@132,4@30/90"]
# The spur's height at each joint: M6/M1, M1/M2 … M5/M6.
_N_JOINTS = [74, 66.1, 58.5, 50.8, 43.2, 35.6]


def _n_trapezoid(k):
    """Settings for ring module M(k), k = 2…5 (the spur 35 mm in throughout)."""
    a, b = _N_JOINTS[k - 1], _N_JOINTS[k]
    return _N_TRAPEZOID + [
        "--track_routes=3:17.5-5:17.5,3:-35-5:-35",
        f"--track_openings=3:-35:{a:g}:35,5:35:{b:g}:35",
        "--deck_slots=3:-35-5:-35/35",
        f"--risers=3:-35-5:-35~{a:g}..{b:g}/35"]


HELIX_RING_N = {
    "M1": _N_TRAPEZOID + [
        "--track_routes=3:17.5-5:17.5,3:-17.5-5:-35",
        "--track_openings=3:-17.5:74:35,5:35:66.1:35",
        "--deck_slots=3:-17.5-5:-35/35",
        "--risers=3:-17.5-5:-35~74..66.1/35"],
    "M2": _n_trapezoid(2),
    "M3": _n_trapezoid(3),
    "M4": _n_trapezoid(4),
    "M5": _n_trapezoid(5),
    "M6": _N_COMMON + [
        "--support_edges=2,4,6",
        "--track_routes=1:-35-5:-17.5,3:-17.5-1:-35,1:0-5:17.5",
        "--under_track_edges=1", "--under_track_height=27.8",
        "--track_openings=5:17.5:74:35,3:-35:35.6:35",
        "--deck_slots=1:0-5:17.5@169../35,3:35-1:0@..186/35",
        "--risers=1:0-5:17.5@169..~77..74/35,3:35-1:0@..186~35.6..31/35,"
        "3:35-1:0@186..~31..27.8/35"],
}

# The entry rectangle at M6 edge 1: two Peco medium turnouts split the entry
# line into M6's three deck tracks; the lower level passes underneath.
HELIX_ENTRY_N = ["--radius=220", "--thickness=3", "--h=80", "--num_rows=3", "--num_columns=2",
                 "--track_width=17", "--track_lead_in=26", "--under_track=1",
                 "--under_track_height=27.8", "--under_track_width=35",
                 "--turnouts=10:0:-35,133.7:0:35"]

# The same ring opened up for scenery (--lower_ground): upper ground on the
# deck, lower ground at 27.8 (the lower level's exit height) on the inner side
# of M1–M5, and M6's side walls stepped to meet them.
HELIX_RING_N_GROUND = {name: args + ["--lower_ground=27.8"]
                       for name, args in HELIX_RING_N.items()}

RINGS = {"N": (HELIX_RING_N, HELIX_ENTRY_N),
         "N-ground": (HELIX_RING_N_GROUND, HELIX_ENTRY_N)}
