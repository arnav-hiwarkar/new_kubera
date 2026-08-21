import { describe, it, expect } from 'vitest'
import {
  matchesQuery,
  buildNeighborSet,
  resolveDimState,
  dimOpacity,
  DIM_OPACITY,
  ISOLATED_DIM_OPACITY,
} from './dimState'
import type { GraphLink, GraphNode } from '../types/graph'

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

const links: GraphLink[] = [
  { source: 'bucket_b1', target: 'doc_1', kind: 'bucket-doc', strength: 0.8, color: '' },
  { source: 'doc_1', target: 'doc_2', kind: 'tag-shared', strength: 0.08, color: '' },
]

describe('matchesQuery', () => {
  it('matches name, bucket, status and tags case-insensitively', () => {
    const node = docNode({ status: 'verified', tags: ['tax'] })
    expect(matchesQuery(node, 'TAX')).toBe(true)
    expect(matchesQuery(node, 'finan')).toBe(true)
    expect(matchesQuery(node, 'verif')).toBe(true)
    expect(matchesQuery(node, 'nomatch')).toBe(false)
  })
  it('empty query never matches', () => {
    expect(matchesQuery(docNode(), '  ')).toBe(false)
  })
})

describe('buildNeighborSet', () => {
  it('collects direct neighbors of the focus node', () => {
    const set = buildNeighborSet(links, 'doc_1')
    expect(set.has('bucket_b1')).toBe(true)
    expect(set.has('doc_2')).toBe(true)
    expect(set.has('unrelated')).toBe(false)
  })
})

describe('resolveDimState', () => {
  const base = { hoveredNodeId: null, selectedNodeId: null, isolatedClusterId: null }

  it('query takes precedence: matches highlight, others dim', () => {
    const node = docNode()
    const input = { ...base, query: 'tax' }
    expect(resolveDimState(node, new Set(), input)).toBe('highlight')
    expect(resolveDimState(docNode({ id: 'doc_x', rawId: 'x', name: 'Other' }), new Set(), input)).toBe('dimmed')
  })

  it('isolation dims nodes outside the cluster', () => {
    const input = { ...base, query: '', isolatedClusterId: 'b1' }
    expect(resolveDimState(docNode(), new Set(), input)).toBe('normal')
    expect(
      resolveDimState(docNode({ id: 'doc_9', rawId: '9', bucketId: 'b2' }), new Set(), input),
    ).toBe('dimmed')
  })

  it('hover highlights node + neighbors, dims the rest', () => {
    const input = { ...base, query: '', hoveredNodeId: 'doc_1' }
    expect(resolveDimState(docNode(), new Set(), input)).toBe('highlight')
    expect(resolveDimState(docNode({ id: 'doc_2', rawId: '2' }), new Set(['doc_2']), input)).toBe('highlight')
    expect(resolveDimState(docNode({ id: 'doc_3', rawId: '3' }), new Set(['doc_2']), input)).toBe('dimmed')
  })

  it('no focus → everything normal', () => {
    expect(resolveDimState(docNode(), new Set(), { ...base, query: '' })).toBe('normal')
  })
})

describe('dimOpacity', () => {
  it('returns highlight=1, dimmed values, normal=1', () => {
    expect(dimOpacity('highlight', false)).toBe(1)
    expect(dimOpacity('normal', false)).toBe(1)
    expect(dimOpacity('dimmed', false)).toBe(DIM_OPACITY)
    expect(dimOpacity('dimmed', true)).toBe(ISOLATED_DIM_OPACITY)
  })
})
