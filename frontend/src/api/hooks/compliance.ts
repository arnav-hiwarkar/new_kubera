import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { rocApi, secretarialApi } from '@/api/endpoints/compliance'
import type { DocumentTypeCreate, MeetingRecordCreate, MeetingRecordUpdate } from '@/api/types'

export type Domain = 'roc' | 'secretarial'

/** The two domains share one router factory; pick the client for the domain. */
export function apiFor(domain: Domain) {
  return domain === 'roc' ? rocApi : secretarialApi
}

export function useDocumentTypes(domain: Domain) {
  return useQuery({
    queryKey: ['compliance', domain, 'types'],
    queryFn: () => apiFor(domain).listDocumentTypes(),
  })
}

export function useMeetingRecords(domain: Domain) {
  return useQuery({
    queryKey: ['compliance', domain, 'records'],
    queryFn: () => apiFor(domain).listMeetingRecords(),
  })
}

function useInvalidateCompliance(domain: Domain) {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: ['compliance', domain] })
}

export function useCreateDocumentType(domain: Domain) {
  const invalidate = useInvalidateCompliance(domain)
  return useMutation({
    mutationFn: (body: DocumentTypeCreate) => apiFor(domain).createDocumentType(body),
    onSuccess: invalidate,
  })
}

export function useUpdateDocumentType(domain: Domain) {
  const invalidate = useInvalidateCompliance(domain)
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DocumentTypeCreate }) =>
      apiFor(domain).updateDocumentType(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteDocumentType(domain: Domain) {
  const invalidate = useInvalidateCompliance(domain)
  return useMutation({
    mutationFn: (id: string) => apiFor(domain).deleteDocumentType(id),
    onSuccess: invalidate,
  })
}

export function useCreateMeetingRecord(domain: Domain) {
  const invalidate = useInvalidateCompliance(domain)
  return useMutation({
    mutationFn: (body: MeetingRecordCreate) => apiFor(domain).createMeetingRecord(body),
    onSuccess: invalidate,
  })
}

export function useUpdateMeetingRecord(domain: Domain) {
  const invalidate = useInvalidateCompliance(domain)
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: MeetingRecordUpdate }) =>
      apiFor(domain).updateMeetingRecord(id, body),
    onSuccess: invalidate,
  })
}

/** Documents sitting in the domain's docVault bucket with no record yet. */
export function useUnsyncedDocuments(domain: Domain) {
  return useQuery({
    queryKey: ['compliance', domain, 'unsynced'],
    queryFn: () => apiFor(domain).listUnsyncedDocuments(),
  })
}

export function useSyncFromDocVault(domain: Domain) {
  const invalidate = useInvalidateCompliance(domain)
  return useMutation({
    mutationFn: () => apiFor(domain).syncFromDocVault(),
    // The ['compliance', domain] prefix covers both records and the unsynced list.
    onSuccess: invalidate,
  })
}
