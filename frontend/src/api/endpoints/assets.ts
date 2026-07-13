import { companyClient } from '@/api/clients/company'
import type { AssetResponse, AssetCreate, AssetUpdate, ImportResult } from '@/api/types'

export type AssetFilters = {
  category?: string
  status?: string
}

export const assetsApi = {
  list: (filters?: AssetFilters) =>
    companyClient.get<AssetResponse[]>('/api/v1/assets', { query: filters }),
  get: (id: string) => companyClient.get<AssetResponse>(`/api/v1/assets/${id}`),
  create: (body: AssetCreate) => companyClient.post<AssetResponse>('/api/v1/assets', { body }),
  update: (id: string, body: AssetUpdate) =>
    companyClient.patch<AssetResponse>(`/api/v1/assets/${id}`, { body }),
  import: (formData: FormData) =>
    companyClient.post<ImportResult>('/api/v1/assets/import', { formData }),
  exportExcel: () =>
    companyClient.get<Blob>('/api/v1/assets/export/excel', { responseType: 'blob' }),
}
