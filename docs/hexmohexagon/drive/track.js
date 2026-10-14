/*
 * Hexmo Drive: the track graph and the train that runs on it.
 *
 * The graph comes from <layout>.track.json (written by
 * boxes/generators/_hexmo_drive.py): edges are rail-top centreline polylines
 * (mm, z up); nodes are where they meet, with the pairs of edge ends a train
 * may pass between.  Here everything is converted to the scene's frame
 * (metres, y up, as the glTF model is).
 *
 * A train's position is a *trail*: the edges it occupies, oldest first, each
 * with the direction it is travelled in, and the head somewhere along the
 * last one.  Moving forward appends edges at the head (a facing turnout
 * follows its setting); backing up drops them at the head and adds them at
 * the tail.  Each vehicle's two bogie points are found by walking back along
 * the trail, so bodies cut across curves (swing-out) and tilt on grades as
 * the real ones do.
 */
import * as THREE from "three";

/**
 * Track-file point (mm, z up) to scene point (m, y up).  The glTF model is
 * the same parts turned -90° about x, which maps (x, y, z) to (x, z, -y).
 * @param {number[]} p - [x, y, z] in mm.
 * @returns {THREE.Vector3}
 */
export const toScene = (p) => new THREE.Vector3(p[0] / 1000, p[2] / 1000, -p[1] / 1000);

/**
 * Wrap the exported graph with scene-space polylines, cumulative lengths and
 * turnout settings.
 * @param {object} raw - The parsed track.json.
 * @returns {object} { edges, nodes, scale, onTurnoutChange }
 */
export function buildGraph(raw) {
  const edges = raw.edges.map((e) => {
    const pts = e.pts.map(toScene);
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
    return { ...e, pts, cum, length: cum[cum.length - 1] };
  });
  const nodes = raw.nodes.map((n) => ({ ...n, pos: toScene(n.pos), state: 0 }));
  // Each turnout's toe (the end with two ways on) and those two ways,
  // straightest first: state 0 = through road, 1 = diverging.
  for (const n of nodes) {
    if (!n.turnout) continue;
    for (const end of n.ends) {
      const ways = linkedEnds(n, end);
      if (ways.length < 2) continue;
      const out = leaving(edges, end);
      ways.sort((a, b) => leaving(edges, a).dot(out) - leaving(edges, b).dot(out));
      n.toe = end;
      n.ways = ways;
    }
  }
  return { edges, nodes, scale: raw.scale, onTurnoutChange: () => {} };
}

/**
 * The [edge, end] pairs a train may pass to from [edge, end] at node n.
 * @param {object} n - A node.
 * @param {number[]} param1 - [edge, end] arriving at the node.
 * @returns {number[][]}
 */
export function linkedEnds(n, [e, end]) {
  const out = [];
  for (const [a, b] of n.links) {
    if (a[0] === e && a[1] === end) out.push(b);
    else if (b[0] === e && b[1] === end) out.push(a);
  }
  return out;
}

/**
 * Unit plan direction leaving a node along edge e from its end.
 * @param {object[]} edges - The graph's edges.
 * @param {number[]} param1 - [edge, end].
 * @returns {THREE.Vector3} horizontal unit vector.
 */
export function leaving(edges, [e, end]) {
  const p = edges[e].pts;
  const a = end === 0 ? p[0] : p[p.length - 1];
  const b = end === 0 ? p[Math.min(3, p.length - 1)] : p[Math.max(0, p.length - 4)];
  return new THREE.Vector3(b.x - a.x, 0, b.z - a.z).normalize();
}

/**
 * Point at distance s along an edge (clamped to it), by binary search of the
 * cumulative lengths and interpolation within the sample.
 * @param {object} edge
 * @param {number} s - metres from the edge's start.
 * @returns {THREE.Vector3}
 */
export function pointOnEdge(edge, s) {
  s = Math.max(0, Math.min(edge.length, s));
  let lo = 0;
  let hi = edge.cum.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (edge.cum[mid] <= s) lo = mid;
    else hi = mid;
  }
  const span = edge.cum[hi] - edge.cum[lo] || 1;
  return edge.pts[lo].clone().lerp(edge.pts[hi], (s - edge.cum[lo]) / span);
}

/*
 * A trail element is { e, dir }: edge e travelled with dir +1 (start → end)
 * or -1.  Distances along an element run from where it is entered.
 */

/** The node an element is entered at ("in") or left at ("out"). */
const nodeAt = (G, el, which) => {
  const e = G.edges[el.e];
  const entered = el.dir > 0 ? e.from : e.to;
  return which === "in" ? entered : el.dir > 0 ? e.to : e.from;
};

/** Scene point s metres into a trail element. */
const pointOnEl = (G, el, s) => {
  const e = G.edges[el.e];
  return pointOnEdge(e, el.dir > 0 ? s : e.length - s);
};

/**
 * The element a train runs onto when leaving `el` forwards, or null at a dead
 * end.  A facing turnout follows its setting; a trailing one is run through
 * and set to match (like spring points), and the graph's onTurnoutChange is
 * told which turnout changed.
 * @param {object} G - The graph.
 * @param {object} el - The element being left.
 * @param {boolean} [peek] - Look only: don't change a turnout's setting.
 * @returns {object|null}
 */
