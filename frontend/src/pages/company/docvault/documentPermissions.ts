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
