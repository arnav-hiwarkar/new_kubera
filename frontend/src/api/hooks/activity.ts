import { useQuery } from '@tanstack/react-query'
import { activityApi, type ActivityFilters } from '../endpoints/activity'

export const ACTIVITY_QUERY_KEY = ['activity']

export function useActivityLog(filters?: ActivityFilters) {
  return useQuery({
    queryKey: [...ACTIVITY_QUERY_KEY, filters],
    queryFn: () => activityApi.list(filters),
  })
}
