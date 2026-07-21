import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { docvaultApi } from '@/api/endpoints/docvault'
import type { BucketAccessUpdate, DocumentUpdate } from '@/api/types'
import { saveBlob } from '@/lib/download'

export const docvaultKeys = {
  buckets: ['docvault', 'buckets'] as const,
  documents: (filters?: { bucket_id?: string; status?: string }) =>
    ['docvault', 'documents', filters ?? {}] as const,
}

export function useBuckets() {
  return useQuery({ queryKey: docvaultKeys.buckets, queryFn: () => docvaultApi.listBuckets() })
}

export function useDocuments(filters?: { bucket_id?: string; status?: string }) {
  return useQuery({
    queryKey: docvaultKeys.documents(filters),
    queryFn: () => docvaultApi.listDocuments(filters),
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

/** Soft-delete (archive + lock) via the DELETE endpoint. */
export function useArchiveDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: (id: string) => docvaultApi.deleteDocument(id),
    onSuccess: invalidate,
  })
}

export function useDownloadDocument() {
  return useMutation({
    mutationFn: ({ id, versionId, filename }: { id: string; versionId?: string; filename: string }) =>
      docvaultApi.downloadDocument(id, versionId).then((blob) => saveBlob(blob, filename)),
  })
}
