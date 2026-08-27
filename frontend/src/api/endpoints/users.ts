import { companyClient } from '@/api/clients/company'
import type { UserResponse, UserCreate, UserUpdate, UserChangePasswordRequest } from '@/api/types'

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
  changePassword: (body: UserChangePasswordRequest) =>
    companyClient.post<{ success: boolean; message: string }>('/api/v1/users/me/change-password', {
      body,
    }),
  uploadAvatar: (file: File | Blob) => {
    const formData = new FormData()
    formData.append('file', file)
    return companyClient.post<UserResponse>('/api/v1/users/me/avatar', { formData })
  },
  getAvatarBlob: (userId?: string) =>
    companyClient.get<Blob>(userId ? `/api/v1/users/${userId}/avatar` : '/api/v1/users/me/avatar', {
      responseType: 'blob',
    }),
}

