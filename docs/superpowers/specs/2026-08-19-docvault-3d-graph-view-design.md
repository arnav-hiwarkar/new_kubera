# DocVault 3D Knowledge Graph View

**Date:** 2026-08-19  
**Branch:** `v2`  
**Module:** DocVault (`/app/docvault`)  
**Status:** Approved — ready for implementation plan  

Adds an interactive 3D force-directed node visualization of DocVault documents and buckets (similar to Obsidian's graph view, in full 3D WebGL space). Documents within a bucket cluster together as cohesive 3D constellations, reacting elastically to drag interactions, zooming with distance-based label level-of-detail (LOD), flying camera navigation, and opening the full DocVault document drawer on node inspection.

---

## 1. Why & Goals

DocVault provides an encrypted, bucket-organized document repository with version control and tags. While the standard table and bucket rail interface is great for tabular data management, it lacks spatial awareness and relational discovery across buckets, tags, and document clusters.

**Key Goals:**
1. **Relational Spatial Visualization**: Visualize documents and buckets as an interactive 3D universe where intra-bucket documents naturally cluster together and documents sharing tags are subtly linked.
2. **Elastic Cluster Interaction**: Clicking and dragging any document or bucket hub node elastically pulls connected cluster nodes along with it, creating a tactile, responsive physics feel.
3. **Distance-Based Label LOD**: Zooming in displays crisp, camera-facing titles, status indicators, and version numbers for nearby nodes, while zooming out smoothly hides document labels to prevent visual noise.
4. **Camera Fly-To & Search**: Instant autocomplete search in the HUD smoothly animates the camera to frame and highlight the target node.
5. **Full Detail & Action Integration**: Clicking a document node opens the DocVault `DocumentDrawer` to view metadata, download versions, update tags/bucket/status, or archive documents in real time. Clicking a bucket hub opens a summary card.

---

## 2. Architecture & Routes

### Route Hierarchy
- **URL**: `/app/docvault/graph`
- **Route Definition**: Inside `frontend/src/routes/company.routes.tsx`, protected by `ModuleGuard moduleId="docvault"`.
- **Navigation Flow**:
  - `DocVaultPage.tsx` page header includes a **"3D Graph View"** button (with icon `Network` / `Orbit`) linking to `/app/docvault/graph`.
  - `DocVaultGraphPage.tsx` provides a clean top-left **"Back to List"** button (`ArrowLeft` + `DocVault`) returning to `/app/docvault`.

```
/app/docvault (DocVaultPage)
     │
     └── [ "3D Graph View" Button ] ───► /app/docvault/graph (DocVaultGraphPage)
```

### Component Structure & Isolation

```
frontend/src/pages/company/docvault/graph/
├── DocVaultGraphPage.tsx              # Main page container: queries data & orchestrates state
├── components/
│   ├── GraphCanvas.tsx                # Three.js / 3d-force-graph WebGL canvas wrapper
│   ├── GraphHud.tsx                   # Top floating header (Back button, Title, Search, Filters, Color mode)
│   ├── GraphNavigationControls.tsx    # Bottom-right dock (Zoom In/Out, Reset View, Recenter, Pause physics)
│   ├── BucketSummaryCard.tsx          # Floating inspector card when a Bucket Hub node is selected
│   └── GraphLegend.tsx                # Collapsible color & shape legend
├── hooks/
│   ├── useGraphData.ts                # Converts Buckets + Documents into 3D Nodes & Links graph data
│   └── useGraphControls.ts            # Camera fly-to and physics manipulation utilities
├── lib/
│   ├── palette.ts                     # Harmonic HSL color palette generator for buckets & status tokens
│   └── textSprite.ts                  # Canvas-based high-DPI billboard text sprite generator with distance LOD
└── types/
    └── graph.ts                       # TypeScript interfaces for GraphNode, GraphLink, and GraphConfig
```

---

## 3. Graph Model & Topology

### Node Schema & Classifications

```typescript
export type NodeType = 'bucket' | 'document'

export interface GraphNode {
  id: string                     // Unique ID (e.g. 'bucket_<id>' or 'doc_<id>')
  rawId: string                  // Database UUID
  type: NodeType
  name: string                   // Bucket name or Document title
  bucketId: string | null        // Parent bucket UUID (null if uncategorized or if self is bucket)
  bucketName?: string
  status?: string                // Document status (uploaded, verified, etc.)
  versionNo?: number             // Current version number
  sizeBytes?: number             // File size
  tags?: string[]                // Tags list
  color: string                  // Current assigned color (based on active color mode)
  size: number                   // Node sphere radius (14 for bucket hubs, 6 for documents)
  // Simulation coordinate props managed by d3-force-3d
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
  fx?: number | null
  fy?: number | null
  fz?: number | null
}

export interface GraphLink {
  source: string | GraphNode     // Source node ID or reference
  target: string | GraphNode     // Target node ID or reference
  kind: 'bucket-doc' | 'tag-shared' // Link category
  strength: number
  color: string
}
```

### Link Relationships
1. **Primary Cluster Links (`kind: 'bucket-doc'`)**:
   - An edge connects every document node to its parent Bucket Hub node (or the virtual "Uncategorized" Hub node).
   - Rendered as a glowing, translucent filament beam (`rgba(100, 160, 255, 0.45)`).
   - High spring strength (`0.8`), resting distance `45-55 units`.
2. **Secondary Tag Links (`kind: 'tag-shared'`)**:
   - Subtle connecting lines between documents that share 2 or more identical tags.
   - Rendered as faint dashed lines (`rgba(255, 255, 255, 0.15)`).
   - Lower spring strength (`0.15`), resting distance `90-120 units`.

---

## 4. 3D Force Physics Simulation & Cluster Drag Mechanics

### Physics Setup (`d3-force-3d`)
- **Link Force**: Sets short distance for intra-bucket connections (`distance: 50`) pulling all documents into tight spherical constellations around their bucket hub.
- **Many-Body Repulsion (`charge`)**: Strong repulsion (`-120`) between nodes prevents overlap and pushes distinct bucket hubs away from each other into balanced 3D sectors.
- **Collision Detection (`collide`)**: Dynamic sphere radius collision preventing geometric clipping between nodes.
- **Center Gravity**: Gentle global gravity pulling the overall galaxy towards `(0, 0, 0)`.

### Elastic Cluster-Drag Behavior
- When dragging any document node:
  - The dragged node is locked to the pointer ray coordinates (`fx, fy, fz`).
  - The physics simulation warms up (`simulation.alphaTarget(0.35).restart()`).
  - Tension transmits through the primary link to the parent bucket hub and sibling cluster documents, causing the entire bucket cluster to organically follow and pivot around the dragged document.
- When dragging a bucket hub node:
  - The entire constellation of documents follows the moving hub centroid.
- Releasing the node (`onNodeDragEnd`) unfixes coordinates (`fx = null, fy = null, fz = null`) and lets the system settle smoothly into dynamic equilibrium.

---

## 5. Distance-Based Level of Detail (LOD) for Labels

### High-DPI Canvas Billboard Sprites
- Node labels are generated via HTML5 2D Canvas textures rendered as Three.js `Sprite` objects positioned slightly above each node.
- Sprites always face the camera billboard-style regardless of camera orbit angle.

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

## 6. Interactivity, Selection & Camera Fly-To

### Pointer & Raycasting Interactions
- **Hover**:
  - Hovering over a node highlights the node and brightens its connected links.
  - Non-connected clusters dim slightly to create focus depth.
  - Cursor changes to `grab` over interactive nodes.
- **Node Click**:
  - **Document Node**:
    - Triggers smooth camera tweening (`graphRef.current.cameraPosition(...)`) flying the camera to orbit around the node at distance $\approx 120\text{px}$.
    - Opens the DocVault `DocumentDrawer` on the right edge of the screen.
  - **Bucket Hub Node**:
    - Camera flies to frame the bucket cluster.
    - Opens the floating `BucketSummaryCard` displaying bucket details and document list.

### Background Click
- Clicking the empty canvas deselects active nodes, closes inspector drawers/cards, and restores full brightness to the entire graph.

---

## 7. Real-Time Data Sync & Drawer Integration

- The 3D Graph uses standard `@tanstack/react-query` hooks (`useBuckets`, `useDocuments`).
- When a document is updated inside `DocumentDrawer` (e.g., renaming title, editing tags, changing status, changing bucket, or uploading a new version):
  - TanStack Query invalidates cache keys `['docvault', 'documents']` and `['docvault', 'buckets']`.
  - `useGraphData` recomputes the node/link dataset.
  - If a document was moved from "Finance" to "Legal", its primary link dynamically reconnects to the "Legal" bucket hub, and 3D physics smoothly floats the document across space into its new cluster without page reload.

---

## 8. Floating HUD, Search & Visual Aesthetic

### Obsidian Cosmic Void Theme
- Background: Deep graphite slate (`#0B0F17` / `#0E131F`).
- Node Materials: Emissive MeshPhong / MeshStandard materials with inner core glow and soft outer aura.
- Glassmorphic UI: Dark translucent panels (`bg-bg-surface/85 backdrop-blur border-border`) with subtle border highlights.

### Floating Controls
1. **Top Header HUD**:
   - Back button (`← DocVault`) and breadcrumb title.
   - Universe Metrics Pill: `X Buckets · Y Documents`.
   - **Real-Time Autocomplete Search**: Search input with dropdown results. Selecting any item flies the camera directly to it and highlights the node.
   - **Color Mode Selector**:
     - *Color by Bucket*: Cohesive distinct hue per bucket.
     - *Color by Status*: Kubera status colors (Verified = Green, Action Required = Red, Uploaded = Blue, etc.).
   - **Bucket Filter Dropdown**: Toggle visibility of individual buckets.
2. **Bottom-Right Navigation Dock**:
   - `[+]` Zoom In / `[-]` Zoom Out.
   - `[🎯]` Reset Camera (fits entire universe to screen).
   - `[🧭]` Recenter View.
   - `[⏸ / ▶]` Freeze / Resume Physics Simulation.
3. **Collapsible Legend**: Bottom-left expandable legend showing active color mappings and interaction hints.

---

## 9. Performance & Optimizations

1. **Lazy Loading**: Three.js and graph dependencies are lazy-loaded via React `lazy()` so initial DocVault list view load times remain instantaneous.
2. **Label Texture Caching**: Canvas sprite textures are cached by node content hash to eliminate unnecessary re-renders.
3. **Raycaster Throttling**: Raycast hover checks are throttled to 60fps animation frames without blocking the main React thread.
4. **Adaptive Device Pixel Ratio**: Three.js renderer dynamically caps `renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))` to maintain smooth 60fps on high-DPI displays.

---

## 10. Verification Plan

1. **Route & Navigation**:
   - Verify clicking "3D Graph View" in `DocVaultPage` navigates to `/app/docvault/graph`.
   - Verify clicking "Back to List" returns to `/app/docvault`.
2. **Graph Generation & Clustering**:
   - Verify all buckets and documents render as 3D nodes.
   - Verify documents are tightly clustered around their respective bucket hubs.
   - Verify uncategorized documents cluster around the Uncategorized hub.
3. **Physics & Elastic Drag**:
   - Verify clicking and dragging a document moves the document and elastically pulls its cluster along.
   - Verify dragging a bucket hub moves the whole cluster.
4. **Zoom & Distance LOD**:
   - Verify zooming out hides document titles and keeps bucket titles visible.
   - Verify zooming in reveals crisp titles, version tags, and status badges.
5. **Node Selection & Drawer**:
   - Verify clicking a document node flies the camera and opens `DocumentDrawer`.
   - Verify actions in the drawer (status change, rename, bucket change, download) execute properly and update the 3D scene.
6. **Search & Filters**:
   - Verify searching for a document in the HUD finds it and smoothly centers the camera.
   - Verify toggling color modes (by Bucket vs by Status) updates node colors dynamically.
   - Verify toggling bucket visibility filters the nodes in 3D.
