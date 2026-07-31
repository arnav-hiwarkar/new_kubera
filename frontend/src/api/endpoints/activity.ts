import { companyClient } from '@/api/clients/company'
import type { ActivityLogOut } from '@/api/types'

export type ActivityFilters = {
  entity_type?: string
  /** Narrow to one record's history — used by the asset detail History tab. */
  entity_id?: string
  limit?: number
}

export const activityApi = {
  list: (filters?: ActivityFilters) =>
    companyClient.get<ActivityLogOut[]>('/api/v1/activity-log', { query: filters }),
}
