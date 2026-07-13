import { useQuery } from '@tanstack/react-query'
import { activityApi } from '../endpoints/activity'

export const ACTIVITY_QUERY_KEY = ['activity']

export function useActivityLog(filters?: { entity_type?: string; limit?: number }) {
  return useQuery({
    queryKey: [...ACTIVITY_QUERY_KEY, filters],
    queryFn: () => activityApi.list(filters),
  })
}
