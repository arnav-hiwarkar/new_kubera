import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { depreciationApi } from '@/api/endpoints/depreciation'

export const depreciationKeys = {
  runs: ['depreciation', 'runs'] as const,
  run: (id: string) => ['depreciation', 'run', id] as const,
  lines: (id: string) => ['depreciation', 'lines', id] as const,
  itLines: (id: string) => ['depreciation', 'it-lines', id] as const,
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
