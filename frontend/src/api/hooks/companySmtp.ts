import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { companySmtpApi } from '@/api/endpoints/companySmtp'

export function useCompanySmtp() {
  return useQuery({
    queryKey: ['companySmtp'],
    queryFn: () => companySmtpApi.get(),
  })
}

export function useUpdateCompanySmtp() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: companySmtpApi.update,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['companySmtp'] }),
  })
}

export function useVerifyCompanySmtp() {
  return useMutation({
    mutationFn: companySmtpApi.verify,
  })
}

export function useResetCompanySmtp() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: companySmtpApi.reset,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['companySmtp'] }),
  })
}
