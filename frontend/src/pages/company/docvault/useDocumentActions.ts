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

  const saveTags = async () => {
    if (!document) return
    return wrap(
      update.mutateAsync({
        id: document.id,
        body: { tags: tagsInput.split(',').map((t) => t.trim()).filter(Boolean) },
      }),
      'Tags saved',
    )
  }

  const changeBucket = async (bucketId: string) => {
    if (!document) return
    return wrap(
      update.mutateAsync({ id: document.id, body: { bucket_id: bucketId || null } }),
      'Moved',
    )
  }

  const changeEditable = async (checked: boolean) => {
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

  const handleApprove = async () => {
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

  const doArchive = async () => {
    if (!document) return
    return wrap(archive.mutateAsync(document.id), 'Document archived')
  }

  const restore = async () => {
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
