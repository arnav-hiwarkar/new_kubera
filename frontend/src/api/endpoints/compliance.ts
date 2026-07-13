import { companyClient } from '@/api/clients/company'
import type {
  DocumentTypeResponse,
  DocumentTypeCreate,
  MeetingRecordResponse,
  MeetingRecordCreate,
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
    listMeetingRecords: () =>
      companyClient.get<MeetingRecordResponse[]>(`${base}/meeting-records`),
    createMeetingRecord: (body: MeetingRecordCreate) =>
      companyClient.post<MeetingRecordResponse>(`${base}/meeting-records`, { body }),
  }
}

export const rocApi = createComplianceApi('/api/v1/roc')
export const secretarialApi = createComplianceApi('/api/v1/secretarial')
