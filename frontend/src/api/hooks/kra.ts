import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { kraApi, type KraFilters } from '@/api/endpoints/kra'
import type { KRACreate, KRAUpdate } from '@/api/types'

export const kraKeys = {
  all: ['kra'] as const,
  list: (filters?: KraFilters) => ['kra', 'list', filters ?? {}] as const,
}

export function useKras(filters?: KraFilters) {
  return useQuery({
    queryKey: kraKeys.list(filters),
    queryFn: () => kraApi.list(filters),
  })
}

function useInvalidateKras() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: kraKeys.all })
}

export function useCreateKra() {
  const invalidate = useInvalidateKras()
  return useMutation({
    mutationFn: (body: KRACreate) => kraApi.create(body),
    onSuccess: invalidate,
  })
}

export function useUpdateKra() {
  const invalidate = useInvalidateKras()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: KRAUpdate }) => kraApi.update(id, body),
    onSuccess: invalidate,
  })
}
