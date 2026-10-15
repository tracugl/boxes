"""Tests for the Hexmo Drive export (boxes/generators/_hexmo_drive.py).

The drivable 3D preview runs a train on a track graph built from the helix
rings' track pieces.  These check the graph: pieces meet at module edges,
turnouts are found at the entry, a single ring has staging at its two dead
ends, and a pair of rings joined entry to entry closes into loops with no
dead ends at all.  The as-built decks (slot mouths opened) need build123d
and are skipped without it.

These tests avoid lxml, so they run in the Docker image.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from hexmo_testutil import IGNORE_CORE_MATMUL

pytestmark = IGNORE_CORE_MATMUL

from boxes.generators import _hexmo_drive as D


@pytest.fixture(scope="module")
def graphs():
    """Track graphs for the layouts the tests walk, built once."""
    return {name: D.layout_track(name)
            for name in ("N250", "N250-x2", "HO-ground-x2", "HO-ground-HO")}


def dead_ends(track):
    return [n for n in track["nodes"] if len(n["ends"]) == 1]


def turnouts(track):
    return [n for n in track["nodes"] if n["turnout"]]


def drive(track, edge, distance):
    """Walk the graph from the start of ``edge``, turnouts set straight on.

    @returns The labels of the edges passed, in order (stops at a dead end).
    """
    edges, nodes = track["edges"], track["nodes"]
    e, d, run, seen = edge, 1, 0.0, []
    while run < distance:
        seen.append(edges[e]["label"])
        pts = edges[e]["pts"]
        run += sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        node = nodes[edges[e]["to"] if d > 0 else edges[e]["from"]]
        here = [e, 1 if d > 0 else 0]
        ways = [b if a == here else a for a, b in node["links"] if here in (a, b)]
        if not ways:
            break
        # Straight on: the way leaving most nearly opposite to how we came in.
        came = D._leaving(pts, here[1])
        e, end = min(ways, key=lambda w: sum(a * b for a, b in zip(D._leaving(edges[w[0]]["pts"], w[1]), came)))
        d = 1 if end == 0 else -1
    return seen


class TestLayouts:

    def test_every_ring_alone_and_paired(self) -> None:
        names = D.layouts()
        for ring in ("N250", "N250-ground", "HO", "HO-ground"):
            assert ring in names and f"{ring}-x2" in names

    def test_unknown_layout_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown layout"):
            D.parse_layout("N220-x2")


class TestGraphBuilding:
    """The graph rules on a small made-up track: a through road and a leg
    leaving it part-way along (a turnout)."""

    THROUGH = {"label": "through", "pts": [[x, 0.0, 10.0] for x in range(0, 101, 5)]}
    LEG = {"label": "leg", "pts": [[50.0 + 5 * k, 1.5 * k * k / 10, 10.0] for k in range(11)]}

    def test_the_through_road_splits_at_the_toe(self) -> None:
        lines = D.split_at_touches([self.THROUGH, self.LEG])
        through = [ln for ln in lines if ln["label"] == "through"]
        assert len(through) == 2
        assert through[0]["pts"][-1] == through[1]["pts"][0] == [50.0, 0.0, 10.0]

    def test_a_turnout_links_straight_on_never_back_through_the_frog(self) -> None:
        g = D.build_graph(D.split_at_touches([self.THROUGH, self.LEG]))
        toe = next(n for n in g["nodes"] if n["pos"] == [50.0, 0.0, 10.0])
        assert toe["turnout"]
        # The edges meeting at the toe: the through road's two halves and the leg.
        name = {}
        for e, end in toe["ends"]:
            label = g["edges"][e]["label"]
            name[(e, end)] = "leg" if label == "leg" else ("approach" if end == 1 else "beyond")
        links = {frozenset((name[tuple(a)], name[tuple(b)])) for a, b in toe["links"]}
        # From the approach to either road, never from one road to the other.
        assert links == {frozenset(("approach", "beyond")), frozenset(("approach", "leg"))}

    def test_ends_apart_in_height_do_not_join(self) -> None:
        upper = {"label": "upper", "pts": [[0.0, 0.0, 80.0], [10.0, 0.0, 80.0]]}
        lower = {"label": "lower", "pts": [[10.0, 0.0, 30.0], [20.0, 0.0, 30.0]]}
        g = D.build_graph([upper, lower])
        assert len(g["nodes"]) == 4


class TestSingleRing:

    def test_two_turnouts_at_the_entry(self, graphs) -> None:
        assert len(turnouts(graphs["N250"])) == 2

    def test_only_the_staging_tracks_end(self, graphs) -> None:
        # The staging tracks' far ends: the upper line and the lower level.
        track = graphs["N250"]
        ends = dead_ends(track)
        assert len(ends) == 2
        for n in ends:
            assert track["edges"][n["ends"][0][0]]["staging"]

    def test_staging_runs_into_the_layout(self, graphs) -> None:
        track = graphs["N250"]
        staging = next(e for e in track["edges"] if e["staging"] and "straight" in e["label"])
        passed = drive(track, staging["id"], 1.6e3)
        assert passed[1].startswith("entry straight")

    def test_scale(self, graphs) -> None:
        assert graphs["N250"]["scale"] == 160
        assert graphs["HO-ground-x2"]["scale"] == 87


class TestPair:
    """Two rings joined entry to entry: one continuous loop through both."""

    @pytest.mark.parametrize("name", ["N250-x2", "HO-ground-x2", "HO-ground-HO"])
    def test_no_dead_ends_and_four_turnouts(self, graphs, name) -> None:
        assert dead_ends(graphs[name]) == []
        assert len(turnouts(graphs[name])) == 4

    @pytest.mark.parametrize("name", ["N250-x2", "HO-ground-x2", "HO-ground-HO"])
    def test_down_one_helix_and_up_the_other(self, graphs, name) -> None:
        # From A's spur, straight on throughout: down A, along the lower level
        # into B, up B, back along the upper level into A and round again.
        track = graphs[name]
        start = next(e for e in track["edges"] if e["label"].startswith("A M3 3:-"))
        # About one and a half laps: 12 m in N, longer in proportion in HO.
        passed = drive(track, start["id"], 12e3 * 160 / track["scale"])
        order = ["A entry lower level", "B entry lower level", "B M3 ", "B entry straight",
                 "A entry straight", "A M3 "]
        at = 0
        for label in passed:
            if at < len(order) and label.startswith(order[at]):
                at += 1
        assert at == len(order), passed

    def test_one_ring_ground_one_plain(self) -> None:
        # HO-ground-HO: ring A opened up for scenery, ring B the plain ring.
        from boxes.generators._hexmo_helix_ring import RINGS
        first, second = D._pair_rings(D.parse_layout("HO-ground-HO")[0])
        assert (first, second) == ("HO-ground", "HO")
        assert any(a.startswith("--lower_ground=") for a in RINGS[first][0]["M1"])
        assert not any(a.startswith("--lower_ground=") for a in RINGS[second][0]["M1"])

    def test_the_second_ring_is_the_first_turned(self, graphs) -> None:
        track = graphs["N250-x2"]
        lines, far_y = D.ring_lines("N250")
        a = next(ln for ln in lines if ln["label"] == "M3 3:22.5-5:22.5@0..415")
        b = next(e for e in track["edges"] if e["label"] == "B M3 3:22.5-5:22.5@0..415")
        x, y, z = a["pts"][0]
        assert b["pts"][0] == pytest.approx([-x, 2 * far_y - y, z], abs=0.01)


@pytest.fixture(scope="module")
def track():
    """The N dogbone's graph, built once."""
    return D.layout_track("N250-dogbone")


