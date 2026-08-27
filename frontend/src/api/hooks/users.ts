import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { usersApi } from '@/api/endpoints/users'
import type { UserChangePasswordRequest, UserResponse } from '@/api/types'

export const userKeys = {
  all: ['users'] as const,
  list: () => [...userKeys.all, 'list'] as const,
  me: () => [...userKeys.all, 'me'] as const,
  myReports: () => [...userKeys.all, 'me', 'reports'] as const,
  detail: (id: string) => [...userKeys.all, 'detail', id] as const,
}

export function useUsers() {
  return useQuery({
    queryKey: userKeys.list(),
    queryFn: () => usersApi.list(),
  })
}

export function useMe() {
  return useQuery({
    queryKey: userKeys.me(),
    queryFn: () => usersApi.me(),
  })
}

export function useChangePassword() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: UserChangePasswordRequest) => usersApi.changePassword(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.me() })
    },
  })
}

export function useUploadAvatar() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File | Blob) => usersApi.uploadAvatar(file),
    onSuccess: (data: UserResponse) => {
      qc.setQueryData(userKeys.me(), data)
      qc.invalidateQueries({ queryKey: userKeys.all })
      qc.invalidateQueries({ queryKey: ['auth'] })
    },
  })
}

/**
 * Returns an authenticated object-URL for the given user's avatar.
 * Object URL is automatically created and revoked on cleanup.
 */
export function useUserAvatar(userId?: string, hasAvatar?: boolean): {
  avatarUrl: string | null
  isLoading: boolean
} {
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!hasAvatar) {
      setAvatarUrl(null)
      setIsLoading(false)
      return
    }

    let active = true
    let objectUrl: string | null = null
    setIsLoading(true)

    usersApi
      .getAvatarBlob(userId)
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setAvatarUrl(objectUrl)
      })
      .catch(() => {
        if (active) setAvatarUrl(null)
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    return () => {
      active = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [userId, hasAvatar])

  return { avatarUrl, isLoading }
}
