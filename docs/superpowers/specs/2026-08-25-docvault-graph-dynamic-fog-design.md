# DocVault 3D Graph — Dynamic Fog Distance

Date: 2026-08-25
Status: Approved design, pending implementation plan

## Problem

The DocVault 3D graph view (`frontend/src/pages/company/docvault/graph/`) applies linear
`THREE.Fog` with fixed distances from `lib/theme.ts` (dark: near 220 / far 900; light:
near 260 / far 1100). As the number of documents and buckets grows, the force layout
spreads nodes farther apart and the fixed fog swallows distant nodes — at overview
distance much of the graph fades into the background. The document-label fade band
(200–420 units from camera, hardcoded in `GraphCanvas.tsx`) has the same fixed-distance
problem.

## Goal

Fog must adapt to the space the graph occupies so that all nodes are clearly visible at
normal overview distance, while small vaults keep today's exact look. Adaptation is
continuous — it tracks the layout as the simulation settles and as nodes are dragged.

## Behavior

### Graph extent

Every 10 rendered frames, compute:

- **Centroid** — mean of all node positions (`x/y/z` on `GraphNode`).
- **Radius R** — maximum distance from centroid over all nodes.

Nodes without valid positions (not yet placed by the force simulation) are skipped.
If no node has a position, extent is treated as unavailable.

### Fog targets

Each frame, given `camDist` = camera distance to centroid:

```
nearTarget = max(theme.fogNear, camDist + NEAR_SPREAD × R)
farTarget  = max(theme.fogFar,  camDist + FAR_SPREAD × R)
```

- Theme values are **floors**: when `camDist + FAR_SPREAD × R` is below the theme far
  value, nothing changes from today.
- At overview distance the far side of the graph stays readable (roughly ≤ 30% haze)
  while depth cueing is preserved.
- Zoomed in close to one cluster, distant clusters still fade out as before.

### Smoothing

Per frame: `current += (target − current) × LERP_RATE`. Fog glides toward targets; no
popping while the simulation spreads nodes or during drags. Theme switches swap floors
instantly and smoothed values converge within about a second.

### Labels

Scale factor `S = currentFogFar / theme.fogFar`, clamped to ≥ 1. The document-label
fade band becomes `[LABEL_FADE_START × S, LABEL_FADE_END × S]` (today: 200 / 420), so
labels fade consistently with sphere fogging. Bucket labels remain always visible.

### Constants

Single source of truth in `lib/dynamicFog.ts`:

| Constant       | Initial value | Purpose                          |
| -------------- | ------------- | -------------------------------- |
| `NEAR_SPREAD`  | 0.2           | fog start relative to graph edge |
| `FAR_SPREAD`   | 3.0           | full-fog point beyond far side   |
| `LERP_RATE`    | 0.08          | per-frame smoothing              |
| `EXTENT_INTERVAL_FRAMES` | 10  | frames between extent passes     |
| `LABEL_FADE_START` / `LABEL_FADE_END` | 200 / 420 | base label fade band |

Values are starting points, calibrated against the real app during implementation.

## Code structure

**New file `graph/lib/dynamicFog.ts`:**

- `computeGraphExtent(nodes) → { centroid: Vector3, radius: number } | null`
  Pure function; null when no positioned nodes.
- `DynamicFogController` class holding cached extent and smoothed values, with:
  - `update(fog, cameraPosition, theme) → scale` — runs the periodic extent pass,
    lerps fog near/far toward targets, returns label scale factor `S`.
  - Reused Vector3s; no allocations in the per-frame path.

**Changes to `GraphCanvas.tsx` (only file touched):**

- Mount effect: wrap created `THREE.Fog` in a controller stored in a ref.
- Theme-change effect: controller re-baselines floors; smoothing continues from
  current values.
- `applyFrame()` loop: call `controller.update(...)` once per frame; replace the
  hardcoded `200`/`420` in the label LOD block with `S`-scaled values.

No changes to force layout, data hooks, HUD components, or theme tokens.

## Edge cases

| Case                        | Behavior                                        |
| --------------------------- | ----------------------------------------------- |
| Empty vault or single node  | Extent null → pure theme floors (today's look)  |
| Unpositioned nodes          | Skipped; all unpositioned → treated as null     |
| Drag / simulation warm-up   | Periodic recompute + lerp hides step changes    |
| Theme switch mid-session    | Floors swap, values converge ~1s, no flicker    |
| Data reload                 | Next extent pass picks it up; no special-casing |

## Testing

- **Unit tests (Vitest)** for `dynamicFog.ts`:
  - `computeGraphExtent`: known point sets → correct centroid/radius; empty input →
    null; NaN/unpositioned nodes skipped.
  - Controller: floors respected for small graphs; targets stretch when
    `camDist + FAR_SPREAD × R` exceeds floor; lerp converges monotonically;
    scale factor ≥ 1.
- **Lint/typecheck:** `npm run lint` and `tsc -b` in `frontend/`.
- **Manual verification:**
  - Large vault: after zoom-to-fit, all nodes readable, labels fade consistently
    with spheres.
  - Small vault: visually identical to current behavior.
  - Fly close to a cluster: distant clusters still haze out.
