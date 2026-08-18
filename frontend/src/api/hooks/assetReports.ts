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
    queryFn: () => assetReportsApi.previewHtml(reportKey, financialYearId, unit, filters),
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

