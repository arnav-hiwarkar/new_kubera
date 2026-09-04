# DocVault Status Actions & API Contract Drift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two DocVault graph actions that 422 in production, and close the stale-generated-types hole that hid them.

**Architecture:** Extract the document workflow rules into one pure predicate (`documentPermissions`) plus one React hook (`useDocumentActions`) and one shared approval component, consumed by both `DocumentDrawer` and `GraphDocumentInspector`. Separately, commit a canonical `openapi.json`, point `gen:api` at that file so regeneration needs no running backend, and add three pytest guards so the contract cannot silently drift again.

**Tech Stack:** FastAPI + Pydantic v2 (backend), React 18 + TanStack Query + TypeScript (frontend), pytest (backend + static guards), vitest + @testing-library/react (frontend), openapi-typescript 7.x.

**Spec:** `docs/superpowers/specs/2026-09-04-docvault-status-and-api-contract-drift-design.md`

## Global Constraints

- Branch: `fix/docvault-status-and-schema-drift`. Already created off `main` at `bc5c35e`.
- **`status` must never be added back to `DocumentUpdate`** (`app/schemas/docvault.py:78`). Its absence is the KUB-007 self-approval fix.
- **No database migration. No backend production code change.** The backend already enforces every rule; it gains only tests and the `openapi.json` artifact.
- Python: run pytest via `./.venv/bin/pytest` from the repo root.
- Backend integration tests need the compose stack: `docker compose up -d postgres redis`. The new guards in `unit_tests/` need neither.
- Never run the full backend suite — it is slow. Run only the modules listed in each task.
- Frontend commands run from `frontend/`.
- Pydantic `EmailStr` rejects `.test` TLDs — use `@testco.com`-style addresses in fixtures.
- `clean_tables` truncates every table between tests.
- Every anti-test must be confirmed to fail when its fix is reverted. This is an explicit step, not an aspiration.

## File Structure

**Created**
- `openapi.json` — canonical API contract snapshot at the repo root. Generated, committed, guarded.
- `unit_tests/test_api_contract.py` — the three static contract guards. DB-free, lives beside the other static guards (`test_compose_exposure.py`).
- `frontend/src/pages/company/docvault/documentPermissions.ts` — the pure predicate. No React, no imports from components.
- `frontend/src/pages/company/docvault/documentPermissions.test.ts` — table-driven unit matrix.
- `frontend/src/pages/company/docvault/useDocumentActions.ts` — React hook: predicate + mutations + toast/error handling.
- `frontend/src/pages/company/docvault/DocumentApprovalPanel.tsx` — shared approval presentation (pending-review block, review-note display, request-approval card).
- `frontend/src/pages/company/docvault/documentActions.test.tsx` — persona tests for the hook via a probe component.

**Modified**
- `frontend/package.json:13` — `gen:api` reads `openapi.json` instead of `http://localhost:8000/openapi.json`.
- `frontend/src/api/schema.d.ts` — regenerated from the snapshot.
- `frontend/src/api/types.ts` — 11 shadow types deleted, 4 enum narrowings converted to intersections, redundant intersections removed.
- `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx` — status dropdown removed, wired to the hook, `restore` fixed, both `as never` casts removed.
- `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx` — the two tests asserting the broken calls rewritten; auth mock added.
- `frontend/src/pages/company/docvault/DocumentDrawer.tsx` — wired to the hook; its two permission gaps closed.
- `frontend/src/pages/company/docvault/docvault_approvals.test.tsx` — updated for the shared panel.
- `tests/test_docvault_approvals.py` — backend anti-test for `status` rejection.
- 6 frontend test fixtures — gain `can_change_password` and `has_avatar`.

**Task ordering note.** The spec argues Bug B is the cause and should be fixed first. The plan deliberately regenerates types in **Task 7**, *after* the DocVault call sites are fixed in Task 5. Regenerating first would leave `tsc -b` red for several tasks, because the fresh types immediately reject `GraphDocumentInspector.tsx:91,118`. Landing the guard infrastructure first (Task 1) and the regeneration last keeps every task's checkpoint green while still ending in the same place.

---

### Task 1: API contract snapshot, currency guard, offline type generation

**Files:**
- Create: `openapi.json`
- Create: `unit_tests/test_api_contract.py`
- Modify: `frontend/package.json:13`

**Interfaces:**
- Consumes: nothing.
- Produces: `openapi.json` at the repo root — every later guard reads it. `unit_tests/test_api_contract.py::canonical_openapi()` helper, reused by Tasks 7 and 8.

- [ ] **Step 1: Write the failing test**

Create `unit_tests/test_api_contract.py`:

```python
"""Static guards keeping the committed API contract honest.

These live in unit_tests/ rather than tests/ because they need no database:
they compare files on disk against the FastAPI app object, which imports
standalone. Same reasoning as test_compose_exposure.py next door.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "openapi.json"

REGEN_HINT = (
    "The committed API contract is out of date.\n"
    "Regenerate both the snapshot and the frontend types:\n"
    "  ./.venv/bin/python -c \"import json,pathlib; from app.main import app; "
    "pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + chr(10))\"\n"
    "  cd frontend && npm run gen:api\n"
    "then commit openapi.json and frontend/src/api/schema.d.ts together."
)


def canonical_openapi() -> str:
    """The one true serialisation of the live schema. Deterministic: sorted keys,
    fixed indent, trailing newline so the file is POSIX-clean."""
    from app.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def test_openapi_snapshot_is_current():
    assert SNAPSHOT.exists(), f"{SNAPSHOT} is missing. {REGEN_HINT}"
    assert SNAPSHOT.read_text() == canonical_openapi(), REGEN_HINT


def test_canonical_openapi_is_deterministic():
    """If this ever fails, the snapshot guard would flap and get disabled."""
    assert canonical_openapi() == canonical_openapi()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest unit_tests/test_api_contract.py -v`
Expected: `test_openapi_snapshot_is_current` FAILS with "openapi.json is missing". `test_canonical_openapi_is_deterministic` PASSES.

- [ ] **Step 3: Generate the snapshot**

Run from the repo root:

```bash
./.venv/bin/python -c "import json,pathlib; from app.main import app; pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + chr(10))"
```

Sanity-check the result is the expected size (~24,313 lines):

```bash
wc -l openapi.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest unit_tests/test_api_contract.py -v`
Expected: both PASS.

- [ ] **Step 5: Point `gen:api` at the file**

In `frontend/package.json`, replace line 13:

```json
    "gen:api": "openapi-typescript ../openapi.json -o src/api/schema.d.ts"
```

Note the `../` — npm scripts run with `frontend/` as the working directory.

- [ ] **Step 6: Verify offline generation produces no diff**

Run: `cd frontend && npm run gen:api && cd .. && git diff --stat frontend/src/api/schema.d.ts`
Expected: `openapi-typescript` succeeds without a network call, and the diff is large (~1000 lines) because the committed types were stale. **Discard it for now** — Task 7 owns the regeneration:

```bash
git checkout -- frontend/src/api/schema.d.ts
```

- [ ] **Step 7: Confirm the guard catches real drift**

Temporarily perturb the snapshot and confirm the guard fires:

```bash
./.venv/bin/python -c "
import json,pathlib
p=pathlib.Path('openapi.json'); d=json.loads(p.read_text())
d['info']['title']='DRIFTED'
p.write_text(json.dumps(d, indent=2, sort_keys=True)+chr(10))"
./.venv/bin/pytest unit_tests/test_api_contract.py::test_openapi_snapshot_is_current -q
```

Expected: FAIL, with the regeneration hint printed. Then restore:

```bash
./.venv/bin/python -c "import json,pathlib; from app.main import app; pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + chr(10))"
./.venv/bin/pytest unit_tests/test_api_contract.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add openapi.json unit_tests/test_api_contract.py frontend/package.json
git commit -m "build(api): commit the canonical OpenAPI snapshot and guard it

Regenerating frontend types needed docker + uvicorn on localhost:8000, and that
friction is why schema.d.ts drifted ~1000 lines behind the backend. gen:api now
reads a committed openapi.json instead, so regeneration is offline and
deterministic, and a pytest guard fails the backend suite whenever the snapshot
falls behind app.openapi().

Lives in unit_tests/ because it needs no database. Verified to fail when the
snapshot is perturbed."
```

---

### Task 2: `documentPermissions` — the pure predicate

**Files:**
- Create: `frontend/src/pages/company/docvault/documentPermissions.ts`
- Test: `frontend/src/pages/company/docvault/documentPermissions.test.ts`

**Interfaces:**
- Consumes: `DocumentResponse` and `CompanyUserOut` from `@/api/types`.
- Produces: `documentPermissions(profile, document) → DocumentPermissions` and the exported `DocumentPermissions` interface. Tasks 3, 5 and 6 depend on these exact names and on every field listed below.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/company/docvault/documentPermissions.test.ts`:

```ts
/**
 * The rules here mirror app/routers/docvault.py exactly. Each assertion cites
 * the server behaviour it mirrors, because a drift in either direction is a bug:
 * a permission we grant but the server refuses is a 403 dead-end, and one we
 * withhold but the server allows is silent loss of function.
 */
import { describe, it, expect } from 'vitest'
import { documentPermissions } from './documentPermissions'
import type { DocumentResponse } from '@/api/types'

const CREATOR = 'u-creator'
const APPROVER = 'u-approver'
const OTHER = 'u-other'

function doc(over: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: 'doc-1',
    company_id: 'co-1',
    title: 'Q3 Board Minutes',
    status: 'uploaded',
    bucket_id: 'bucket-1',
    doc_type_id: null,
    tags: [],
    is_editable: true,
    created_by: CREATOR,
    approver_id: APPROVER,
    current_version_id: 'v-1',
    versions: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  } as unknown as DocumentResponse
}

const asAdmin = { id: OTHER, role: 'admin' }
const asCreator = { id: CREATOR, role: 'employee' }
const asApprover = { id: APPROVER, role: 'employee' }
const asStranger = { id: OTHER, role: 'employee' }

