# DocVault 3D Knowledge Graph View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive Obsidian-style 3D knowledge graph view for DocVault documents and buckets with elastic cluster-drag physics, distance-based LOD labels, instant camera fly-to, HUD search/filter tools, and full DocVault document drawer integration.

**Architecture:** A dedicated WebGL 3D graph route (`/app/docvault/graph`) powered by `3d-force-graph` and `three.js`. Buckets are rendered as glowing hub centroids connected by primary spring links to their member documents, with elastic cluster-drag physics, billboard canvas sprites with distance-based level-of-detail, and full bi-directional synchronization with DocVault TanStack Query data and the `DocumentDrawer`.

**Tech Stack:** React 18, TypeScript, Three.js, `3d-force-graph`, `@tanstack/react-query`, Tailwind CSS, Lucide React, Vitest.

## Global Constraints

- Protected under `ModuleGuard moduleId="docvault"` at route `/app/docvault/graph`.
- UI must follow Kubera design tokens (`bg-bg-surface`, `border-border`, `text-text-primary`, `accent`).
- 60 FPS WebGL rendering with device pixel ratio capped at `Math.min(window.devicePixelRatio, 2)`.
- No broken imports or TypeScript build errors (`tsc -b` and `vite build` must pass cleanly).

---

## File Structure

```
frontend/src/pages/company/docvault/
├── DocVaultPage.tsx                                # Modified: adds "3D Graph View" button in header
└── graph/
    ├── DocVaultGraphPage.tsx                       # Main page container with data loading & drawer
    ├── types/
    │   └── graph.ts                                # TypeScript interfaces for nodes, links, HUD state
    ├── lib/
    │   ├── palette.ts                              # Color generators for bucket hues and status tokens
    │   └── textSprite.ts                           # Canvas high-DPI billboard text sprites with LOD
    ├── hooks/
    │   ├── useGraphData.ts                         # Transforms Buckets & Documents into 3D graph topology
    │   ├── useGraphData.test.ts                    # Unit tests for graph data transformation
    │   ├── useGraphControls.ts                     # Camera tweening & physics simulation control hook
    │   └── useGraphControls.test.ts                # Unit tests for graph controls
    └── components/
        ├── GraphCanvas.tsx                         # Three.js / 3d-force-graph WebGL container
        ├── GraphHud.tsx                            # Top floating HUD (Search, Filters, Color mode, Metrics)
        ├── GraphNavigationControls.tsx             # Bottom-right navigation dock (Zoom, Reset, Recenter, Pause)
        ├── BucketSummaryCard.tsx                   # Floating card when a Bucket Hub node is clicked
        ├── GraphLegend.tsx                         # Collapsible bottom-left legend
        └── DocVaultGraphPage.test.tsx              # Component integration tests
frontend/src/routes/company.routes.tsx              # Modified: registers /app/docvault/graph route
```

---

## Tasks

### Task 1: Dependencies, Core Types & Graph Data Transformation

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/pages/company/docvault/graph/types/graph.ts`
- Create: `frontend/src/pages/company/docvault/graph/lib/palette.ts`
- Create: `frontend/src/pages/company/docvault/graph/hooks/useGraphData.ts`
- Test: `frontend/src/pages/company/docvault/graph/hooks/useGraphData.test.ts`

**Interfaces:**
- Consumes: `BucketResponse`, `DocumentResponse` from `@/api/types`
- Produces:
  - `GraphNode`: `{ id, rawId, type: 'bucket'|'document', name, bucketId, status, versionNo, sizeBytes, tags, color, size, ... }`
  - `GraphLink`: `{ source, target, kind: 'bucket-doc'|'tag-shared', strength, color }`
  - `useGraphData(buckets, documents, colorMode, filterBuckets)` returning `{ nodes, links, bucketMap, counts }`

- [ ] **Step 1: Install 3D graph and Three.js dependencies**

Run in terminal:
```bash
cd frontend && npm install three 3d-force-graph && npm install -D @types/three
```

- [ ] **Step 2: Create TypeScript definitions in `graph.ts`**

Create `frontend/src/pages/company/docvault/graph/types/graph.ts`:
```typescript
import type { BucketResponse, DocumentResponse } from '@/api/types'

export type NodeType = 'bucket' | 'document'
export type ColorMode = 'bucket' | 'status'

export interface GraphNode {
  id: string
  rawId: string
  type: NodeType
  name: string
  bucketId: string | null
  bucketName: string
  status?: string
  versionNo?: number
  sizeBytes?: number
  tags?: string[]
  color: string
  size: number
  rawDoc?: DocumentResponse
  rawBucket?: BucketResponse
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
  fx?: number | null
  fy?: number | null
  fz?: number | null
  __sprite?: any
}

export interface GraphLink {
  source: string | GraphNode
  target: string | GraphNode
  kind: 'bucket-doc' | 'tag-shared'
  strength: number
  color: string
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
  bucketMap: Map<string, BucketResponse>
  totalDocuments: number
  totalBuckets: number
}
```

- [ ] **Step 3: Create color palette helper in `palette.ts`**

Create `frontend/src/pages/company/docvault/graph/lib/palette.ts`:
```typescript
export const BUCKET_PALETTE = [
  '#38BDF8', // Sky
  '#818CF8', // Indigo
  '#A78BFA', // Violet
  '#F472B6', // Pink
  '#FB7185', // Rose
  '#FBBF24', // Amber
  '#34D399', // Emerald
  '#2DD4BF', // Teal
  '#60A5FA', // Blue
  '#C084FC', // Purple
]

export const STATUS_COLORS: Record<string, string> = {
  verified: '#10B981',
  uploaded: '#3B82F6',
  submitted: '#6366F1',
  pending_approval: '#F59E0B',
  action_required: '#EF4444',
  overdue: '#DC2626',
  archived: '#6B7280',
}

export function getBucketColor(bucketId: string | null | undefined, index = 0): string {
  if (!bucketId || bucketId === 'uncategorized') return '#94A3B8'
  let hash = 0
  for (let i = 0; i < bucketId.length; i++) {
    hash = (hash << 5) - hash + bucketId.charCodeAt(i)
    hash |= 0
  }
  const idx = Math.abs(hash + index) % BUCKET_PALETTE.length
  return BUCKET_PALETTE[idx]
}

