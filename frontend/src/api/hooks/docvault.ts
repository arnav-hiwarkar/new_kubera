import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { docvaultApi } from '@/api/endpoints/docvault'
import type { BucketAccessUpdate, BucketUpdate, DocumentUpdate, DocumentReviewRequest, DocumentRequestApprovalRequest } from '@/api/types'
import { saveBlob } from '@/lib/download'

export interface DocumentFilters {
  bucket_id?: string
  status?: string
  tag?: string
  doc_type_id?: string
  approver_id?: string
  pending_my_approval?: boolean
}

export const docvaultKeys = {
  buckets: ['docvault', 'buckets'] as const,
  approvers: (bucketId?: string | null) => ['docvault', 'approvers', bucketId ?? 'all'] as const,
  documents: (filters?: DocumentFilters) =>
    ['docvault', 'documents', filters ?? {}] as const,
}

export function useBuckets() {
  return useQuery({ queryKey: docvaultKeys.buckets, queryFn: () => docvaultApi.listBuckets() })
}

export function useDocVaultApprovers(bucketId?: string | null) {
  return useQuery({
    queryKey: docvaultKeys.approvers(bucketId),
    queryFn: () => docvaultApi.listApprovers(bucketId ? { bucket_id: bucketId } : undefined),
  })
}

export function useDocuments(filters?: DocumentFilters) {
  return useQuery({
    queryKey: docvaultKeys.documents(filters),
    queryFn: () => docvaultApi.listDocuments(filters),
  })
}

export function usePendingApprovals() {
  return useQuery({
    queryKey: docvaultKeys.documents({ pending_my_approval: true }),
    queryFn: () => docvaultApi.listDocuments({ pending_my_approval: true }),
  })
}

/** Invalidate every documents list (any filter combination) after a mutation. */
function useInvalidateDocuments() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: ['docvault', 'documents'] })
}

export function useCreateBucket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => docvaultApi.createBucket({ name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: docvaultKeys.buckets }),
  })
}

export function useDeleteBucket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => docvaultApi.deleteBucket(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: docvaultKeys.buckets }),
  })
}

export function useUpdateBucket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: BucketUpdate }) =>
      docvaultApi.updateBucket(id, body),
    // The documents table resolves bucket names from the buckets list.
    onSuccess: () => qc.invalidateQueries({ queryKey: docvaultKeys.buckets }),
  })
}

export function useUpdateBucketAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: BucketAccessUpdate }) =>
      docvaultApi.updateBucketAccess(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: docvaultKeys.buckets })
      // Restricting a bucket changes which documents the viewer can see.
      qc.invalidateQueries({ queryKey: ['docvault', 'documents'] })
    },
  })
}

export function useUploadDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: (formData: FormData) => docvaultApi.uploadDocument(formData),
    onSuccess: invalidate,
  })
}

export function useUploadVersion() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: ({ id, formData }: { id: string; formData: FormData }) =>
      docvaultApi.uploadVersion(id, formData),
    onSuccess: invalidate,
  })
}

export function useUpdateDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DocumentUpdate }) =>
      docvaultApi.updateDocument(id, body),
    onSuccess: invalidate,
  })
}

export function useReviewDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DocumentReviewRequest }) =>
      docvaultApi.reviewDocument(id, body),
    onSuccess: invalidate,
  })
}

export function useRequestApproval() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DocumentRequestApprovalRequest }) =>
      docvaultApi.requestApproval(id, body),
    onSuccess: invalidate,
  })
}

/** Soft-delete (archive + lock) via the DELETE endpoint. */
export function useArchiveDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: (id: string) => docvaultApi.deleteDocument(id),
    onSuccess: invalidate,
  })
}

/** Restore an archived document via the restore endpoint. */
export function useRestoreDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: (id: string) => docvaultApi.restoreDocument(id),
    onSuccess: invalidate,
  })
}

export function useDownloadDocument() {
  return useMutation({
    mutationFn: ({ id, versionId, filename }: { id: string; versionId?: string; filename: string }) =>
      docvaultApi.downloadDocument(id, versionId).then((blob) => saveBlob(blob, filename)),
  })
}
