import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { salesApi } from '@/api/endpoints/sales'
import type { SalesRecordCreate, SalesRecordUpdate } from '@/api/types'

type SalesFilters = { status?: string }

export const salesKeys = {
  all: ['sales'] as const,
  list: (filters?: SalesFilters) => ['sales', 'list', filters ?? {}] as const,
  aggregate: ['sales', 'aggregate'] as const,
}

export function useSales(filters?: SalesFilters) {
  return useQuery({
    queryKey: salesKeys.list(filters),
    queryFn: () => salesApi.list(filters),
  })
}

export function useSalesAggregate() {
  return useQuery({
    queryKey: salesKeys.aggregate,
    queryFn: () => salesApi.aggregate(),
  })
}

function useInvalidateSales() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: salesKeys.all })
}

export function useCreateSale() {
  const invalidate = useInvalidateSales()
  return useMutation({
    mutationFn: (body: SalesRecordCreate) => salesApi.create(body),
    onSuccess: invalidate,
  })
}

export function useUpdateSale() {
  const invalidate = useInvalidateSales()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SalesRecordUpdate }) => salesApi.update(id, body),
    onSuccess: invalidate,
  })
}

/** Reads the uploaded file's sheets/headers for the import mapping step. */
export function useInspectSalesImport() {
  return useMutation({
    mutationFn: (formData: FormData) => salesApi.inspectImport(formData),
  })
}

export function useImportSales() {
  const invalidate = useInvalidateSales()
  return useMutation({
    mutationFn: (formData: FormData) => salesApi.import(formData),
    onSuccess: invalidate,
  })
}
