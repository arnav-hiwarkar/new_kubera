import type { GraphLink, GraphNode } from '../types/graph'

export type DimState = 'normal' | 'highlight' | 'dimmed'

export const DIM_OPACITY = 0.12
export const ISOLATED_DIM_OPACITY = 0.08

export interface DimInput {
  query: string
  hoveredNodeId: string | null
  selectedNodeId: string | null
  /** Raw bucket id (or 'uncategorized') of the isolated cluster */
  isolatedClusterId: string | null
}

export function matchesQuery(node: GraphNode, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return false
  return (
    node.name.toLowerCase().includes(q) ||
    (node.bucketName?.toLowerCase().includes(q) ?? false) ||
    (node.status?.toLowerCase().includes(q) ?? false) ||
    (node.tags?.some((t) => t.toLowerCase().includes(q)) ?? false)
  )
}

export function buildNeighborSet(links: GraphLink[], focusNodeId: string | null): Set<string> {
  const set = new Set<string>()
  if (!focusNodeId) return set
  for (const link of links) {
    const s = typeof link.source === 'string' ? link.source : link.source.id
    const t = typeof link.target === 'string' ? link.target : link.target.id
    if (s === focusNodeId) set.add(t)
    else if (t === focusNodeId) set.add(s)
  }
  return set
}

export function resolveDimState(
  node: GraphNode,
  neighbors: Set<string>,
  input: DimInput,
): DimState {
  if (input.query.trim()) {
    return matchesQuery(node, input.query) ? 'highlight' : 'dimmed'
  }
  if (input.isolatedClusterId) {
    const inCluster =
      node.type === 'bucket'
        ? node.rawId === input.isolatedClusterId
        : (node.bucketId ?? 'uncategorized') === input.isolatedClusterId
    return inCluster ? 'normal' : 'dimmed'
  }
  const focusId = input.hoveredNodeId ?? input.selectedNodeId
  if (focusId) {
    return node.id === focusId || neighbors.has(node.id) ? 'highlight' : 'dimmed'
  }
  return 'normal'
}

export function dimOpacity(state: DimState, isolatedActive: boolean): number {
  if (state === 'dimmed') return isolatedActive ? ISOLATED_DIM_OPACITY : DIM_OPACITY
  return 1
}
