import * as THREE from 'three'
import type { GraphNode } from '../types/graph'
import type { GraphTheme } from './theme'

// Fog stretches relative to camera distance and graph spread; theme values
// are floors so small graphs keep the static appearance.
export const NEAR_SPREAD = 0.2
export const FAR_SPREAD = 3.0
export const LERP_RATE = 0.08
export const EXTENT_INTERVAL_FRAMES = 10

// Base document-label fade band (world units), scaled by fog growth.
export const LABEL_FADE_START = 200
export const LABEL_FADE_END = 420

export interface GraphExtent {
  centroid: THREE.Vector3
  radius: number
}

function isPositioned(node: GraphNode): boolean {
  return (
    node.x !== undefined &&
    Number.isFinite(node.x) &&
    node.y !== undefined &&
    Number.isFinite(node.y) &&
    node.z !== undefined &&
    Number.isFinite(node.z)
  )
}

// Bounding sphere of all positioned nodes. Returns null when the simulation
// has not placed at least two nodes yet.
export function computeGraphExtent(nodes: GraphNode[]): GraphExtent | null {
  let count = 0
  let cx = 0
  let cy = 0
  let cz = 0
  for (const node of nodes) {
    if (!isPositioned(node)) continue
    cx += node.x as number
    cy += node.y as number
    cz += node.z as number
    count += 1
  }
  if (count < 2) return null
  cx /= count
  cy /= count
  cz /= count
  let radius = 0
  for (const node of nodes) {
    if (!isPositioned(node)) continue
    const dx = (node.x as number) - cx
    const dy = (node.y as number) - cy
    const dz = (node.z as number) - cz
    const dist = Math.sqrt(dx * dx + dy * dy + dz * dz)
    if (dist > radius) radius = dist
  }
  return { centroid: new THREE.Vector3(cx, cy, cz), radius }
}

// Keeps a THREE.Fog aligned with the graph's current spread. Runs an O(n)
// extent pass every EXTENT_INTERVAL_FRAMES frames (and every frame until the
// first successful pass, e.g. before the simulation places nodes), then lerps
// fog.near/fog.far toward targets anchored to the camera position. Returns
// the label fade scale factor S >= 1.
export class DynamicFogController {
  private extent: GraphExtent | null = null
  private frameCount = 0

  update(
    fog: THREE.Fog,
    cameraPosition: THREE.Vector3,
    nodes: GraphNode[],
    theme: GraphTheme,
  ): number {
    this.frameCount += 1
    if (this.extent === null || this.frameCount % EXTENT_INTERVAL_FRAMES === 0) {
      this.extent = computeGraphExtent(nodes)
    }
    let nearTarget = theme.fogNear
    let farTarget = theme.fogFar
    if (this.extent) {
      const camDist = cameraPosition.distanceTo(this.extent.centroid)
      nearTarget = Math.max(nearTarget, camDist + NEAR_SPREAD * this.extent.radius)
      farTarget = Math.max(farTarget, camDist + FAR_SPREAD * this.extent.radius)
    }
    fog.near += (nearTarget - fog.near) * LERP_RATE
    fog.far += (farTarget - fog.far) * LERP_RATE
    return Math.max(1, fog.far / theme.fogFar)
  }
}
