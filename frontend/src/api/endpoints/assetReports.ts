import { companyClient } from '@/api/clients/company'

export interface AssetReportDescriptor {
  key: string
  title: string
  description: string
}

export const assetReportsApi = {
  list: () => companyClient.get<AssetReportDescriptor[]>('/api/v1/asset-reports'),
  previewHtml: (reportKey: string, financialYearId: string, unit: string = 'absolute') =>
    companyClient.get<string>(`/api/v1/asset-reports/${reportKey}/preview-html`, {
      query: { financial_year_id: financialYearId, unit },
      responseType: 'text' as unknown as undefined,
    }),
  exportUrl: (
    reportKey: string,
    financialYearId: string,
    format: 'xlsx' | 'pdf' | 'html',
    unit: string = 'absolute',
  ) =>
    `/api/v1/asset-reports/${reportKey}/export?financial_year_id=${encodeURIComponent(
      financialYearId,
    )}&format=${encodeURIComponent(format)}&unit=${encodeURIComponent(unit)}`,
  packUrl: (
    financialYearId: string,
    format: 'xlsx' | 'pdf',
    unit: string = 'absolute',
  ) =>
    `/api/v1/asset-reports/pack?financial_year_id=${encodeURIComponent(
      financialYearId,
    )}&format=${encodeURIComponent(format)}&unit=${encodeURIComponent(unit)}`,
  archive: (
    reportKey: string,
    financialYearId: string,
    format: 'xlsx' | 'pdf' = 'pdf',
    unit: string = 'absolute',
  ) =>
    companyClient.post<{ status: string; document_id: string; title: string }>(
      `/api/v1/asset-reports/archive?report_key=${encodeURIComponent(
        reportKey,
      )}&financial_year_id=${encodeURIComponent(
        financialYearId,
      )}&format=${encodeURIComponent(format)}&unit=${encodeURIComponent(unit)}`,
    ),
}
