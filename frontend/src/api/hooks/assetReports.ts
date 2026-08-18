import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assetReportsApi } from '@/api/endpoints/assetReports'

export const assetReportKeys = {
  list: ['asset-reports'] as const,
  preview: (key: string, fyId: string, unit: string) =>
    ['asset-reports', 'preview', key, fyId, unit] as const,
}

export function useAssetReportsList() {
  return useQuery({
    queryKey: assetReportKeys.list,
    queryFn: () => assetReportsApi.list(),
  })
}

export function useAssetReportPreview(reportKey: string, financialYearId: string, unit: string = 'absolute') {
  return useQuery({
    queryKey: assetReportKeys.preview(reportKey, financialYearId, unit),
    queryFn: async () => {
      const res = await fetch(
        `/api/v1/asset-reports/${reportKey}/preview-html?financial_year_id=${encodeURIComponent(
          financialYearId,
        )}&unit=${encodeURIComponent(unit)}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('company_token') || ''}`,
          },
        },
      )
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to load preview' }))
        throw new Error(err.detail || 'Failed to load preview')
      }
      return res.text()
    },
    enabled: !!reportKey && !!financialYearId,
  })
}

export function useArchiveAssetReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportKey,
      financialYearId,
      format = 'pdf',
      unit = 'absolute',
    }: {
      reportKey: string
      financialYearId: string
      format?: 'xlsx' | 'pdf'
      unit?: string
    }) => assetReportsApi.archive(reportKey, financialYearId, format, unit),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['docvault'] })
    },
  })
}
