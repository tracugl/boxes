/*
 * Hexmo Drive: clearance warnings between the train and the layout.
 *
 * Every frame each vehicle's body (a box) is tested against the layout's
 * parts: boards, walls, supports, risers, ground plates.  The track strips it
 * rides on are left out.  A body *touches* a part when the two intersect, and
 * is *close* when the gap between them (the shortest distance from the box
 * to the part's surface) is no more than the margin.  The bodies stand a
 * floor height above the rails, so a margin smaller than that never reaches
 * the riser bed underneath.
 *
 * Testing a box against thousands of triangles is made cheap by a bounding
 * volume hierarchy (three-mesh-bvh): each part's triangles are sorted into a
 * tree of boxes once at load, and a test only descends into the boxes the
 * body overlaps.  A first pass against each part's overall bounding box
 * skips the parts nowhere near.
 */
import * as THREE from "three";
import { MeshBVH } from "three-mesh-bvh";

/** Whether a part is a track strip (the train rides on those). */
const isTrack = (name) => /(^| )track /.test(name);

export class Clearance {
  /**
   * Build the collision trees for a layout's parts.
   * @param {{name: string, geometry: THREE.BufferGeometry}[]} parts - One
   *        world-space shape per part (see layout.js).
   * @param {number} margin - "Close" distance, in scene metres.
   */
  constructor(parts, margin) {
    this.margin = margin;
    this.parts = parts
      .filter((p) => !isTrack(p.name))
      .map((p) => {
        p.geometry.computeBoundingBox();
        return { name: p.name, geometry: p.geometry, tree: new MeshBVH(p.geometry),
                 world: p.geometry.boundingBox };
      });
    this._box = new THREE.Box3();
    this._worldBox = new THREE.Box3();
  }

  /**
   * Test one vehicle body against the layout.
   * @param {THREE.Mesh} body - A box mesh (BoxGeometry), placed this frame.
   * @returns {{level: "clear"|"close"|"touch", part: string|null, shape: object|null,
   *            near: object|null}} the worst part: `shape` with its world-space
   *          `geometry` (for highlighting it), `near` where the two come
   *          nearest (see nearest()).
   */
  check(body) {
    body.updateWorldMatrix(true, false);
    if (!body.geometry.boundingBox) body.geometry.computeBoundingBox();
    this._worldBox.setFromObject(body).expandByScalar(this.margin);
    let best = null;
    for (const p of this.parts) {
      if (!p.world.intersectsBox(this._worldBox)) continue;
      // The parts are in world space, so the body's own matrix takes its
      // box (in the body's frame) into theirs.
      this._box.copy(body.geometry.boundingBox);
      if (p.tree.intersectsBox(this._box, body.matrixWorld)) {
        return { level: "touch", part: p.name, shape: p, near: this.nearest(body, p) };
      }
      // The box grown by the margin is a quick first pass (it reaches a
      // little further at its corners); the measured gap decides.
      if (!p.tree.intersectsBox(this._box.expandByScalar(this.margin), body.matrixWorld)) continue;
      const near = this.nearest(body, p);
      if (near && near.distance <= this.margin && (!best || near.distance < best.near.distance)) {
        best = { shape: p, near };
      }
    }
    return best ? { level: "close", part: best.shape.name, shape: best.shape, near: best.near }
      : { level: "clear", part: null, shape: null, near: null };
  }

  /**
   * Where a body comes nearest a part: the closest pair of points between
   * the body's box and the part's triangles, searched only out to twice the
   * margin (enough for anything that set the alarm off).
   * @param {THREE.Mesh} body - A placed box mesh.
   * @param {object} shape - A part from check().
   * @returns {{onPart: THREE.Vector3, onCar: THREE.Vector3, distance: number}|null}
   *          world points and the gap (scene metres; 0 when they overlap).
   */
  nearest(body, shape) {
    const onPart = {};
    const onCar = {};
    shape.tree.closestPointToGeometry(body.geometry, body.matrixWorld, onPart, onCar,
                                      0, 2 * this.margin + 0.001);
    if (!onPart.point) return null;
    // The part's point is in the part's frame (world); the car's is in the
    // box's own frame, so it is taken to world by the body's matrix.
    return { onPart: onPart.point.clone(), onCar: onCar.point.clone().applyMatrix4(body.matrixWorld),
             distance: onPart.distance };
  }
}