export function getDocumentColor(
  doc: { bucket_id: string | null; status: string },
  colorMode: 'bucket' | 'status',
  bucketIndex = 0,
): string {
  if (colorMode === 'status') {
    return STATUS_COLORS[doc.status] || '#94A3B8'
  }
  return getBucketColor(doc.bucket_id, bucketIndex)
}
```

- [ ] **Step 4: Write failing unit test for `useGraphData`**

Create `frontend/src/pages/company/docvault/graph/hooks/useGraphData.test.ts`:
```typescript
import { describe, it, expect } from 'vitest'
import { transformToGraphData } from './useGraphData'
import type { BucketResponse, DocumentResponse } from '@/api/types'

describe('transformToGraphData', () => {
  const mockBuckets: BucketResponse[] = [
    {
      id: 'b1',
      name: 'Finance',
      visibility: 'everyone',
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      access_user_ids: [],
    },
  ]

  const mockDocs: DocumentResponse[] = [
    {
      id: 'd1',
      title: 'Tax Filing 2026',
      bucket_id: 'b1',
      status: 'verified',
      is_editable: true,
      current_version_id: 'v1',
      tags: ['tax', 'q1'],
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      versions: [],
    },
    {
      id: 'd2',
      title: 'Audit Report',
      bucket_id: 'b1',
      status: 'pending_approval',
      is_editable: true,
      current_version_id: 'v2',
      tags: ['tax', 'audit'],
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      versions: [],
    },
    {
      id: 'd3',
      title: 'Uncategorized Doc',
      bucket_id: null,
      status: 'uploaded',
      is_editable: true,
      current_version_id: 'v3',
      tags: [],
      created_by: 'u1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      versions: [],
    },
  ]

  it('generates bucket hub nodes and document nodes with primary cluster links', () => {
    const data = transformToGraphData(mockBuckets, mockDocs, 'bucket', new Set(['all']))
    
    // 1 bucket hub + 1 uncategorized hub + 3 documents = 5 nodes
    expect(data.nodes.length).toBe(5)
    
    const bucketHub = data.nodes.find((n) => n.id === 'bucket_b1')
    expect(bucketHub).toBeDefined()
    expect(bucketHub?.type).toBe('bucket')
    expect(bucketHub?.size).toBe(14)

    const docNode = data.nodes.find((n) => n.id === 'doc_d1')
    expect(docNode).toBeDefined()
    expect(docNode?.type).toBe('document')
    expect(docNode?.size).toBe(6)

    // Check primary links
    const primaryLinks = data.links.filter((l) => l.kind === 'bucket-doc')
    expect(primaryLinks.length).toBe(3)
  })

  it('filters nodes when specific buckets are selected', () => {
    const data = transformToGraphData(mockBuckets, mockDocs, 'bucket', new Set(['b1']))
    // Only bucket b1 and its 2 documents
    expect(data.nodes.length).toBe(3)
    expect(data.nodes.some((n) => n.id === 'doc_d3')).toBe(false)
  })
})
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd frontend && npm test useGraphData.test.ts`
Expected: FAIL (module not yet implemented).

- [ ] **Step 6: Implement `useGraphData.ts`**

Create `frontend/src/pages/company/docvault/graph/hooks/useGraphData.ts`:
```typescript
import { useMemo } from 'react'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import type { ColorMode, GraphData, GraphLink, GraphNode } from '../types/graph'
import { getBucketColor, getDocumentColor } from '../lib/palette'

export function transformToGraphData(
  buckets: BucketResponse[],
  documents: DocumentResponse[],
  colorMode: ColorMode,
  visibleBucketIds: Set<string>,
): GraphData {
  const bucketMap = new Map<string, BucketResponse>()
  buckets.forEach((b) => bucketMap.set(b.id, b))

  const showAll = visibleBucketIds.has('all')
  const activeDocs = documents.filter((d) => d.status !== 'archived')

  // Filter documents by visible buckets
  const filteredDocs = activeDocs.filter((d) => {
    if (showAll) return true
    if (!d.bucket_id) return visibleBucketIds.has('uncategorized')
    return visibleBucketIds.has(d.bucket_id)
  })

  const nodes: GraphNode[] = []
  const links: GraphLink[] = []

  // Add Bucket Hub Nodes
  const includedBucketIds = new Set<string>()
  filteredDocs.forEach((d) => {
    includedBucketIds.add(d.bucket_id || 'uncategorized')
  })
  if (showAll) {
    buckets.forEach((b) => includedBucketIds.add(b.id))
  }

  Array.from(includedBucketIds).forEach((bId, idx) => {
    const isUncategorized = bId === 'uncategorized'
    const bucket = bucketMap.get(bId)
    const name = isUncategorized ? 'Uncategorized' : bucket?.name || 'Unknown Bucket'
    const color = getBucketColor(isUncategorized ? null : bId, idx)

    nodes.push({
      id: `bucket_${bId}`,
      rawId: bId,
      type: 'bucket',
      name,
      bucketId: isUncategorized ? null : bId,
      bucketName: name,
      color,
      size: 14,
      rawBucket: bucket,
    })
  })

  // Add Document Nodes & Primary Links
  filteredDocs.forEach((doc, idx) => {
    const parentBucketId = doc.bucket_id || 'uncategorized'
    const bucketName = doc.bucket_id
      ? bucketMap.get(doc.bucket_id)?.name || 'Uncategorized'
      : 'Uncategorized'
    const color = getDocumentColor(doc, colorMode, idx)
    const currentVer = doc.versions.find((v) => v.id === doc.current_version_id)
    const versionNo = currentVer?.version_number ?? doc.versions.length || 1

    const docNodeId = `doc_${doc.id}`
    nodes.push({
      id: docNodeId,
      rawId: doc.id,
      type: 'document',
      name: doc.title,
      bucketId: doc.bucket_id,
      bucketName,
      status: doc.status,
      versionNo,
      sizeBytes: currentVer?.size_bytes,
      tags: doc.tags,
      color,
      size: 6,
      rawDoc: doc,
    })

    // Primary link to parent bucket hub
    links.push({
      source: `bucket_${parentBucketId}`,
      target: docNodeId,
      kind: 'bucket-doc',
      strength: 0.8,
      color: 'rgba(100, 160, 255, 0.35)',
    })
  })

  // Add Secondary Links between docs sharing ≥ 2 tags
  for (let i = 0; i < filteredDocs.length; i++) {
    for (let j = i + 1; j < filteredDocs.length; j++) {
      const docA = filteredDocs[i]
      const docB = filteredDocs[j]
      if (!docA.tags?.length || !docB.tags?.length) continue
      const sharedTags = docA.tags.filter((t) => docB.tags.includes(t))
      if (sharedTags.length >= 2) {
        links.push({
          source: `doc_${docA.id}`,
          target: `doc_${docB.id}`,
          kind: 'tag-shared',
          strength: 0.15,
          color: 'rgba(255, 255, 255, 0.12)',
        })
      }
    }
  }

  return {
    nodes,
    links,
    bucketMap,
    totalDocuments: activeDocs.length,
    totalBuckets: buckets.length,
  }
}

