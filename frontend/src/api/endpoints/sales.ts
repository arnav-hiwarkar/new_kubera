import { companyClient } from '@/api/clients/company'
import type {
  SalesRecordResponse,
  SalesRecordCreate,
  SalesRecordUpdate,
  ImportResult,
  SalesImportInspectResponse,
} from '@/api/types'

export interface SalesAggregateRow {
  status: string
  total_amount: number
  count: number
}

export const salesApi = {
  list: (filters?: { status?: string }) =>
    companyClient.get<SalesRecordResponse[]>('/api/v1/sales', { query: filters }),
  aggregate: () => companyClient.get<SalesAggregateRow[]>('/api/v1/sales/aggregate'),
  get: (id: string) => companyClient.get<SalesRecordResponse>(`/api/v1/sales/${id}`),
  create: (body: SalesRecordCreate) =>
    companyClient.post<SalesRecordResponse>('/api/v1/sales', { body }),
  update: (id: string, body: SalesRecordUpdate) =>
    companyClient.patch<SalesRecordResponse>(`/api/v1/sales/${id}`, { body }),
  inspectImport: (formData: FormData) =>
    companyClient.post<SalesImportInspectResponse>('/api/v1/sales/import/inspect', { formData }),
  import: (formData: FormData) =>
    companyClient.post<ImportResult>('/api/v1/sales/import', { formData }),
  exportExcel: () =>
    companyClient.get<Blob>('/api/v1/sales/export/excel', { responseType: 'blob' }),
}
