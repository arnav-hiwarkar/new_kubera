import { companyClient } from '@/api/clients/company'
import type {
  DepreciationRunResponse,
  AssetDepreciationLineResponse,
  ItBlockDepreciationLineResponse,
} from '@/api/types'

export const depreciationApi = {
  listRuns: () => companyClient.get<DepreciationRunResponse[]>('/api/v1/depreciation/runs'),
  createRun: (financialYearId: string, notes?: string) =>
    companyClient.post<DepreciationRunResponse>('/api/v1/depreciation/runs', {
      body: { financial_year_id: financialYearId, notes },
    }),
  getRun: (runId: string) =>
    companyClient.get<DepreciationRunResponse>(`/api/v1/depreciation/runs/${runId}`),
  getLines: (runId: string) =>
    companyClient.get<AssetDepreciationLineResponse[]>(`/api/v1/depreciation/runs/${runId}/lines`),
  getItLines: (runId: string) =>
    companyClient.get<ItBlockDepreciationLineResponse[]>(
      `/api/v1/depreciation/runs/${runId}/it-lines`,
    ),
  finalizeRun: (runId: string) =>
    companyClient.post<DepreciationRunResponse>(`/api/v1/depreciation/runs/${runId}/finalize`),
  deleteRun: (runId: string) =>
    companyClient.delete<void>(`/api/v1/depreciation/runs/${runId}`),
}
