# DocVault Graph Dynamic Fog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the DocVault 3D graph's fog and label-fade distances adapt continuously to the graph's bounding extent, so all nodes stay visible at overview distance in large vaults while small vaults keep today's look.

**Architecture:** A new pure helper computes the graph's centroid + radius from node positions; a controller class runs a periodic extent pass, lerps `THREE.Fog.near/far` toward targets derived from camera distance and radius (theme values act as floors), and returns a scale factor used to widen the document-label fade band. `GraphCanvas.tsx` feeds the render loop into the controller.

**Tech Stack:** TypeScript, React, three.js (`THREE.Fog`, `THREE.Vector3`), 3d-force-graph, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-25-docvault-graph-dynamic-fog-design.md`

## Global Constraints

- Constants exact values: `NEAR_SPREAD = 0.2`, `FAR_SPREAD = 3.0`, `LERP_RATE = 0.08`, `EXTENT_INTERVAL_FRAMES = 10`, `LABEL_FADE_START = 200`, `LABEL_FADE_END = 420`.
- Theme fog values are floors — never shrink below them: dark near 220 / far 900; light near 260 / far 1100.
- Scale factor `S = fog.far / theme.fogFar`, clamped to ≥ 1.
- `computeGraphExtent` returns null when fewer than 2 positioned nodes; unpositioned/NaN nodes are skipped.
- Do not modify force layout parameters, theme tokens, HUD components, or data hooks.
- Follow existing file style (this codebase uses explanatory comments sparingly).
- Run all commands from `frontend/`.

## File Structure

- Create: `frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts` — extent math + controller + constants. One responsibility: dynamic fog state.
- Test: `frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts` — unit tests for both exports.
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx` — three touch points only: import + ref, mount-effect fog creation, `applyFrame()` loop call + label LOD block, cleanup, theme-effect smoothing carry-over.

---