class TestDogbone:
    """A double-track main with a single-track loop round each ring and a Peco
    crossover on each entry rectangle; deck only."""

    def test_listed_first(self) -> None:
        assert D.layouts()[0] == "N250-dogbone"

    def test_every_piece_joins(self, track) -> None:
        assert dead_ends(track) == []

    def test_the_only_turnouts_are_the_crossovers(self, track) -> None:
        # Both ends of each entry's crossover; none on the curving modules.
        found = turnouts(track)
        assert len(found) == 4
        for n in found:
            assert all(track["edges"][e]["label"].split()[1] == "entry" for e, _ in n["ends"])

    def test_one_track_round_each_ring(self, track) -> None:
        labels = {e["label"].split("@")[0] for e in track["edges"]}
        for ring in "AB":
            for k in range(1, 6):
                # Down the middle of the trapezoids, and only there.
                assert f"{ring} M{k} 3:0-5:0" in labels
                assert not any(lb.startswith(f"{ring} M{k} ") and lb != f"{ring} M{k} 3:0-5:0"
                               for lb in labels)

    def test_continuous_running(self, track) -> None:
        # Straight on throughout: round ring A, along one main track into
        # ring B, round it and back along the other, and round again.
        start = next(e for e in track["edges"] if e["label"].startswith("A M3 "))
        passed = drive(track, start["id"], 9000)
        order = ["A M6 3:0-1:-20", "A entry straight", "B M6 1:-20-5:0", "B M3 ",
                 "B M6 3:0-1:-20", "B entry straight", "A M6 1:-20-5:0", "A M3 "]
        at = 0
        for label in passed:
            if at < len(order) and label.startswith(order[at]):
                at += 1
        assert at == len(order), passed

    def test_no_staging(self, track) -> None:
        assert not any(e["staging"] for e in track["edges"])