export function useGraphData(
  buckets: BucketResponse[],
  documents: DocumentResponse[],
  colorMode: ColorMode,
  visibleBucketIds: Set<string>,
): GraphData {
  return useMemo(
    () => transformToGraphData(buckets, documents, colorMode, visibleBucketIds),
    [buckets, documents, colorMode, visibleBucketIds],
  )
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd frontend && npm test useGraphData.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/pages/company/docvault/graph/types/graph.ts frontend/src/pages/company/docvault/graph/lib/palette.ts frontend/src/pages/company/docvault/graph/hooks/useGraphData.ts frontend/src/pages/company/docvault/graph/hooks/useGraphData.test.ts
git commit -m "feat(docvault-graph): add graph types, color palette, and graph data hook"
```

---

### Task 2: High-DPI Canvas Text Sprites & Distance LOD Engine

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/lib/textSprite.ts`
- Test: `frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts`

**Interfaces:**
- Produces:
  - `createNodeSprite(node: GraphNode): THREE.Sprite`
  - `updateSpriteLOD(sprite: THREE.Sprite, distance: number, isBucket: boolean): void`

- [ ] **Step 1: Write failing unit test for `textSprite.ts`**

Create `frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts`:
```typescript
import { describe, it, expect } from 'vitest'
import { updateSpriteLOD } from './textSprite'
import * as THREE from 'three'

describe('textSprite LOD engine', () => {
  it('hides document sprite when camera distance is greater than 420px', () => {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial())
    updateSpriteLOD(sprite, 500, false)
    expect(sprite.material.opacity).toBe(0)
    expect(sprite.visible).toBe(false)
  })

  it('keeps bucket sprite visible even at far distance', () => {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial())
    updateSpriteLOD(sprite, 500, true)
    expect(sprite.material.opacity).toBeGreaterThan(0.5)
    expect(sprite.visible).toBe(true)
  })

  it('smoothly fades in document sprite in mid-distance zone', () => {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial())
    updateSpriteLOD(sprite, 300, false)
    expect(sprite.material.opacity).toBeGreaterThan(0)
    expect(sprite.material.opacity).toBeLessThanOrEqual(1)
    expect(sprite.visible).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test textSprite.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement `textSprite.ts`**

Create `frontend/src/pages/company/docvault/graph/lib/textSprite.ts`:
```typescript
import * as THREE from 'three'
import type { GraphNode } from '../types/graph'

const textureCache = new Map<string, THREE.CanvasTexture>()

export function createNodeSprite(node: GraphNode): THREE.Sprite {
  const isBucket = node.type === 'bucket'
  const cacheKey = `${node.id}_${node.name}_${node.status}_${node.versionNo}_${node.color}`

  let texture = textureCache.get(cacheKey)
  if (!texture) {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      const fallbackMat = new THREE.SpriteMaterial({ opacity: 0 })
      return new THREE.Sprite(fallbackMat)
    }

    const scale = 2 // High DPI factor
    const fontSize = isBucket ? 14 : 11
    ctx.font = `${isBucket ? '600' : '500'} ${fontSize * scale}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

    const labelText = node.name.length > 28 ? `${node.name.slice(0, 26)}…` : node.name
    const badgeText = !isBucket && node.versionNo ? `v${node.versionNo}` : ''

    const textWidth = ctx.measureText(labelText).width
    const badgeWidth = badgeText ? ctx.measureText(` ${badgeText}`).width + 12 * scale : 0
    const totalWidth = textWidth + badgeWidth + 24 * scale
    const height = 30 * scale

    canvas.width = totalWidth
    canvas.height = height

    // Re-set font after resize
    ctx.font = `${isBucket ? '600' : '500'} ${fontSize * scale}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
    ctx.textBaseline = 'middle'

    // Background pill
    const radius = 6 * scale
    ctx.fillStyle = isBucket ? 'rgba(15, 23, 42, 0.85)' : 'rgba(11, 15, 23, 0.85)'
    ctx.beginPath()
    ctx.roundRect(0, 0, totalWidth, height, radius)
    ctx.fill()

    // Border
    ctx.strokeStyle = isBucket ? node.color : 'rgba(255, 255, 255, 0.15)'
    ctx.lineWidth = 1.5 * scale
    ctx.stroke()

    // Node indicator dot
    const dotRadius = 3.5 * scale
    ctx.fillStyle = node.color
    ctx.beginPath()
    ctx.arc(12 * scale, height / 2, dotRadius, 0, Math.PI * 2)
    ctx.fill()

    // Main text
    ctx.fillStyle = isBucket ? '#FFFFFF' : '#E2E8F0'
    ctx.fillText(labelText, 20 * scale, height / 2)

    // Version badge
    if (badgeText) {
      const badgeX = 20 * scale + textWidth + 6 * scale
      ctx.fillStyle = 'rgba(255, 255, 255, 0.15)'
      ctx.beginPath()
      ctx.roundRect(badgeX, height / 2 - 8 * scale, badgeWidth - 4 * scale, 16 * scale, 3 * scale)
      ctx.fill()

      ctx.fillStyle = '#94A3B8'
      ctx.font = `500 ${9 * scale}px monospace`
      ctx.fillText(badgeText, badgeX + 4 * scale, height / 2)
    }

    texture = new THREE.CanvasTexture(canvas)
    texture.minFilter = THREE.LinearFilter
    textureCache.set(cacheKey, texture)
  }

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: isBucket ? 0.95 : 0,
    depthWrite: false,
  })

  const sprite = new THREE.Sprite(material)
  const baseScale = isBucket ? 34 : 26
  sprite.scale.set(baseScale * 1.5, baseScale * 0.45, 1)
  sprite.position.set(0, node.size + (isBucket ? 6 : 4), 0)
  return sprite
}

