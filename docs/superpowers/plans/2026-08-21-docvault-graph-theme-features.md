# DocVault 3D Graph — Theme Alignment, Inspector Redesign & Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the DocVault 3D graph with Kubera's "Emerald Prosperity" theme (light/dark), rebuild the node inspector as a tabbed glass panel, and add search spotlight, neighbor focus/isolation, status pulse, and toggleable tag cross-links.

**Architecture:** All graph visuals derive from a new `GraphTheme` token map selected by the app's `useTheme()` hook. Dimming/spotlight is resolved by a pure helper (`resolveDimState`) and applied per-frame in `GraphCanvas`'s existing render loop. New UI state (search query, isolated cluster, showTagLinks) lives in `DocVaultGraphPage` and flows down as props. The inspector keeps its exact mutation logic; only presentation is restructured into tabs.

**Tech Stack:** React + TypeScript, Tailwind (CSS-var design tokens), `three` ^0.185, `3d-force-graph` ^1.80, `framer-motion`, vitest + testing-library.

**Spec:** `docs/superpowers/specs/2026-08-21-docvault-graph-theme-features-design.md`

## Global Constraints

- Frontend commands run in `frontend/`: `npm run test` (vitest run), `npm run lint` (eslint, `--max-warnings 0`), typecheck via `npx tsc --noEmit`.
- Design tokens come from CSS vars (`--bg-primary`, `--accent`, etc.) via Tailwind classes like `bg-bg-surface`, `text-text-muted`, `border-border`. Never hardcode slate/blue hexes in HUD components.
- Graph dark background must be `#0a0e0c`; light background `#f6f7f5` (exact values).
- Existing public behavior/testids of the inspector (mutations, payload shapes) must not change.
- No new npm dependencies (bloom comes from `three/examples/jsm`).

---

### Task 1: Graph theme tokens

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/lib/theme.ts`
- Test: `frontend/src/pages/company/docvault/graph/lib/theme.test.ts`

**Interfaces:**
- Produces: `type GraphThemeMode = 'light' | 'dark'`, `interface GraphTheme`, `GRAPH_THEMES: Record<GraphThemeMode, GraphTheme>`, `getGraphTheme(mode: GraphThemeMode): GraphTheme`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/pages/company/docvault/graph/lib/theme.test.ts
import { describe, it, expect } from 'vitest'
import { GRAPH_THEMES, getGraphTheme } from './theme'

describe('graph themes', () => {
  it('exposes dark and light modes', () => {
    expect(Object.keys(GRAPH_THEMES).sort()).toEqual(['dark', 'light'])
  })

  it('dark mode uses the app emerald-black background', () => {
    expect(getGraphTheme('dark').background).toBe('#0a0e0c')
    expect(getGraphTheme('dark').emissiveMultiplier).toBe(1)
  })

  it('light mode uses warm paper background and reduced emissive', () => {
    const t = getGraphTheme('light')
    expect(t.background).toBe('#f6f7f5')
    expect(t.emissiveMultiplier).toBeLessThan(1)
  })

  it('tag links are gold-tinted in both modes', () => {
    expect(getGraphTheme('dark').linkTag).toContain('224, 181, 102')
    expect(getGraphTheme('light').linkTag).toContain('196, 139, 44')
  })
})
```

