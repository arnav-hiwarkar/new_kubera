import { companyClient } from '@/api/clients/company'
import type {
  BucketResponse,
  BucketCreate,
  BucketUpdate,
  BucketAccessUpdate,
  DocumentResponse,
  DocumentUpdate,
  DocumentVersionResponse,
} from '@/api/types'

export const docvaultApi = {
  listBuckets: () => companyClient.get<BucketResponse[]>('/api/v1/docvault/buckets'),
  createBucket: (body: BucketCreate) =>
    companyClient.post<BucketResponse>('/api/v1/docvault/buckets', { body }),
  updateBucket: (id: string, body: BucketUpdate) =>
    companyClient.patch<BucketResponse>(`/api/v1/docvault/buckets/${id}`, { body }),
  updateBucketAccess: (id: string, body: BucketAccessUpdate) =>
    companyClient.patch<BucketResponse>(`/api/v1/docvault/buckets/${id}/access`, { body }),
  deleteBucket: (id: string) =>
    companyClient.delete<void>(`/api/v1/docvault/buckets/${id}`),

  listDocuments: (filters?: { bucket_id?: string; status?: string }) =>
    companyClient.get<DocumentResponse[]>('/api/v1/docvault/documents', { query: filters }),
  searchDocuments: (q: string) =>
    companyClient.get<DocumentResponse[]>('/api/v1/docvault/documents/search', { query: { q } }),
  getDocument: (id: string) =>
    companyClient.get<DocumentResponse>(`/api/v1/docvault/documents/${id}`),
  uploadDocument: (formData: FormData) =>
    companyClient.post<DocumentResponse>('/api/v1/docvault/documents', { formData }),
  uploadVersion: (id: string, formData: FormData) =>
    companyClient.post<DocumentVersionResponse>(
      `/api/v1/docvault/documents/${id}/versions`,
      { formData },
    ),
  updateDocument: (id: string, body: DocumentUpdate) =>
    companyClient.patch<DocumentResponse>(`/api/v1/docvault/documents/${id}`, { body }),
  deleteDocument: (id: string) =>
    companyClient.delete<void>(`/api/v1/docvault/documents/${id}`),
  downloadDocument: (id: string, versionId?: string) =>
    companyClient.get<Blob>(`/api/v1/docvault/documents/${id}/download`, {
      responseType: 'blob',
      query: versionId ? { version_id: versionId } : undefined,
    }),
}
