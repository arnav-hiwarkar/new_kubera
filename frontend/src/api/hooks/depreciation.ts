import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { depreciationApi } from '@/api/endpoints/depreciation'

export const depreciationKeys = {
  runs: ['depreciation', 'runs'] as const,
  run: (id: string) => ['depreciation', 'run', id] as const,
  lines: (id: string) => ['depreciation', 'lines', id] as const,
  itLines: (id: string) => ['depreciation', 'it-lines', id] as const,
  explain: (assetId: string, fyId: string) =>
    ['depreciation', 'explain', assetId, fyId] as const,
}

export function useDepreciationRuns() {
  return useQuery({
    queryKey: depreciationKeys.runs,
    queryFn: () => depreciationApi.listRuns(),
  })
}

export function useDepreciationRun(runId: string) {
  return useQuery({
    queryKey: depreciationKeys.run(runId),
    queryFn: () => depreciationApi.getRun(runId),
    enabled: !!runId,
  })
}

export function useAssetDepreciationLines(runId: string) {
  return useQuery({
    queryKey: depreciationKeys.lines(runId),
    queryFn: () => depreciationApi.getLines(runId),
    enabled: !!runId,
  })
}

export function useItBlockDepreciationLines(runId: string) {
  return useQuery({
    queryKey: depreciationKeys.itLines(runId),
    queryFn: () => depreciationApi.getItLines(runId),
    enabled: !!runId,
  })
}

export function useCreateDepreciationRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ financialYearId, notes }: { financialYearId: string; notes?: string }) =>
      depreciationApi.createRun(financialYearId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: depreciationKeys.runs })
    },
  })
}

export function useFinalizeDepreciationRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => depreciationApi.finalizeRun(runId),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: depreciationKeys.runs })
      qc.invalidateQueries({ queryKey: depreciationKeys.run(runId) })
    },
  })
}

/** Flips a finalized year back to draft. The reason is recorded in the audit
 *  log, so it travels with the mutation rather than being a UI-only note. */
export function useReopenDepreciationRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, reason }: { runId: string; reason: string }) =>
      depreciationApi.reopenRun(runId, reason),
    onSuccess: (_data, { runId }) => {
      qc.invalidateQueries({ queryKey: depreciationKeys.runs })
      qc.invalidateQueries({ queryKey: depreciationKeys.run(runId) })
    },
  })
}

export function useDeleteDepreciationRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => depreciationApi.deleteRun(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: depreciationKeys.runs })
    },
  })
}

/**
 * A depreciation projection for one asset and year, computed on demand.
 *
 * `enabled` is required rather than defaulted: this fires the engine, so it must wait
 * until the drawer is actually open.
 */
export function useExplainDepreciation(assetId: string, fyId: string, enabled: boolean) {
  return useQuery({
    queryKey: depreciationKeys.explain(assetId, fyId),
    queryFn: () => depreciationApi.explain(assetId, fyId),
    enabled: enabled && !!assetId && !!fyId,
    // Inputs change while a user is editing the asset, so a stale projection would
    // explain figures they have already moved past.
    staleTime: 0,
    retry: false,
  })
}