(Note: the test body contains only the four `it(...)` blocks.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/lib/theme.test.ts`
Expected: FAIL — cannot resolve `./theme`

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/pages/company/docvault/graph/lib/theme.ts
export type GraphThemeMode = 'light' | 'dark'

export interface GraphTheme {
  mode: GraphThemeMode
  background: string
  fogNear: number
  fogFar: number
  linkBucketDoc: string
  linkTag: string
  particle: string
  selectionRing: string
  bucketRing: string
  spriteText: string
  spriteBgBucket: string
  spriteBgDoc: string
  spriteBorderDoc: string
  emissiveMultiplier: number
  ambientIntensity: number
  directionalIntensity: number
}

export const GRAPH_THEMES: Record<GraphThemeMode, GraphTheme> = {
  dark: {
    mode: 'dark',
    background: '#0a0e0c',
    fogNear: 220,
    fogFar: 900,
    linkBucketDoc: 'rgba(31, 185, 140, 0.28)',
    linkTag: 'rgba(224, 181, 102, 0.18)',
    particle: '#1fb98c',
    selectionRing: '#1fb98c',
    bucketRing: '#e0b566',
    spriteText: '#edf2ee',
    spriteBgBucket: 'rgba(10, 16, 13, 0.92)',
    spriteBgDoc: 'rgba(10, 16, 13, 0.82)',
    spriteBorderDoc: 'rgba(237, 242, 238, 0.18)',
    emissiveMultiplier: 1,
    ambientIntensity: 0.7,
    directionalIntensity: 0.8,
  },
  light: {
    mode: 'light',
    background: '#f6f7f5',
    fogNear: 260,
    fogFar: 1100,
    linkBucketDoc: 'rgba(15, 157, 118, 0.35)',
    linkTag: 'rgba(196, 139, 44, 0.25)',
    particle: '#0f9d76',
    selectionRing: '#0f9d76',
    bucketRing: '#c48b2c',
    spriteText: '#10201a',
    spriteBgBucket: 'rgba(255, 255, 255, 0.94)',
    spriteBgDoc: 'rgba(255, 255, 255, 0.9)',
    spriteBorderDoc: 'rgba(16, 32, 26, 0.18)',
    emissiveMultiplier: 0.45,
    ambientIntensity: 1.1,
    directionalIntensity: 0.9,
  },
}

export function getGraphTheme(mode: GraphThemeMode): GraphTheme {
  return GRAPH_THEMES[mode]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/lib/theme.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/lib/theme.ts frontend/src/pages/company/docvault/graph/lib/theme.test.ts
git commit -m "feat(graph): emerald/light theme token map for 3d graph"
```

---

### Task 2: Dim-state resolver (spotlight / focus / isolation)

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/lib/dimState.ts`
- Test: `frontend/src/pages/company/docvault/graph/lib/dimState.test.ts`

**Interfaces:**
- Consumes: `GraphNode` from `../types/graph`
- Produces: `type DimState = 'normal' | 'highlight' | 'dimmed'`, `DIM_OPACITY = 0.12`, `ISOLATED_DIM_OPACITY = 0.08`, `matchesQuery(node, query): boolean`, `buildNeighborSet(links, focusNodeId): Set<string>`, `resolveDimState(node, neighbors, input): DimState`, `dimOpacity(state, isolatedActive): number`, `interface DimInput { query, hoveredNodeId, selectedNodeId, isolatedClusterId }`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/pages/company/docvault/graph/lib/dimState.test.ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/lib/dimState.test.ts`
Expected: FAIL — cannot resolve `./dimState`

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/pages/company/docvault/graph/lib/dimState.ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/lib/dimState.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/lib/dimState.ts frontend/src/pages/company/docvault/graph/lib/dimState.test.ts
git commit -m "feat(graph): pure dim-state resolver for spotlight/focus/isolation"
```

---

### Task 3: Tag cross-links in useGraphData (threshold ≥1, cap 8/doc, toggle)

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/hooks/useGraphData.ts`
- Test: `frontend/src/pages/company/docvault/graph/hooks/useGraphData.test.ts`

**Interfaces:**
- Produces: `transformToGraphData(buckets, documents, colorMode, visibleBucketIds, showTagLinks? = true)` and `useGraphData(buckets, documents, colorMode, visibleBucketIds, showTagLinks? =  true)` — same `GraphData` return; `tag-shared` links now require ≥1 shared tag, capped at 8 per document, sorted by shared-tag count desc, `strength: 0.08`, `color: ''` (color now supplied by canvas theme).

- [ ] **Step 1: Update the failing tests**

Add to the existing describe block in `useGraphData.test.ts` (reuse the existing mock factories already present in that file):

```ts
it('creates tag-shared links for docs sharing >= 1 tag', () => {
  const data = transformToGraphData(mockBuckets, mockDocs, 'bucket', new Set(['all']))
  const tagLinks = data.links.filter((l) => l.kind === 'tag-shared')
  expect(tagLinks.length).toBeGreaterThanOrEqual(1)
})

it('does not create tag links when docs share no tags', () => {
  const noTags = mockDocs.map((d) => ({ ...d, tags: [] }))
  const data = transformToGraphData(mockBuckets, noTags, 'bucket', new Set(['all']))
  expect(data.links.filter((l) => l.kind === 'tag-shared')).toHaveLength(0)
})

it('respects showTagLinks=false', () => {
  const data = transformToGraphData(mockBuckets, mockDocs, 'bucket', new Set(['all']), false)
  expect(data.links.filter((l) => l.kind === 'tag-shared')).toHaveLength(0)
})

it('caps tag links at 8 per document, prioritizing more shared tags', () => {
  const many = Array.from({ length: 12 }, (_, i) => ({
    ...mockDocs[0],
    id: `extra-${i}`,
    title: `Extra ${i}`,
    tags: ['common'],
  }))
  const docs = [{ ...mockDocs[0], id: 'hub', title: 'Hub', tags: ['common'] }, ...many]
  const data = transformToGraphData(mockBuckets, docs, 'bucket', new Set(['all']))
  const hubLinks = data.links.filter(
    (l) =>
      l.kind === 'tag-shared' &&
      ((l.source as string) === 'doc_hub' || (l.target as string) === 'doc_hub'),
  )
  expect(hubLinks.length).toBeLessThanOrEqual(8)
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/hooks/useGraphData.test.ts`
Expected: FAIL on threshold/cap/toggle assertions (current code requires ≥2 tags, has no cap/toggle)

- [ ] **Step 3: Implement**

In `useGraphData.ts`:

1. Change both signatures to accept a fifth parameter:

```ts
export function transformToGraphData(
  buckets: BucketResponse[],
  documents: DocumentResponse[],
  colorMode: ColorMode,
  visibleBucketIds: Set<string>,
  showTagLinks = true,
): GraphData {

export function useGraphData(
  buckets: BucketResponse[],
  documents: DocumentResponse[],
  colorMode: ColorMode,
  visibleBucketIds: Set<string>,
  showTagLinks = true,
): GraphData {
  return useMemo(
    () => transformToGraphData(buckets, documents, colorMode, visibleBucketIds, showTagLinks),
    [buckets, documents, colorMode, visibleBucketIds, showTagLinks],
  )
}
```

2. Replace the entire "Secondary Links" block (the `for (let i...)` loop) with:

```ts
  // Secondary links between docs sharing >= 1 tag, capped at 8 per doc,
  // prioritized by shared-tag count so strongest relationships survive the cap.
  if (showTagLinks) {
    const candidates: { a: DocumentResponse; b: DocumentResponse; shared: number }[] = []
    for (let i = 0; i < filteredDocs.length; i++) {
      for (let j = i + 1; j < filteredDocs.length; j++) {
        const docA = filteredDocs[i]
        const docB = filteredDocs[j]
        if (!docA.tags?.length || !docB.tags?.length) continue
        const shared = docA.tags.filter((t) => docB.tags.includes(t)).length
        if (shared >= 1) candidates.push({ a: docA, b: docB, shared })
      }
    }
    candidates.sort((x, y) => y.shared - x.shared)

    const perDoc = new Map<string, number>()
    const canLink = (id: string) => (perDoc.get(id) ?? 0) < 8
    for (const c of candidates) {
      if (!canLink(c.a.id) || !canLink(c.b.id)) continue
      perDoc.set(c.a.id, (perDoc.get(c.a.id) ?? 0) + 1)
      perDoc.set(c.b.id, (perDoc.get(c.b.id) ?? 0) + 1)
      links.push({
        source: `doc_${c.a.id}`,
        target: `doc_${c.b.id}`,
        kind: 'tag-shared',
        strength: 0.08,
        color: '',
      })
    }
  }
```

Also update the `bucket-doc` link push to `color: ''` (canvas supplies themed colors by kind).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/hooks/useGraphData.test.ts`
Expected: PASS (all, including pre-existing tests — update any that asserted ≥2-tag behavior)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/hooks/useGraphData.ts frontend/src/pages/company/docvault/graph/hooks/useGraphData.test.ts
git commit -m "feat(graph): tag cross-links >=1 shared tag, cap 8/doc, toggleable"
```

---

### Task 4: Theme-aware label sprites

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/lib/textSprite.ts`
- Test: `frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts` (update)

**Interfaces:**
- Consumes: `GraphTheme` from `./theme`
- Produces: `createNodeSprite(node, theme?: GraphTheme)` — second optional param defaults to `getGraphTheme('dark')` so existing callers/tests keep working. Cache key includes `theme.mode`.

- [ ] **Step 1: Update cache key and drawing colors**

In `textSprite.ts`:

```ts
import { getGraphTheme, type GraphTheme } from './theme'
```

Change `getNodeCacheKey` to accept the theme mode and include it:

```ts
function getNodeCacheKey(node: GraphNode, themeMode: string): string {
  if (node.type === 'bucket') {
    return `${themeMode}:bucket:${node.name}:${node.color}`
  }
  return `${themeMode}:doc:${node.name}:${node.color}:${node.versionNo ?? 1}:${node.status ?? ''}`
}
```

Thread `theme: GraphTheme` through `createTextTexture(node, theme)`, `getOrCreateTexture(node, theme)`, and `createNodeSprite(node, theme = getGraphTheme('dark'))`. Replace hardcoded colors in `createTextTexture`:

| Line today | Replace with |
|---|---|
| `ctx.fillStyle = isBucket ? 'rgba(15, 23, 42, 0.92)' : 'rgba(15, 23, 42, 0.82)'` | `ctx.fillStyle = isBucket ? theme.spriteBgBucket : theme.spriteBgDoc` |
| `ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)'` (doc border) | `ctx.strokeStyle = theme.spriteBorderDoc` |
| `ctx.fillStyle = isBucket ? '#FFFFFF' : '#F1F5F9'` | `ctx.fillStyle = theme.spriteText` |
| version badge fill `'rgba(255, 255, 255, 0.12)'` | `isBucket ? 'rgba(255, 255, 255, 0.12)' : theme.spriteBorderDoc` |