@pytest.fixture(scope="module")
def dual():
    """The N dual-ring dogbone's graph, built once."""
    return D.layout_track("N250-dual-dogbone")


class TestDualDogbone:
    """Double track round each ring; on each entry, Peco turnouts split the
    main's two tracks into four, one pair per loop, interleaved with a
    crossover; the two entries' crossovers go opposite ways."""

    def test_every_piece_joins(self, dual) -> None:
        assert dead_ends(dual) == []

    def test_the_only_turnouts_are_on_the_entries(self, dual) -> None:
        # Two splitting turnouts on each entry, and both ends of its crossover.
        found = turnouts(dual)
        assert len(found) == 8
        for n in found:
            assert all(dual["edges"][e]["label"].split()[1] == "entry" for e, _ in n["ends"])

    def test_the_crossovers_are_opposite_hands(self, dual) -> None:
        # In plan (the rings in line along y), one crossover's diagonal runs
        # from −x to +x as y grows and the other from +x to −x: mirror
        # images, not one turned round (which would be the same hand).
        slopes = []
        for ring in "AB":
            leg = next(e for e in dual["edges"] if e["label"] == f"{ring} entry crossover 1")
            (x0, y0, _), (x1, y1, _) = leg["pts"][0], leg["pts"][-1]
            slopes.append((x1 - x0) / (y1 - y0))
        assert slopes[0] * slopes[1] < 0

    def test_both_tracks_round_both_rings(self, dual) -> None:
        labels = {e["label"].split("@")[0] for e in dual["edges"]}
        for ring in "AB":
            for k in range(1, 6):
                assert f"{ring} M{k} 3:25-5:25" in labels
                assert f"{ring} M{k} 3:-15-5:-15" in labels

    def test_through_takes_the_inner_loops(self, dual) -> None:
        start = next(e for e in dual["edges"] if e["label"].startswith("A M3 3:-15"))
        passed = drive(dual, start["id"], 9000)
        assert any(label.startswith("B M3 3:-15") for label in passed), passed
        assert not any("3:25-5:25" in label for label in passed)


@pytest.fixture(scope="module")
def ho_dual():
    """The HO dual-ring dogbone's graph, built once."""
    return D.layout_track("HO-dual-dogbone")


def tightest_radius(pts, step=6):
    """The smallest radius (mm, in plan) through points ``step`` samples apart."""
    radii = []
    for i in range(step, len(pts) - step):
        a, b, c = pts[i - step][:2], pts[i][:2], pts[i + step][:2]
        area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
        if area > 1e-6:
            radii.append(math.dist(a, b) * math.dist(b, c) * math.dist(a, c) / (4 * area))
    return min(radii, default=math.inf)


