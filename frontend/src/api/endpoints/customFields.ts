import { companyClient } from '@/api/clients/company'
import type { CustomFieldResponse, CustomFieldCreate, CustomFieldUpdate } from '@/api/types'
import type { components } from '@/api/schema'

type Module = components['schemas']['CustomFieldModule']

export const customFieldsApi = {
  list: (module: Module, includeInactive = false) =>
    companyClient.get<CustomFieldResponse[]>(`/api/v1/custom-fields/${module}`, {
      query: { include_inactive: includeInactive },
    }),
  create: (module: Module, body: CustomFieldCreate) =>
    companyClient.post<CustomFieldResponse>(`/api/v1/custom-fields/${module}`, { body }),
  update: (module: Module, fieldId: string, body: CustomFieldUpdate) =>
    companyClient.patch<CustomFieldResponse>(`/api/v1/custom-fields/${module}/${fieldId}`, {
      body,
    }),
  deactivate: (module: Module, fieldId: string) =>
    companyClient.patch<CustomFieldResponse>(
      `/api/v1/custom-fields/${module}/${fieldId}/deactivate`,
    ),
  reactivate: (module: Module, fieldId: string) =>
    companyClient.patch<CustomFieldResponse>(
      `/api/v1/custom-fields/${module}/${fieldId}/reactivate`,
    ),
}
