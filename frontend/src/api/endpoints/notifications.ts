import { companyClient } from '@/api/clients/company'
import type { NotificationOut } from '@/api/types'

export const notificationsApi = {
  list: () => companyClient.get<NotificationOut[]>('/api/v1/notifications'),
  markRead: (id: string) =>
    companyClient.patch<NotificationOut>(`/api/v1/notifications/${id}/read`),
}
