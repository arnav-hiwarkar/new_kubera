import { api } from '@/lib/api';
import type { 
  BucketResponse, 
  BucketCreate, 
  DocumentResponse, 
  DocumentUpdate 
} from '@/types/docvault';

export const docvaultApi = {
  // Buckets
  getBuckets: async () => {
    const { data } = await api.get<BucketResponse[]>('/docvault/buckets');
    return data;
  },
  createBucket: async (payload: BucketCreate) => {
    const { data } = await api.post<BucketResponse>('/docvault/buckets', payload);
    return data;
  },
  deleteBucket: async (bucketId: string) => {
    await api.delete(`/docvault/buckets/${bucketId}`);
  },

  // Documents
  getDocuments: async (bucketId?: string) => {
    const url = bucketId ? `/docvault/documents?bucket_id=${bucketId}` : '/docvault/documents';
    const { data } = await api.get<DocumentResponse[]>(url);
    return data;
  },
  getDocument: async (documentId: string) => {
    const { data } = await api.get<DocumentResponse>(`/docvault/documents/${documentId}`);
    return data;
  },
  uploadDocument: async (formData: FormData) => {
    const { data } = await api.post<DocumentResponse>('/docvault/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return data;
  },
  uploadVersion: async (documentId: string, formData: FormData) => {
    const { data } = await api.post<DocumentResponse>(`/docvault/documents/${documentId}/versions`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return data;
  },
  updateDocument: async (documentId: string, payload: DocumentUpdate) => {
    const { data } = await api.patch<DocumentResponse>(`/docvault/documents/${documentId}`, payload);
    return data;
  },
  deleteDocument: async (documentId: string) => {
    await api.delete(`/docvault/documents/${documentId}`);
  },
  downloadDocument: async (documentId: string) => {
    const response = await api.get(`/docvault/documents/${documentId}/download`, {
      responseType: 'blob'
    });
    return response.data;
  },
};
