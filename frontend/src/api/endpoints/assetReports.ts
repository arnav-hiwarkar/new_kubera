import { companyClient } from '@/api/clients/company'

export interface AssetReportDescriptor {
  key: string
  title: string
  description: string
}

export interface AssetReportFilters {
  lifecycle_status?: string
  operational_status?: string
  condition?: string
  category_id?: string
  location_id?: string
  branch_id?: string
  custodian_id?: string
  acquisition_id?: string
}

function buildFilterQuery(filters?: AssetReportFilters): string {
  if (!filters) return ''
  const params = new URLSearchParams()
  if (filters.lifecycle_status) params.append('lifecycle_status', filters.lifecycle_status)
  if (filters.operational_status) params.append('operational_status', filters.operational_status)
  if (filters.condition) params.append('condition', filters.condition)
  if (filters.category_id) params.append('category_id', filters.category_id)
  if (filters.location_id) params.append('location_id', filters.location_id)
  if (filters.branch_id) params.append('branch_id', filters.branch_id)
  if (filters.custodian_id) params.append('custodian_id', filters.custodian_id)
  if (filters.acquisition_id) params.append('acquisition_id', filters.acquisition_id)
  const q = params.toString()
  return q ? `&${q}` : ''
}

/**
 * Every call goes through `companyClient`, which reads the access token from
 * `companyTokenStorage` and refreshes it on 401. Earlier versions of this module
 * returned bare URL strings for export/pack, which forced the page to hand-roll a
 * `fetch` and read the token from a localStorage key that did not exist — so every
 * asset report came back 403 "Not authenticated".
 */
export const assetReportsApi = {
  list: () => companyClient.get<AssetReportDescriptor[]>('/api/v1/asset-reports'),
  previewHtml: (
    reportKey: string,
    financialYearId: string,
    unit: string = 'absolute',
    filters?: AssetReportFilters,
  ) =>
    companyClient.get<string>(
      `/api/v1/asset-reports/${reportKey}/preview-html?financial_year_id=${encodeURIComponent(
        financialYearId,
      )}&unit=${encodeURIComponent(unit)}${buildFilterQuery(filters)}`,
      { responseType: 'text' },
    ),
  exportBlob: (
    reportKey: string,
    financialYearId: string,
    format: 'xlsx' | 'pdf' | 'html',
    unit: string = 'absolute',
    filters?: AssetReportFilters,
  ) =>
    companyClient.get<Blob>(
      `/api/v1/asset-reports/${reportKey}/export?financial_year_id=${encodeURIComponent(
        financialYearId,
      )}&format=${encodeURIComponent(format)}&unit=${encodeURIComponent(unit)}${buildFilterQuery(
        filters,
      )}`,
      { responseType: 'blob' },
    ),
  packBlob: (
    financialYearId: string,
    format: 'xlsx' | 'pdf',
    unit: string = 'absolute',
    filters?: AssetReportFilters,
  ) =>
    companyClient.post<Blob>(
      `/api/v1/asset-reports/pack?financial_year_id=${encodeURIComponent(
        financialYearId,
      )}&format=${encodeURIComponent(format)}&unit=${encodeURIComponent(unit)}${buildFilterQuery(
        filters,
      )}`,
      { responseType: 'blob' },
    ),
  archive: (
    reportKey: string,
    financialYearId: string,
    format: 'xlsx' | 'pdf' = 'pdf',
    unit: string = 'absolute',
    filters?: AssetReportFilters,
  ) =>
    companyClient.post<{ status: string; document_id: string; title: string }>(
      `/api/v1/asset-reports/archive?report_key=${encodeURIComponent(
        reportKey,
      )}&financial_year_id=${encodeURIComponent(
        financialYearId,
      )}&format=${encodeURIComponent(format)}&unit=${encodeURIComponent(unit)}${buildFilterQuery(
        filters,
      )}`,
    ),
}
