import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFieldsApi } from '@/api/endpoints/customFields'
import type { CustomFieldCreate, CustomFieldUpdate } from '@/api/types'
import type { components } from '@/api/schema'

type Module = components['schemas']['CustomFieldModule']

export function useCustomFields(module: Module, includeInactive = false) {
  return useQuery({
    queryKey: ['custom-fields', module, includeInactive],
    queryFn: () => customFieldsApi.list(module, includeInactive),
  })
}

function useInvalidateCustomFields() {
  const qc = useQueryClient()
  return (module: Module) => qc.invalidateQueries({ queryKey: ['custom-fields', module] })
}

export function useCreateCustomField() {
  const invalidate = useInvalidateCustomFields()
  return useMutation({
    mutationFn: ({ module, body }: { module: Module; body: CustomFieldCreate }) =>
      customFieldsApi.create(module, body),
    onSuccess: (_data, { module }) => invalidate(module),
  })
}

export function useUpdateCustomField() {
  const invalidate = useInvalidateCustomFields()
  return useMutation({
    mutationFn: ({
      module,
      fieldId,
      body,
    }: {
      module: Module
      fieldId: string
      body: CustomFieldUpdate
    }) => customFieldsApi.update(module, fieldId, body),
    onSuccess: (_data, { module }) => invalidate(module),
  })
}

export function useDeactivateCustomField() {
  const invalidate = useInvalidateCustomFields()
  return useMutation({
    mutationFn: ({ module, fieldId }: { module: Module; fieldId: string }) =>
      customFieldsApi.deactivate(module, fieldId),
    onSuccess: (_data, { module }) => invalidate(module),
  })
}

export function useReactivateCustomField() {
  const invalidate = useInvalidateCustomFields()
  return useMutation({
    mutationFn: ({ module, fieldId }: { module: Module; fieldId: string }) =>
      customFieldsApi.reactivate(module, fieldId),
    onSuccess: (_data, { module }) => invalidate(module),
  })
}
