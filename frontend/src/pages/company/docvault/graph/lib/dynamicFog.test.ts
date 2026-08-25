import { describe, it, expect } from 'vitest'
import * as THREE from 'three'
import { computeGraphExtent, DynamicFogController } from './dynamicFog'
import { getGraphTheme } from './theme'
import type { GraphNode } from '../types/graph'

function docNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 'doc_1',
    rawId: '1',
    type: 'document',
    name: 'Tax Filing',
    bucketId: 'b1',
    bucketName: 'Finance',
    color: '#38BDF8',
    size: 6,
    ...overrides,
  }
}

describe('computeGraphExtent', () => {
  it('returns null for empty input', () => {
    expect(computeGraphExtent([])).toBeNull()
  })

  it('returns null when fewer than two nodes have positions', () => {
    const nodes = [docNode(), docNode({ id: 'doc_2', rawId: '2' })]
    expect(computeGraphExtent(nodes)).toBeNull()
    const onePositioned = [
      docNode({ x: 0, y: 0, z: 0 }),
      docNode({ id: 'doc_2', rawId: '2' }),
    ]
    expect(computeGraphExtent(onePositioned)).toBeNull()
  })

  it('skips NaN and partially-positioned nodes', () => {
    const nodes = [
      docNode({ id: 'doc_1', rawId: '1', x: 0, y: 0, z: 0 }),
      docNode({
        id: 'doc_2',
        rawId: '2',
        x: Number.NaN,
        y: 5,
        z: 5,
      }),
      docNode({ id: 'doc_3', rawId: '3', x: 10, y: undefined, z: 0 }),
      docNode({ id: 'doc_4', rawId: '4', x: 20, y: 0, z: 0 }),
    ]
    const extent = computeGraphExtent(nodes)
    // Only doc_1 and doc_4 count: centroid (10,0,0), radius 10
    expect(extent).not.toBeNull()
    expect(extent!.centroid.x).toBe(10)
    expect(extent!.centroid.y).toBe(0)
    expect(extent!.centroid.z).toBe(0)
    expect(extent!.radius).toBeCloseTo(10, 6)
  })

  it('computes centroid and max radius for an asymmetric cluster', () => {
    const nodes = [
      docNode({ id: 'doc_1', rawId: '1', x: 0, y: 0, z: 0 }),
      docNode({ id: 'doc_2', rawId: '2', x: 6, y: 0, z: 0 }),
      docNode({ id: 'doc_3', rawId: '3', x: 0, y: 8, z: 0 }),
    ]
    const extent = computeGraphExtent(nodes)!
    expect(extent.centroid.x).toBeCloseTo(2, 6)
    expect(extent.centroid.y).toBeCloseTo(8 / 3, 6)
    expect(extent.radius).toBeGreaterThan(5)
    expect(extent.radius).toBeLessThan(6)
  })
})

function positionedPair(halfSpread: number): GraphNode[] {
  return [
    docNode({ id: 'doc_a', rawId: 'a', x: -halfSpread, y: 0, z: 0 }),
    docNode({ id: 'doc_b', rawId: 'b', x: halfSpread, y: 0, z: 0 }),
  ]
}

const DARK = getGraphTheme('dark')

describe('DynamicFogController', () => {
  it('converges to theme floors for small graphs close to camera', () => {
    const fog = new THREE.Fog('#000000', DARK.fogNear, DARK.fogFar)
    const controller = new DynamicFogController()
    const nodes = positionedPair(5) // radius ~5, camera at origin → camDist 0
    for (let i = 0; i < 300; i++) {
      controller.update(fog, new THREE.Vector3(0, 0, 0), nodes, DARK)
    }
    expect(fog.near).toBeCloseTo(DARK.fogNear, 4)
    expect(fog.far).toBeCloseTo(DARK.fogFar, 4)
  })

  it('scale factor is never below 1', () => {
    const fog = new THREE.Fog('#000000', DARK.fogNear, DARK.fogFar)
    const controller = new DynamicFogController()
    const s = controller.update(
      fog,
      new THREE.Vector3(0, 0, 0),
      positionedPair(5),
      DARK,
    )
    expect(s).toBeGreaterThanOrEqual(1)
  })

  it('stretches fog beyond floors for large graphs viewed from afar', () => {
    const fog = new THREE.Fog('#000000', DARK.fogNear, DARK.fogFar)
    const controller = new DynamicFogController()
    const nodes = positionedPair(500) // radius ~500
    const camPos = new THREE.Vector3(0, 0, 2000) // camDist 2000
    for (let i = 0; i < 300; i++) {
      controller.update(fog, camPos, nodes, DARK)
    }
    // Targets: near = 2000 + 0.2*500 = 2100, far = 2000 + 3*500 = 3500
    expect(fog.near).toBeCloseTo(2100, 0)
    expect(fog.far).toBeCloseTo(3500, 0)
  })

  it('moves monotonically toward its target each frame', () => {
    const fog = new THREE.Fog('#000000', DARK.fogNear, DARK.fogFar)
    const controller = new DynamicFogController()
    const nodes = positionedPair(500)
    const camPos = new THREE.Vector3(0, 0, 2000)
    let previous = fog.far
    for (let i = 0; i < 50; i++) {
      controller.update(fog, camPos, nodes, DARK)
      expect(fog.far).toBeGreaterThanOrEqual(previous)
      expect(fog.far).toBeLessThanOrEqual(3500)
      previous = fog.far
    }
  })

  it('picks up nodes spreading apart without special-casing reloads', () => {
    const fog = new THREE.Fog('#000000', DARK.fogNear, DARK.fogFar)
    const controller = new DynamicFogController()
    const nodes = positionedPair(5)
    const camPos = new THREE.Vector3(0, 0, 350)
    for (let i = 0; i < 100; i++) {
      controller.update(fog, camPos, nodes, DARK)
    }
    expect(fog.far).toBeCloseTo(DARK.fogFar, 2)
    // Simulation spreads the pair apart to ±500
    nodes[0].x = -500
    nodes[1].x = 500
    for (let i = 0; i < 300; i++) {
      controller.update(fog, camPos, nodes, DARK)
    }
    // New target: 350 + 3*500 = 1850 > floor 900
    expect(fog.far).toBeCloseTo(1850, 0)
  })
})