- [ ] **Step 2: Update the test**

In `textSprite.test.ts`, existing calls stay valid (optional param). Add:

```ts
import { getGraphTheme } from './theme'

it('produces distinct cache entries per theme', () => {
  const node = makeNode() // reuse existing factory in this file
  const a = createNodeSprite(node, getGraphTheme('dark'))
  const b = createNodeSprite(node, getGraphTheme('light'))
  expect(a).not.toBe(b)
})
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/lib/textSprite.test.ts`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/lib/textSprite.ts frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts
git commit -m "feat(graph): theme-aware label sprites"
```

---

### Task 5: GraphCanvas — theme prop, fog, bloom, kind-based link styling

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`

**Interfaces:**
- Consumes: `getGraphTheme`, `GraphThemeMode` (Task 1); `createNodeSprite(node, theme)` (Task 4)
- Produces: new optional props `theme?: GraphThemeMode` (default `'dark'`), `searchQuery?: string`, `isolatedClusterId?: string | null`, `onIsolateCluster?: (bucketRawId: string) => void`. Also exports nothing new; internal visual registry `nodesVisualRef: Map<string, { group, sphereMat, baseEmissive, baseScale, sprite }>` consumed by Task 6.

- [ ] **Step 1: Add imports and props**

```tsx
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { getGraphTheme, type GraphThemeMode } from '../lib/theme'
```

Extend `GraphCanvasProps`:

```tsx
export interface GraphCanvasProps {
  data: GraphData
  selectedNodeId?: string | null
  onSelectNode?: (node: GraphNode | null) => void
  hoveredNodeId?: string | null
  onHoverNode?: (node: GraphNode | null) => void
  graphInstanceRef?: ...
  className?: string
  theme?: GraphThemeMode
  searchQuery?: string
  isolatedClusterId?: string | null
  onIsolateCluster?: (bucketRawId: string) => void
}
```

Destructure with defaults `theme = 'dark'`, `searchQuery = ''`, `isolatedClusterId = null`. Mirror each into a ref (same pattern as `selectedNodeIdRef`) so the mount effect reads current values without re-initializing.

- [ ] **Step 2: Apply theme in the mount effect**

After `const scene = graph.scene()` replace the lighting block with:

```tsx
const themeObj = getGraphTheme(themeRef.current)

if (scene) {
  scene.add(new THREE.AmbientLight(0xffffff, themeObj.ambientIntensity))
  const dirLight = new THREE.DirectionalLight(0xffffff, themeObj.directionalIntensity)
  dirLight.position.set(100, 200, 150)
  scene.add(dirLight)
  scene.fog = new THREE.Fog(themeObj.background, themeObj.fogNear, themeObj.fogFar)
}

// Bloom in dark mode only — degrade silently on failure
if (themeRef.current === 'dark') {
  try {
    const composer = graph.postProcessingComposer()
    const width = containerRef.current?.clientWidth || window.innerWidth
    const height = containerRef.current?.clientHeight || window.innerHeight
    composer.addPass(new UnrealBloomPass(new THREE.Vector2(width, height), 0.35, 0.6, 0.55))
  } catch {
    // no bloom
  }
}
```

And change the init chain: `.backgroundColor(themeObj.background)` instead of `'#0B0F17'`.

Replace `.linkColor(...)`, `.linkDirectionalParticleColor(...)`, and add curvature:

```tsx
.linkColor((link) => {
  const t = getGraphTheme(themeRef.current)
  return (link as GraphLink).kind === 'bucket-doc' ? t.linkBucketDoc : t.linkTag
})
.linkDirectionalParticleColor(() => getGraphTheme(themeRef.current).particle)
.linkCurvature((link) => ((link as GraphLink).kind === 'tag-shared' ? 0.25 : 0))
```

- [ ] **Step 3: Theme-aware node objects**