describe('documentPermissions — review', () => {
  it('lets the assigned approver review a pending document', () => {
    expect(documentPermissions(asApprover, doc({ status: 'pending_approval' })).canReview).toBe(true)
  })

  it('refuses review when the document is not pending', () => {
    // server: 409 "Document is not pending approval"
    for (const status of ['uploaded', 'action_required', 'verified', 'archived'] as const) {
      expect(documentPermissions(asApprover, doc({ status })).canReview).toBe(false)
    }
  })

  it('refuses review to someone who is neither approver nor admin', () => {
    // server: 403 "Not authorized to review"
    expect(documentPermissions(asStranger, doc({ status: 'pending_approval' })).canReview).toBe(false)
  })

  it('refuses review to the creator even when they are the approver', () => {
    // server: 403 "Uploader cannot review their own document". Reachable because
    // an admin may assign the creator as approver via PATCH approver_id.
    const selfApproved = doc({ status: 'pending_approval', created_by: CREATOR, approver_id: CREATOR })
    expect(documentPermissions({ id: CREATOR, role: 'employee' }, selfApproved).canReview).toBe(false)
  })

  it('allows an admin to review even when they created it', () => {
    // server: the self-review block is exempted for admins
    const own = doc({ status: 'pending_approval', created_by: OTHER, approver_id: OTHER })
    expect(documentPermissions(asAdmin, own).canReview).toBe(true)
  })
})

describe('documentPermissions — restore', () => {
  it('allows only an admin, and only on an archived document', () => {
    // server: require_admin + 409 unless status == archived
    expect(documentPermissions(asAdmin, doc({ status: 'archived' })).canRestore).toBe(true)
    expect(documentPermissions(asCreator, doc({ status: 'archived' })).canRestore).toBe(false)
    expect(documentPermissions(asAdmin, doc({ status: 'uploaded' })).canRestore).toBe(false)
  })
})

describe('documentPermissions — archive', () => {
  it('allows an admin or the creator', () => {
    // server: 403 "Only creator or admin can archive a document"
    expect(documentPermissions(asAdmin, doc()).canArchive).toBe(true)
    expect(documentPermissions(asCreator, doc()).canArchive).toBe(true)
  })

  it('refuses a non-creator non-admin — the drawer currently offers this and 403s', () => {
    expect(documentPermissions(asStranger, doc()).canArchive).toBe(false)
    expect(documentPermissions(asApprover, doc()).canArchive).toBe(false)
  })

  it('refuses while pending approval unless approver or admin', () => {
    const pending = doc({ status: 'pending_approval' })
    expect(documentPermissions(asCreator, pending).canArchive).toBe(false)
    expect(documentPermissions(asAdmin, pending).canArchive).toBe(true)
  })

  it('refuses on an already-archived document', () => {
    expect(documentPermissions(asAdmin, doc({ status: 'archived' })).canArchive).toBe(false)
  })
})

describe('documentPermissions — metadata edits', () => {
  it('refuses a non-creator non-approver non-admin — the drawer currently offers this and 403s', () => {
    // server: 403 "Not authorized to modify this document" (_may_edit_document)
    expect(documentPermissions(asStranger, doc()).canEditMeta).toBe(false)
    expect(documentPermissions(asStranger, doc()).canUploadVersion).toBe(false)
  })

  it('allows admin, creator and approver', () => {
    expect(documentPermissions(asAdmin, doc()).canEditMeta).toBe(true)
    expect(documentPermissions(asCreator, doc()).canEditMeta).toBe(true)
    expect(documentPermissions(asApprover, doc()).canEditMeta).toBe(true)
  })

  it('refuses when the document is locked', () => {
    // server: 409 "Document is not editable" for title/tags/bucket
    expect(documentPermissions(asAdmin, doc({ is_editable: false })).canEditMeta).toBe(false)
  })

  it('freezes edits while pending approval for everyone but approver and admin', () => {
    const pending = doc({ status: 'pending_approval' })
    expect(documentPermissions(asCreator, pending).canEditMeta).toBe(false)
    expect(documentPermissions(asApprover, pending).canEditMeta).toBe(true)
    expect(documentPermissions(asAdmin, pending).canEditMeta).toBe(true)
  })

  it('restricts version upload to admin or creator, not the approver', () => {
    // server: 403 "Only creator or admin can upload new versions"
    expect(documentPermissions(asApprover, doc()).canUploadVersion).toBe(false)
    expect(documentPermissions(asCreator, doc()).canUploadVersion).toBe(true)
    expect(documentPermissions(asAdmin, doc()).canUploadVersion).toBe(true)
  })
})

describe('documentPermissions — unlocking', () => {
  it('lets only an admin unlock a locked document', () => {
    // server: 403 "Only administrators can unlock a finalized document"
    const locked = doc({ is_editable: false })
    expect(documentPermissions(asAdmin, locked).canUnlock).toBe(true)
    expect(documentPermissions(asCreator, locked).canUnlock).toBe(false)
  })

  it('reports canUnlock false for an already-unlocked document', () => {
    expect(documentPermissions(asAdmin, doc({ is_editable: true })).canUnlock).toBe(false)
  })
})

describe('documentPermissions — request approval', () => {
  it('allows creator or admin from uploaded and action_required only', () => {
    // server: 403 unless creator/admin; 409 unless status in {uploaded, action_required}
    for (const status of ['uploaded', 'action_required'] as const) {
      expect(documentPermissions(asCreator, doc({ status })).canRequestApproval).toBe(true)
      expect(documentPermissions(asAdmin, doc({ status })).canRequestApproval).toBe(true)
      expect(documentPermissions(asStranger, doc({ status })).canRequestApproval).toBe(false)
    }
    for (const status of ['pending_approval', 'verified', 'archived'] as const) {
      expect(documentPermissions(asCreator, doc({ status })).canRequestApproval).toBe(false)
    }
  })
})

describe('documentPermissions — assign approver', () => {
  it('refuses a non-admin on a verified or archived document', () => {
    // server: 400 "Cannot change approver on a resolved or archived document"
    expect(documentPermissions(asCreator, doc({ status: 'verified' })).canAssignApprover).toBe(false)
    expect(documentPermissions(asAdmin, doc({ status: 'verified' })).canAssignApprover).toBe(true)
  })
})

describe('documentPermissions — no profile', () => {
  it('grants nothing while the profile is still loading', () => {
    const p = documentPermissions(null, doc())
    expect(p.canEditMeta).toBe(false)
    expect(p.canArchive).toBe(false)
    expect(p.canReview).toBe(false)
    expect(p.canRestore).toBe(false)
    expect(p.canRequestApproval).toBe(false)
    expect(p.canUploadVersion).toBe(false)
  })
})

