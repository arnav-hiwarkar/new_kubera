import * as THREE from 'three'
import type { GraphNode } from '../types/graph'

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