Inside `nodeThreeObject`: pass theme to the sprite (`createNodeSprite(node, getGraphTheme(themeRef.current))`), multiply emissive intensity by `getGraphTheme(themeRef.current).emissiveMultiplier`, change the selection ring color from `'#FFFFFF'` to `getGraphTheme(themeRef.current).selectionRing`, and the bucket orbital ring material color from `node.color` to `getGraphTheme(themeRef.current).bucketRing`.

Register visuals for the render loop (used again in Task 6):

```tsx
const group = new THREE.Group()
// ...existing sphere/ring/sprite construction...
visualRegistryRef.current.set(node.id, {
  group,
  sphereMat: material,
  baseEmissive: material.emissiveIntensity,
  baseScale: 1,
  sprite,
})
return group
```

Declare near the other refs:

```tsx
const visualRegistryRef = useRef<Map<string, {
  group: THREE.Group
  sphereMat: THREE.MeshStandardMaterial
  baseEmissive: number
  baseScale: number
  sprite: THREE.Sprite
}>>(new Map())
```

Clear it at the top of the mount effect alongside `spritesRef.current.clear()`.

- [ ] **Step 4: Re-apply theme when the theme prop changes**

```tsx
useEffect(() => {
  const graph = graphObjRef.current
  if (!graph) return
  const t = getGraphTheme(theme)
  graph.backgroundColor(t.background)
  const scene = graph.scene()
  if (scene) {
    scene.fog = new THREE.Fog(t.background, t.fogNear, t.fogFar)
    scene.traverse((obj) => {
      if ((obj as THREE.AmbientLight).isAmbientLight) (obj as THREE.AmbientLight).intensity = t.ambientIntensity
      if ((obj as THREE.DirectionalLight).isDirectionalLight) (obj as THREE.DirectionalLight).intensity = t.directionalIntensity
    })
  }
  // rebuild node objects so sprites/materials pick up new colors
  graph.nodeThreeObject(graph.nodeThreeObject())
}, [theme])
```

- [ ] **Step 5: Double-click detection for cluster isolation**

Add refs and wire into `onNodeClick`:

```tsx
const lastClickRef = useRef<{ id: string; time: number }>({ id: '', time: 0 })
```

At the top of `.onNodeClick((node) => {...})`:

```tsx
const now = Date.now()
const n = node as GraphNode
if (lastClickRef.current.id === n.id && now - lastClickRef.current.time < 350) {
  lastClickRef.current = { id: '', time: 0 }
  if (n.type === 'bucket') onIsolateClusterRef.current?.(n.rawId)
  onSelectNodeRef.current?.(n)
  return
}
lastClickRef.current = { id: n.id, time: now }
onSelectNodeRef.current?.(n)
```

- [ ] **Step 6: Verify**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphCanvas.test.tsx && npx tsc --noEmit`
Expected: PASS (new props are optional; update mocks if the test file stubs `postProcessingComposer` — add `postProcessingComposer: vi.fn(() => ({ addPass: vi.fn() }))` to the graph instance mock)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx frontend/src/pages/company/docvault/graph/components/GraphCanvas.test.tsx
git commit -m "feat(graph): theme-aware canvas with fog, bloom, gold/emerald accents, dblclick isolate"
```

---

### Task 6: GraphCanvas — unified render loop (LOD + dimming + status pulse)

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`

**Interfaces:**
- Consumes: `resolveDimState`, `buildNeighborSet`, `dimOpacity` (Task 2); visual registry (Task 5)
- Produces: single per-frame loop replacing the `setInterval`; pulsing for `action_required`/`overdue`.

- [ ] **Step 1: Replace the LOD interval with a unified loop**

Delete the existing `setInterval` block. In its place:

```tsx
const PULSE_STATUSES = new Set(['action_required', 'overdue'])

const applyFrame = () => {
  const cam = graph.camera()
  if (!cam) return
  const t = getGraphTheme(themeRef.current)
  const now = performance.now() / 1000
  const pulse = Math.sin((now * Math.PI * 2) / 1.4) // ~1.4s cycle

  const input = {
    query: searchQueryRef.current,
    hoveredNodeId: hoveredNodeIdRef.current,
    selectedNodeId: selectedNodeIdRef.current,
    isolatedClusterId: isolatedClusterIdRef.current,
  }
  const focusId = input.hoveredNodeId ?? input.selectedNodeId
  const neighbors = buildNeighborSet(dataRef.current.links, focusId)
  const isolatedActive = !!input.isolatedClusterId || !!input.query.trim()

  dataRef.current.nodes.forEach((node) => {
    const vis = visualRegistryRef.current.get(node.id)
    if (!vis) return

    // Dim / spotlight
    const state = resolveDimState(node, neighbors, input)
    const opacity = dimOpacity(state, isolatedActive)
    vis.group.traverse((obj) => {
      const mesh = obj as THREE.Mesh
      if (mesh.material && 'opacity' in mesh.material) {
        ;(mesh.material as THREE.Material).transparent = true
        ;(mesh.material as THREE.Material).opacity = opacity
      }
    })

    // Status pulse (only when not dimmed)
    const shouldPulse = node.type === 'document' && !!node.status && PULSE_STATUSES.has(node.status)
    if (shouldPulse && opacity === 1) {
      const s = 1 + 0.1 * pulse
      vis.group.scale.setScalar(s)
      vis.sphereMat.emissiveIntensity = vis.baseEmissive * (1 + 0.5 * pulse)
    } else {
      vis.group.scale.setScalar(1)
      vis.sphereMat.emissiveIntensity =
        vis.baseEmissive * t.emissiveMultiplier * (state === 'highlight' ? 1.25 : 1)
    }

    // Label LOD (existing behavior) × dim factor
    const sprite = vis.sprite
    if (sprite && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
      const dist = cam.position.distanceTo(new THREE.Vector3(node.x, node.y, node.z))
      const isBucket = node.type === 'bucket'
      let lodOpacity = 1
      if (!isBucket) {
        if (dist >= 420) lodOpacity = 0
        else if (dist > 200) lodOpacity = (420 - dist) / (420 - 200)
      }
      sprite.material.opacity = opacity * Math.max(0, Math.min(1, lodOpacity))
      sprite.visible = sprite.material.opacity > 0.001
    }
  })
}

