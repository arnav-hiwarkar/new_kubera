import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { financialYearsApi } from '@/api/endpoints/financialYears'
import type { FinancialYearCreate } from '@/api/types'

export const financialYearKeys = {
  all: ['financial-years'] as const,
}

export function useFinancialYears() {
  return useQuery({
    queryKey: financialYearKeys.all,
    queryFn: () => financialYearsApi.list(),
  })
}

export function useCreateFinancialYear() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FinancialYearCreate) => financialYearsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: financialYearKeys.all })
    },
  })
}

export function useCloseFinancialYear() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => financialYearsApi.close(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: financialYearKeys.all })
    },
  })
}

export function useReopenFinancialYear() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => financialYearsApi.reopen(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: financialYearKeys.all })
    },
  })
}