export function nextEl(G, el, peek = false) {
  const node = G.nodes[nodeAt(G, el, "out")];
  const end = [el.e, el.dir > 0 ? 1 : 0];
  let ways = linkedEnds(node, end);
  if (!ways.length) return null;
  if (ways.length > 1) ways = [node.ways[node.state]];
  if (!peek && node.ways && !(node.toe[0] === end[0] && node.toe[1] === end[1])) {
    // Trailing through the turnout from one of its roads: set it to match.
    const k = node.ways.findIndex(([a, b]) => a === end[0] && b === end[1]);
    if (k >= 0 && node.state !== k) {
      node.state = k;
      G.onTurnoutChange(node);
    }
  }
  const [e2, end2] = ways[0];
  return { e: e2, dir: end2 === 0 ? 1 : -1 };
}

/** The element behind `el`: the one a train backing out of it runs onto. */
function prevEl(G, el) {
  const back = nextEl(G, { e: el.e, dir: -el.dir });
  return back && { e: back.e, dir: -back.dir };
}

// Spare trail kept behind the tail (m), so a short reverse needs no lookup.
const TRAIL_SPARE = 0.05;

/**
 * A train: vehicles hanging back from the head along a trail of elements.
 */
export class Train {
  /**
   * @param {object} G - The graph.
   * @param {object[]} consist - Vehicles, front first, each with `length`.
   * @param {number} gap - Coupler gap between vehicles (m).
   * @param {number} startEdge - Edge the head starts on, facing its end.
   * @param {number} startS - Head's distance along it (m).
   */
  constructor(G, consist, gap, startEdge, startS) {
    this.G = G;
    this.consist = consist;
    this.gap = gap;
    this.length = consist.reduce((t, v) => t + v.length + gap, 0);
    this.trail = [{ e: startEdge, dir: 1 }];
    this.head = startS;
    this.speed = 0;
    this.extendBack();
  }

  /** Total trail length behind the head (m). */
  behind() {
    let total = this.head;
    for (let i = this.trail.length - 2; i >= 0; i--) total += this.G.edges[this.trail[i].e].length;
    return total;
  }

  /**
   * Make the trail reach the train's length behind the head.
   * @returns {boolean} false when the tail is at a dead end.
   */
  extendBack() {
    let behind = this.behind();
    while (behind < this.length + TRAIL_SPARE) {
      const p = prevEl(this.G, this.trail[0]);
      if (!p) return behind >= this.length;
      this.trail.unshift(p);
      behind += this.G.edges[p.e].length;
    }
    return true;
  }

  /** Drop trail elements wholly behind the train. */
  trim() {
    let behind = this.head;
    let i = this.trail.length - 2;
    while (i >= 0 && behind < this.length + TRAIL_SPARE) behind += this.G.edges[this.trail[i--].e].length;
    if (i > 0) this.trail.splice(0, i);
  }

  /**
   * Move the head by d metres (negative backs the train up).
   * @param {number} d
   * @returns {boolean} false when it stopped at a dead end.
   */
  move(d) {
    const G = this.G;
    if (d >= 0) {
      this.head += d;
      for (;;) {
        const cur = this.trail[this.trail.length - 1];
        const len = G.edges[cur.e].length;
        if (this.head <= len) break;
        const nxt = nextEl(G, cur);
        if (!nxt) {
          this.head = len;
          return false;
        }
        this.head -= len;
        this.trail.push(nxt);
      }
      this.trim();
      return true;
    }
    this.head += d;
    while (this.head < 0 && this.trail.length > 1) {
      this.trail.pop();
      this.head += G.edges[this.trail[this.trail.length - 1].e].length;
    }
    if (this.head < 0 || !this.extendBack()) {
      // The tail reached a dead end: undo the move.
      this.move(-d);
      return false;
    }
    return true;
  }

  /** Scene point `back` metres behind the head, along the trail. */
  pointBehind(back) {
    let s = this.head - back;
    let i = this.trail.length - 1;
    while (s < 0 && i > 0) s += this.G.edges[this.trail[--i].e].length;
    return pointOnEl(this.G, this.trail[i], Math.max(0, s));
  }

  /** Scene point `ahead` metres in front of the head, following the turnouts. */
  pointAhead(ahead) {
    let el = this.trail[this.trail.length - 1];
    let s = this.head + ahead;
    for (let k = 0; k < 20; k++) {
      const len = this.G.edges[el.e].length;
      if (s <= len) break;
      const nxt = nextEl(this.G, el, true);
      if (!nxt) {
        s = len;
        break;
      }
      s -= len;
      el = nxt;
    }
    return pointOnEl(this.G, el, s);
  }

  /**
   * Whether node n lies under the train: between its front and its back.
   * The node just ahead of the head (where the train is about to run) and
   * the trail kept spare behind the tail don't count, so a turnout can be
   * thrown right up until the train reaches it.
   * @param {object} n - A node of the graph.
   * @returns {boolean}
   */
  occupies(n) {
    const k = this.G.nodes.indexOf(n);
    // Distance back from the head to where each trail element was entered.
    let back = this.head;
    for (let i = this.trail.length - 1; i >= 0 && back <= this.length; i--) {
      if (nodeAt(this.G, this.trail[i], "in") === k) return true;
      if (i > 0) back += this.G.edges[this.trail[i - 1].e].length;
    }
    return false;
  }
}
