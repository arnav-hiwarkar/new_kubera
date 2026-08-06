import { companyClient } from '@/api/clients/company'
import type {
  BucketRefResponse,
  DocumentTypeResponse,
  DocumentTypeCreate,
  MeetingRecordResponse,
  MeetingRecordCreate,
  MeetingRecordUpdate,
  SyncResultResponse,
  UnsyncedDocumentResponse,
} from '@/api/types'

/**
 * The backend serves ROC and Secretarial compliance from one router factory,
 * differing only by URL prefix. We mirror that with a single factory keyed by
 * the domain's base path.
 */
function createComplianceApi(base: '/api/v1/roc' | '/api/v1/secretarial') {
  return {
    listDocumentTypes: () => companyClient.get<DocumentTypeResponse[]>(`${base}/document-types`),
    createDocumentType: (body: DocumentTypeCreate) =>
      companyClient.post<DocumentTypeResponse>(`${base}/document-types`, { body }),
    updateDocumentType: (id: string, body: DocumentTypeCreate) =>
      companyClient.put<DocumentTypeResponse>(`${base}/document-types/${id}`, { body }),
    deleteDocumentType: (id: string) =>
      companyClient.delete<void>(`${base}/document-types/${id}`),
    /** Live records by default; `archived` switches to the archived view. */
    listMeetingRecords: (archived = false) =>
      companyClient.get<MeetingRecordResponse[]>(`${base}/meeting-records`, {
        query: { archived },
      }),
    createMeetingRecord: (body: MeetingRecordCreate) =>
      companyClient.post<MeetingRecordResponse>(`${base}/meeting-records`, { body }),
    updateMeetingRecord: (id: string, body: MeetingRecordUpdate) =>
      companyClient.patch<MeetingRecordResponse>(`${base}/meeting-records/${id}`, { body }),
    /** The docVault bucket this domain files into; created server-side if absent. */
    getBucket: () => companyClient.get<BucketRefResponse>(`${base}/bucket`),
    listUnsyncedDocuments: () =>
      companyClient.get<UnsyncedDocumentResponse[]>(`${base}/meeting-records/unsynced`),
    syncFromDocVault: () =>
      companyClient.post<SyncResultResponse>(`${base}/meeting-records/sync`),
    /** Retires the record and archives its docVault document; nothing is deleted. */
    archiveMeetingRecord: (id: string) =>
      companyClient.post<MeetingRecordResponse>(`${base}/meeting-records/${id}/archive`),
    unarchiveMeetingRecord: (id: string) =>
      companyClient.post<MeetingRecordResponse>(`${base}/meeting-records/${id}/unarchive`),
  }
}

export const rocApi = createComplianceApi('/api/v1/roc')
export const secretarialApi = createComplianceApi('/api/v1/secretarial')