describe('documentPermissions — full matrix is total', () => {
  it('returns a boolean for every flag across role x relationship x status x lock', () => {
    const roles = ['admin', 'employee'] as const
    const ids = [CREATOR, APPROVER, OTHER]
    const statuses = ['uploaded', 'pending_approval', 'action_required', 'verified', 'archived'] as const
    for (const role of roles)
      for (const id of ids)
        for (const status of statuses)
          for (const is_editable of [true, false]) {
            const p = documentPermissions({ id, role }, doc({ status, is_editable }))
            for (const [k, v] of Object.entries(p)) {
              expect(typeof v, `${k} for ${role}/${id}/${status}/${is_editable}`).toBe('boolean')
            }
          }
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/company/docvault/documentPermissions.test.ts`
Expected: FAIL — cannot resolve `./documentPermissions`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/pages/company/docvault/documentPermissions.ts`:

```ts
import type { CompanyUserOut, DocumentResponse } from '@/api/types'

/**
 * What the current user may do to this document.
 *
 * Every flag mirrors a rule in `app/routers/docvault.py`. Derived from the
 * server's handlers rather than from the existing UI, which was wrong in two
 * places: `DocumentDrawer` offered Archive and metadata edits to users the
 * server refuses. The server remains the boundary — this only decides what to
 * render, so that we neither show a control that 403s nor hide one that works.
 *
 * Bucket access is deliberately absent. It is checked server-side only and
 * answers with 404 rather than 403, so the endpoints are not a
 * document-existence oracle; the frontend must not try to second-guess it.
 */
export interface DocumentPermissions {
  isAdmin: boolean
  isCreator: boolean
  isApprover: boolean
  isArchived: boolean
  isPending: boolean
  /** `_may_edit_document`: admin, creator or assigned approver. */
  mayEdit: boolean
  /** While pending approval, only the approver or an admin may touch anything. */
  pendingOk: boolean
  canEditMeta: boolean
  canToggleEditable: boolean
  canUnlock: boolean
  canAssignApprover: boolean
  canRequestApproval: boolean
  canReview: boolean
  canArchive: boolean
  canRestore: boolean
  canUploadVersion: boolean
}

type Actor = Pick<CompanyUserOut, 'id' | 'role'> | null | undefined

export function documentPermissions(
  profile: Actor,
  document: DocumentResponse | null | undefined,
): DocumentPermissions {
  if (!document || !profile) {
    return {
      isAdmin: false,
      isCreator: false,
      isApprover: false,
      isArchived: false,
      isPending: false,
      mayEdit: false,
      pendingOk: false,
      canEditMeta: false,
      canToggleEditable: false,
      canUnlock: false,
      canAssignApprover: false,
      canRequestApproval: false,
      canReview: false,
      canArchive: false,
      canRestore: false,
      canUploadVersion: false,
    }
  }

  const isAdmin = profile.role === 'admin'
  const isCreator = profile.id === document.created_by
  const isApprover = profile.id === document.approver_id
  const isArchived = document.status === 'archived'
  const isPending = document.status === 'pending_approval'
  // `is_editable` is nullable in the schema; absent means editable.
  const editable = document.is_editable !== false

  const mayEdit = isAdmin || isCreator || isApprover
  const pendingOk = !isPending || isApprover || isAdmin
  const resolved = document.status === 'verified' || isArchived

  return {
    isAdmin,
    isCreator,
    isApprover,
    isArchived,
    isPending,
    mayEdit,
    pendingOk,
    // Archiving sets is_editable = false, so `editable` already covers the
    // archived case. Not adding an explicit !isArchived here on purpose: an
    // admin who unlocks an archived document may legitimately edit it, and
    // hiding the control would be a false negative.
    canEditMeta: mayEdit && pendingOk && editable,
    canToggleEditable: mayEdit && pendingOk && (editable || isAdmin),
    canUnlock: !editable && isAdmin,
    canAssignApprover: mayEdit && pendingOk && (isAdmin || !resolved),
    canRequestApproval:
      (document.status === 'uploaded' || document.status === 'action_required') &&
      (isCreator || isAdmin),
    canReview: isPending && (isApprover || isAdmin) && !(isCreator && !isAdmin),
    canArchive: !isArchived && (isAdmin || isCreator) && pendingOk,
    canRestore: isArchived && isAdmin,
    canUploadVersion: (isAdmin || isCreator) && editable && pendingOk,
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/company/docvault/documentPermissions.test.ts`
Expected: PASS, all cases.

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: exit 0, no output.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/company/docvault/documentPermissions.ts \
        frontend/src/pages/company/docvault/documentPermissions.test.ts
git commit -m "feat(docvault): add documentPermissions, derived from the server's rules

One pure predicate for what a user may do to a document, mirroring all six
handlers in app/routers/docvault.py. Derived from the server rather than from
the existing UI on purpose: DocumentDrawer offers Archive and metadata edits to
users the server refuses with 403, so copying it would have propagated the bug.

Table-driven over role x relationship x status x lock, asserting both
directions — a permission granted but refused server-side is a dead end, and one
withheld but allowed is silent loss of function."
```

---

### Task 3: `useDocumentActions` — the shared hook

**Files:**
- Create: `frontend/src/pages/company/docvault/useDocumentActions.ts`
- Test: `frontend/src/pages/company/docvault/documentActions.test.tsx`

**Interfaces:**
- Consumes: `documentPermissions`, `DocumentPermissions` from Task 2. Existing hooks from `@/api/hooks/docvault`: `useUpdateDocument`, `useReviewDocument`, `useRequestApproval`, `useArchiveDocument`, `useRestoreDocument`, `useUploadVersion`, `useDownloadDocument`.
- Produces: `useDocumentActions(document) → DocumentActions`. Tasks 5 and 6 consume exactly these member names: the spread of `DocumentPermissions`, plus `notes`, `setNotes`, `approverId`, `setApproverId`, `titleInput`, `setTitleInput`, `tagsInput`, `setTagsInput`, `saveTitle`, `saveTags`, `changeBucket`, `changeEditable`, `handleRequestApproval`, `handleApprove`, `handleRequestChanges`, `doArchive`, `restore`, `handleNewVersion`, `downloadVersion`, `isMutating`, `isReviewing`, `isRequesting`, `isRestoring`, `isUploadingVersion`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/company/docvault/documentActions.test.tsx`:

```tsx
/**
 * The hook's job is to call the *right endpoint*. Bug A was two actions calling
 * PATCH with a `status` field the server forbids, so these tests assert the
 * endpoint and body of every mutation.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { useDocumentActions } from './useDocumentActions'
import { docvaultApi } from '@/api/endpoints/docvault'
import type { DocumentResponse } from '@/api/types'

const authState = vi.hoisted(() => ({
  profile: null as { id: string; role: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: authState.profile, status: 'authenticated' }),
}))

vi.mock('@/api/endpoints/docvault', () => ({
  docvaultApi: {
    updateDocument: vi.fn().mockResolvedValue({}),
    reviewDocument: vi.fn().mockResolvedValue({}),
    requestApproval: vi.fn().mockResolvedValue({}),
    deleteDocument: vi.fn().mockResolvedValue(undefined),
    restoreDocument: vi.fn().mockResolvedValue({}),
    uploadVersion: vi.fn().mockResolvedValue({}),
    downloadDocument: vi.fn().mockResolvedValue(new Blob()),
    listDocuments: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock('@/lib/download', () => ({ saveBlob: vi.fn() }))

const DOC = {
  id: 'doc-1',
  company_id: 'co-1',
  title: 'Minutes',
  status: 'archived',
  bucket_id: 'bucket-1',
  doc_type_id: null,
  tags: [],
  is_editable: false,
  created_by: 'u-creator',
  approver_id: 'u-approver',
  current_version_id: 'v-1',
  versions: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as unknown as DocumentResponse

/** Minimal probe so we can drive the hook without a full component. */
function Probe({ document }: { document: DocumentResponse }) {
  const a = useDocumentActions(document)
  return (
    <div>
      <button onClick={() => void a.restore()}>restore</button>
      <button onClick={() => void a.doArchive()}>archive</button>
      <button onClick={() => void a.handleApprove()}>approve</button>
      <span data-testid="can-restore">{String(a.canRestore)}</span>
    </div>
  )
}

function wrap(document: DocumentResponse) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <Probe document={document} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('useDocumentActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.profile = { id: 'u-admin', role: 'admin' }
  })

  it('restores through the restore endpoint, never through PATCH', async () => {
    // This is Bug A: restore used to PATCH {status:'uploaded', is_editable:true},
    // which DocumentUpdate forbids (extra="forbid"), so it 422'd.
    const u = userEvent.setup()
    wrap(DOC)
    await u.click(screen.getByText('restore'))
    await waitFor(() => expect(docvaultApi.restoreDocument).toHaveBeenCalledWith('doc-1'))
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('archives through the DELETE endpoint', async () => {
    const u = userEvent.setup()
    wrap({ ...DOC, status: 'uploaded', is_editable: true } as DocumentResponse)
    await u.click(screen.getByText('archive'))
    await waitFor(() => expect(docvaultApi.deleteDocument).toHaveBeenCalledWith('doc-1'))
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('approves through the review endpoint with a decision, not a status', async () => {
    const u = userEvent.setup()
    wrap({ ...DOC, status: 'pending_approval', is_editable: true } as DocumentResponse)
    await u.click(screen.getByText('approve'))
    await waitFor(() =>
      expect(docvaultApi.reviewDocument).toHaveBeenCalledWith('doc-1', {
        decision: 'verified',
        approval_notes: undefined,
      }),
    )
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('exposes the permission flags alongside the handlers', async () => {
    wrap(DOC)
    expect(screen.getByTestId('can-restore').textContent).toBe('true')
  })

  it('withholds restore from a non-admin', async () => {
    authState.profile = { id: 'u-creator', role: 'employee' }
    wrap(DOC)
    expect(screen.getByTestId('can-restore').textContent).toBe('false')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/company/docvault/documentActions.test.tsx`
Expected: FAIL — cannot resolve `./useDocumentActions`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/pages/company/docvault/useDocumentActions.ts`:

```ts
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useCompanyAuth } from '@/auth/company'
import {
  useUpdateDocument,
  useReviewDocument,
  useRequestApproval,
  useArchiveDocument,
  useRestoreDocument,
  useUploadVersion,
  useDownloadDocument,
} from '@/api/hooks/docvault'
import type { DocumentResponse } from '@/api/types'
import { documentPermissions, type DocumentPermissions } from './documentPermissions'

/**
 * Every mutation a document supports, plus the permissions that say which of
 * them to render. Shared by DocumentDrawer and GraphDocumentInspector so the
 * two surfaces cannot drift again — that divergence is what let the graph
 * inspector keep PATCHing a `status` field the server forbids.
 *
 * Each handler is wired to the endpoint that actually owns the transition:
 * status moves via request-approval, review, archive and restore. There is no
 * "set arbitrary status" endpoint, by design (KUB-007).
 */
export interface DocumentActions extends DocumentPermissions {
  notes: string
  setNotes: (v: string) => void
  approverId: string | null
  setApproverId: (v: string | null) => void
  titleInput: string
  setTitleInput: (v: string) => void
  tagsInput: string
  setTagsInput: (v: string) => void

  saveTitle: () => Promise<void> | undefined
  saveTags: () => Promise<void>
  changeBucket: (bucketId: string) => Promise<void>
  changeEditable: (checked: boolean) => Promise<void>
  handleRequestApproval: () => Promise<void> | undefined
  handleApprove: () => Promise<void>
  handleRequestChanges: () => Promise<void> | undefined
  doArchive: () => Promise<void>
  restore: () => Promise<void>
  handleNewVersion: (files: File[]) => void
  downloadVersion: (versionId: string, filename: string) => void

  isMutating: boolean
  isReviewing: boolean
  isRequesting: boolean
  isRestoring: boolean
  isUploadingVersion: boolean
}

export function useDocumentActions(document: DocumentResponse | null | undefined): DocumentActions {
  const toast = useToast()
  const qc = useQueryClient()
  const { profile } = useCompanyAuth()

  const update = useUpdateDocument()
  const review = useReviewDocument()
  const requestApproval = useRequestApproval()
  const archive = useArchiveDocument()
  const restoreMutation = useRestoreDocument()
  const uploadVersion = useUploadVersion()
  const download = useDownloadDocument()

  const [notes, setNotes] = useState('')
  const [approverId, setApproverId] = useState<string | null>(null)
  const [titleInput, setTitleInput] = useState('')
  const [tagsInput, setTagsInput] = useState('')

  useEffect(() => {
    if (!document) return
    setNotes(document.approval_notes ?? '')
    setApproverId(document.approver_id ?? null)
    setTitleInput(document.title ?? '')
    setTagsInput(document.tags?.join(', ') ?? '')
  }, [document])

  const permissions = documentPermissions(profile, document)

  /**
   * 403 and 409 mean the caller's view of the document is stale — their role
   * changed, or someone else advanced it. Neither is fixable by resubmitting,
   * so refresh instead of leaving a control that can only keep failing. Same
   * pattern as the KUB-020 disposal modal.
   */
  const wrap = async (p: Promise<unknown>, ok: string) => {
    try {
      await p
      toast.success(ok)
    } catch (err) {
      if (err instanceof ApiError && (err.status === 403 || err.status === 409)) {
        toast.error(err.message || 'That is no longer permitted on this document.')
        qc.invalidateQueries({ queryKey: ['docvault', 'documents'] })
      } else {
        toast.error(err instanceof Error ? err.message : 'Action failed')
      }
    }
  }

  const saveTitle = () => {
    if (!document) return
    const title = titleInput.trim()
    if (!title || title === document.title) return
    return wrap(update.mutateAsync({ id: document.id, body: { title } }), 'Name updated')
  }

  const saveTags = () => {
    if (!document) return
    return wrap(
      update.mutateAsync({
        id: document.id,
        body: { tags: tagsInput.split(',').map((t) => t.trim()).filter(Boolean) },
      }),
      'Tags saved',
    )
  }

  const changeBucket = (bucketId: string) => {
    if (!document) return
    return wrap(
      update.mutateAsync({ id: document.id, body: { bucket_id: bucketId || null } }),
      'Moved',
    )
  }

  const changeEditable = (checked: boolean) => {
    if (!document) return
    return wrap(update.mutateAsync({ id: document.id, body: { is_editable: checked } }), 'Updated')
  }

  const handleRequestApproval = () => {
    if (!document) return
    const target = approverId || document.approver_id
    if (!target) {
      toast.error('Please select an approver')
      return
    }
    return wrap(
      requestApproval.mutateAsync({ id: document.id, body: { approver_id: target } }),
      document.status === 'action_required'
        ? 'Document resubmitted for approval'
        : 'Document submitted for approval',
    )
  }

  const handleApprove = () => {
    if (!document) return
    return wrap(
      review.mutateAsync({
        id: document.id,
        body: { decision: 'verified', approval_notes: notes.trim() || undefined },
      }),
      'Document approved (Status: Verified)',
    )
  }

  const handleRequestChanges = () => {
    if (!document) return
    if (!notes.trim()) {
      toast.error('Please enter notes explaining the requested changes')
      return
    }
    return wrap(
      review.mutateAsync({
        id: document.id,
        body: { decision: 'action_required', approval_notes: notes.trim() },
      }),
      'Document flagged for changes (Status: Action Required)',
    )
  }

  const doArchive = () => {
    if (!document) return
    return wrap(archive.mutateAsync(document.id), 'Document archived')
  }

  const restore = () => {
    if (!document) return
    return wrap(restoreMutation.mutateAsync(document.id), 'Document restored')
  }

  const handleNewVersion = (files: File[]) => {
    if (!document || !files.length) return
    const fd = new FormData()
    fd.append('file', files[0])
    void wrap(uploadVersion.mutateAsync({ id: document.id, formData: fd }), 'New version uploaded')
  }

  const downloadVersion = (versionId: string, filename: string) => {
    if (!document) return
    void wrap(download.mutateAsync({ id: document.id, versionId, filename }), 'Download started')
  }

  return {
    ...permissions,
    notes,
    setNotes,
    approverId,
    setApproverId,
    titleInput,
    setTitleInput,
    tagsInput,
    setTagsInput,
    saveTitle,
    saveTags,
    changeBucket,
    changeEditable,
    handleRequestApproval,
    handleApprove,
    handleRequestChanges,
    doArchive,
    restore,
    handleNewVersion,
    downloadVersion,
    isMutating: update.isPending,
    isReviewing: review.isPending,
    isRequesting: requestApproval.isPending,
    isRestoring: restoreMutation.isPending,
    isUploadingVersion: uploadVersion.isPending,
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/company/docvault/documentActions.test.tsx`
Expected: PASS, 5 tests.

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/company/docvault/useDocumentActions.ts \
        frontend/src/pages/company/docvault/documentActions.test.tsx
git commit -m "feat(docvault): add useDocumentActions, one hook for every document mutation

Wires each transition to the endpoint that owns it: request-approval, review,
archive (DELETE) and restore (POST /restore). There is no set-arbitrary-status
endpoint by design, which is what the graph inspector was wrongly assuming.

403 and 409 now refresh and explain rather than leaving a control that can only
keep failing — the caller's view is stale, and resubmitting cannot fix it."
```

---

### Task 4: `DocumentApprovalPanel` — the shared approval UI

**Files:**
- Create: `frontend/src/pages/company/docvault/DocumentApprovalPanel.tsx`
- Test: covered by Task 5 and Task 6 surface tests (this component has no logic of its own; it renders from `DocumentActions`).

**Interfaces:**
- Consumes: `DocumentActions` from Task 3, `ApproverPicker` from `./ApproverPicker`, `BucketResponse`/`DocumentResponse` from `@/api/types`.
- Produces: `<DocumentApprovalPanel document={...} actions={...} />`. Tasks 5 and 6 render exactly this.

- [ ] **Step 1: Write the implementation**

This component is pure presentation driven by `DocumentActions`, so it gets no
standalone test — Tasks 5 and 6 assert it through both surfaces, which is where
regressions would actually appear.

Create `frontend/src/pages/company/docvault/DocumentApprovalPanel.tsx`:

```tsx
import { Clock, CheckCircle2, AlertTriangle, MessageSquareQuote } from 'lucide-react'
import { Button, Field, Input } from '@/components/ui'
import { cn } from '@/lib/cn'
import { formatDate } from '@/lib/format'
import type { DocumentResponse } from '@/api/types'
import { ApproverPicker } from './ApproverPicker'
import type { DocumentActions } from './useDocumentActions'

/**
 * The approval section of a document: the pending-review block, the resolved
 * review note, and the submit/resubmit card. Shared by DocumentDrawer and
 * GraphDocumentInspector — it is the one piece of approval presentation
 * intricate enough that writing it twice is how the two surfaces drifted apart
 * in the first place.
 */
export function DocumentApprovalPanel({
  document,
  actions,
}: {
  document: DocumentResponse
  actions: DocumentActions
}) {
  const { isPending, canReview, canRequestApproval } = actions

  return (
    <>
      {isPending && (
        <div className="rounded-card border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col gap-3">
          <div className="flex items-start gap-2.5">
            <Clock className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold text-text-primary">
                {canReview ? 'Review & Approval Required' : 'Awaiting Document Approval'}
              </h4>
              <p className="text-xs text-text-muted mt-0.5">
                {canReview
                  ? `Requested by ${document.created_by_name || 'team member'} ${
                      document.approval_requested_at
                        ? `on ${formatDate(document.approval_requested_at)}`
                        : ''
                    }`
                  : `Assigned to ${
                      document.approver_name || 'the designated approver'
                    }. Edits are paused until review is completed.`}
              </p>
            </div>
          </div>

          {canReview && (
            <div className="flex flex-col gap-3 pt-2 border-t border-amber-500/20">
              <Field
                label="Review notes / feedback"
                htmlFor="approval-notes"
                hint="Optional for approval; required when requesting changes"
              >
                <Input
                  id="approval-notes"
                  value={actions.notes}
                  onChange={(e) => actions.setNotes(e.target.value)}
                  placeholder="e.g. Verified compliance checklist, ready for submission"
                  disabled={actions.isReviewing}
                />
              </Field>

              <div className="flex flex-wrap items-center gap-2.5 pt-1">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={actions.handleApprove}
                  loading={actions.isReviewing}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white"
                >
                  <CheckCircle2 className="h-4 w-4 mr-1.5" />
                  Approve (Verified)
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={actions.handleRequestChanges}
                  loading={actions.isReviewing}
                  className="border-amber-500/40 text-amber-400 hover:bg-amber-500/10"
                >
                  <AlertTriangle className="h-4 w-4 mr-1.5" />
                  Request Changes
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {!isPending && document.approval_notes && (
        <div
          className={cn(
            'rounded-card border p-3 flex items-start gap-2.5',
            document.status === 'action_required'
              ? 'border-amber-500/40 bg-amber-500/10'
              : 'border-border bg-bg-surface',
          )}
        >
          <MessageSquareQuote
            className={cn(
              'h-4 w-4 shrink-0 mt-0.5',
              document.status === 'action_required' ? 'text-amber-400' : 'text-accent',
            )}
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                {document.status === 'action_required' ? 'Requested Changes Note' : 'Review Note'} ·{' '}
                {document.approver_name || 'Approver'}
              </span>
              {document.approved_at && (
                <span className="text-xs text-text-muted">{formatDate(document.approved_at)}</span>
              )}
            </div>
            <p className="text-sm text-text-primary mt-1">{document.approval_notes}</p>
          </div>
        </div>
      )}

      {canRequestApproval && (
        <div className="rounded-card border border-accent/30 bg-accent/5 p-4 flex flex-col gap-3">
          <div className="flex items-start gap-2.5">
            <Clock className="h-5 w-5 shrink-0 text-accent mt-0.5" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold text-text-primary">
                {document.status === 'action_required' ? 'Resubmit for Review' : 'Submit for Review'}
              </h4>
              <p className="text-xs text-text-muted mt-0.5">
                {document.status === 'action_required'
                  ? 'Once revisions are complete, resubmit this document for approval.'
                  : 'Request an approver to review and verify this document.'}
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 pt-2 border-t border-accent/20">
            <Field label="Assign Approver">
              <ApproverPicker
                value={actions.approverId}
                onChange={actions.setApproverId}
                bucketId={document.bucket_id}
                disabled={actions.isRequesting || !actions.canAssignApprover}
              />
            </Field>
            <div className="flex justify-end pt-1">
              <Button
                variant="primary"
                size="sm"
                onClick={actions.handleRequestApproval}
                loading={actions.isRequesting}
                disabled={!actions.approverId && !document.approver_id}
              >
                {document.status === 'action_required'
                  ? 'Resubmit for Approval'
                  : 'Submit for Approval'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: exit 0.

- [ ] **Step 3: Confirm nothing regressed**

Run: `cd frontend && npx vitest run`
Expected: all tests pass. The component is not yet rendered anywhere, so counts are unchanged from baseline plus the tests added in Tasks 2 and 3.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/company/docvault/DocumentApprovalPanel.tsx
git commit -m "feat(docvault): extract DocumentApprovalPanel for both surfaces

The pending-review block, the resolved review note and the submit/resubmit card,
driven entirely by DocumentActions. This is the one piece of approval
presentation intricate enough that writing it twice is how the drawer and the
graph inspector drifted apart."
```

---

### Task 5: Fix `GraphDocumentInspector` — this closes Bug A

**Files:**
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx`
- Modify: `frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx`

**Interfaces:**
- Consumes: `useDocumentActions` (Task 3), `DocumentApprovalPanel` (Task 4).
- Produces: nothing new. This is the fix.

- [ ] **Step 1: Write the failing tests**

In `GraphDocumentInspector.test.tsx`, first add the auth mock the component will
now require. Insert immediately after the existing `vi.mock('@/lib/download', ...)`
block near the top of the file:

```tsx
// The inspector now reads the profile to decide which controls to render.
// mockDoc.created_by is 'u-1', so an admin with that id is creator + admin and
// therefore sees every control — which keeps the pre-existing cases valid.
const authState = vi.hoisted(() => ({
  profile: { id: 'u-1', role: 'admin' } as { id: string; role: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: authState.profile, status: 'authenticated' }),
}))
```

Then extend the `docvaultApi` mock object (currently 7 entries) with the three
endpoints the inspector will now call:

```tsx
    reviewDocument: vi.fn().mockResolvedValue({}),
    requestApproval: vi.fn().mockResolvedValue({}),
    restoreDocument: vi.fn().mockResolvedValue({}),
    listApprovers: vi.fn().mockResolvedValue([]),
```

Replace the test at line 256, `'handles changing status from select dropdown'`,
with this — the free status dropdown is gone, because the server has no endpoint
for it:

```tsx
  it('offers no free-form status control — status moves only through the workflow', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    // Bug A: this dropdown PATCHed a `status` field DocumentUpdate forbids, so
    // every pick 422'd. DocVault status transitions are request-approval,
    // review, archive and restore — there is no "set status" endpoint.
    expect(screen.queryByDisplayValue('Uploaded')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('Pending Approval')).not.toBeInTheDocument()
  })

  it('submits for approval through the request-approval endpoint', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={{ ...mockDoc, approver_id: 'u-approver' } as DocumentResponse}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')
    await user.click(screen.getByRole('button', { name: 'Submit for Approval' }))

    await waitFor(() =>
      expect(docvaultApi.requestApproval).toHaveBeenCalledWith('doc-1', {
        approver_id: 'u-approver',
      }),
    )
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('reviews a pending document through the review endpoint', async () => {
    const user = userEvent.setup()
    authState.profile = { id: 'u-approver', role: 'employee' }
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={
          { ...mockDoc, status: 'pending_approval', approver_id: 'u-approver' } as DocumentResponse
        }
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')
    await user.click(screen.getByRole('button', { name: /Approve \(Verified\)/ }))

    await waitFor(() =>
      expect(docvaultApi.reviewDocument).toHaveBeenCalledWith('doc-1', {
        decision: 'verified',
        approval_notes: undefined,
      }),
    )
  })

  it('allows approval review directly from the default Overview tab', async () => {
    const user = userEvent.setup()
    authState.profile = { id: 'u-approver', role: 'employee' }
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={
          { ...mockDoc, status: 'pending_approval', approver_id: 'u-approver' } as DocumentResponse
        }
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    // User is on the default 'overview' tab without switching
    expect(screen.getByText('Review & Approval Required')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Approve \(Verified\)/ }))

    await waitFor(() =>
      expect(docvaultApi.reviewDocument).toHaveBeenCalledWith('doc-1', {
        decision: 'verified',
        approval_notes: undefined,
      }),
    )
  })

  it('hides review controls from someone who is neither approver nor admin', async () => {
    const user = userEvent.setup()
    authState.profile = { id: 'u-stranger', role: 'employee' }
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={
          { ...mockDoc, status: 'pending_approval', approver_id: 'u-approver' } as DocumentResponse
        }
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')
    expect(screen.getByText('Awaiting Document Approval')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Approve \(Verified\)/ })).not.toBeInTheDocument()
  })

  it('withholds archive from a user who is neither creator nor admin', async () => {
    authState.profile = { id: 'u-stranger', role: 'employee' }
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    // server: 403 "Only creator or admin can archive a document"
    expect(screen.queryByRole('button', { name: 'Archive document' })).not.toBeInTheDocument()
  })
