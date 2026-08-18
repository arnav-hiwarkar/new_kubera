import { companyClient } from '@/api/clients/company'
import type {
  AcquisitionResponse,
  AcquisitionUpdate,
  AssetDetailResponse,
  AssetDocRole,
  AssetDocumentAttach,
  AssetDocumentResponse,
  AssetQuickAddRequest,
  AssetQuickAddResponse,
  AssetResponse,
  AssetUpdate,
  BulkSerialRequest,
  CostPreviewRequest,
  CostPreviewResponse,
  TransitionRequest,
  TransitionResponse,
} from '@/api/types'

export type AssetFilters = {
  lifecycle_status?: string
  operational_status?: string
  condition?: string
  category_id?: string
  location_id?: string
  branch_id?: string
  custodian_id?: string
  acquisition_id?: string
  search?: string
}

export const assetsApi = {
  list: (filters?: AssetFilters) =>
    companyClient.get<AssetResponse[]>('/api/v1/assets', { query: filters }),
  /** Full detail for the tabbed page: asset + acquisition + siblings + docs + checklist. */
  get: (id: string) => companyClient.get<AssetDetailResponse>(`/api/v1/assets/${id}`),
  quickAdd: (body: AssetQuickAddRequest) =>
    companyClient.post<AssetQuickAddResponse>('/api/v1/assets/quick-add', { body }),
  update: (id: string, body: AssetUpdate) =>
    companyClient.patch<AssetResponse>(`/api/v1/assets/${id}`, { body }),
  remove: (id: string) => companyClient.delete<void>(`/api/v1/assets/${id}`),
  /** Server-authoritative costing, so the live form shows what will be stored. */
  costPreview: (body: CostPreviewRequest) =>
    companyClient.post<CostPreviewResponse>('/api/v1/assets/cost-preview', { body }),
  assignSerials: (id: string, body: BulkSerialRequest) =>
    companyClient.post<AssetResponse[]>(`/api/v1/assets/${id}/serials`, { body }),
  submit: (id: string, body: TransitionRequest) =>
    companyClient.post<TransitionResponse>(`/api/v1/assets/${id}/submit`, { body }),
  approve: (id: string, body: TransitionRequest) =>
    companyClient.post<TransitionResponse>(`/api/v1/assets/${id}/approve`, { body }),
  reject: (id: string, body: TransitionRequest) =>
    companyClient.post<TransitionResponse>(`/api/v1/assets/${id}/reject`, { body }),
  dispose: (id: string, body: import('@/api/types').AssetDisposalRequest) =>
    companyClient.post<AssetResponse>(`/api/v1/assets/${id}/dispose`, { body }),
  exportExcel: () =>
    companyClient.get<Blob>('/api/v1/assets/export/excel', { responseType: 'blob' }),

  // --- Documents ---
  listDocuments: (assetId: string) =>
    companyClient.get<AssetDocumentResponse[]>(`/api/v1/assets/${assetId}/documents`),
  attachDocument: (assetId: string, body: AssetDocumentAttach) =>
    companyClient.post<AssetDocumentResponse>(`/api/v1/assets/${assetId}/documents`, { body }),
  uploadDocument: (assetId: string, formData: FormData) =>
    companyClient.post<AssetDocumentResponse>(`/api/v1/assets/${assetId}/documents/upload`, {
      formData,
    }),
  uploadAcquisitionDocument: (acqId: string, formData: FormData) =>
    companyClient.post<AssetDocumentResponse>(
      `/api/v1/asset-acquisitions/${acqId}/documents/upload`,
      { formData },
    ),
  detachDocument: (linkId: string) =>
    companyClient.delete<void>(`/api/v1/asset-documents/${linkId}`),
  /** Vault files are encrypted at rest, so images load through this authenticated
   *  decrypt-and-stream endpoint rather than a direct <img src>. */
  documentBlob: (linkId: string) =>
    companyClient.get<Blob>(`/api/v1/asset-documents/${linkId}/thumbnail`, {
      responseType: 'blob',
    }),
}

export const acquisitionsApi = {
  list: (supplierId?: string) =>
    companyClient.get<AcquisitionResponse[]>('/api/v1/asset-acquisitions', {
      query: supplierId ? { supplier_id: supplierId } : undefined,
    }),
  get: (id: string) => companyClient.get<AcquisitionResponse>(`/api/v1/asset-acquisitions/${id}`),
  units: (id: string) =>
    companyClient.get<AssetResponse[]>(`/api/v1/asset-acquisitions/${id}/units`),
  update: (id: string, body: AcquisitionUpdate) =>
    companyClient.patch<AcquisitionResponse>(`/api/v1/asset-acquisitions/${id}`, { body }),
}

/** Roles that live on the acquisition (shared paperwork) rather than a single unit.
 *  Mirrors ACQUISITION_DOC_ROLES in app/models/assets.py. */
export const ACQUISITION_DOC_ROLES: readonly AssetDocRole[] = [
  'invoice',
  'purchase_order',
  'grn',
  'eway_bill',
  'approval',
  'customs',
  'lease',
]

export const PHOTO_DOC_ROLES: readonly AssetDocRole[] = ['asset_photo', 'serial_photo']
