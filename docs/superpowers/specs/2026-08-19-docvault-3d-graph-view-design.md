# DocVault 3D Knowledge Graph View

**Date:** 2026-08-19  
**Branch:** `v3`  
**Module:** DocVault (`/app/docvault`)  
**Status:** Approved — ready for implementation plan  

Adds an interactive, edge-to-edge fullscreen 3D force-directed node visualization of DocVault documents and buckets (similar to Obsidian's graph view, in full 3D WebGL space). Documents within a bucket cluster together as cohesive 3D constellations, reacting elastically to drag interactions, zooming with elevated distance-based label level-of-detail (LOD), camera fly-to navigation, and opening a dedicated floating top-right document inspector card in the 3D space with full editing and version download capabilities.

---

## 1. Why & Goals

DocVault provides an encrypted, bucket-organized document repository with version control and tags. While the standard table and bucket rail interface is great for tabular data management, it lacks spatial awareness and relational discovery across buckets, tags, and document clusters.

**Key Goals:**
1. **Edge-to-Edge Fullscreen 3D Universe**: A dedicated fullscreen 3D workspace (`fixed inset-0 z-40`) giving an immersive, distraction-free Obsidian-style graph canvas.
2. **Elevated & Visible Node Labels**: Billboard text sprites anchored cleanly above the top pole of each 3D node sphere with `depthTest = false` and `renderOrder = 999`, eliminating any clipping or occlusion by the 3D sphere geometry.
3. **Embedded Top-Right Document Inspector (`GraphDocumentInspector.tsx`)**: Clicking a document node opens an embedded, floating glassmorphic inspector card in the top-right corner of the 3D canvas (without slide-over drawer overlays that dim the screen), providing complete metadata, version history with per-version downloads, new version uploads, inline rename, lock/editable toggle, status picker, bucket mover, tags editor, and archive/restore actions.
4. **Elastic Cluster Interaction**: Clicking and dragging any document or bucket hub node elastically pulls connected cluster nodes along with it, creating a tactile, responsive physics feel.
5. **Distance-Based Label LOD**: Zooming in displays crisp, camera-facing titles, status indicators, and version numbers for nearby nodes, while zooming out smoothly hides document labels to prevent visual noise.
6. **Camera Fly-To & Search**: Instant autocomplete search in the HUD smoothly animates the camera to frame and highlight the target node.

---

## 2. Architecture & Routes

### Route Hierarchy
- **URL**: `/app/docvault/graph`
- **Route Definition**: Inside `frontend/src/routes/company.routes.tsx`, protected by `ModuleGuard moduleId="docvault"`.
- **Navigation Flow**:
  - `DocVaultPage.tsx` page header includes a **"3D Graph View"** button (with icon `Network` / `Orbit`) linking to `/app/docvault/graph`.
  - `DocVaultGraphPage.tsx` provides a clean top-left **"Back to DocVault"** button (`ArrowLeft` + `DocVault`) returning to `/app/docvault`.

```
/app/docvault (DocVaultPage)
     │
     └── [ "3D Graph View" Button ] ───► /app/docvault/graph (DocVaultGraphPage - Fullscreen 3D)
```

### Component Structure & Isolation

```
frontend/src/pages/company/docvault/graph/
├── DocVaultGraphPage.tsx              # Fullscreen container: loads data & orchestrates state
├── components/
│   ├── GraphCanvas.tsx                # Three.js / 3d-force-graph WebGL canvas wrapper
│   ├── GraphHud.tsx                   # Top floating header (Back button, Title, Search, Filters, Color mode)
│   ├── GraphNavigationControls.tsx    # Bottom-right dock (Zoom In/Out, Reset View, Recenter, Pause physics)
│   ├── GraphDocumentInspector.tsx     # Floating top-right glassmorphic inspector for clicked document
│   ├── BucketSummaryCard.tsx          # Floating card when a Bucket Hub node is selected
│   └── GraphLegend.tsx                # Collapsible color & shape legend
├── hooks/
│   ├── useGraphData.ts                # Converts Buckets + Documents into 3D Nodes & Links graph data
│   └── useGraphControls.ts            # Camera fly-to and physics manipulation utilities
├── lib/
│   ├── palette.ts                     # Harmonic HSL color palette generator for buckets & status tokens
│   └── textSprite.ts                  # Canvas-based high-DPI billboard text sprite generator with LOD
└── types/
    └── graph.ts                       # TypeScript interfaces for GraphNode, GraphLink, and GraphConfig
```

---

## 3. Label Geometry, Elevation & LOD

### Anchor & Elevation Math
- **Sprite Anchor**: Anchor the sprite texture at its bottom-center: `sprite.center.set(0.5, 0)`.
- **Vertical Offset**: Position the sprite at `(0, node.size + (isBucket ? 6 : 4), 0)` in the node's Three.js group.
- **Occlusion Prevention**: Set `material.depthTest = false` and `sprite.renderOrder = 999` so labels always render above node spheres and links.

### Distance Thresholds
During each render frame tick, the camera distance $D = \|\mathbf{P}_{\text{node}} - \mathbf{P}_{\text{camera}}\|$ determines visibility and opacity:

1. **Far Zone ($D > 420\text{px}$)**:
   - Document labels: Hidden (`opacity: 0`).
   - Bucket Hub labels: Fully visible with large glowing text.
2. **Mid Zone ($180\text{px} < D \le 420\text{px}$)**:
   - Nearby document labels smoothly fade in ($\text{opacity} = \frac{420 - D}{240}$).
   - Shows document title and format badge.
3. **Close Zone ($D \le 180\text{px}$)**:
   - Full high-resolution label (`opacity: 1.0`): Document Title, Status Pill (e.g. *Verified*, *Action Required*), and Version Badge (`v2`).

---

## 4. Top-Right Document Inspector (`GraphDocumentInspector.tsx`)

### Layout & Placement
- Fixed to the top-right corner inside the 3D canvas viewport: `absolute top-18 right-4 w-96 max-h-[calc(100vh-6rem)] overflow-y-auto z-30`.
- Styled as a dark glassmorphic card: `bg-bg-surface/95 backdrop-blur-md border border-border shadow-2xl rounded-2xl p-4.5`.
- Does not block 3D canvas drag, orbit, or pan interactions outside the card.
- Closes via the `X` button, pressing `Escape`, or clicking on empty canvas space.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [← Back to DocVault]  DocVault 3D Graph (12 Buckets · 84 Docs)                         │
├─────────────────────────────────────────────────────────┬──────────────────────────────┤
│                                                         │ 📄 Audit Report 2026     [✕] │
│                                                         │ [Verified] · Finance · v2    │
│                     (3D Galaxy)                         │ ──────────────────────────── │
│                                                         │ 👤 Created by: John Doe      │
│                                                         │ 🏷️ Name: [Audit Report 2026] │
│                                                         │ 🔒 Editable: [On / Off]      │
│                                                         │ 📊 Status: [Verified ▾]      │
│                                                         │ 📁 Bucket: [Finance ▾]       │
│                                                         │ 🏷️ Tags: [audit, 2026] [Save]│
│                                                         │ ──────────────────────────── │
│                                                         │ 📜 Version History:          │
│                                                         │   • v2 (Current) [Download]  │
│                                                         │   • v1 [Download]            │
│                                                         │ ⬆️ Upload New Version        │
│                                                         │ 🗑️ [ Archive Document ]     │
└─────────────────────────────────────────────────────────┴──────────────────────────────┘
```

### Inspector Capabilities
1. **Header & Metadata**: Document Title, Status badge, Bucket name, Version badge, Creator, Upload date, File size.
2. **Inline Name Edit**: Input with Save button (disabled when unchanged or locked).
3. **Lock / Editable Toggle**: Toggle between Editable and Locked (locks rename, bucket change, tags, and new version uploads).
4. **Status Picker**: Update document status (*Uploaded*, *Pending Approval*, *Action Required*, *Verified*, *Submitted*, *Overdue*).
5. **Bucket Move Selector**: Move document between buckets; immediately triggers 3D physics to re-route link and float node to the new bucket cluster.
6. **Tags Editor**: Comma-separated tags input with Save button.
7. **Version History & Download**: Table of all versions with version number, uploaded by, size, date, and individual **Download** buttons.
8. **Upload New Version**: Drag-and-drop / file picker area to upload replacement version files.
9. **Archive / Restore**: Restore action if archived, or Archive button with confirmation dialog.

---

## 5. Fullscreen Layout & Visual Aesthetic

### Viewport Structure
- `DocVaultGraphPage.tsx` root container: `fixed inset-0 z-40 bg-[#0B0F17] flex flex-col w-screen h-screen overflow-hidden`.
- Covers 100% of the browser window edge-to-edge, removing outer shell card paddings and borders.
- Top HUD bar floats across the top edge with `Back to DocVault` button, search bar with autocomplete fly-to, color mode toggle (`By Bucket` vs `By Status`), and bucket filters.

---

## 6. Verification Plan

1. **Fullscreen Layout**:
   - Verify `/app/docvault/graph` renders edge-to-edge across the entire screen (`fixed inset-0 z-40`).
   - Verify clicking "Back to DocVault" returns cleanly to `/app/docvault`.
2. **Label Elevation & Visibility**:
   - Verify text labels float visibly above the top pole of each node sphere.
   - Verify labels are never occluded by node spheres or connection links.
3. **Top-Right Inspector**:
   - Verify clicking a document node opens `GraphDocumentInspector` in the top-right corner.
   - Verify 3D canvas in the background remains interactive while the inspector is open.
   - Verify updating title, status, bucket, tags, and uploading/downloading versions works properly and updates the 3D scene in real time.
   - Verify clicking `X`, pressing `Escape`, or clicking empty background closes the inspector.
4. **Tests & Build**:
   - Verify all unit and integration tests pass with 0 errors.
   - Verify `tsc -b && vite build` compiles cleanly with 0 errors.
