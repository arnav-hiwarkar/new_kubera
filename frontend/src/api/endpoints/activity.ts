import { companyClient } from '@/api/clients/company'
import type { ActivityLogOut } from '@/api/types'

export const activityApi = {
  list: (filters?: { entity_type?: string; limit?: number }) =>
    companyClient.get<ActivityLogOut[]>('/api/v1/activity-log', { query: filters }),
}