// Prefer the library's frame hook; fall back to an interval.
const g = graph as unknown as { onRenderFramePre?: (cb: () => void) => unknown }
if (typeof g.onRenderFramePre === 'function') {
  g.onRenderFramePre(applyFrame)
} else {
  const interval = setInterval(applyFrame, 60)
  // remember to clear in cleanup below
}
```

Update the cleanup function: remove `clearInterval(interval)` if using `onRenderFramePre`, or keep it for the fallback path (store the interval id in a local `let intervalId: ReturnType<typeof setInterval> | undefined`).

Note: because the loop now handles sprite opacity including LOD, remove the old standalone `updateSpriteLOD` interval usage; keep `updateSpriteLOD` exported in `textSprite.ts` (still used by tests) but it is no longer called here.

- [ ] **Step 2: Link dimming during focus**

Below the loop setup, add a `useEffect` that refreshes link visibility when focus changes:

```tsx
useEffect(() => {
  const graph = graphObjRef.current
  if (!graph) return
  const focusId = hoveredNodeId ?? selectedNodeId
  const neighbors = buildNeighborSet(dataRef.current.links, focusId)
  const active = !!(searchQuery.trim() || isolatedClusterId || focusId)
  if (!active) {
    graph.linkVisibility(() => true)
    return
  }
  graph.linkVisibility((link) => {
    const l = link as GraphLink
    const s = typeof l.source === 'string' ? l.source : l.source.id
    const t = typeof l.target === 'string' ? l.target : l.target.id
    if (isolatedClusterId) {
      const inCluster = (id: string) => id === `bucket_${isolatedClusterId}` || id.startsWith('doc_')
      return s === `bucket_${isolatedClusterId}` || t === `bucket_${isolatedClusterId}` ||
        (s.startsWith('doc_') && t.startsWith('doc_') &&
          sameCluster(s, t, dataRef.current.nodes))
    }
    return neighbors.has(s) || neighbors.has(t) || s === focusId || t === focusId
  })
}, [hoveredNodeId, selectedNodeId, searchQuery, isolatedClusterId])
```

with a small module-level helper:

```tsx
function sameCluster(docA: string, docB: string, nodes: GraphNode[]): boolean {
  const m = new Map(nodes.map((n) => [n.id, n]))
  const a = m.get(docA)
  const b = m.get(docB)
  return (a?.bucketId ?? 'uncategorized') === (b?.bucketId ?? 'uncategorized')
}
```

If `linkVisibility` is unavailable at runtime (older builds), guard: `const anyG = graph as any; if (typeof anyG.linkVisibility !== 'function') return`.

- [ ] **Step 3: Verify**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphCanvas.test.tsx && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx
git commit -m "feat(graph): spotlight dimming, neighbor focus, isolation and status pulse"
```

---

### Task 7: Page wiring (theme, search, isolation, tag-link toggle)

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx`

**Interfaces:**
- Consumes: all new props from Tasks 5–6; `useTheme` from `@/lib/useTheme`; `useGraphData(..., showTagLinks)`
- Produces: page-level state `searchQuery`, `isolatedClusterId`, `showTagLinks`; handlers passed to HUD/Legend/Canvas.

- [ ] **Step 1: Add state and wiring**

```tsx
import { useTheme } from '@/lib/useTheme'
```

Inside the component:

```tsx
const { theme } = useTheme()
const [searchQuery, setSearchQuery] = useState('')
const [isolatedClusterId, setIsolatedClusterId] = useState<string | null>(null)
const [showTagLinks, setShowTagLinks] = useState(true)

const graphData = useGraphData(buckets, documents, colorMode, visibleBucketIds, showTagLinks)
```

Extend the existing Escape handler to also clear isolation:

```tsx
if (e.key === 'Escape') {
  setSelectedNode(null)
  setIsolatedClusterId(null)
}
```

Add handler:

```tsx
const handleIsolateCluster = (bucketRawId: string) => {
  setIsolatedClusterId((prev) => (prev === bucketRawId ? null : bucketRawId))
}
```

- [ ] **Step 2: Pass props down**

```tsx
<GraphHud
  {...existingProps}
  searchQuery={searchQuery}
  onSearchQueryChange={setSearchQuery}
/>

<GraphCanvas
  {...existingProps}
  theme={theme}
  searchQuery={searchQuery}
  isolatedClusterId={isolatedClusterId}
  onIsolateCluster={handleIsolateCluster}
/>

<BucketSummaryCard
  {...existingProps}
  onIsolate={() => setIsolatedClusterId(selectedNode!.rawId)}
  isIsolated={isolatedClusterId === selectedNode?.rawId}
/>

<GraphLegend
  {...existingProps}
  showTagLinks={showTagLinks}
  onToggleTagLinks={setShowTagLinks}
/>
```

Also render an isolation pill above the canvas (top-center):

```tsx
{isolatedClusterId && (
  <div
    data-testid="isolation-pill"
    className="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 rounded-full bg-bg-surface/90 backdrop-blur-md border border-border px-3 py-1.5 text-xs text-text-primary shadow-lg"
  >
    <span>
      Isolated:{' '}
      {buckets.find((b) => b.id === isolatedClusterId)?.name ??
        (isolatedClusterId === 'uncategorized' ? 'Uncategorized' : isolatedClusterId)}
    </span>
    <button
      type="button"
      data-testid="isolation-exit-btn"
      onClick={() => setIsolatedClusterId(null)}
      aria-label="Exit isolation"
      className="text-text-muted hover:text-text-primary"
    >
      <X className="w-3.5 h-3.5" />
    </button>
  </div>
)}
```

(import `X` from `lucide-react`.)

- [ ] **Step 3: Verify**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/DocVaultGraphPage.test.tsx`
Expected: may FAIL until Tasks 8–10 add the new props to child components — that's expected mid-stream; proceed to Task 8 before running the full suite.

- [ ] **Step 4: Commit (after Task 8 compiles)**