export function updateSpriteLOD(
  sprite: THREE.Sprite,
  distance: number,
  isBucket: boolean,
): void {
  if (isBucket) {
    sprite.visible = true
    sprite.material.opacity = distance > 600 ? 0.6 : 0.95
    return
  }

  // Document LOD thresholds
  const FAR_THRESHOLD = 420
  const CLOSE_THRESHOLD = 180

  if (distance >= FAR_THRESHOLD) {
    sprite.visible = false
    sprite.material.opacity = 0
  } else if (distance <= CLOSE_THRESHOLD) {
    sprite.visible = true
    sprite.material.opacity = 1
  } else {
    sprite.visible = true
    sprite.material.opacity = (FAR_THRESHOLD - distance) / (FAR_THRESHOLD - CLOSE_THRESHOLD)
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test textSprite.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add frontend/src/pages/company/docvault/graph/lib/textSprite.ts frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts
git commit -m "feat(docvault-graph): add high-dpi billboard canvas sprite and LOD engine"
```

---

### Task 3: 3D Force Graph WebGL Canvas & Elastic Cluster Drag Engine

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/hooks/useGraphControls.ts`
- Create: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`

**Interfaces:**
- `useGraphControls(graphRef)` produces `{ flyToNode, resetCamera, recenter, togglePhysics, isPaused }`
- `<GraphCanvas />` receives `{ data, colorMode, onSelectNode, selectedNodeId, hoveredNodeId, setHoveredNodeId, controlsRef }`

- [ ] **Step 1: Implement `useGraphControls.ts`**

Create `frontend/src/pages/company/docvault/graph/hooks/useGraphControls.ts`:
```typescript
import { useCallback, useState } from 'react'
import type { GraphNode } from '../types/graph'

export interface GraphControlsApi {
  flyToNode: (node: GraphNode) => void
  resetCamera: () => void
  recenter: () => void
  zoomIn: () => void
  zoomOut: () => void
  togglePhysics: () => void
  isPaused: boolean
}

export function useGraphControls(graphRef: React.MutableRefObject<any>): GraphControlsApi {
  const [isPaused, setIsPaused] = useState(false)

  const flyToNode = useCallback(
    (node: GraphNode) => {
      const graph = graphRef.current
      if (!graph || node.x === undefined || node.y === undefined || node.z === undefined) return

      const distance = node.type === 'bucket' ? 180 : 120
      const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z || 1)

      graph.cameraPosition(
        { x: node.x * distRatio, y: node.y * distRatio, z: (node.z || 0) * distRatio },
        { x: node.x, y: node.y, z: node.z || 0 },
        1200,
      )
    },
    [graphRef],
  )

  const resetCamera = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    graph.zoomToFit(1000, 80)
  }, [graphRef])

  const recenter = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    graph.cameraPosition({ x: 0, y: 0, z: 350 }, { x: 0, y: 0, z: 0 }, 1000)
  }, [graphRef])

  const zoomIn = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    const current = graph.cameraPosition()
    graph.cameraPosition(
      { x: current.x * 0.75, y: current.y * 0.75, z: current.z * 0.75 },
      undefined,
      400,
    )
  }, [graphRef])

  const zoomOut = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    const current = graph.cameraPosition()
    graph.cameraPosition(
      { x: current.x * 1.35, y: current.y * 1.35, z: current.z * 1.35 },
      undefined,
      400,
    )
  }, [graphRef])

  const togglePhysics = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    setIsPaused((prev) => {
      const next = !prev
      if (next) {
        graph.pauseAnimation()
      } else {
        graph.resumeAnimation()
      }
      return next
    })
  }, [graphRef])

  return {
    flyToNode,
    resetCamera,
    recenter,
    zoomIn,
    zoomOut,
    togglePhysics,
    isPaused,
  }
}
```

- [ ] **Step 2: Implement `GraphCanvas.tsx`**

Create `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`:
```typescript
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import ForceGraph3D from '3d-force-graph'
import type { GraphData, GraphNode } from '../types/graph'
import { createNodeSprite, updateSpriteLOD } from '../lib/textSprite'

export interface GraphCanvasProps {
  data: GraphData
  selectedNodeId: string | null
  onSelectNode: (node: GraphNode | null) => void
  hoveredNodeId: string | null
  onHoverNode: (node: GraphNode | null) => void
  graphInstanceRef: React.MutableRefObject<any>
}

