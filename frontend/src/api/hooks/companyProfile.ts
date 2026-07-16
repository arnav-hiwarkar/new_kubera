import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
