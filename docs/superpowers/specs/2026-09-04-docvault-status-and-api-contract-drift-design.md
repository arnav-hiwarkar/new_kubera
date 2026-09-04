# DocVault status actions & API contract drift — design

**Date:** 2026-09-04
**Branch:** `fix/docvault-status-and-schema-drift`
**Status:** design agreed, not yet implemented

---

## 1. The two bugs, and why they are one piece of work

### Bug A — two DocVault graph actions are dead in production

`frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx`
sends a `status` field to `PATCH /api/v1/docvault/documents/{id}`:

* line 91 — `changeStatus`, backing the status dropdown in the Edit tab
* line 118 — `restore`, backing the "Restore document" button for archived docs

`DocumentUpdate` (`app/schemas/docvault.py:78`) declares
`model_config = ConfigDict(extra="forbid")` and has **no** `status` field —
KUB-007 removed it deliberately, because free status-setting *was* the
self-approval bypass. Both calls therefore return **422**. Both call sites carry
an `as never` cast, which is how they passed review.

`GraphDocumentInspector.test.tsx:256` and `:445` assert the broken calls and
pass, because they mock the API client and never exercise the real contract.
**The tests currently enshrine the bug.**

### Bug B — `frontend/src/api/schema.d.ts` is stale, and that is what hid Bug A

A fresh `openapi-typescript` run against the live app produces a ~1000-line diff.
**11 schema components are missing entirely**, including every type KUB-007
added:

`CompanySmtpConfigOut`, `CompanySmtpConfigUpdate`, `CompanySmtpVerifyRequest`,
`CompanySmtpVerifyResponse`, `DocVaultApproverResponse`,
`DocumentRequestApprovalRequest`, `DocumentReviewRequest`, `EmailLogOut`,
`FinancialYearReopenRequest`, `UserChangePasswordRequest`.

Regenerating surfaces exactly **8 type errors**: the 2 real ones above, plus 6
test fixtures missing `UserResponse`'s newly-required `can_change_password` and
`has_avatar`.

The drift *mechanism* is hand-written shadow types in `src/api/types.ts`. When
the generated schema lacks a type, someone hand-declares it; it then drifts
silently. There are **11** such shadows — standalone `export interface`
declarations whose name matches an OpenAPI component:

`AssetDepreciationLineResponse`, `AssetDisposalRequest`, `AssetExistingCreate`,
`DepreciationRunResponse`, `DocVaultApproverResponse`,
`DocumentRequestApprovalRequest`, `DocumentReviewRequest`,
`FinancialYearCreate`, `FinancialYearResponse`,
`ItBlockDepreciationLineResponse`, `UserChangePasswordRequest`.

Only `ImpactPreview` and `TBColumnMap` are genuinely frontend-local.

Compared field-by-field **and type-by-type** against the live OpenAPI, three of
them actively lie: `DepreciationRunResponse`, `AssetDepreciationLineResponse`
and `ItBlockDepreciationLineResponse` declare **`number` for ~29 money fields
the API serialises as `string`** (they are `Decimal` server-side). This is the
same class as the `AssetResponse` `string & number` intersection that collapsed
every disposal field to `null` (fixed in KUB-020).

Measured: pointing all three at the generated types produces **zero** new type
errors, because the consuming code was written against reality rather than the
declaration — `DepreciationRunCard.tsx:322` wraps values in `String(...)`, and
`explain.test.tsx` fixtures already use `'0.00'`. So nobody depended on the lie
and the shadows can be deleted at no cost. Had anyone written
`line.additions.toFixed(2)`, it would have crashed in production.

Four shadows narrow an enum-ish field the backend types loosely as `str`, where
the hand-written narrowing is *correct* and worth keeping:
`FinancialYearResponse.status`, `DepreciationRunResponse.status`,
`DocVaultApproverResponse.role`, `DocumentReviewRequest.decision`. These become
intersections over the generated type rather than standalone declarations, which
preserves the narrowing and satisfies the ban rule by construction. The
underlying backend looseness is recorded as a follow-up in §5.4.

**Ordering:** B is the cause, A is the symptom. Restore type safety at the
boundary first, then fix what it surfaces. Doing A alone means the next contract
change breaks silently again.

---

