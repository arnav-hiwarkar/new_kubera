import { companyClient } from '@/api/clients/company'
import type { UserResponse, UserCreate, UserUpdate } from '@/api/types'

export const usersApi = {
  list: () => companyClient.get<UserResponse[]>('/api/v1/users'),
  me: () => companyClient.get<UserResponse>('/api/v1/users/me'),
  myReports: () => companyClient.get<UserResponse[]>('/api/v1/users/me/reports'),
  get: (id: string) => companyClient.get<UserResponse>(`/api/v1/users/${id}`),
  create: (body: UserCreate) => companyClient.post<UserResponse>('/api/v1/users', { body }),
  update: (id: string, body: UserUpdate) =>
    companyClient.patch<UserResponse>(`/api/v1/users/${id}`, { body }),
  deactivate: (id: string) =>
    companyClient.patch<UserResponse>(`/api/v1/users/${id}/deactivate`),
  reactivate: (id: string) =>
    companyClient.patch<UserResponse>(`/api/v1/users/${id}/reactivate`),
  remove: (id: string) => companyClient.delete<void>(`/api/v1/users/${id}`),
}
