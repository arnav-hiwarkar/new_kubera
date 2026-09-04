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

describe('documentPermissions — no document', () => {
  it('grants nothing if document is null or undefined', () => {
    const p1 = documentPermissions(asAdmin, null)
    expect(p1.canEditMeta).toBe(false)
    expect(p1.canArchive).toBe(false)
    const p2 = documentPermissions(asAdmin, undefined)
    expect(p2.canEditMeta).toBe(false)
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
