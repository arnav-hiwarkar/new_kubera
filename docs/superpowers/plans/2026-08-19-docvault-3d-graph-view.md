# DocVault 3D Knowledge Graph View Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the DocVault 3D Graph View with: (1) elevated billboard text labels positioned cleanly above node spheres with zero occlusion, (2) an embedded, floating glassmorphic document inspector card on the top-right with full editing and version download capabilities (replacing the slide-over drawer), and (3) an edge-to-edge fullscreen 3D viewport.

**Architecture:** 
- Billboard canvas text sprites are anchored at bottom-center `(0.5, 0)` and elevated to `y = node.size + (isBucket ? 6 : 4)` with `depthTest = false` and `renderOrder = 999`.
- A dedicated `<GraphDocumentInspector />` component floats statically in the top-right corner of the 3D space (`w-96`, glassmorphic styling), maintaining full background 3D canvas interactivity.
- `DocVaultGraphPage` renders as a fixed full-viewport overlay (`fixed inset-0 z-40 bg-[#0B0F17]`), giving a distraction-free Obsidian-style 3D experience.

**Tech Stack:** React 18, TypeScript, Three.js, `3d-force-graph`, `@tanstack/react-query`, Tailwind CSS, Lucide React, Vitest.

## Global Constraints

- Protected under `ModuleGuard moduleId="docvault"` at route `/app/docvault/graph`.
- UI must follow Kubera design tokens (`bg-bg-surface`, `border-border`, `text-text-primary`, `accent`).
- 60 FPS WebGL rendering with device pixel ratio capped at `Math.min(window.devicePixelRatio, 2)`.
- No broken imports or TypeScript build errors (`tsc -b && vite build` must pass cleanly).

---

## File Structure

```
frontend/src/pages/company/docvault/graph/
├── DocVaultGraphPage.tsx                       # Modified: fullscreen container & top-right inspector integration
├── components/
│   ├── GraphCanvas.tsx                         # Modified: elevated sprite positioning
│   ├── GraphHud.tsx                            # Modified: "Back to DocVault" label & styling
│   ├── GraphDocumentInspector.tsx              # Created: floating top-right glassmorphic inspector
│   ├── GraphDocumentInspector.test.tsx         # Created: unit tests for document inspector
│   ├── BucketSummaryCard.tsx                   # Maintained: floating card for bucket hubs
│   ├── GraphNavigationControls.tsx             # Maintained: bottom-right navigation dock
│   └── GraphLegend.tsx                         # Maintained: collapsible legend
├── lib/
│   ├── textSprite.ts                           # Modified: anchor (0.5, 0), depthTest false, renderOrder 999
│   └── textSprite.test.ts                      # Modified: unit tests for elevation and depthTest
└── DocVaultGraphPage.test.tsx                  # Modified: integration tests for fullscreen & inspector
```

---

## Tasks

### Task 1: Label Geometry, Elevation & Depth Ordering Fix

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/lib/textSprite.ts`
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`
- Test: `frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts`

**Interfaces:**
- `createNodeSprite(node: GraphNode)` returns `THREE.Sprite` with `center.set(0.5, 0)`, `material.depthTest = false`, and `renderOrder = 999`.

- [ ] **Step 1: Update unit tests in `textSprite.test.ts`**

In `frontend/src/pages/company/docvault/graph/lib/textSprite.test.ts`, add tests verifying:
- `sprite.center.x === 0.5` and `sprite.center.y === 0` (anchored at bottom-center)
- `sprite.material.depthTest === false` (never occluded by 3D geometry)
- `sprite.renderOrder === 999` (drawn on top)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test textSprite.test.ts`

- [ ] **Step 3: Update `textSprite.ts` and `GraphCanvas.tsx`**

In `frontend/src/pages/company/docvault/graph/lib/textSprite.ts`:
```typescript
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    opacity: 1.0,
  })

  const sprite = new THREE.Sprite(material)
  sprite.renderOrder = 999
  sprite.center.set(0.5, 0)
```

In `frontend/src/pages/company/docvault/graph/components/GraphCanvas.tsx`:
Ensure `sprite.position.set(0, node.size + (isBucket ? 6 : 4), 0)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test textSprite.test.ts`
Expected: PASS.

---

### Task 2: Embedded Top-Right Document Inspector (`GraphDocumentInspector.tsx`)

**Files:**
- Create: `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx`
- Test: `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx`

**Interfaces:**
- Produces: `<GraphDocumentInspector document={selectedDoc} buckets={buckets} onClose={closeFn} />`
- Capabilities:
  - Header with title, status badge, bucket name, current version badge, close button
  - Creator info and timestamps
  - Inline Title input with Save button
  - Editable switch (locked / unlocked)
  - Status dropdown (uploaded, verified, etc.)
  - Bucket select dropdown (moves node in 3D scene)
  - Tags input with Save button
  - Version history list with direct Download buttons
  - Upload new version dropzone (`useUploadVersion`)
  - Archive / Restore button (`useArchiveDocument`, `useUpdateDocument`)

- [ ] **Step 1: Write failing unit tests in `GraphDocumentInspector.test.tsx`**

Create `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx` testing:
- Renders metadata, title, status, bucket, and versions
- Saves new title, tags, status, and bucket changes
- Handles download version click
- Handles archive and restore flows

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test GraphDocumentInspector.test.tsx`

- [ ] **Step 3: Implement `GraphDocumentInspector.tsx`**

Create `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test GraphDocumentInspector.test.tsx`
Expected: PASS.

---

### Task 3: Fullscreen Viewport Layout & Page Integration

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.tsx`
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphHud.tsx`
- Test: `frontend/src/pages/company/docvault/graph/DocVaultGraphPage.test.tsx`

**Interfaces:**
- `DocVaultGraphPage` root container has `fixed inset-0 z-40 bg-[#0B0F17] flex flex-col w-screen h-screen overflow-hidden`.
- Integrates `GraphDocumentInspector` instead of `DocumentDrawer`.
- Adds `Escape` key listener to deselect node / close inspector.
- Top HUD shows "Back to DocVault" button.

- [ ] **Step 1: Update `DocVaultGraphPage.tsx` and `GraphHud.tsx`**

In `DocVaultGraphPage.tsx`:
- Change container classes to `fixed inset-0 z-40 bg-[#0B0F17] flex flex-col w-screen h-screen overflow-hidden`
- Replace `DocumentDrawer` with `<GraphDocumentInspector document={selectedDoc} open={!!selectedDoc} onClose={() => setSelectedNode(null)} buckets={buckets} />`
- Add `useEffect` listening for `Escape` key to close inspector.

In `GraphHud.tsx`:
- Change button label to "Back to DocVault".

- [ ] **Step 2: Update integration tests in `DocVaultGraphPage.test.tsx`**

Ensure tests assert `GraphDocumentInspector` appears in top-right when selecting a document, and `Escape` closes it.

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd frontend && npm test DocVaultGraphPage.test.tsx`
Expected: PASS.

---

### Task 4: Full Build Verification & Lint Check

**Files:**
- None (Entire codebase validation)

- [ ] **Step 1: Run TypeScript compiler build**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` completes with 0 errors.

- [ ] **Step 2: Run all unit and integration tests**

Run: `cd frontend && npm test`
Expected: All tests pass.

- [ ] **Step 3: Run ESLint**

Run: `cd frontend && npx eslint src/pages/company/docvault --ext ts,tsx --max-warnings 0`
Expected: 0 errors and 0 warnings.
