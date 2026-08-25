import { describe, it, expect } from 'vitest'
import { computeGraphExtent } from './dynamicFog'
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