export function GraphCanvas({
  data,
  selectedNodeId,
  onSelectNode,
  hoveredNodeId,
  onHoverNode,
  graphInstanceRef,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphObjRef = useRef<any>(null)
  const spritesRef = useRef<Map<string, THREE.Sprite>>(new Map())

  useEffect(() => {
    if (!containerRef.current) return

    // Initialize 3d-force-graph
    const graph = ForceGraph3D()(containerRef.current)
      .backgroundColor('#0B0F17')
      .showNavInfo(false)
      .nodeRelSize(4)
      .nodeVal((node: any) => (node.type === 'bucket' ? 16 : 6))
      .linkWidth((link: any) => (link.kind === 'bucket-doc' ? 1.5 : 0.8))
      .linkOpacity(0.4)
      .linkColor((link: any) => link.color)
      .linkDirectionalParticles((link: any) => (link.kind === 'bucket-doc' ? 2 : 0))
      .linkDirectionalParticleWidth(1.2)
      .linkDirectionalParticleSpeed(0.004)
      .nodeThreeObject((node: any) => {
        const group = new THREE.Group()
        const isBucket = node.type === 'bucket'

        // Core Sphere
        const geometry = isBucket
          ? new THREE.SphereGeometry(node.size, 24, 24)
          : new THREE.SphereGeometry(node.size, 16, 16)
        
        const material = new THREE.MeshStandardMaterial({
          color: node.color,
          emissive: node.color,
          emissiveIntensity: isBucket ? 0.6 : 0.35,
          roughness: 0.3,
          metalness: 0.2,
        })
        const sphere = new THREE.Mesh(geometry, material)
        group.add(sphere)

        // Outer glow orbital ring for Bucket Hubs
        if (isBucket) {
          const ringGeom = new THREE.RingGeometry(node.size * 1.3, node.size * 1.45, 32)
          const ringMat = new THREE.MeshBasicMaterial({
            color: node.color,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.45,
          })
          const ring = new THREE.Mesh(ringGeom, ringMat)
          ring.rotation.x = Math.PI / 3
          group.add(ring)
        }

        // Billboard text sprite
        const sprite = createNodeSprite(node)
        spritesRef.current.set(node.id, sprite)
        group.add(sprite)

        return group
      })
      .onNodeHover((node: any) => {
        if (containerRef.current) {
          containerRef.current.style.cursor = node ? 'grab' : 'default'
        }
        onHoverNode(node || null)
      })
      .onNodeClick((node: any) => {
        onSelectNode(node || null)
      })
      .onBackgroundClick(() => {
        onSelectNode(null)
      })
      // Elastic cluster drag
      .onNodeDrag((node: any) => {
        if (containerRef.current) {
          containerRef.current.style.cursor = 'grabbing'
        }
        // Keep physics warm during drag so connected cluster follows
        const sim = graph.d3Force('simulation')
        if (sim) sim.alphaTarget(0.35).restart()
      })
      .onNodeDragEnd((node: any) => {
        if (containerRef.current) {
          containerRef.current.style.cursor = 'grab'
        }
        node.fx = null
        node.fy = null
        node.fz = null
      })

    // Custom d3 forces for clustering
    const linkForce = graph.d3Force('link')
    if (linkForce) {
      linkForce.distance((link: any) => (link.kind === 'bucket-doc' ? 45 : 100))
      linkForce.strength((link: any) => (link.kind === 'bucket-doc' ? 0.85 : 0.12))
    }

    const chargeForce = graph.d3Force('charge')
    if (chargeForce) {
      chargeForce.strength(-110)
    }

    // Per-frame LOD update loop
    const camera = graph.camera()
    const scene = graph.scene()

    // Add ambient light and directional lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.7))
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
    dirLight.position.set(100, 200, 150)
    scene.add(dirLight)

    const interval = setInterval(() => {
      if (!camera || !graph) return
      const camPos = camera.position
      data.nodes.forEach((node) => {
        const sprite = spritesRef.current.get(node.id)
        if (sprite && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
          const dist = camPos.distanceTo(new THREE.Vector3(node.x, node.y, node.z))
          updateSpriteLOD(sprite, dist, node.type === 'bucket')
        }
      })
    }, 60)

    graphObjRef.current = graph
    graphInstanceRef.current = graph

    const handleResize = () => {
      if (!containerRef.current || !graph) return
      graph.width(containerRef.current.clientWidth)
      graph.height(containerRef.current.clientHeight)
    }
    window.addEventListener('resize', handleResize)

    return () => {
      clearInterval(interval)
      window.removeEventListener('resize', handleResize)
      if (graph) {
        graph._destructor?.()
      }
    }
  }, [])

  // Update graph data when data changes
  useEffect(() => {
    if (!graphObjRef.current) return
    graphObjRef.current.graphData({
      nodes: data.nodes,
      links: data.links,
    })
  }, [data])

  return <div ref={containerRef} className="h-full w-full select-none" />
}
```

- [ ] **Step 3: Commit Task 3**

```bash
git add frontend/src/pages/company/docvault/graph/hooks/useGraphControls.ts frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx
git commit -m "feat(docvault-graph): add 3d WebGL canvas with elastic cluster drag and camera controls"
```

---

### Task 4: HUD, Search Bar, Color Modes & Navigation Controls

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/components/GraphHud.tsx`
- Create: `frontend/src/pages/company/docvault/graph/components/GraphNavigationControls.tsx`
- Create: `frontend/src/pages/company/docvault/graph/components/BucketSummaryCard.tsx`
- Create: `frontend/src/pages/company/docvault/graph/components/GraphLegend.tsx`

**Interfaces:**
- `<GraphHud />` manages search input, search dropdown results, color mode switch, bucket filter menu, and back button.
- `<GraphNavigationControls />` provides Zoom In/Out, Reset View, Recenter, and Pause physics.
- `<BucketSummaryCard />` renders details of the selected bucket.
- `<GraphLegend />` shows active color scheme.

- [ ] **Step 1: Implement `GraphHud.tsx`**

Create `frontend/src/pages/company/docvault/graph/components/GraphHud.tsx`:
```typescript
import { useState, useMemo } from 'react'
import { ArrowLeft, Search, SlidersHorizontal, Palette, Folder, FileText, Check } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { BucketResponse } from '@/api/types'
import type { ColorMode, GraphData, GraphNode } from '../types/graph'
import { cn } from '@/lib/cn'

export interface GraphHudProps {
  data: GraphData
  buckets: BucketResponse[]
  colorMode: ColorMode
  onChangeColorMode: (mode: ColorMode) => void
  visibleBucketIds: Set<string>
  onToggleBucket: (bucketId: string) => void
  onSelectAllBuckets: () => void
  onSelectNode: (node: GraphNode) => void
}

export function GraphHud({
  data,
  buckets,
  colorMode,
  onChangeColorMode,
  visibleBucketIds,
  onToggleBucket,
  onSelectAllBuckets,
  onSelectNode,
}: GraphHudProps) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)

  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return []
    const q = searchQuery.toLowerCase()
    return data.nodes
      .filter((n) => n.name.toLowerCase().includes(q) || n.tags?.some((t) => t.toLowerCase().includes(q)))
      .slice(0, 8)
  }, [data.nodes, searchQuery])

  return (
    <header className="absolute left-4 right-4 top-4 z-20 flex flex-wrap items-center justify-between gap-3 pointer-events-none">
      {/* Left: Back & Title */}
      <div className="flex items-center gap-3 pointer-events-auto">
        <button
          onClick={() => navigate('/app/docvault')}
          className="flex items-center gap-2 rounded-btn border border-border bg-bg-surface/90 px-3 py-2 text-sm font-medium text-text-primary backdrop-blur hover:bg-bg-raised transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to List</span>
        </button>

        <div className="hidden sm:flex items-center gap-2 rounded-btn border border-border bg-bg-surface/90 px-3 py-2 text-sm backdrop-blur">
          <span className="font-semibold text-text-primary">DocVault 3D Graph</span>
          <span className="text-text-muted">·</span>
          <span className="text-xs text-text-secondary">
            {data.totalBuckets} Buckets · {data.totalDocuments} Docs
          </span>
        </div>
      </div>

      {/* Center: Search */}
      <div className="relative w-full max-w-sm pointer-events-auto">
        <div className="relative flex items-center">
          <Search className="absolute left-3 h-4 w-4 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
            placeholder="Search documents or buckets…"
            className="h-10 w-full rounded-btn border border-border bg-bg-surface/90 pl-9 pr-4 text-sm text-text-primary placeholder:text-text-muted backdrop-blur focus:border-accent focus:outline-none"
          />
        </div>

        {/* Search Results Dropdown */}
        {searchFocused && searchResults.length > 0 && (
          <ul className="absolute left-0 right-0 top-12 max-h-72 overflow-y-auto rounded-card border border-border bg-bg-surface/95 p-1.5 shadow-popover backdrop-blur">
            {searchResults.map((node) => (
              <li key={node.id}>
                <button
                  onMouseDown={() => {
                    onSelectNode(node)
                    setSearchQuery('')
                  }}
                  className="flex w-full items-center gap-2.5 rounded-btn px-3 py-2 text-left text-sm text-text-primary hover:bg-bg-raised"
                >
                  {node.type === 'bucket' ? (
                    <Folder className="h-4 w-4 shrink-0 text-accent" />
                  ) : (
                    <FileText className="h-4 w-4 shrink-0 text-text-muted" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{node.name}</div>
                    <div className="text-xs text-text-muted">
                      {node.type === 'bucket' ? 'Bucket' : node.bucketName}
                    </div>
                  </div>
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: node.color }}
                  />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Right: Color Mode & Filter */}
      <div className="flex items-center gap-2 pointer-events-auto">
        {/* Color Mode Switch */}
        <div className="flex rounded-btn border border-border bg-bg-surface/90 p-0.5 backdrop-blur">
          <button
            onClick={() => onChangeColorMode('bucket')}
            className={cn(
              'flex items-center gap-1.5 rounded-btn px-2.5 py-1.5 text-xs font-medium transition-colors',
              colorMode === 'bucket'
                ? 'bg-accent text-white'
                : 'text-text-secondary hover:text-text-primary',
            )}
          >
            <Palette className="h-3.5 w-3.5" />
            By Bucket
          </button>
          <button
            onClick={() => onChangeColorMode('status')}
            className={cn(
              'flex items-center gap-1.5 rounded-btn px-2.5 py-1.5 text-xs font-medium transition-colors',
              colorMode === 'status'
                ? 'bg-accent text-white'
                : 'text-text-secondary hover:text-text-primary',
            )}
          >
            By Status
          </button>
        </div>

        {/* Bucket Filter Dropdown */}
        <div className="relative">
          <button
            onClick={() => setFilterOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded-btn border border-border bg-bg-surface/90 px-3 py-2 text-xs font-medium text-text-primary backdrop-blur hover:bg-bg-raised transition-colors"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span>Buckets</span>
          </button>

          {filterOpen && (
            <div className="absolute right-0 top-11 w-56 rounded-card border border-border bg-bg-surface/95 p-2 shadow-popover backdrop-blur">
              <div className="mb-2 flex items-center justify-between border-b border-border pb-1.5">
                <span className="text-xs font-semibold uppercase text-text-muted">Filter View</span>
                <button
                  onClick={onSelectAllBuckets}
                  className="text-xs text-accent hover:underline"
                >
                  Show All
                </button>
              </div>
              <ul className="max-h-60 overflow-y-auto space-y-1">
                {buckets.map((b) => {
                  const isChecked = visibleBucketIds.has('all') || visibleBucketIds.has(b.id)
                  return (
                    <li key={b.id}>
                      <button
                        onClick={() => onToggleBucket(b.id)}
                        className="flex w-full items-center justify-between rounded-btn px-2 py-1.5 text-left text-xs text-text-primary hover:bg-bg-raised"
                      >
                        <span className="truncate">{b.name}</span>
                        {isChecked && <Check className="h-3.5 w-3.5 text-accent" />}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
```

- [ ] **Step 2: Implement `GraphNavigationControls.tsx`**

Create `frontend/src/pages/company/docvault/graph/components/GraphNavigationControls.tsx`:
```typescript
import { Plus, Minus, Focus, Compass, Pause, Play } from 'lucide-react'

export interface GraphNavigationControlsProps {
  onZoomIn: () => void
  onZoomOut: () => void
  onResetCamera: () => void
  onRecenter: () => void
  onTogglePhysics: () => void
  isPaused: boolean
}

export function GraphNavigationControls({
  onZoomIn,
  onZoomOut,
  onResetCamera,
  onRecenter,
  onTogglePhysics,
  isPaused,
}: GraphNavigationControlsProps) {
  return (
    <aside className="absolute bottom-6 right-6 z-20 flex flex-col gap-1.5 rounded-card border border-border bg-bg-surface/90 p-1.5 shadow-popover backdrop-blur">
      <button
        onClick={onZoomIn}
        aria-label="Zoom in"
        title="Zoom In"
        className="flex h-8 w-8 items-center justify-center rounded-btn text-text-secondary hover:bg-bg-raised hover:text-text-primary"
      >
        <Plus className="h-4 w-4" />
      </button>
      <button
        onClick={onZoomOut}
        aria-label="Zoom out"
        title="Zoom Out"
        className="flex h-8 w-8 items-center justify-center rounded-btn text-text-secondary hover:bg-bg-raised hover:text-text-primary"
      >
        <Minus className="h-4 w-4" />
      </button>
      <div className="my-0.5 border-t border-border" />
      <button
        onClick={onResetCamera}
        aria-label="Reset camera"
        title="Fit All Nodes"
        className="flex h-8 w-8 items-center justify-center rounded-btn text-text-secondary hover:bg-bg-raised hover:text-text-primary"
      >
        <Focus className="h-4 w-4" />
      </button>
      <button
        onClick={onRecenter}
        aria-label="Recenter view"
        title="Recenter"
        className="flex h-8 w-8 items-center justify-center rounded-btn text-text-secondary hover:bg-bg-raised hover:text-text-primary"
      >
        <Compass className="h-4 w-4" />
      </button>
      <button
        onClick={onTogglePhysics}
        aria-label={isPaused ? 'Resume physics simulation' : 'Pause physics simulation'}
        title={isPaused ? 'Resume Simulation' : 'Pause Simulation'}
        className="flex h-8 w-8 items-center justify-center rounded-btn text-text-secondary hover:bg-bg-raised hover:text-text-primary"
      >
        {isPaused ? <Play className="h-4 w-4 text-accent" /> : <Pause className="h-4 w-4" />}
      </button>
    </aside>
  )
}
```

- [ ] **Step 3: Implement `BucketSummaryCard.tsx` and `GraphLegend.tsx`**

Create `frontend/src/pages/company/docvault/graph/components/BucketSummaryCard.tsx`:
```typescript
import { Folder, X } from 'lucide-react'
import type { GraphNode } from '../types/graph'
import { formatDate } from '@/lib/format'

export interface BucketSummaryCardProps {
  node: GraphNode | null
  onClose: () => void
}

export function BucketSummaryCard({ node, onClose }: BucketSummaryCardProps) {
  if (!node || node.type !== 'bucket') return null

  const bucket = node.rawBucket

  return (
    <div className="absolute bottom-6 left-6 z-20 w-80 rounded-card border border-border bg-bg-surface/95 p-4 shadow-popover backdrop-blur">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-btn"
            style={{ backgroundColor: `${node.color}25` }}
          >
            <Folder className="h-4 w-4" style={{ color: node.color }} />
          </div>
          <div>
            <h3 className="font-semibold text-text-primary text-sm">{node.name}</h3>
            <span className="text-xs text-text-muted">Bucket Cluster</span>
          </div>
        </div>
        <button onClick={onClose} className="text-text-muted hover:text-text-primary">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-1.5 text-xs text-text-secondary">
        <div className="flex justify-between">
          <span className="text-text-muted">Visibility</span>
          <span className="capitalize font-medium text-text-primary">
            {bucket?.visibility || 'everyone'}
          </span>
        </div>
        {bucket?.created_at && (
          <div className="flex justify-between">
            <span className="text-text-muted">Created</span>
            <span>{formatDate(bucket.created_at)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
```

Create `frontend/src/pages/company/docvault/graph/components/GraphLegend.tsx`:
```typescript
import { useState } from 'react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { ColorMode } from '../types/graph'
import { STATUS_COLORS } from '../lib/palette'
import { humanize } from '@/api/enums'

export function GraphLegend({ colorMode }: { colorMode: ColorMode }) {
  const [collapsed, setCollapsed] = useState(true)

  return (
    <div className="absolute bottom-6 left-6 z-10 rounded-card border border-border bg-bg-surface/85 p-2 text-xs shadow-popover backdrop-blur">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between gap-3 text-text-muted hover:text-text-primary font-medium"
      >
        <span>Legend</span>
        {collapsed ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {!collapsed && (
        <div className="mt-2 space-y-1.5 border-t border-border pt-2">
          {colorMode === 'status' ? (
            Object.entries(STATUS_COLORS).map(([status, color]) => (
              <div key={status} className="flex items-center gap-2 text-text-secondary">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                <span>{humanize(status)}</span>
              </div>
            ))
          ) : (
            <div className="space-y-1 text-text-muted">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-accent" />
                <span>Bucket Centroid</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-slate-400" />
                <span>Document Node</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Commit Task 4**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphHud.tsx frontend/src/pages/company/docvault/graph/components/GraphNavigationControls.tsx frontend/src/pages/company/docvault/graph/components/BucketSummaryCard.tsx frontend/src/pages/company/docvault/graph/components/GraphLegend.tsx
git commit -m "feat(docvault-graph): add floating HUD, search, navigation dock, and legend"
```

---

### Task 5: DocVault Graph Page, Routing & Header Navigation Link

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx`
- Modify: `frontend/src/routes/company.routes.tsx:79`
- Modify: `frontend/src/pages/company/docvault/DocVaultPage.tsx:135-141`
- Test: `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.test.tsx`

**Interfaces:**
- `DocVaultGraphPage` loads buckets and documents via `useBuckets()` and `useDocuments()`, connects `GraphCanvas`, `GraphHud`, `GraphNavigationControls`, `DocumentDrawer`, and `BucketSummaryCard`.
- Route `/app/docvault/graph` resolves to `DocVaultGraphPage`.

- [ ] **Step 1: Create `DocVaultGraphPage.tsx`**

Create `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx`:
```typescript
import { useRef, useState } from 'react'
import { useBuckets, useDocuments } from '@/api/hooks/docvault'
import type { ColorMode, GraphNode } from './types/graph'
import { useGraphData } from './hooks/useGraphData'
import { useGraphControls } from './hooks/useGraphControls'
import { GraphCanvas } from './components/GraphCanvas'
import { GraphHud } from './components/GraphHud'
import { GraphNavigationControls } from './components/GraphNavigationControls'
import { BucketSummaryCard } from './components/BucketSummaryCard'
import { GraphLegend } from './components/GraphLegend'
import { DocumentDrawer } from '../DocumentDrawer'

export function DocVaultGraphPage() {
  const { data: buckets = [] } = useBuckets()
  const { data: documents = [] } = useDocuments()

  const [colorMode, setColorMode] = useState<ColorMode>('bucket')
  const [visibleBucketIds, setVisibleBucketIds] = useState<Set<string>>(new Set(['all']))
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)

  const graphInstanceRef = useRef<any>(null)
  const graphControls = useGraphControls(graphInstanceRef)

  const graphData = useGraphData(buckets, documents, colorMode, visibleBucketIds)

  const handleToggleBucket = (bucketId: string) => {
    setVisibleBucketIds((prev) => {
      const next = new Set(prev)
      if (next.has('all')) {
        next.clear()
        buckets.forEach((b) => next.add(b.id))
      }
      if (next.has(bucketId)) {
        next.delete(bucketId)
      } else {
        next.add(bucketId)
      }
      return next
    })
  }

  const handleSelectNode = (node: GraphNode | null) => {
    setSelectedNode(node)
    if (node) {
      graphControls.flyToNode(node)
    }
  }

  const selectedDoc =
    selectedNode?.type === 'document'
      ? documents.find((d) => d.id === selectedNode.rawId) ?? null
      : null

  return (
    <div className="relative h-[calc(100vh-4rem)] w-full overflow-hidden bg-[#0B0F17]">
      <GraphHud
        data={graphData}
        buckets={buckets}
        colorMode={colorMode}
        onChangeColorMode={setColorMode}
        visibleBucketIds={visibleBucketIds}
        onToggleBucket={handleToggleBucket}
        onSelectAllBuckets={() => setVisibleBucketIds(new Set(['all']))}
        onSelectNode={handleSelectNode}
      />

      <GraphCanvas
        data={graphData}
        selectedNodeId={selectedNode?.id ?? null}
        onSelectNode={handleSelectNode}
        hoveredNodeId={hoveredNode?.id ?? null}
        onHoverNode={setHoveredNode}
        graphInstanceRef={graphInstanceRef}
      />

      <GraphNavigationControls
        onZoomIn={graphControls.zoomIn}
        onZoomOut={graphControls.zoomOut}
        onResetCamera={graphControls.resetCamera}
        onRecenter={graphControls.recenter}
        onTogglePhysics={graphControls.togglePhysics}
        isPaused={graphControls.isPaused}
      />

      {selectedNode?.type === 'bucket' && (
        <BucketSummaryCard node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}

      {selectedDoc && (
        <DocumentDrawer
          document={selectedDoc}
          open={!!selectedDoc}
          onClose={() => setSelectedNode(null)}
          buckets={buckets}
        />
      )}

      <GraphLegend colorMode={colorMode} />
    </div>
  )
}
```

- [ ] **Step 2: Register `/app/docvault/graph` route in `company.routes.tsx`**

Modify `frontend/src/routes/company.routes.tsx`:
Add import:
```typescript
import { DocVaultGraphPage } from '@/pages/company/docvault/graph/DocVaultGraphPage'
```
And add route inside children:
```typescript
{ path: 'docvault', element: <ModuleGuard moduleId="docvault"><DocVaultPage /></ModuleGuard> },
{ path: 'docvault/graph', element: <ModuleGuard moduleId="docvault"><DocVaultGraphPage /></ModuleGuard> },
```

- [ ] **Step 3: Add "3D Graph View" button in `DocVaultPage.tsx`**

Modify `frontend/src/pages/company/docvault/DocVaultPage.tsx`:
Add `Network` from `lucide-react` and `useNavigate` from `react-router-dom`:
```typescript
import { Archive, Upload, Network } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
```
Inside `DocVaultPage`:
```typescript
const navigate = useNavigate()
```
And in `PageHeader`:
```typescript
actions={
  <div className="flex items-center gap-2">
    <Button variant="secondary" onClick={() => navigate('/app/docvault/graph')}>
      <Network className="h-4 w-4" />
      3D Graph View
    </Button>
    <Button onClick={() => setUploadOpen(true)}>
      <Upload />
      Upload
    </Button>
  </div>
}
```

- [ ] **Step 4: Write component test for `DocVaultGraphPage`**

Create `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.test.tsx`:
```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DocVaultGraphPage } from './DocVaultGraphPage'