```

Replace the assertion at the end of the archived-document test (line ~445) so it
expects the restore endpoint:

```tsx
    await waitFor(() => expect(docvaultApi.restoreDocument).toHaveBeenCalledWith('doc-1'))
    // Bug A: restore used to PATCH {status:'uploaded', is_editable:true}, which
    // DocumentUpdate forbids, so it 422'd.
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
```

Add a `beforeEach` inside the top-level `describe` so the profile cannot leak
between cases (place it above the first `it`):

```tsx
  beforeEach(() => {
    vi.clearAllMocks()
    authState.profile = { id: 'u-1', role: 'admin' }
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx`
Expected: FAIL. The status-dropdown test fails because the dropdown still exists; the restore test fails because `restoreDocument` was not called; the new workflow tests fail because those controls do not exist yet.

- [ ] **Step 3: Rewire the component**

In `GraphDocumentInspector.tsx`:

1. Delete the `LIVE_STATUSES` constant (line ~29) and drop `DOCUMENT_STATUS` and `humanize` from the `@/api/enums` import. If the import becomes empty, delete the line.
2. Delete the `ApiError` import and the `useUpdateDocument`, `useArchiveDocument`, `useUploadVersion`, `useDownloadDocument` imports from `@/api/hooks/docvault` — the hook owns them now.
3. Add:

```tsx
import { useDocumentActions } from '../../useDocumentActions'
import { DocumentApprovalPanel } from '../../DocumentApprovalPanel'
```

4. Replace the whole block from `const toast = useToast()` down to and including
   `const downloadVersion = ...` with:

```tsx
  const actions = useDocumentActions(document)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    setTab('overview')
  }, [document])

  if (!open || !document) return null

  const bucketName = buckets.find((b) => b.id === document.bucket_id)?.name ?? 'Uncategorized'
  const currentVersion = document.versions.find((v) => v.id === document.current_version_id)
  const currentVersionNo =
    currentVersion?.version_number ??
    Math.max(0, ...document.versions.map((v) => v.version_number))
  const sortedVersions = [...document.versions].sort((a, b) => b.version_number - a.version_number)

  const doArchive = async () => {
    await actions.doArchive()
    setConfirmArchive(false)
  }