```bash
git add frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx
git commit -m "feat(graph): wire theme, search spotlight, isolation and tag-link toggle into page"
```

---

### Task 8: GraphHud — lift search query + design-token restyle

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphHud.tsx`
- Test: `frontend/src/pages/company/docvault/graph/components/GraphHud.test.tsx` (update)

**Interfaces:**
- Produces: new required props `searchQuery: string`, `onSearchQueryChange: (q: string) => void`. HUD becomes controlled: internal `searchQuery` state is removed; typing calls `onSearchQueryChange`. Enter key selects the first result (`handleSelectSearchResult(searchResults[0])`). All `slate-*` glass classes replaced with tokens.

- [ ] **Step 1: Make search controlled**

Remove `const [searchQuery, setSearchQuery] = useState('')`. Add props:

```tsx
export interface GraphHudProps {
  // ...existing...
  searchQuery: string
  onSearchQueryChange: (q: string) => void
}
```

Replace every `setSearchQuery(x)` with `onSearchQueryChange(x)` and read `searchQuery` from props. On the input add:

```tsx
onKeyDown={(e) => {
  if (e.key === 'Enter' && searchResults.length > 0) {
    handleSelectSearchResult(searchResults[0])
  }
  if (e.key === 'Escape') {
    onSearchQueryChange('')
    setIsSearchOpen(false)
  }
}}
```

- [ ] **Step 2: Token restyle (mechanical replacement)**

| Old class fragment | New class fragment |
|---|---|
| `bg-slate-900/85 backdrop-blur-md border border-slate-700/60` | `bg-bg-surface/85 backdrop-blur-md border border-border` |
| `bg-slate-900/95 ... border-slate-700/80` (dropdowns) | `bg-bg-surface/95 ... border-border` |
| `text-slate-200` / `text-slate-100` / `hover:text-white` | `text-text-primary` / `hover:text-text-primary` |
| `text-slate-300` | `text-text-secondary` |
| `text-slate-400` / `placeholder-slate-400` | `text-text-muted` / `placeholder-text-muted` |
| `hover:bg-slate-800/90` / `hover:bg-slate-800/80` | `hover:bg-bg-raised/80` |
| `border-slate-800` / `border-slate-800/60` | `border-border` |
| `bg-slate-800` (tag chips) | `bg-bg-inset` |
| `focus:ring-emerald-500/50 focus:border-emerald-500/80` | `focus:ring-accent-ring focus:border-accent` |
| `bg-emerald-600 text-white` (active segment) | `bg-accent text-accent-contrast` |
| `text-emerald-400 hover:text-emerald-300` | `text-accent hover:text-accent-hover` |
| `bg-emerald-500/20 text-emerald-300 border-emerald-500/30` | `bg-accent-subtle text-accent border-accent/30` |
| `bg-sky-500/20 text-sky-300 border-sky-500/30` | `bg-bg-inset text-text-secondary border-border` |
| `ring-slate-500` | `ring-border-strong` |

Keep `bg-emerald-400 animate-pulse` dot in the breadcrumb → change to `bg-accent animate-pulse`.

- [ ] **Step 3: Update tests**

In `GraphHud.test.tsx`, wrap renders with the two new required props:

```tsx
const baseProps = {
  searchQuery: '',
  onSearchQueryChange: vi.fn(),
}
```

Add a test:

```ts
it('lifts typed query to parent and selects first result on Enter', async () => {
  const onSearchQueryChange = vi.fn()
  const onSelectNode = vi.fn()
  render(<GraphHud {...base} searchQuery="" onSearchQueryChange={onSearchQueryChange} onSelectNode={onSelectNode} data={data} />)
  const input = screen.getByTestId('graph-search-input')
  await user.type(input, 'tax')
  expect(onSearchQueryChange).toHaveBeenCalledWith('t')
  await user.keyboard('{Enter}')
  expect(onSelectNode).toHaveBeenCalled()
})
```

- [ ] **Step 4: Verify + commit**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphHud.test.tsx && npx tsc --noEmit`
Expected: PASS

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphHud.tsx frontend/src/pages/company/docvault/graph/components/GraphHud.test.tsx frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx
git commit -m "feat(graph): controlled theme-token HUD search with Enter-to-select"
```

---

### Task 9: GraphLegend — tag-links toggle + token restyle

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphLegend.tsx`
- Test: `frontend/src/pages/company/docvault/graph/components/GraphLegend.test.tsx` (update)

**Interfaces:**
- Produces: new optional props `showTagLinks?: boolean`, `onToggleTagLinks?: (v: boolean) => void`

- [ ] **Step 1: Add the toggle row**

New props on the component. Inside the legend body, under "Node Types", add:

```tsx
{onToggleTagLinks && (
  <label
    data-testid="legend-tag-links-toggle"
    className="flex items-center justify-between cursor-pointer select-none pt-1"
  >
    <span className="text-[11px] text-text-secondary">Shared-tag links</span>
    <input
      type="checkbox"
      checked={showTagLinks ?? true}
      onChange={(e) => onToggleTagLinks(e.target.checked)}
      className="accent-[var(--accent)] w-3.5 h-3.5"
    />
  </label>
)}
```

Apply the same class-replacement table from Task 8 Step 2 to all slate classes in this file.

- [ ] **Step 2: Update tests + verify**

Add to `GraphLegend.test.tsx`:

```ts
it('renders tag-links toggle and reports changes', async () => {
  const onToggleTagLinks = vi.fn()
  render(<GraphLegend colorMode="bucket" showTagLinks onToggleTagLinks={onToggleTagLinks} />)
  const toggle = screen.getByTestId('legend-tag-links-toggle')
  const checkbox = within(toggle).getByRole('checkbox')
  expect(checkbox).toBeChecked()
  await user.click(checkbox)
  expect(onToggleTagLinks).toHaveBeenCalledWith(false)
})
```

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphLegend.test.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphLegend.tsx frontend/src/pages/company/docvault/graph/components/GraphLegend.test.tsx
git commit -m "feat(graph): legend tag-links toggle and token-based styling"
```

---

### Task 10: BucketSummaryCard — token restyle + isolate action

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/BucketSummaryCard.tsx`