// Mock 3d-force-graph WebGL engine in jsdom
vi.mock('3d-force-graph', () => {
  return {
    default: () => () => {
      const mockObj = {
        backgroundColor: () => mockObj,
        showNavInfo: () => mockObj,
        nodeRelSize: () => mockObj,
        nodeVal: () => mockObj,
        linkWidth: () => mockObj,
        linkOpacity: () => mockObj,
        linkColor: () => mockObj,
        linkDirectionalParticles: () => mockObj,
        linkDirectionalParticleWidth: () => mockObj,
        linkDirectionalParticleSpeed: () => mockObj,
        nodeThreeObject: () => mockObj,
        onNodeHover: () => mockObj,
        onNodeClick: () => mockObj,
        onBackgroundClick: () => mockObj,
        onNodeDrag: () => mockObj,
        onNodeDragEnd: () => mockObj,
        d3Force: () => ({ distance: () => {}, strength: () => {} }),
        camera: () => ({ position: { distanceTo: () => 100 } }),
        scene: () => ({ add: () => {} }),
        graphData: () => mockObj,
        width: () => mockObj,
        height: () => mockObj,
        cameraPosition: () => ({ x: 0, y: 0, z: 300 }),
        zoomToFit: () => {},
        pauseAnimation: () => {},
        resumeAnimation: () => {},
        _destructor: () => {},
      }
      return mockObj
    },
  }
})