## 2. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| 1 | Extract one shared actions layer rather than patching the two call sites | The graph inspector (541 lines) is a divergent copy of `DocumentDrawer` (546 lines). Patching leaves two editors drifting; extraction removes the cause. |
| 2 | Seam = a `useDocumentActions` hook **plus** a shared `DocumentApprovalPanel` | The two surfaces' layouts genuinely differ (side drawer vs floating tabbed panel); sharing presentation would force one into the wrong shape. The approval panel is the one piece intricate enough that writing it twice would re-create the drift. |
| 3 | Commit a canonical `openapi.json`; `gen:api` reads the file; pytest asserts it matches `app.openapi()` | Regenerating today needs docker + uvicorn on `localhost:8000`. That friction is why nobody re-ran it. Reading a committed file makes regeneration offline and deterministic, and the pytest guard keeps the file honest. |

There is no CI and no pre-commit hooks in this repo, so a guard only works if it
is a test in an existing suite.

---

## 3. Part 1 — the API contract becomes a committed artifact

### 3.1 `openapi.json` at the repo root

Canonicalised: `json.dumps(app.openapi(), indent=2, sort_keys=True)`. ~24k lines
/ 608K. It *is* the contract, so its diffs read as an API changelog.

Verified safe to commit: no `examples`, no `servers` block, no URLs or hosts, no
secret-shaped values. The only `default` values are business strings already
public in the API (lead auto-reply copy, enum defaults). It is a schema
description and contains no tenant data.

### 3.2 `gen:api` reads the file

```
"gen:api": "openapi-typescript openapi.json -o src/api/schema.d.ts"
```

Confirmed working: `openapi-typescript` accepts a local path and produced
identical output from the file as from the URL.

### 3.3 Three guard tests

1. **Snapshot currency** (pytest, `tests/test_api_contract.py`).
   `json.dumps(app.openapi(), indent=2, sort_keys=True)` must equal the committed
   `openapi.json`. Needs no DB and no server — `app.main` imports standalone.
   Failure message names the exact commands to re-run. A backend schema change
   now breaks the **backend** suite until the types are regenerated.

2. **No shadow types** (pytest, same file). `src/api/types.ts` may not
   hand-declare a type — `export interface X` or `export type X = { ... }` —
   whose name matches a component in `openapi.json#/components/schemas`. Names
   that are not component names (`UserRoleType`, `ImpactKind`, `Domain`) are out
   of the rule's scope by construction and need no allowlist entry.

   Allowlist, for the two types that genuinely have no server counterpart
   (verified absent from the OpenAPI): `ImpactPreview`, `TBColumnMap`. Each
   allowlist entry must carry a comment saying why, so the list cannot quietly
   become a dumping ground.

3. **Every called route exists** (pytest, same file). Paths referenced in
   `src/api/endpoints/*.ts` must exist in the snapshot with that method.
   Template literals (`` `/api/v1/docvault/documents/${id}/review` ``) are
   normalised to `{param}` shape before matching. Best-effort regex; catches the
   *route* half of contract drift while guard 1 catches the *shape* half.

### 3.4 Reconciliation commit

* Regenerate `schema.d.ts` from the snapshot.
* Delete shadow declarations the fresh schema makes redundant. Verified
  field-for-field against the live OpenAPI:
  * **Hand-written interfaces that now exist generated, identically:**
    `UserChangePasswordRequest`, `DocumentReviewRequest`,
    `DocumentRequestApprovalRequest`, `DocVaultApproverResponse`,
    `FinancialYearReopenRequest`, `AssetExistingCreate` (all 20 fields match).
  * **Redundant intersections** — every field they add is now generated:
    `DocumentResponse`, `DocumentUpdate` (`approver_id`), and `CompanyUserOut`
    (`can_change_password`, `has_avatar`, `avatar_updated_at`,
    `password_changed_at` are all present in the schema).
  * **The three lying depreciation shadows** — `DepreciationRunResponse`,
    `AssetDepreciationLineResponse`, `ItBlockDepreciationLineResponse`. Deleting
    them also *gains* fields the hand-written versions omitted entirely:
    `calc_trace` on both line types and `book` on the run response.
  * **Redundant `Omit<…, 'role'>` overrides** on `UserResponse`, `UserCreate`
    and `UserUpdate`. The generated `UserRole` is already `"admin" |
    "employee"` — KUB-018's removal of `manager` is reflected in the live API —
    so the override reproduces the generated type exactly. `UserRoleType`
    becomes `S['UserRole']` rather than a hand-maintained union that only
    happens to be correct today.
* Convert the four correct enum narrowings to intersections over the generated
  type, e.g. `export type DocumentReviewRequest = S['DocumentReviewRequest'] &
  { decision: 'verified' | 'action_required' }`.
* Fix the 6 test fixtures to include `can_change_password` and `has_avatar`.