**Interfaces:**
- Produces: new optional props `onIsolate?: () => void`, `isIsolated?: boolean`

- [ ] **Step 1: Restyle and extend**

Add the two props. Replace card shell classes:

```
old: bg-slate-900/90 backdrop-blur-md border border-slate-700/70 ... text-slate-100
new: bg-bg-surface/90 backdrop-blur-md border border-border ... text-text-primary
```

Apply the Task 8 class table throughout (`slate-400`→`text-text-muted`, `border-slate-800`→`border-border`, `hover:bg-slate-800`→`hover:bg-bg-raised`, amber badge stays as-is since it maps to pending semantics, `bg-emerald-500/20 text-emerald-300 border-emerald-500/30`→`bg-accent-subtle text-accent border-accent/30`).

Change the action button area to offer both actions:

```tsx
<div className="mt-4 pt-3 border-t border-border flex flex-col gap-2">
  {onFocusCluster && (
    <button
      type="button"
      data-testid="focus-cluster-btn"
      onClick={() => onFocusCluster(node)}
      className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-accent hover:bg-accent-hover text-accent-contrast font-medium text-xs transition-colors shadow-md focus:outline-none focus:ring-1 focus:ring-accent-ring"
    >
      <Folder className="w-3.5 h-3.5" />
      <span>Focus Cluster</span>
    </button>
  )}
  {onIsolate && (
    <button
      type="button"
      data-testid="isolate-cluster-btn"
      onClick={onIsolate}
      className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg border border-border bg-bg-raised hover:bg-bg-inset text-text-primary font-medium text-xs transition-colors focus:outline-none focus:ring-1 focus:ring-accent-ring"
    >
      <Layers className="w-3.5 h-3.5" />
      <span>{isIsolated ? 'Show all clusters' : 'Isolate cluster'}</span>
    </button>
  )}
</div>
```

(`Layers` is already imported.)

- [ ] **Step 2: Verify + commit**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph && npx tsc --noEmit`
Expected: PASS (page from Task 7 now compiles)

```bash
git add frontend/src/pages/company/docvault/graph/components/BucketSummaryCard.tsx
git commit -m "feat(graph): token-styled bucket summary card with isolate action"
```

---

### Task 11: Inspector — tabbed glass panel rewrite

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx`
- Test: `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx` (update)

**Interfaces:**
- Props contract unchanged: `{ document, buckets, open, onClose }`. All mutations, payloads, toasts, lock/archive rules unchanged. New internal state: `tab: 'overview' | 'edit' | 'versions'` (reset to `'overview'` whenever `document.id` changes).

- [ ] **Step 1: Rewrite the component**

Keep ALL existing handler functions (`changeStatus`, `changeBucket`, `saveTitle`, `changeEditable`, `saveTags`, `restore`, `doArchive`, `handleNewVersion`, `downloadVersion`, `wrap`) exactly as they are. Replace only the JSX return and add tab state:

```tsx
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, FileText, Pencil, History } from 'lucide-react'
import { cn } from '@/lib/cn'

type Tab = 'overview' | 'edit' | 'versions'
const TABS: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: 'overview', label: 'Overview', icon: FileText },
  { key: 'edit', label: 'Edit', icon: Pencil },
  { key: 'versions', label: 'Versions', icon: History },
]
```

Reset tab on document change (extend the existing `useEffect`):

```tsx
const [tab, setTab] = useState<Tab>('overview')
useEffect(() => {
  setTagsInput(document?.tags.join(', ') ?? '')
  setTitleInput(document?.title ?? '')
  setTab('overview')
}, [document])
```

New JSX structure (testids preserved where they existed):

```tsx
<div
  data-testid="graph-document-inspector"
  className="absolute top-18 right-4 w-96 max-h-[calc(100vh-6rem)] overflow-hidden rounded-2xl border border-border bg-bg-surface/95 backdrop-blur-md shadow-2xl z-30 flex flex-col"
>
  {/* Header */}
  <div className="p-4 pb-3 border-b border-border">
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-2.5 min-w-0 flex-1">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
          <FileText className="w-4 h-4" />
        </span>
        <div className="min-w-0">
          <h2
            className="text-base font-semibold text-text-primary truncate leading-snug"
            title={document.title}
            data-testid="inspector-document-title"
          >
            {document.title}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-text-muted">
            <StatusBadge status={document.status} />
            <span>·</span>
            <span className="truncate max-w-[140px]" title={bucketName}>{bucketName}</span>
            <span>·</span>
            <span className="font-mono">v{currentVersionNo}</span>
          </div>
        </div>
      </div>
      <button
        type="button" onClick={onClose} aria-label="Close"
        data-testid="inspector-close-btn"
        className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-subtle transition-colors shrink-0"
      >
        <X className="w-4 h-4" />
      </button>
    </div>

    {/* Meta row */}
    <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-text-muted">
      <span>Created by <span className="font-medium text-text-primary">{document.created_by_name ?? 'Unknown'}</span></span>
      <span>·</span>
      <span>Updated <span className="font-medium text-text-primary">{document.updated_at ? formatDate(document.updated_at) : '—'}</span></span>
    </div>

    {/* Tabs */}
    <div role="tablist" className="mt-3 grid grid-cols-3 gap-1 rounded-xl bg-bg-inset p-1">
      {TABS.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          role="tab"
          type="button"
          aria-selected={tab === key}
          data-testid={`inspector-tab-${key}`}
          onClick={() => setTab(key)}
          className={cn(
            'flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors',
            tab === key
              ? 'bg-bg-surface text-text-primary shadow-sm'
              : 'text-text-muted hover:text-text-primary',
          )}
        >
          <Icon className="w-3.5 h-3.5" />
          {label}
        </button>
      ))}
    </div>
  </div>

  {/* Tab content */}
  <div className="flex-1 overflow-y-auto p-4">
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={tab}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.15 }}
      >
        {tab === 'overview' && <OverviewTab ... />}
        {tab === 'edit' && <EditTab ... />}
        {tab === 'versions' && <VersionsTab ... />}
      </motion.div>
    </AnimatePresence>
  </div>

  {/* Danger zone footer */}
  <div className="border-t border-border p-3">
    {isArchived ? (
      <Button variant="secondary" onClick={restore} loading={update.isPending} className="w-full">
        Restore document
      </Button>
    ) : (
      <Button variant="danger" onClick={() => setConfirmArchive(true)} className="w-full">
        Archive document
      </Button>
    )}
  </div>
</div>
```