describe('DocVaultGraphPage', () => {
  it('renders top HUD, navigation controls, and back button', () => {
    const qc = new QueryClient()
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <DocVaultGraphPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText(/Back to List/i)).toBeDefined()
    expect(screen.getByPlaceholderText(/Search documents or buckets…/i)).toBeDefined()
    expect(screen.getByText(/By Bucket/i)).toBeDefined()
    expect(screen.getByText(/By Status/i)).toBeDefined()
  })
})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test DocVaultGraphPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx frontend/src/pages/company/docvault/graph/DocVaultGraphPage.test.tsx frontend/src/routes/company.routes.tsx frontend/src/pages/company/docvault/DocVaultPage.tsx
git commit -m "feat(docvault-graph): add DocVaultGraphPage, routing, and header entry link"
```

---

### Task 6: Build Verification, Linting & E2E Validation

**Files:**
- None (Validation across entire codebase)

- [ ] **Step 1: Run TypeScript compiler check**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` completes with 0 errors.

- [ ] **Step 2: Run all unit & integration tests**

Run: `cd frontend && npm test`
Expected: All tests pass.

- [ ] **Step 3: Run ESLint**

Run: `cd frontend && npm run lint`
Expected: 0 warnings and 0 errors.

- [ ] **Step 4: Final Git Commit & Summary**

```bash
git status
git commit --allow-empty -m "chore(docvault-graph): verify clean build and test suite passing"
```