Every deletion here is mechanical and proven by `tsc -b`: if a shadow was
load-bearing, removing it fails the typecheck rather than changing behaviour at
runtime. Dropping the `role` overrides cannot cascade into the dead
`role === 'manager'` comparisons in Sales and KRA, because those read
`profile.role` from `CompanyUserOut`, whose `role` the backend types as a plain
`string`.

---

## 4. Part 2 — one source of truth for document actions

### 4.1 The server's real rules

Read from all nine handlers in `app/routers/docvault.py`. This table is the
specification the frontend must mirror — not the drawer's current code, which is
wrong in two places (§4.3).

| Action | Endpoint | Server requires |
|---|---|---|
| Edit title / tags / bucket | `PATCH /documents/{id}` | `admin \|\| creator \|\| approver`; `is_editable`; and (not pending, or caller is approver/admin) |
| Toggle editable **on** | `PATCH` | admin only |
| Toggle editable **off** | `PATCH` | `admin \|\| creator \|\| approver` + pending guard |
| Assign approver | `PATCH` | as above, plus: not verified/archived unless admin; approver ≠ creator unless admin; approver must be active, have DocVault access, and have access to the target bucket |
| Request approval | `POST /documents/{id}/request-approval` | `creator \|\| admin`; status ∈ {`uploaded`, `action_required`}; approver ≠ self unless admin; same approver validity rules |
| Review | `POST /documents/{id}/review` | status = `pending_approval`; `approver \|\| admin`; **and not** `creator` unless admin (self-review block) |
| Archive | `DELETE /documents/{id}` | `admin \|\| creator` + pending guard. Sets `archived`, `is_editable = false` |
| Restore | `POST /documents/{id}/restore` | **admin only** (`require_admin`); status = `archived`. Resets to `uploaded`, `is_editable = true`, clears all approval fields |
| Upload version | `POST /documents/{id}/versions` | `admin \|\| creator`; `is_editable`; + pending guard. A new version on a `verified` doc resets it to `uploaded` and clears approval |

`canAssignApprover` covers only whether the caller may change the approver at
all. The server's *per-candidate* rules — approver must be active, hold DocVault
access, have access to the target bucket, and not be the creator unless the
caller is an admin — are properties of each candidate, not of the document, so
they belong in `ApproverPicker`'s filtering (which `GET /approvers` already does
server-side) rather than in this predicate.

Every endpoint is additionally gated on company scope and `can_access_bucket`,
which returns **404, not 403** — deliberately, so the endpoints are not a
document-existence oracle. The frontend must not attempt to second-guess bucket
access; that stays server-side only.

### 4.2 The seam

```ts
// Pure. No React. This is what gets the table-driven unit tests.
export function documentPermissions(
  profile: Pick<CompanyUserOut, 'id' | 'role'> | null | undefined,
  document: DocumentResponse | null | undefined,
): DocumentPermissions
```

returning:

```
isAdmin, isCreator, isApprover, isArchived, isPending,
mayEdit,            // admin || creator || approver          (_may_edit_document)
pendingOk,          // !isPending || isApprover || isAdmin
canEditMeta,        // mayEdit && pendingOk && is_editable
canToggleEditable,  // mayEdit && pendingOk && (is_editable || isAdmin)
canUnlock,          // !is_editable && isAdmin   — the false->true case specifically
canAssignApprover,  // mayEdit && pendingOk && (isAdmin || status not in {verified, archived})
canRequestApproval, // (uploaded || action_required) && (isCreator || isAdmin) && !isArchived
canReview,          // isPending && (isApprover || isAdmin) && !(isCreator && !isAdmin)
canArchive,         // !isArchived && (isAdmin || isCreator) && pendingOk
canRestore,         // isArchived && isAdmin
canUploadVersion,   // (isAdmin || isCreator) && is_editable && pendingOk
```

```ts
// Thin React wrapper: the predicate + every mutation handler + pending flags.
export function useDocumentActions(document: DocumentResponse)
```

Handlers: `saveTitle`, `saveTags`, `changeBucket`, `changeEditable`,
`assignApprover`, `handleRequestApproval`, `handleApprove`,
`handleRequestChanges`, `doArchive`, `restore`, `handleNewVersion`,
`downloadVersion` — each wired to its correct endpoint via the existing hooks
(`useUpdateDocument`, `useRequestApproval`, `useReviewDocument`,
`useArchiveDocument`, `useRestoreDocument`, `useUploadVersion`,
`useDownloadDocument`), all of which already exist.

