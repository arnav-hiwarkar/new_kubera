import { companyClient } from '@/api/clients/company'
import type { KRAResponse, KRACreate, KRAUpdate } from '@/api/types'

export type KraFilters = {
  cycle?: string
  user_id?: string
}

export const kraApi = {
  list: (filters?: KraFilters) =>
    companyClient.get<KRAResponse[]>('/api/v1/kra', { query: filters }),
  get: (id: string) => companyClient.get<KRAResponse>(`/api/v1/kra/${id}`),
  create: (body: KRACreate) => companyClient.post<KRAResponse>('/api/v1/kra', { body }),
  update: (id: string, body: KRAUpdate) =>
    companyClient.patch<KRAResponse>(`/api/v1/kra/${id}`, { body }),
}
