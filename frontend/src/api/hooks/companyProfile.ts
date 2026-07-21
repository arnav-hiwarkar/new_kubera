import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import {
  companyProfileApi,
  type CompanyProfile,
  type CompanyProfileUpdate,
} from '@/api/endpoints/companyProfile'

export const companyProfileKeys = {
  profile: ['company', 'profile'] as const,
}

export function useCompanyProfile() {
  return useQuery({
    queryKey: companyProfileKeys.profile,
    queryFn: () => companyProfileApi.get(),
  })
}

export function useUpdateCompanyProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CompanyProfileUpdate) => companyProfileApi.update(body),
    onSuccess: (data: CompanyProfile) => {
      qc.setQueryData(companyProfileKeys.profile, data)
    },
  })
}

export function useUploadLogo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => companyProfileApi.uploadLogo(file),
    onSuccess: (data: CompanyProfile) => {
      qc.setQueryData(companyProfileKeys.profile, data)
    },
  })
}

/**
 * Company display branding for chrome (e.g. the sidebar): the company name and,
 * if a logo is uploaded, an object-URL for it. The logo is served as
 * authenticated bytes, so it's fetched as a blob and wrapped in a
 * `URL.createObjectURL` (revoked on cleanup) rather than used as a bare src.
 */
export function useCompanyBranding(): { name: string | undefined; logoUrl: string | null } {
  const { data } = useCompanyProfile()
  const hasLogo = !!data?.has_logo
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!hasLogo) {
      setLogoUrl(null)
      return
    }
    let active = true
    let objectUrl: string | null = null
    companyProfileApi
      .getLogoBlob()
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setLogoUrl(objectUrl)
      })
      .catch(() => {
        if (active) setLogoUrl(null)
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [hasLogo])

  return { name: data?.name, logoUrl }
}