```

   Note: `useDocumentActions` must be called before the `if (!open || !document)`
   early return, because hooks cannot be called conditionally. `useDocumentActions`
   safely handles `null`/`undefined` document by returning all `false` flags.

5. In tab content, pass `actions` to both `OverviewTab` and `EditTab` (and drop the
   previous individual props on `EditTab`):

```tsx
              {tab === 'overview' && (
                <OverviewTab document={document} currentVersion={currentVersion} actions={actions} />
              )}
              {tab === 'edit' && (
                <EditTab document={document} buckets={buckets} actions={actions} />
              )}
```

6. Replace `OverviewTab` and `EditTab`:

```tsx
function OverviewTab({
  document,
  currentVersion,
  actions,
}: {
  document: DocumentResponse
  currentVersion?: DocumentResponse['versions'][number]
  actions: DocumentActions
}) {
  const facts: [string, string][] = [
    ['Created by', document.created_by_name ?? 'Unknown'],
    ['Current version by', currentVersion?.uploaded_by_name ?? 'Unknown'],
    ['Current version size', currentVersion ? formatBytes(currentVersion.size_bytes) : '—'],
    ['Versions', String(document.versions.length)],
    ['Updated', document.updated_at ? formatDate(document.updated_at) : '—'],
  ]
  return (
    <div className="flex flex-col gap-4">
      <DocumentApprovalPanel document={document} actions={actions} />
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {facts.map(([k, v]) => (
          <div key={k} className="col-span-2 grid grid-cols-[130px_1fr] items-baseline gap-3">
            <dt className="text-xs text-text-muted">{k}</dt>
            <dd className="text-sm text-text-primary truncate" title={v}>
              {v}
            </dd>
          </div>
        ))}
      </dl>
      <div>
        <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
          Tags
        </h3>
        {document.tags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {document.tags.map((t) => (
              <span
                key={t}
                className="rounded-full bg-bg-inset border border-border px-2 py-0.5 text-xs text-text-secondary"
              >
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

```tsx
function EditTab({
  document,
  buckets,
  actions,
}: {
  document: DocumentResponse
  buckets: BucketResponse[]
  actions: DocumentActions
}) {
  const isTitleUnchanged =
    !actions.titleInput.trim() || actions.titleInput.trim() === document.title

  return (
    <div className="flex flex-col gap-4">
      <DocumentApprovalPanel document={document} actions={actions} />

      {/* Status is read-only here: it moves through the workflow above, never
          by direct assignment. */}
      <Field label="Status">
        <div className="flex items-center gap-2">
          <StatusBadge status={document.status} />
          {actions.isArchived && (
            <span className="text-sm text-text-muted">Archived documents are locked.</span>
          )}
        </div>
      </Field>

      <Field
        label="Name"
        htmlFor="doc-title"
        hint={!actions.canEditMeta ? 'Locked — you cannot rename this document' : undefined}
      >
        <div className="flex gap-2">
          <Input
            id="doc-title"
            value={actions.titleInput}
            onChange={(e) => actions.setTitleInput(e.target.value)}
            disabled={!actions.canEditMeta}
            placeholder="Document name"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={actions.saveTitle}
            disabled={!actions.canEditMeta || isTitleUnchanged || actions.isMutating}
          >
            Save
          </Button>
        </div>
      </Field>

      <Field
        label="Editable"
        hint={
          actions.isPending && !actions.canReview
            ? 'Locked while pending approval. Only the assigned approver or an admin can adjust.'
            : !document.is_editable && !actions.isAdmin
              ? 'Finalized (Locked). Only an administrator can unlock this document.'
              : 'When off, the file is Final: no new versions, renaming, tags or bucket changes.'
        }
      >
        <Switch
          checked={document.is_editable}
          onChange={actions.changeEditable}
          disabled={!actions.canToggleEditable || actions.isMutating}
          label={document.is_editable ? 'Editable' : 'Locked'}
        />
      </Field>

      <Field label="Bucket" htmlFor="doc-bucket">
        <Select
          id="doc-bucket"
          value={document.bucket_id ?? ''}
          onChange={(e) => actions.changeBucket(e.target.value)}
          disabled={!actions.canEditMeta || actions.isMutating}
        >
          <option value="">Uncategorized</option>
          {buckets.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Tags" htmlFor="doc-tags" hint="Comma-separated">
        <div className="flex gap-2">
          <Input
            id="doc-tags"
            value={actions.tagsInput}
            onChange={(e) => actions.setTagsInput(e.target.value)}
            placeholder="board, 2026"
            disabled={!actions.canEditMeta}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={actions.saveTags}
            disabled={!actions.canEditMeta || actions.isMutating}
          >
            Save
          </Button>
        </div>
      </Field>
    </div>
  )
}
```

   Add `import type { DocumentActions } from '../../useDocumentActions'` at the top.

7. Replace the danger-zone footer so both buttons are permission-gated:

```tsx
        <div className="border-t border-border p-3">
          {actions.isArchived ? (
            actions.canRestore ? (
              <Button
                variant="secondary"
                onClick={actions.restore}
                loading={actions.isRestoring}
                className="w-full"
              >
                Restore document
              </Button>
            ) : (
              <p className="text-center text-xs text-text-muted">
                Only an administrator can restore an archived document.
              </p>
            )
          ) : (
            actions.canArchive && (
              <Button
                variant="danger"
                onClick={() => setConfirmArchive(true)}
                className="w-full"
              >
                Archive document
              </Button>
            )
          )}
        </div>
```

8. In `VersionsTab`, replace the `uploadVersion.isPending` / locked checks with
   `!actions.canUploadVersion` and `actions.isUploadingVersion`, and pass
   `actions` in place of `handleNewVersion`, `downloadVersion` and
   `uploadVersion`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx`
Expected: PASS, all cases including the five new ones.

- [ ] **Step 5: Confirm no `status` and no `as never` remain**

Run:

```bash
cd frontend && grep -n "status:" src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx | grep -v "document.status\|status=" ; grep -c "as never" src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx
```

Expected: no `status:` assignment lines, and `0` occurrences of `as never`.

- [ ] **Step 6: Typecheck and full frontend suite**

Run: `cd frontend && npx tsc -b && npx vitest run`
Expected: typecheck exit 0; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx \
        frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.test.tsx
git commit -m "fix(docvault): make the graph inspector's status actions actually work

Two actions were dead in production. The Edit tab's status dropdown and the
Restore button both sent a \`status\` field to PATCH /documents/{id}, which
DocumentUpdate forbids (extra=\"forbid\", no status field) since KUB-007 removed
it as the self-approval bypass. Both 422'd. Both were cast \`as never\`, which is
how they passed review, and both were covered by tests that mocked the client
and asserted the broken call.

The dropdown is gone — there is no set-arbitrary-status endpoint by design. The
inspector now runs the real workflow through useDocumentActions: request
approval, review, archive, restore. Restore calls POST /restore.

Controls are gated on the server's actual rules, so archive no longer shows to a
non-creator non-admin and metadata edits no longer show to someone outside
admin/creator/approver."
```

---

### Task 6: Migrate `DocumentDrawer` and close its two permission gaps

**Files:**
- Modify: `frontend/src/pages/company/docvault/DocumentDrawer.tsx`
- Modify: `frontend/src/pages/company/docvault/docvault_approvals.test.tsx`

**Interfaces:**
- Consumes: `useDocumentActions` (Task 3), `DocumentApprovalPanel` (Task 4).
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/pages/company/docvault/docvault_approvals.test.tsx`. Match
the file's existing mock and render helpers; if it does not already mock
`@/auth/company` with a mutable `authState`, add the same `vi.hoisted` pattern
used in Task 5 Step 1.

```tsx
describe('DocumentDrawer — permissions match the server', () => {
  it('withholds archive from a user who is neither creator nor admin', async () => {
    // server: 403 "Only creator or admin can archive a document". The drawer
    // used to show an enabled Archive here, which simply 403'd.
    authState.profile = { id: 'u-stranger', role: 'employee' }
    renderDrawer({ ...baseDoc, created_by: 'u-creator', approver_id: 'u-approver' })

    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
  })

  it('withholds metadata edits from a user outside admin/creator/approver', async () => {
    // server: 403 "Not authorized to modify this document" (_may_edit_document).
    // The drawer used to leave these inputs live.
    authState.profile = { id: 'u-stranger', role: 'employee' }
    renderDrawer({ ...baseDoc, created_by: 'u-creator', approver_id: 'u-approver' })

    expect(screen.getByLabelText('Name')).toBeDisabled()
  })

  it('still lets the creator archive their own document', async () => {
    authState.profile = { id: 'u-creator', role: 'employee' }
    renderDrawer({ ...baseDoc, created_by: 'u-creator', approver_id: 'u-approver' })

    expect(screen.getByRole('button', { name: 'Archive' })).toBeEnabled()
  })

  it('restores through the restore endpoint for an admin', async () => {
    const user = userEvent.setup()
    authState.profile = { id: 'u-admin', role: 'admin' }
    renderDrawer({ ...baseDoc, status: 'archived', is_editable: false })

    await user.click(screen.getByRole('button', { name: 'Restore document' }))
    await waitFor(() => expect(docvaultApi.restoreDocument).toHaveBeenCalledWith(baseDoc.id))
  })
})
```

If `renderDrawer` and `baseDoc` do not exist in that file under those names, add
them mirroring the file's existing setup, using a document whose `created_by` is
`'u-creator'` and `approver_id` is `'u-approver'`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/company/docvault/docvault_approvals.test.tsx`
Expected: FAIL — the archive button is present for the stranger, and the Name input is enabled.

- [ ] **Step 3: Rewire the drawer**

In `DocumentDrawer.tsx`:

1. Delete the local mutation hooks, the `useState` blocks for `tagsInput`,
   `titleInput`, `approvalNotesInput`, `reapproverId`, the `useEffect` that seeds
   them, all the derived permission booleans (`isArchived` through `editFrozen`),
   the `wrap` helper, and every handler from `handleApprove` to `downloadVersion`.
   Keep `const [confirmArchive, setConfirmArchive] = useState(false)`.
2. Add:

```tsx
import { useDocumentActions } from './useDocumentActions'
import { DocumentApprovalPanel } from './DocumentApprovalPanel'
```

3. Insert, calling the hook before the early return:

```tsx
  const actions = useDocumentActions(document)
  if (!document) return null
```

   `useDocumentActions` must be called before the early return, because hooks
   cannot be called conditionally. `useDocumentActions` safely handles
   `null`/`undefined` document.

4. Replace the three approval blocks (the `isPendingApproval` review section, the
   review-note display, and the submit/resubmit card — everything from
   `{/* Pending Approval Review Section */}` through the end of the
   `canRequestApproval` block) with:

```tsx
          <DocumentApprovalPanel document={document} actions={actions} />
```

5. Replace the remaining references: `editFrozen` → `!actions.canEditMeta`,
   `isAdmin` → `actions.isAdmin`, `isPendingApproval` → `actions.isPending`,
   `canReview` → `actions.canReview`, `update.isPending` → `actions.isMutating`,
   `titleInput`/`setTitleInput`/`tagsInput`/`setTagsInput` → the `actions.*`
   equivalents, and each handler → `actions.<handler>`.
6. Give the Name field an id so it is reachable by label:

```tsx
          <Field label="Name" htmlFor="drawer-title" hint={!actions.canEditMeta ? 'Locked from renaming' : undefined}>
            <div className="flex gap-2">
              <Input
                id="drawer-title"
                value={actions.titleInput}
                onChange={(e) => actions.setTitleInput(e.target.value)}
                disabled={!actions.canEditMeta}
              />
```

7. Gate the footer exactly as in Task 5 Step 3 item 7, using `actions.canArchive`
   and `actions.canRestore`.
8. Replace the version dropzone's disabled condition with
   `!actions.canUploadVersion`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/company/docvault/`
Expected: PASS — the new cases plus every pre-existing DocVault test.

- [ ] **Step 5: Confirm the duplication is gone**

Run:

```bash
cd frontend && grep -c "useReviewDocument\|useRequestApproval\|useRestoreDocument" \
  src/pages/company/docvault/DocumentDrawer.tsx \
  src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx
```

Expected: `0` for both files — only `useDocumentActions.ts` calls those hooks now.

- [ ] **Step 6: Typecheck and full frontend suite**

Run: `cd frontend && npx tsc -b && npx vitest run`
Expected: typecheck exit 0; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/company/docvault/DocumentDrawer.tsx \
        frontend/src/pages/company/docvault/docvault_approvals.test.tsx
git commit -m "fix(docvault): drawer shares the actions hook, closing two 403 dead-ends

The drawer was the reference implementation but it was wrong twice. Archive was
only disabled while pending approval, though the server also requires
admin||creator, so a colleague with bucket access saw an enabled Archive that
403'd. And editFrozen omitted _may_edit_document, leaving the name, tag, bucket
and new-version controls live for that same user.

Both surfaces now derive their controls from the server's rules through
useDocumentActions, so neither can offer an action the server refuses. The
approval UI is the shared panel."
```

---

### Task 7: Regenerate types, delete the 11 shadows, add the remaining guards

**Files:**
- Modify: `frontend/src/api/schema.d.ts` (regenerated)
- Modify: `frontend/src/api/types.ts`
- Modify: `unit_tests/test_api_contract.py`
- Modify: `frontend/src/pages/company/kra/kra.test.tsx:63`, `frontend/src/pages/company/users/UserModal.test.tsx:44,72`, `frontend/src/pages/company/UsersDirectory.test.tsx:33,34,35`

**Interfaces:**
- Consumes: `openapi.json` and `canonical_openapi()` from Task 1.
- Produces: `unit_tests/test_api_contract.py::test_types_ts_has_no_shadow_of_an_api_schema` and `::test_every_called_route_exists_in_the_contract`.

- [ ] **Step 1: Write the failing tests**

Append to `unit_tests/test_api_contract.py`:

```python
import re

TYPES_TS = REPO_ROOT / "frontend/src/api/types.ts"
ENDPOINTS_DIR = REPO_ROOT / "frontend/src/api/endpoints"

# Types with no server counterpart, verified absent from the OpenAPI. Every
# entry needs a reason, so this cannot quietly become a dumping ground.
LOCAL_ONLY_TYPES = {
    "ImpactPreview": "master-data impact preview is assembled client-side",
    "TBColumnMap": "trial-balance column mapping is a wizard-local structure",
}


def _schema_names() -> set[str]:
    return set(json.loads(SNAPSHOT.read_text())["components"]["schemas"])


def test_types_ts_has_no_shadow_of_an_api_schema():
    """A hand-written type whose name matches an API component is how drift
    becomes a silent bug: the declaration and the server disagree and nothing
    notices. Three depreciation shadows declared `number` for ~29 fields the API
    sends as Decimal strings; the DocVault approval types were hand-written
    because the generated schema was stale, which is what hid KUB-020-adjacent
    breakage in the graph inspector.

    Narrowing a loosely-typed server field is still allowed — write it as an
    intersection over the generated type (`S['X'] & { status: 'open' | 'closed' }`)
    so the rest of the shape cannot drift.
    """
    src = TYPES_TS.read_text()
    declared = {
        m.group(1)
        for m in re.finditer(
            r"^export\s+(?:interface|type)\s+([A-Za-z0-9_]+)\s*(?:=\s*)?\{", src, re.M
        )
    }
    shadows = sorted((declared & _schema_names()) - set(LOCAL_ONLY_TYPES))
    assert not shadows, (
        "types.ts hand-declares types the API already defines: "
        f"{shadows}\nUse S['<Name>'] instead, or an intersection over it to "
        "narrow a field. Add to LOCAL_ONLY_TYPES with a reason only if the type "
        "genuinely has no server counterpart."
    )


def _normalise(path: str) -> str:
    """`/api/v1/x/${id}/y` and `/api/v1/x/{id}/y` both become `/api/v1/x/{p}/y`."""
    path = re.sub(r"\$\{[^}]*\}", "{p}", path)
    path = re.sub(r"\{[^}]*\}", "{p}", path)
    return path.split("?")[0].rstrip("/")


def test_every_called_route_exists_in_the_contract():
    """Guard 1 catches drift in request/response *shapes*; this catches drift in
    *routes* — a frontend calling an endpoint that no longer exists.

    A bare prefix constant (`'/api/v1/asset-masters'`) counts as valid when real
    routes live beneath it, since those get concatenated at the call site.
    """
    known = {_normalise(p) for p in json.loads(SNAPSHOT.read_text())["paths"]}
    unmatched = []
    for f in sorted(ENDPOINTS_DIR.glob("*.ts")):
        for m in re.finditer(r"""[`'"](/api/v1/[^`'"]*)[`'"]""", f.read_text()):
            raw = m.group(1)
            n = _normalise(raw)
            if n in known or any(k.startswith(n + "/") for k in known):
                continue
            unmatched.append(f"{f.name}: {raw}")
    assert not unmatched, f"frontend calls routes absent from the API: {unmatched}"
```

- [ ] **Step 2: Run tests to verify the shadow guard fails**

Run: `./.venv/bin/pytest unit_tests/test_api_contract.py -v`
Expected: `test_types_ts_has_no_shadow_of_an_api_schema` FAILS, listing all 11:
`AssetDepreciationLineResponse`, `AssetDisposalRequest`, `AssetExistingCreate`,
`DepreciationRunResponse`, `DocVaultApproverResponse`,
`DocumentRequestApprovalRequest`, `DocumentReviewRequest`,
`FinancialYearCreate`, `FinancialYearResponse`,
`ItBlockDepreciationLineResponse`, `UserChangePasswordRequest`.
`test_every_called_route_exists_in_the_contract` PASSES.

- [ ] **Step 3: Regenerate the frontend types**

Run: `cd frontend && npm run gen:api`
Expected: ~1000-line diff in `src/api/schema.d.ts`, adding the 11 previously-missing components.

- [ ] **Step 4: Delete the shadows and convert the four narrowings**

In `frontend/src/api/types.ts`:

Replace the seven interfaces that match the server exactly with aliases:

```ts
export type UserChangePasswordRequest = S['UserChangePasswordRequest']
export type DocumentRequestApprovalRequest = S['DocumentRequestApprovalRequest']
export type AssetExistingCreate = S['AssetExistingCreate']
export type AssetDisposalRequest = S['AssetDisposalRequest']
export type FinancialYearCreate = S['FinancialYearCreate']
export type AssetDepreciationLineResponse = S['AssetDepreciationLineResponse']
export type ItBlockDepreciationLineResponse = S['ItBlockDepreciationLineResponse']
```

The two depreciation line types declared `number` for every money field, which
the API sends as `Decimal` strings. Nothing depended on the lie — the consuming
code already wraps values in `String(...)` and the fixtures use `'0.00'` — and
the generated types additionally carry `calc_trace`, which the hand-written ones
omitted entirely.

Replace the four that narrow a loosely-typed server field with intersections, so
the narrowing survives but the rest of the shape cannot drift:

```ts
// The backend types these as bare `str` even though a Python enum backs each
// one, so the generated types are wider than reality. Narrow here rather than
// re-declaring the whole shape. Typing them as enums server-side would remove
// the need — recorded as a follow-up in the design doc.
export type FinancialYearResponse = S['FinancialYearResponse'] & {
  status: 'open' | 'closed'
}
export type DepreciationRunResponse = S['DepreciationRunResponse'] & {
  status: 'draft' | 'finalized'
}
export type DocVaultApproverResponse = S['DocVaultApproverResponse'] & {
  role: 'admin' | 'employee'
}
export type DocumentReviewRequest = S['DocumentReviewRequest'] & {
  decision: 'verified' | 'action_required'
}
```

Delete the now-redundant intersections and role overrides — every field they add
is present in the regenerated schema, and `UserRole` is already
`"admin" | "employee"`:

```ts
export type UserRoleType = S['UserRole']
export type UserResponse = S['UserResponse']
export type UserCreate = S['UserCreate']
export type UserUpdate = S['UserUpdate']
export type CompanyUserOut = S['CompanyUserOut']
export type DocumentResponse = S['DocumentResponse']
export type DocumentUpdate = S['DocumentUpdate']
```

- [ ] **Step 5: Fix the six test fixtures**

`UserResponse` now requires `can_change_password: boolean` and exposes a
readonly `has_avatar: boolean`. Add both to each fixture at
`kra.test.tsx:63`, `UserModal.test.tsx:44`, `UserModal.test.tsx:72`,
`UsersDirectory.test.tsx:33`, `:34`, `:35`:

```ts
      can_change_password: true,
      has_avatar: false,
```

- [ ] **Step 6: Run all guards and the frontend suite**

Run:

```bash
./.venv/bin/pytest unit_tests/test_api_contract.py -v
cd frontend && npx tsc -b && npx vitest run && npm run build
```

Expected: all four pytest guards PASS; typecheck exit 0; every frontend test passes; build succeeds.

- [ ] **Step 7: Confirm the shadow guard catches a reintroduction**

```bash
cd frontend && printf '\nexport interface DocumentReviewRequest { decision: string }\n' >> src/api/types.ts
cd .. && ./.venv/bin/pytest unit_tests/test_api_contract.py::test_types_ts_has_no_shadow_of_an_api_schema -q
```

Expected: FAIL naming `DocumentReviewRequest`. Then revert:

```bash
cd frontend && git checkout -- src/api/types.ts && cd ..
```

Re-apply Step 4 if the checkout discarded it — verify with
`./.venv/bin/pytest unit_tests/test_api_contract.py -q` showing all PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/schema.d.ts frontend/src/api/types.ts unit_tests/test_api_contract.py \
        frontend/src/pages/company/kra/kra.test.tsx \
        frontend/src/pages/company/users/UserModal.test.tsx \
        frontend/src/pages/company/UsersDirectory.test.tsx
git commit -m "refactor(api): regenerate types and delete all 11 shadow declarations

schema.d.ts was ~1000 lines stale, missing 11 components including every type
KUB-007 added for DocVault approvals. Because the generated schema lacked them,
they were hand-written in types.ts — and then drifted.

Three lied outright: DepreciationRunResponse, AssetDepreciationLineResponse and
ItBlockDepreciationLineResponse declared \`number\` for ~29 money fields the API
sends as Decimal strings. Nobody depended on it (the UI wraps values in
String(...) and the fixtures use '0.00'), so deleting them is free — and the
generated types also carry calc_trace and book, which the hand-written versions
omitted entirely. Anyone who had written .toFixed() would have crashed.

Four narrowed a server field typed as bare \`str\`; those narrowings are correct
and become intersections over the generated type so only the narrowing is
hand-held. The User* overrides are gone: UserRole is already admin|employee
server-side after KUB-018.

Two new guards: no shadow declarations, and no frontend call to a route absent
from the contract. Both verified to fail when violated."
```

---

### Task 8: Anti-tests that keep both bugs dead

**Files:**
- Modify: `unit_tests/test_api_contract.py`
- Modify: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing consumed by later tasks. This is the final task.

- [ ] **Step 1: Write the failing static anti-tests**

Append to `unit_tests/test_api_contract.py`:

```python
FRONTEND_SRC = REPO_ROOT / "frontend/src"
DOCVAULT_SRC = FRONTEND_SRC / "pages/company/docvault"


def test_no_frontend_call_site_sends_a_document_status():
    """The KUB-020-shaped anti-test for this fix.

    `DocumentUpdate` has `extra="forbid"` and no `status` field — KUB-007
    removed it because free status-setting was the self-approval bypass. Two
    call sites in the graph inspector sent one anyway and 422'd in production.
    Status moves only through request-approval, review, archive and restore.

    Stays meaningful if someone "fixes" a future 422 by re-adding the field.
    """
    offenders = []
    for f in sorted(FRONTEND_SRC.rglob("*.ts*")):
        if f.name.endswith(".d.ts"):
            continue
        text = f.read_text()
        # A `status:` key inside a body passed to a document update.
        for m in re.finditer(r"(updateDocument|useUpdateDocument)[\s\S]{0,400}?", text):
            window = text[m.start(): m.start() + 400]
            if re.search(r"body:\s*\{[^}]*\bstatus\s*:", window):
                offenders.append(f"{f.relative_to(REPO_ROOT)}")
    assert not offenders, (
        "document update call sites sending a `status` field: "
        f"{sorted(set(offenders))}\nDocumentUpdate forbids it. Use "
        "requestApproval / reviewDocument / deleteDocument / restoreDocument."
    )


def test_docvault_surfaces_have_no_as_never_casts():
    """`as never` is what let the `status` bug past review — it silenced the
    exact type error that would have caught it."""
    offenders = [
        str(f.relative_to(REPO_ROOT))
        for f in sorted(DOCVAULT_SRC.rglob("*.tsx"))
        if "as never" in f.read_text()
    ] + [
        str(f.relative_to(REPO_ROOT))
        for f in sorted(DOCVAULT_SRC.rglob("*.ts"))
        if "as never" in f.read_text()
    ]
    assert not offenders, (
        f"`as never` casts in DocVault: {offenders}. These suppress the type "
        "errors that catch contract drift — fix the type instead."
    )
```

- [ ] **Step 2: Run to verify they pass now and would have failed before**

Run: `./.venv/bin/pytest unit_tests/test_api_contract.py -v`
Expected: both PASS (Task 5 removed the offenders).

Now prove they are not vacuous:

```bash
cd frontend && cp src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx /tmp/gdi.bak
python3 - <<'PY'
from pathlib import Path
p = Path('src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx')
s = p.read_text().replace(
  "const actions = useDocumentActions(",
  "const _regress = () => update.mutateAsync({ id: document.id, body: { status: 'uploaded' as never } })\n  const actions = useDocumentActions(",
  1)
p.write_text(s)
PY
cd .. && ./.venv/bin/pytest unit_tests/test_api_contract.py -q
```

Expected: BOTH new tests FAIL — one for the `status` body, one for `as never`. Then restore:

```bash
cp /tmp/gdi.bak frontend/src/pages/company/docvault/graph/components/GraphDocumentInspector.tsx
./.venv/bin/pytest unit_tests/test_api_contract.py -q
```

Expected: all PASS.

- [ ] **Step 3: Write the failing backend anti-test**

Append to `tests/test_docvault_approvals.py`:

```python
@pytest.mark.asyncio
async def test_patch_document_rejects_a_status_field_even_for_an_admin(client: AsyncClient):
    """The server half of the anti-test.

    KUB-007 removed `status` from DocumentUpdate because setting it directly was
    the self-approval bypass: an uploader could mark their own document verified
    without review. `extra="forbid"` makes the attempt a 422 rather than a
    silently-ignored field. Asserted for an admin too, so nobody "fixes" this by
    re-adding the field behind a role check.
    """
    await create_test_company(
        client, name="StatusCo", email="admin@statusco.com", password="Valid1!Pass"
    )
    token = await get_company_token(
        client, email="admin@statusco.com", password="Valid1!Pass"
    )
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("policy.pdf", b"pdf content", "application/pdf")}
    upload = await client.post(
        "/api/v1/docvault/documents",
        files=files,
        data={"title": "Policy"},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]
    assert upload.json()["status"] == "uploaded"

    for body in ({"status": "verified"}, {"status": "verified", "title": "Renamed"}):
        res = await client.patch(
            f"/api/v1/docvault/documents/{doc_id}", json=body, headers=headers
        )
        assert res.status_code == 422, f"{body} -> {res.status_code} {res.text}"

    # Neither the status nor the co-submitted title may have been applied.
    after = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=headers)
    assert after.json()["status"] == "uploaded"
    assert after.json()["title"] == "Policy"


@pytest.mark.asyncio
async def test_document_update_schema_has_no_status_field():
    """Fails the moment someone re-adds the field, without needing a request."""
    from app.schemas.docvault import DocumentUpdate

    assert "status" not in DocumentUpdate.model_fields
    assert DocumentUpdate.model_config.get("extra") == "forbid"
```

- [ ] **Step 4: Run the backend anti-tests**

Ensure the stack is up, then run:

```bash
docker compose up -d postgres redis
./.venv/bin/pytest tests/test_docvault_approvals.py -q
```

Expected: PASS, including the two new tests.

- [ ] **Step 5: Prove the schema anti-test is not vacuous**

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('app/schemas/docvault.py'); s = p.read_text()
p.write_text(s.replace("    title: Optional[str] = Field(None, max_length=255)",
                       "    status: Optional[str] = None\n    title: Optional[str] = Field(None, max_length=255)", 1))
PY
./.venv/bin/pytest tests/test_docvault_approvals.py::test_document_update_schema_has_no_status_field -q
git checkout -- app/schemas/docvault.py
```

Expected: FAIL while the field is present, then restore. Confirm with
`./.venv/bin/pytest tests/test_docvault_approvals.py -q` → PASS.

- [ ] **Step 6: Full verification across both stacks**

```bash
./.venv/bin/pytest unit_tests/test_api_contract.py tests/test_docvault.py \
  tests/test_docvault_approvals.py tests/test_docvault_bucket_rbac.py \
  tests/test_module_enforcement.py tests/test_document_attach_gating.py -q

cd frontend && npx tsc -b && npx vitest run && npm run build
```

Expected: all backend tests pass; typecheck exit 0; all frontend tests pass; build succeeds.

- [ ] **Step 7: Confirm the snapshot is still current**

The backend gained no production code, so this must still hold:

```bash
./.venv/bin/pytest unit_tests/test_api_contract.py::test_openapi_snapshot_is_current -q
```

Expected: PASS. If it fails, a production schema change slipped in — regenerate and review the diff before committing.

- [ ] **Step 8: Commit**

```bash
git add unit_tests/test_api_contract.py tests/test_docvault_approvals.py
git commit -m "test(docvault): anti-tests keeping the status bug and the drift dead

Four guards, each verified to fail when its fix is reverted:

- no frontend call site sends a \`status\` field to a document update
- no \`as never\` casts in the DocVault surfaces; that cast is what silenced the
  type error which would have caught the bug at review time
- PATCH /documents/{id} rejects \`status\` with 422, admin included, so nobody
  re-adds the field behind a role check and reopens the KUB-007 self-approval
  bypass
- DocumentUpdate.model_fields has no \`status\` and still forbids extras

The first two are static and run without a database, alongside the other static
guards in unit_tests/."
```

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| §3.1 canonical `openapi.json` | Task 1 |
| §3.2 `gen:api` reads the file | Task 1 Step 5 |
| §3.3 guard 1 snapshot currency | Task 1 |
| §3.3 guard 2 no shadow types | Task 7 |
| §3.3 guard 3 route existence | Task 7 |
| §3.4 regeneration, 11 shadows, 4 narrowings, 6 fixtures | Task 7 |
| §4.1 server permission matrix | Task 2 (predicate) + Task 2 tests |
| §4.2 `documentPermissions` | Task 2 |
| §4.2 `useDocumentActions` | Task 3 |
| §4.2 `DocumentApprovalPanel` | Task 4 |
| §4.3 graph inspector rewrite | Task 5 |
| §4.3 drawer's two gaps | Task 6 |
| §4.3 403/409 error handling | Task 3 (`wrap`) |
| §5.1 backend already sound, no production change | Global Constraints; Task 8 Step 7 asserts it |
| §5.2 bidirectional matrix | Task 2 tests (both directions asserted) |
| §6.1 unit matrix | Task 2 |
| §6.2 functional, both surfaces | Tasks 5 and 6 |
| §6.3 edge cases | Task 2 (state/role edges), Task 8 Step 3 (server 422/state) |
| §6.4 anti-tests 1–3 | Task 8 |
| §6.4 anti-tests 4–6 | Tasks 1 and 7 |
| §7 verification commands | Task 8 Step 6 |

Every spec section maps to a task. §6.3's endpoint-level 409/403 edges
(restore on a non-archived document, review when not pending, archive while
pending as a non-approver) are already covered by
`tests/test_docvault_approvals.py` and `tests/test_docvault_bucket_rbac.py`,
which Task 8 Step 6 runs; the new backend test adds only the `status`-rejection
case that did not exist.

**Placeholder scan:** no TBDs, no "add error handling", no "similar to Task N",
no "write tests for the above". Every code step carries the actual code. Every
type and function referenced across tasks is defined in an earlier task's
Interfaces block.

**Type consistency:** `documentPermissions` (Task 2) returns
`DocumentPermissions`; `DocumentActions` (Task 3) extends it, so every flag name
used in Tasks 4, 5 and 6 — `canEditMeta`, `canToggleEditable`, `canRestore`,
`canArchive`, `canReview`, `canRequestApproval`, `canUploadVersion`,
`canAssignApprover`, `isAdmin`, `isPending`, `isArchived` — resolves to the Task 2
definition. Pending flags are named `isMutating`, `isReviewing`, `isRequesting`,
`isRestoring`, `isUploadingVersion` consistently in Tasks 3–6.
`DocumentApprovalPanel` takes `{ document, actions }` in Tasks 4, 5 and 6 alike.

**One correctness note carried into the plan:** both Task 5 and Task 6 call
`useDocumentActions` *before* their `if (!document) return null` guard, because
React forbids conditional hook calls. Both tasks state this explicitly and pass
`document` directly since `useDocumentActions` safely handles `null` or `undefined`.