class TestHODualDogbone:
    """The N dual-ring dogbone at HO size: double track 80 mm apart round each
    ring, Peco HO medium turnouts and crossover on each entry."""

    def test_listed(self) -> None:
        assert "HO-dual-dogbone" in D.layouts()

    def test_every_piece_joins(self, ho_dual) -> None:
        assert dead_ends(ho_dual) == []

    def test_the_only_turnouts_are_on_the_entries(self, ho_dual) -> None:
        found = turnouts(ho_dual)
        assert len(found) == 8
        for n in found:
            assert all(ho_dual["edges"][e]["label"].split()[1] == "entry" for e, _ in n["ends"])

    def test_the_crossovers_are_opposite_hands(self, ho_dual) -> None:
        slopes = []
        for ring in "AB":
            leg = next(e for e in ho_dual["edges"] if e["label"] == f"{ring} entry crossover 1")
            (x0, y0, _), (x1, y1, _) = leg["pts"][0], leg["pts"][-1]
            slopes.append((x1 - x0) / (y1 - y0))
        assert slopes[0] * slopes[1] < 0

    def test_both_tracks_round_both_rings(self, ho_dual) -> None:
        labels = {e["label"].split("@")[0] for e in ho_dual["edges"]}
        for ring in "AB":
            for k in range(1, 6):
                assert f"{ring} M{k} 3:40-5:40" in labels
                assert f"{ring} M{k} 3:-40-5:-40" in labels

    def test_through_takes_the_inner_loops(self, ho_dual) -> None:
        start = next(e for e in ho_dual["edges"] if e["label"].startswith("A M3 3:-40"))
        passed = drive(ho_dual, start["id"], 18000)
        assert any(label.startswith("B M3 3:-40") for label in passed), passed
        assert not any("3:40-5:40" in label for label in passed)

    def test_ring_radii_and_legs(self, ho_dual) -> None:
        # The ring at R740 and R660; M6's legs no tighter than about R495.
        edges = {e["label"].split("@")[0]: e for e in ho_dual["edges"]}
        assert tightest_radius(edges["A M3 3:40-5:40"]["pts"]) == pytest.approx(740, abs=10)
        assert tightest_radius(edges["A M3 3:-40-5:-40"]["pts"]) == pytest.approx(660, abs=10)
        legs = [e for label, e in edges.items() if label.startswith("A M6 ")]
        assert len(legs) == 4
        assert min(tightest_radius(e["pts"]) for e in legs) > 490


class TestAsBuiltDecks:
    """The strip left across a deck slot's mouth is cut away in the model."""

    @pytest.mark.parametrize("ring, module", [("N250", "M2"), ("HO-ground", "M6")])
    def test_no_deck_across_a_slot_mouth(self, ring, module) -> None:
        bd = pytest.importorskip("build123d")
        from boxes.generators import _hexmo_step as S
        from boxes.generators._hexmo_helix_ring import RINGS
        from boxes.generators._hexmo_risers import point_at
        from boxes.generators.hexmohexagon import HexmoHexagon

        def deck_and_pieces(cut):
            box = HexmoHexagon()
            box.parseArgs(RINGS[ring][0][module])
            cutters = D._mouth_cutters(bd, box) if cut else []
            pieces = S.hexmo_pieces(box)
            parts = D._as_built(S.module_parts(box, "hexmo", "none", "exact"), cutters)
            return (next(p.solid for p in parts if p.name == "deck"), pieces,
                    S._frame(box), box.train_envelope)

        for cut, expect_deck in ((False, True), (True, False)):
            deck, pieces, (_, l, t), envelope = deck_and_pieces(cut)
            mouths = 0
            for piece in pieces:
                if not piece.on_riser:
                    continue
                total = sum(seg.length for seg in piece.segments)
                start, _ = point_at(piece.segments, 0.0)
                for point, height in piece.ends:
                    if height + envelope <= l:
                        continue          # the train passes under the deck here
                    # Half a thickness in from the module edge: over the wall.
                    s = t / 2 if math.dist(point, start) < 1e-6 else total - t / 2
                    (x, y), _ = point_at(piece.segments, s)
                    assert deck.is_inside(bd.Vector(x, y, l + t / 2)) == expect_deck
                    mouths += 1
            assert mouths >= 2
