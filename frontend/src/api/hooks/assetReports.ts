import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assetReportsApi, AssetReportFilters } from '@/api/endpoints/assetReports'

export const assetReportKeys = {
  list: ['asset-reports'] as const,
  preview: (key: string, fyId: string, unit: string, filters?: AssetReportFilters) =>
    ['asset-reports', 'preview', key, fyId, unit, filters] as const,
}

export function useAssetReportsList() {
  return useQuery({
    queryKey: assetReportKeys.list,
    queryFn: () => assetReportsApi.list(),
  })
}

export function useAssetReportPreview(
  reportKey: string,
  financialYearId: string,
  unit: string = 'absolute',
  filters?: AssetReportFilters,
) {
  return useQuery({
    queryKey: assetReportKeys.preview(reportKey, financialYearId, unit, filters),
    queryFn: async () => {
      const q = new URLSearchParams()
      q.append('financial_year_id', financialYearId)
      q.append('unit', unit)
      if (filters?.lifecycle_status) q.append('lifecycle_status', filters.lifecycle_status)
      if (filters?.operational_status) q.append('operational_status', filters.operational_status)
      if (filters?.condition) q.append('condition', filters.condition)
      if (filters?.category_id) q.append('category_id', filters.category_id)
      if (filters?.location_id) q.append('location_id', filters.location_id)
      if (filters?.branch_id) q.append('branch_id', filters.branch_id)
      if (filters?.custodian_id) q.append('custodian_id', filters.custodian_id)
      if (filters?.acquisition_id) q.append('acquisition_id', filters.acquisition_id)

      const res = await fetch(
        `/api/v1/asset-reports/${reportKey}/preview-html?${q.toString()}`,
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
      filters,
    }: {
      reportKey: string
      financialYearId: string
      format?: 'xlsx' | 'pdf'
      unit?: string
      filters?: AssetReportFilters
    }) => assetReportsApi.archive(reportKey, financialYearId, format, unit, filters),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['docvault'] })
    },
  })
}

