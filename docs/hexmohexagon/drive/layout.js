/*
 * Hexmo Drive: the layout model, baked for speed.
 *
 * The exported glTF holds every part as a node with one mesh per face of the
 * part: tens of thousands of small meshes, each a separate draw call, which
 * makes the frame rate uneven.  At load they are merged twice over:
 *
 * - for drawing, into one mesh per colour (a handful of draw calls);
 * - for the clearance check, into one shape per part, so a hit can still name
 *   the part (see clearance.js).
 *
 * Both are baked into world space (each mesh's placement applied), so the
 * merged meshes need no transform of their own.
 */
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

/**
 * A part's readable name, from its node: the object just under the model's
 * root node (scene → root → part → its meshes).  Not the mesh's own name: a
 * pair's second ring reuses the first ring's meshes, whose names are shared.
 * GLTFLoader turns spaces into underscores and drops ".:/[]" from names.
 * @param {THREE.Object3D} o - A mesh.
 * @param {THREE.Object3D} scene - The loaded glTF scene.
 * @returns {string}
 */
function partName(o, scene) {
  let p = o;
  while (p.parent && p.parent.parent && p.parent.parent !== scene) p = p.parent;
  return (p.name || "part").replace(/_/g, " ");
}

/**
 * A mesh's geometry in world space, positions and normals only, unindexed
 * (so every piece merges with every other, whatever the exporter wrote).
 * @param {THREE.Mesh} mesh
 * @returns {THREE.BufferGeometry}
 */
function worldGeometry(mesh) {
  const source = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", source.getAttribute("position"));
  if (source.getAttribute("normal")) g.setAttribute("normal", source.getAttribute("normal"));
  else g.computeVertexNormals();
  g.applyMatrix4(mesh.matrixWorld);
  return g;
}

/**
 * Merge a loaded glTF scene into a few drawable meshes and one shape per part.
 * @param {THREE.Object3D} scene - The glTF scene (not added to the page).
 * @returns {{group: THREE.Group, parts: {name: string, geometry: THREE.BufferGeometry}[]}}
 *          `group`: the meshes to draw; `parts`: world-space shapes by name.
 */
export function bakeLayout(scene) {
  scene.updateMatrixWorld(true);
  const byColour = new Map();
  const byPart = new Map();
  scene.traverse((o) => {
    if (!o.isMesh) return;
    const g = worldGeometry(o);
    const colour = o.material.color.getHex();
    if (!byColour.has(colour)) byColour.set(colour, []);
    byColour.get(colour).push(g);
    const name = partName(o, scene);
    if (!byPart.has(name)) byPart.set(name, []);
    byPart.get(name).push(g);
  });
  const group = new THREE.Group();
  for (const [colour, list] of byColour) {
    // Matte wood, lit on both sides.  The exported materials give only a
    // colour, and glTF then defaults to fully metallic, which renders near
    // black without reflections to show.
    const material = new THREE.MeshStandardMaterial({
      color: colour, metalness: 0, roughness: 0.85, side: THREE.DoubleSide,
    });
    group.add(new THREE.Mesh(mergeGeometries(list), material));
  }
  const parts = [...byPart].map(([name, list]) => ({ name, geometry: mergeGeometries(list) }));
  return { group, parts };
}