### Task 1: `computeGraphExtent` pure function

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts`
- Test: `frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts`

**Interfaces:**
- Consumes: `GraphNode` from `../types/graph` (has optional `x?: number; y?: number; z?: number`).
- Produces: `computeGraphExtent(nodes: GraphNode[]): GraphExtent | null` where `interface GraphExtent { centroid: THREE.Vector3; radius: number }`. Also exports constants `NEAR_SPREAD`, `FAR_SPREAD`, `LERP_RATE`, `EXTENT_INTERVAL_FRAMES`, `LABEL_FADE_START`, `LABEL_FADE_END` (used by Tasks 2–3).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- src/pages/company/docvault/graph/lib/dynamicFog.test.ts`
Expected: FAIL — cannot resolve `./dynamicFog` (module does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts`:

```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- src/pages/company/docvault/graph/lib/dynamicFog.test.ts`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts
git commit -m "feat(docvault-graph): add computeGraphExtent helper for dynamic fog"
```

---

### Task 2: `DynamicFogController`

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts` (append class)
- Test: `frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts` (append describe blocks)

**Interfaces:**
- Consumes: `computeGraphExtent`, `GraphExtent`, constants from Task 1; `GraphTheme` from `./theme`; `GraphNode` from `../types/graph`.
- Produces: `class DynamicFogController` with `update(fog: THREE.Fog, cameraPosition: THREE.Vector3, nodes: GraphNode[], theme: GraphTheme): number` returning scale factor `S ≥ 1`. (`nodes` is passed per-call rather than stored so the periodic extent pass automatically tracks drags and data reloads — the spec's "no special-casing" edge case.) Task 3 calls this once per frame inside `applyFrame()`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts`:

```ts
import * as THREE from 'three'
import { DynamicFogController } from './dynamicFog'
import { getGraphTheme } from './theme'

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
```

Note: move the two new imports (`* as THREE from 'three'`, `getGraphTheme`) to the top of the file with the existing imports; Vitest hoists imports so placement above the first `describe` is conventional.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- src/pages/company/docvault/graph/lib/dynamicFog.test.ts`
Expected: FAIL — `DynamicFogController` is not exported.

- [ ] **Step 3: Write the implementation**

Append to `frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts`:

```ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test -- src/pages/company/docvault/graph/lib/dynamicFog.test.ts`
Expected: PASS (9 tests total across both describes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts frontend/src/pages/company/docvault/graph/lib/dynamicFog.test.ts
git commit -m "feat(docvault-graph): add DynamicFogController for spread-aware fog"
```

---

### Task 3: Wire controller into `GraphCanvas.tsx`

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`
- Verify: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.test.tsx` (existing tests must still pass)

**Interfaces:**
- Consumes: `DynamicFogController`, `LABEL_FADE_START`, `LABEL_FADE_END` from `../lib/dynamicFog` (exact signatures from Tasks 1–2).
- Produces: no interface changes — component props and behavior contract unchanged; fog now adapts.

- [ ] **Step 1: Add import and ref**

In `GraphCanvas.tsx`, add after line 8 (`import { buildNeighborSet, ... }`):

```ts
import { DynamicFogController, LABEL_FADE_START, LABEL_FADE_END } from '../lib/dynamicFog'
```

Add next to the other refs (after `spritesRef`, line 55):

```ts
const fogControllerRef = useRef<DynamicFogController | null>(null)
```

- [ ] **Step 2: Create controller in the mount effect**

Replace lines 269–275:

```ts
    if (scene) {
      scene.add(new THREE.AmbientLight(0xffffff, themeObj.ambientIntensity))
      const dirLight = new THREE.DirectionalLight(0xffffff, themeObj.directionalIntensity)
      dirLight.position.set(100, 200, 150)
      scene.add(dirLight)
      scene.fog = new THREE.Fog(themeObj.background, themeObj.fogNear, themeObj.fogNear)
    }
```

with:

```ts
    if (scene) {
      scene.add(new THREE.AmbientLight(0xffffff, themeObj.ambientIntensity))
      const dirLight = new THREE.DirectionalLight(0xffffff, themeObj.directionalIntensity)
      dirLight.position.set(100, 200, 150)
      scene.add(dirLight)
      scene.fog = new THREE.Fog(themeObj.background, themeObj.fogNear, themeObj.fogFar)
    }
    fogControllerRef.current = new DynamicFogController()
```

(Note: the original line 274 ends `themeObj.fogFar` — preserve that exactly.)

- [ ] **Step 3: Call controller once per frame in `applyFrame()`**

Inside `applyFrame()`, after line 298 (`const t = getGraphTheme(themeRef.current)`), add:

```ts
      const fog = scene ? (scene.fog as THREE.Fog | null) : null
      const labelScale =
        fog && fogControllerRef.current
          ? fogControllerRef.current.update(fog, cam.position, dataRef.current.nodes, t)
          : 1
      const labelFadeStart = LABEL_FADE_START * labelScale
      const labelFadeEnd = LABEL_FADE_END * labelScale
```

Reading `scene.fog` fresh each frame matters: the theme effect swaps in a new Fog instance, and mutating a captured stale one would silently do nothing.

- [ ] **Step 4: Use scaled band in the label LOD block**

Replace lines 347–348:

```ts
            if (dist >= 420) lodOpacity = 0
            else if (dist > 200) lodOpacity = (420 - dist) / (420 - 200)
```

with:

```ts
            if (dist >= labelFadeEnd) lodOpacity = 0
            else if (dist > labelFadeStart)
              lodOpacity = (labelFadeEnd - dist) / (labelFadeEnd - labelFadeStart)
```

- [ ] **Step 5: Carry smoothed values across theme switches**

The theme effect (lines 405–420) currently replaces `scene.fog` with a fresh Fog at floor values, which would flash large graphs back to heavy fog on every theme toggle. Replace line 412:

```ts
      scene.fog = new THREE.Fog(t.background, t.fogNear, t.fogFar)
```

with:

```ts
      const prevFog = scene.fog as THREE.Fog | null
      const nextFog = new THREE.Fog(t.background, t.fogNear, t.fogFar)
      if (prevFog) {
        nextFog.near = prevFog.near
        nextFog.far = prevFog.far
      }
      scene.fog = nextFog
```

The controller keeps lerping toward the new theme's targets from these carried-over values — smoothing continues uninterrupted.

- [ ] **Step 6: Clear the controller on unmount**

In the mount effect's cleanup (inside the `return () => { ... }` starting line 377), add before `if (graph) {`:

```ts
      fogControllerRef.current = null
```

- [ ] **Step 7: Run existing component tests and lint/typecheck**

Run:
```bash
npm run test -- src/pages/company/docvault/graph/
npm run lint
npx tsc -b
```
Expected: all graph tests PASS (including pre-existing `GraphCanvas.test.tsx`), lint clean, typecheck clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx
git commit -m "feat(docvault-graph): scale fog and label fade with graph spread"
```

---

### Task 4: Full verification & calibration checklist

**Files:**
- None created or modified (verification only; fix forward if anything fails).

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: verified working software.

- [ ] **Step 1: Run the full frontend suite**

Run: `npm run test`
Expected: full suite PASS with no regressions.

- [ ] **Step 2: Manual verification (requires running app)**

Start the dev server and open `/app/docvault/graph`. Check against the spec:

1. **Large vault:** with many buckets/docs, zoom-to-fit — every node readable, none swallowed by background haze; far side at most lightly fogged.
2. **Small vault:** visually matches today's rendering (fog stays at theme floors).
3. **Zoom-in inspection:** flying close to one cluster, distant clusters still fade for depth cueing.
4. **Labels:** doc labels fade out smoothly and consistently with their spheres; bucket labels always visible.
5. **Theme toggle:** light↔dark switch causes no fog flash; appearance settles within about a second.
6. **Drag/warm-up:** dragging clusters or watching initial settle shows fog gliding, never popping.

If the far-side haze feels too strong/weak at overview, tune `FAR_SPREAD` (larger = clearer far side) and re-check steps 1 and 3. If labels vanish too early on big vaults, confirm `S` is growing by temporarily logging it — do not change the label constants independently of fog behavior.

- [ ] **Step 3: Commit any calibration constant changes**

Only if Step 2 required tuning values in `lib/dynamicFog.ts`:

```bash
git add frontend/src/pages/company/docvault/graph/lib/dynamicFog.ts
git commit -m "tune(docvault-graph): calibrate dynamic fog spread constants"
```
