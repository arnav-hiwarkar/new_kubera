import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notificationsApi } from '../endpoints/notifications'

const NOTIFICATIONS_QUERY_KEY = ['notifications']

export function useNotifications() {
  return useQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: () => notificationsApi.list(),
    refetchInterval: 30000,
  })
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: notificationsApi.markRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })
    },
  })
}