Define the three tab sections as small local components in the same file (below the main component), receiving exactly the props they use:

- `OverviewTab({ document, currentVersion })` — read-only fact grid:

```tsx
function OverviewTab({ document, currentVersion }: { document: DocumentResponse; currentVersion?: DocumentResponse['versions'][number] }) {
  const facts: [string, string][] = [
    ['Created by', document.created_by_name ?? 'Unknown'],
    ['Current version by', currentVersion?.uploaded_by_name ?? 'Unknown'],
    ['Current version size', currentVersion ? formatBytes(currentVersion.size_bytes) : '—'],
    ['Versions', String(document.versions.length)],
    ['Updated', document.updated_at ? formatDate(document.updated_at) : '—'],
  ]
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {facts.map(([k, v]) => (
          <div key={k} className="col-span-2 grid grid-cols-[130px_1fr] items-baseline gap-3">
            <dt className="text-xs text-text-muted">{k}</dt>
            <dd className="text-sm text-text-primary truncate" title={v}>{v}</dd>
          </div>
        ))}
      </dl>
      <div>
        <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">Tags</h3>
        {document.tags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {document.tags.map((t) => (
              <span key={t} className="rounded-full bg-bg-inset border border-border px-2 py-0.5 text-xs text-text-secondary">
                {t}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-muted">No tags</p>
        )}
      </div>
    </div>
  )
}
```

- `EditTab` — move the existing Name field+Save, Editable Switch, Status Select, Bucket Select, Tags field+Save JSX verbatim into it (props: `document, buckets, locked, isArchived, titleInput, setTitleInput, tagsInput, setTagsInput, saveTitle, saveTags, changeEditable, changeStatus, changeBucket, update`).

- `VersionsTab` — move the existing version history `<ul>` and upload dropzone JSX verbatim (props: `document, sortedVersions, downloadVersion, handleNewVersion, uploadVersion`). The archived/locked notices ("Archived — new versions are disabled." / "This document is locked (new versions not allowed).") stay in this tab.

Keep `<ConfirmDialog>` block unchanged after the panel div.

- [ ] **Step 2: Update tests**

Changes needed in `GraphDocumentInspector.test.tsx` (mutations/payloads unchanged, so most tests just need navigation to the right tab first):

1. Add a helper and use it in edit/version tests:

```tsx
async function goToTab(user: UserEvent, tab: 'edit' | 'versions') {
  await user.click(screen.getByTestId(`inspector-tab-${tab}`))
}
```

2. Tests touching rename/tags/status/bucket/editable switch → call `await goToTab(user, 'edit')` first.
3. Version history, download, upload-version tests → `await goToTab(user, 'versions')` first.
4. Header/metadata/close/archive/restore/locked tests work unchanged (header + footer always visible); the archived test's `'Archived documents are locked.'` assertion moves behind the Edit tab — either navigate to Edit first, or drop that one line and keep the Versions-tab notice assertion.
5. Add new tests:

```tsx
it('defaults to Overview tab showing read-only facts and tag chips', () => {
  renderComponent(<GraphDocumentInspector open document={mockDoc} buckets={mockBuckets} onClose={vi.fn()} />)
  expect(screen.getByTestId('inspector-tab-overview').getAttribute('aria-selected')).toBe('true')
  expect(screen.getByText('board')).toBeInTheDocument()
  expect(screen.getByText('minutes')).toBeInTheDocument()
  expect(screen.queryByDisplayValue('Q3 Board Minutes')).not.toBeInTheDocument()
})

it('switches tabs and resets to Overview when document changes', async () => {
  const user = userEvent.setup()
  const { rerender } = renderComponent(<GraphDocumentInspector open document={mockDoc} buckets={mockBuckets} onClose={vi.fn()} />)
  await user.click(screen.getByTestId('inspector-tab-edit'))
  expect(screen.getByTestId('inspector-tab-edit').getAttribute('aria-selected')).toBe('true')
  rerender(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <ToastProvider>
        <GraphDocumentInspector open document={{ ...mockDoc, id: 'doc-2' }} buckets={mockBuckets} onClose={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  expect(screen.getByTestId('inspector-tab-overview').getAttribute('aria-selected')).toBe('true')
})
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx
git commit -m "feat(graph): tabbed glass inspector (Overview/Edit/Versions) with danger-zone footer"
```

---

### Task 12: Full verification & cleanup

**Files:** none created; sweep only.

- [ ] **Step 1: Full test suite**

Run: `cd frontend && npm run test`
Expected: all suites PASS. Fix any fallout from prop signature changes (search for remaining callers passing old arg counts: `grep -rn "useGraphData(" frontend/src`).

- [ ] **Step 2: Lint + typecheck**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: clean (lint has `--max-warnings 0`).

- [ ] **Step 3: Manual smoke check**

Run: `cd frontend && npm run dev` — verify against a running backend:
- Toggle theme (TopBar) → reopen graph → background `#f6f7f5` in light, `#0a0e0c` in dark; bloom only in dark.
- Type in HUD search → non-matches dim; Enter flies to best match.
- Hover node → neighbors lit, rest dim. Double-click bucket → isolation pill appears; Esc exits.
- `action_required`/`overdue` docs pulse.
- Legend toggle removes/adds gold curved tag links.
- Click doc node → tabbed inspector opens on Overview; Edit/Versions behave as before; archive confirm still works.

- [ ] **Step 4: Final commit**

```bash
git add -A frontend/src/pages/company/docvault/graph
git commit -m "chore(graph): final cleanup for theme alignment and features"
```