`DocumentApprovalPanel` — shared component: notes textarea, Approve /
Request-changes buttons, the "notes required to request changes" rule, and
role-dependent copy ("Review & Approval Required" vs "Awaiting Document
Approval").

### 4.3 What changes in each surface

**`GraphDocumentInspector.tsx`**
* The free status dropdown is **removed**. The server has no endpoint for setting
  an arbitrary status, by design.
* Gains the real workflow: request approval (with `ApproverPicker`), the shared
  `DocumentApprovalPanel` placed in **both Overview and Edit tabs** (so inspecting an amber node allows immediate review without tab switching), archive, restore.
* `restore` moves from `PATCH {status}` to `useRestoreDocument`.
* Every control's enabled state comes from `useDocumentActions`.
* Both `as never` casts are removed.

**`DocumentDrawer.tsx`** — consumes the same hook, which fixes two live
frontend/server mismatches it has today:
* **Archive** is only disabled while pending approval. The server also requires
  `admin || creator`, so a colleague with mere bucket access currently sees an
  enabled Archive that 403s.
* **`editFrozen`** omits `_may_edit_document`, so that same user gets live
  title / tag / bucket controls, and a New Version dropzone, that 403.
* New: `canReview` picks up the self-review block, reachable when an admin
  assigns the creator as approver (permitted for admins via `PATCH approver_id`).

Copying the drawer would therefore have shipped two more KUB-020-shaped
"button that 403s" bugs. Extraction fixes the drawer too.

**Error handling** — a 403 or 409 from a stale session (role changed, someone
else advanced the document) closes the dialog and invalidates the document
queries rather than leaving a form that can only keep failing. Same pattern as
the KUB-020 disposal modal.

---

## 5. Checks at both ends, and the no-leak position

### 5.1 Backend: sound already; zero production changes

Verified by reading every handler. Pinned by test rather than trusted:

* Router-level `require_module("docvault")` covers the whole prefix.
* Every document endpoint: company scope, then `can_access_bucket` → **404**.
* `list_documents` / `search_documents` filter on `accessible_bucket_ids`; no
  cross-bucket row can escape. Admins are unfiltered by design.
* Bucket create / rename / access / delete and document `restore` are
  `require_admin`.
* `download_document` checks bucket access, confirms the requested version
  belongs to the document, and writes a `document.downloaded` activity row.
* `GET /approvers` is company-scoped, excludes the caller, includes only active
  users with DocVault access, and narrows to grant-holders (plus admins) for a
  restricted bucket. Every field returned (`email`, `full_name`, `role`,
  `department`, `designation`) is used by `ApproverPicker` for search and
  display, so nothing is over-returned.
* `DocVaultGraphPage` reads only `useBuckets` / `useDocuments`, both filtered.

### 5.2 Frontend: bidirectional, because both directions are bugs

The unit matrix asserts both:
* no control rendered that the server would refuse (403 dead-end — KUB-020 shape)
* no control hidden that the server would allow (silent loss of function)

### 5.3 No-leak position on this change

`useDocumentActions` derives everything from `profile` plus the already-returned
`DocumentResponse`. It requests no new data and surfaces no field the server did
not already return to that caller. The committed `openapi.json` is a schema
description, verified to contain no tenant data, hosts, or secrets.

### 5.4 Flagged, deliberately not fixed

* `download_document`'s `else` branch can raise `AttributeError` → 500 if
  `current_version_id` points at a version missing from `doc.versions` (the
  `version_id` branch 404s correctly). Robustness, not a leak.
* `Content-Disposition` uses the raw `original_filename` — this is **KUB-010**,
  already tracked as open in the security audit.
* The backend types several enum-backed response fields as bare `str`
  (`FinancialYearResponse.status`, `DepreciationRunResponse.status`,
  `DocVaultApproverResponse.role`, `DocumentReviewRequest.decision`), so the
  generated types are wider than reality and the frontend must re-narrow by
  hand. Typing these as their Python enums would remove the need. It is a
  production schema change, so it is out of scope here.
* `SalesPage.tsx:38`, `SalesDrawer.tsx:39` and `KraPage.tsx:23` still compare
  `role === 'manager'`. The live API's `UserRole` no longer contains `manager`
  (KUB-018), so these branches are dead. Behaviour is correct today — there are
  no managers — so this is cosmetic dead code, not breakage, and the typecheck
  will not flag it because `CompanyUserOut.role` is typed `string`. Left for a
  KUB-018 cleanup.

---

## 6. Test plan

### 6.1 Unit — `documentPermissions.test.ts`

Table-driven over **role** (admin, employee) × **relationship** (creator,
approver, both, neither) × **status** (uploaded, pending_approval,
action_required, verified, archived) × **`is_editable`** (true, false). Every
cell asserted against the §4.1 matrix, in both directions.

Named cases for the rules that are easy to get wrong:
* `test_creator_cannot_review_own_document_unless_admin`
* `test_only_admin_can_restore_archived_document`
* `test_only_admin_can_unlock_a_locked_document`
* `test_non_creator_non_approver_cannot_archive` (the drawer's current bug)
* `test_non_creator_non_approver_cannot_edit_metadata` (the drawer's other bug)
* `test_pending_approval_freezes_edits_for_everyone_but_approver_and_admin`

### 6.2 Functional

**Frontend** — for both `DocumentDrawer` and `GraphDocumentInspector`:
* each persona (admin / creator / approver / unrelated-with-bucket-access) sees
  exactly the controls the matrix allows
* each action calls the correct endpoint with the correct body
* `restore` calls `POST /restore`, never `PATCH`
* request-approval and review round-trip through the shared panel

**Backend** — extend `tests/test_docvault_approvals.py` for anything the §4.1
matrix shows uncovered.

### 6.3 Edge cases

* Self-review reachable only via an admin assigning creator-as-approver, then
  that creator attempting review → 403.
* `POST /restore` by a non-admin → 403; on a non-archived document → 409.
* Request approval from `verified` or `archived` → 409.
* Review a document not pending → 409.
* Archive while pending, as a non-approver → 403.
* New version on a `verified` document → status resets to `uploaded`, approval
  fields cleared.
* Locked document: title / tags / bucket → 409; `is_editable` on → 403 unless
  admin.
* Cross-tenant and no-bucket-access document ids → **404**, never 403, on every
  endpoint (no existence oracle).

### 6.4 Anti-tests

These assert the bugs are dead and stay meaningful if someone "fixes" the code
wrongly.

1. **No frontend call site sends `status` in a document update.** Static scan of
   `frontend/src`. Direct kill for Bug A; stays meaningful if someone resolves a
   future 422 by re-adding the field.
2. **Backend: `PATCH /documents/{id}` rejects `status` with 422 — including for
   an admin.** Proves the contract from the server side. Re-adding `status` to
   `DocumentUpdate` would undo KUB-007's self-approval fix.
3. **No `as never` casts in the DocVault surfaces** — that is what hid this from
   review.
4. **`openapi.json` matches `app.openapi()`** (guard 1).
5. **No hand-written shadow types** for anything the API defines (guard 2).
6. **Every route `docvaultApi` calls exists in the snapshot** (guard 3).

`GraphDocumentInspector.test.tsx:256` and `:445` are **rewritten, not deleted** —
the behaviours they cover are real; only their expected endpoints were wrong.

---

## 7. Verification

Because `schema.d.ts` and `types.ts` are app-wide, verification cannot be
DocVault-only.

```bash
# Backend — DocVault, the new guards, and the enforcement reflection tests
./.venv/bin/pytest tests/test_docvault.py tests/test_docvault_approvals.py \
  tests/test_docvault_bucket_rbac.py tests/test_api_contract.py \
  tests/test_module_enforcement.py tests/test_document_attach_gating.py -q

# Frontend — whole app, since the generated types touch every module
cd frontend && npx tsc -b && npx vitest run && npm run build
```

Type changes cannot alter runtime, so the blast radius of the regeneration is
compile-time. The one genuine runtime risk is the shadow-type removals, which is
precisely why the entire frontend suite runs rather than the DocVault files.

Each new anti-test must be **confirmed to fail when the fix is reverted**, as was
done for the KUB-020 static and concurrency guards.

---

## 8. Scope

**In scope**
* `useDocumentActions` + `documentPermissions` + `DocumentApprovalPanel`
* `GraphDocumentInspector` rewrite (status dropdown removed, real workflow added)
* `DocumentDrawer`'s two permission gaps
* Committed `openapi.json`, offline `gen:api`, three guard tests
* `schema.d.ts` regeneration, removal of all 11 shadow types, and the four enum
  narrowings converted to intersections
* The 6 test fixtures gaining `can_change_password` / `has_avatar`

**Out of scope**
* KUB-001 `GET /api/v1/custom-fields/{module}` gate
* KUB-008 `POST /api/v1/depreciation/runs` role gating
* KUB-010 `Content-Disposition` filename sanitisation
* `download_document`'s orphaned-version 500
* Any graph UX redesign — the Overview / Edit / Versions tabs stay
* Bucket RBAC changes

**Explicitly not done:** `status` is **not** added back to `DocumentUpdate`.
That field's absence is the KUB-007 fix.

**No database migration. No backend production code change** — Bug A is entirely
frontend correctness, since the server already enforces every rule; the backend
gains only tests and the snapshot artifact. This keeps production risk low.
