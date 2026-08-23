import { companyClient } from '@/api/clients/company'
import type { CalcTrace } from '@/components/calc'
import type {
  DepreciationRunResponse,
  AssetDepreciationLineResponse,
  ItBlockDepreciationLineResponse,
} from '@/api/types'

/** Traces computed on demand and never stored. `income_tax` is null without a block. */
export interface DepreciationExplain {
  companies_act: CalcTrace
  income_tax: CalcTrace | null
}

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
  reopenRun: (runId: string, reason: string) =>
    companyClient.post<DepreciationRunResponse>(`/api/v1/depreciation/runs/${runId}/reopen`, {
      body: { reason },
    }),
  deleteRun: (runId: string) =>
    companyClient.delete<void>(`/api/v1/depreciation/runs/${runId}`),
  explain: (assetId: string, financialYearId: string) =>
    companyClient.post<DepreciationExplain>('/api/v1/depreciation/explain', {
      body: { asset_id: assetId, financial_year_id: financialYearId },
    }),
}
