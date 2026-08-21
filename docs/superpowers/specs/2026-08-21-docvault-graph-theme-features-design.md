# DocVault 3D Graph — Theme Alignment, Inspector Redesign & New Features

**Date:** 2026-08-21
**Status:** Approved (design discussion 2026-08-21)

## Problem

The DocVault graph page (`frontend/src/pages/company/docvault/graph/`) is visually
disconnected from Kubera's "Emerald Prosperity" design system:

1. The canvas background is `#0B0F17` (blue-slate) while the app's dark theme is a
   green-tinted black (`#0a0e0c`); links/particles are sky-blue rather than
   emerald/gold. The graph ignores the app's light/dark toggle entirely.
2. `GraphDocumentInspector` renders every control at once (rename, lock switch,
   status, bucket, tags, version history, upload dropzone, archive) in one dense
   column — cluttered and hard to scan.
3. Missing affordances expected of an Obsidian-style graph: search/spotlight,
   neighbor focus, attention-pulsing, tag cross-links.

## Goals

- Graph visuals derive from the app theme (`useTheme`, `data-theme` attribute) —
  light mode gets a warm paper-toned graph, dark mode an emerald-black one.
- Inspector becomes a tabbed glass panel consistent with app surfaces.
- Add four features: search & spotlight, focus/neighbor highlight, status pulse,
  tag cross-links (toggleable).

## Non-goals

- No changes to the DocVault list page or API.
- No physics/layout engine swap (staying on `3d-force-graph` + d3 forces).
- No minimap, no VR, no server-side graph computation.

## Design

### 1. Theme-aware graph visuals

New module `graph/lib/theme.ts` exports a `GraphTheme` object per mode:

| Token | Dark | Light |
|---|---|---|
| background | `#0a0e0c` | `#f6f7f5` |
| fog | same as bg, near 220 / far 900 | same, near 260 / far 1100 |
| linkColor (bucket-doc) | `rgba(31,185,140,0.28)` | `rgba(15,157,118,0.35)` |
| linkColor (tag) | gold `rgba(224,181,102,0.18)` | `rgba(196,139,44,0.25)` |
| particle color | emerald `#1fb98c` | accent `#0f9d76` |
| selection ring | `#1fb98c` | `#0f9d76` |
| bucket ring | gold `#e0b566` | `#c48b2c` |
| label text | light (`#edf2ee`) | dark (`#10201a`) |
| emissiveIntensity multiplier | 1.0 | 0.45 |

- `GraphCanvas` accepts a `theme: 'light' | 'dark'` prop; `DocVaultGraphPage`
  obtains it via the existing `useTheme()` hook (`frontend/src/lib/useTheme.ts`)
  and passes it down. Theme change re-applies background/fog/link colors without
  rebuilding the graph where the API allows; node objects rebuild on toggle.
- Node labels (`lib/textSprite.ts`) take a text color derived from theme.
- **Bloom (dark only):** add `UnrealBloomPass` (from `three/examples`) to
  `graph.postProcessingComposer()` with low strength (~0.35, radius 0.6,
  threshold 0.55). Skipped in light mode. Guarded so failure degrades silently
  to no bloom.

### 2. Inspector redesign — tabbed glass panel

Rewrite `GraphDocumentInspector.tsx` (same props contract, same testids kept
where behavior is unchanged):

- **Header:** document icon, title (click-to-edit inline, Save on Enter/blur),
  status badge, bucket chip, `vN`, close button. Meta row beneath: created by ·
  current version by · updated.
- **Tabs:** `Overview | Edit | Versions` — segmented control; content animated
  with framer-motion (`AnimatePresence`, fade/slide ~150ms).
  - *Overview:* read-only fact grid (created by, current version by, updated,
    size, version count) + tags rendered as chips.
  - *Edit:* rename field + Save, status Select, bucket Select, editable Switch
    (with existing locked/archived disable rules).
  - *Versions:* vertical timeline list (version, size, date, uploader, current
    badge, Download) + upload dropzone for new versions.
- **Footer danger zone:** Archive (or Restore when archived) button, full width;
  archive still gated by `ConfirmDialog`.
- All mutations reuse existing hooks (`useUpdateDocument`, `useArchiveDocument`,
  `useUploadVersion`, `useDownloadDocument`) and toast wrapping — logic is
  unchanged, only presentation is restructured.
- `BucketSummaryCard` restyled to match the glass language (surface/border/
  backdrop-blur tokens) so bucket clicks feel like the same family.

### 3. Features

**a. Search & spotlight**
- Search input added to `GraphHud` (⌘K/Ctrl-K focuses it; Esc clears).
- As the user types, nodes whose name/tags/status match stay lit; all others dim
  to ~12% opacity (material transparency + sprite opacity). Matching count shown.
- Enter flies the camera to the best match (`flyToNode`) and selects it.
- Clearing the query restores full opacity.

**b. Focus / neighbor highlight**
- Hovering a node highlights it and its directly linked neighbors + connecting
  links; everything else fades (same dim mechanism as spotlight).
- Double-click a bucket isolates its cluster: camera flies in, other clusters dim
  to ~8%; a small "Isolated: <bucket> ✕" pill appears top-center; Esc, pill ✕, or
  background click restores.
- Selection takes precedence over hover dimming.

**c. Status pulse**
- Document nodes with status `action_required` or `overdue` pulse continuously:
  scale oscillates ±10% and emissiveIntensity oscillates around their base value
  (~1.4s sine cycle), driven from the existing per-frame interval loop in
  `GraphCanvas` (upgraded to use `graph.onRenderFramePre` if available, else the
  interval).

**d. Tag cross-links**
- Existing `tag-shared` links (currently ≥2 shared tags, white 0.12) are lowered
  to **≥1 shared tag**, recolored to the theme's gold token, drawn with slight
  curvature (`linkCurvature(0.25)` applied per-kind), and capped (a doc
  participates in at most ~8 tag links, prioritized by shared-tag count, to keep
  the layout readable).
- New boolean state `showTagLinks` (default on) toggled from `GraphLegend`;
  off removes tag links from the data passed to the graph.

### Data flow

Unchanged: `useBuckets`/`useDocuments` → `useGraphData` → `GraphCanvas`. New
derived state (search query, isolated cluster id, showTagLinks) lives in
`DocVaultGraphPage` and flows down as props; dimming is resolved inside
`GraphCanvas` from `(query, hoveredNodeId, selectedNodeId, isolatedClusterId)`.

### Error handling

- Bloom construction wrapped in try/catch → no bloom on failure.
- All mutations keep the existing `wrap()` toast error pattern.
- Empty search results show "No matches" in the HUD input dropdown area.

### Testing

- Unit: `theme.ts` token map; `useGraphData` tag-link threshold/cap/toggle;
  dim-resolution helper (pure function `resolveDimState`).
- Component: inspector tabs render/dispatch existing mutations (update existing
  `GraphDocumentInspector.test.tsx`); HUD search filters; legend toggle.
- Existing tests updated where classnames/testids changed; run
  `npm run test` + `npm run lint` + `npm run typecheck` in `frontend/`.

## Affected files

- `graph/lib/theme.ts` (new), `graph/lib/palette.ts`, `graph/lib/textSprite.ts`
- `graph/components/GraphCanvas.tsx`, `GraphDocumentInspector.tsx`,
  `GraphHud.tsx`, `GraphLegend.tsx`, `BucketSummaryCard.tsx`
- `graph/hooks/useGraphData.ts`, `graph/types/graph.ts`
- `graph/DocVaultGraphPage.tsx`
- corresponding `*.test.ts(x)` files
