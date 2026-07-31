import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { acquisitionsApi, assetsApi, type AssetFilters } from '@/api/endpoints/assets'
import type {
  AcquisitionUpdate,
  AssetDetailResponse,
  AssetQuickAddRequest,
  AssetUpdate,
  BulkSerialRequest,
  CostPreviewRequest,
  TransitionRequest,
} from '@/api/types'

/**
 * `AssetDetailResponse` declares its collections optional because the Pydantic
 * models give them defaults, which OpenAPI reports as "not required". The server
 * always sends them. Normalizing once here means seven tab components don't each
 * carry `?? []` noise.
 */
export type AssetDetail = Omit<
  AssetDetailResponse,
  'siblings' | 'documents' | 'applicable_field_groups' | 'blocking_issues' | 'completeness_by_tab'
> & {
  siblings: NonNullable<AssetDetailResponse['siblings']>
  documents: NonNullable<AssetDetailResponse['documents']>
  applicable_field_groups: string[]
  blocking_issues: NonNullable<AssetDetailResponse['blocking_issues']>
  completeness_by_tab: Record<string, number>
}

export const assetKeys = {
  all: ['assets'] as const,
  list: (filters?: AssetFilters) => ['assets', 'list', filters ?? {}] as const,
  detail: (id: string) => ['assets', 'detail', id] as const,
  documents: (id: string) => ['assets', 'documents', id] as const,
  acquisitionUnits: (id: string) => ['assets', 'acquisition', id, 'units'] as const,
}

export function useAssets(filters?: AssetFilters) {
  return useQuery({
    queryKey: assetKeys.list(filters),
    queryFn: () => assetsApi.list(filters),
  })
}

export function useAsset(id: string | undefined) {
  return useQuery({
    queryKey: assetKeys.detail(id ?? ''),
    queryFn: () => assetsApi.get(id as string),
    enabled: !!id,
    select: (d): AssetDetail => ({
      ...d,
      siblings: d.siblings ?? [],
      documents: d.documents ?? [],
      applicable_field_groups: d.applicable_field_groups ?? [],
      blocking_issues: d.blocking_issues ?? [],
      completeness_by_tab: d.completeness_by_tab ?? {},
    }),
  })
}

export function useAcquisitionUnits(id: string | undefined) {
  return useQuery({
    queryKey: assetKeys.acquisitionUnits(id ?? ''),
    queryFn: () => acquisitionsApi.units(id as string),
    enabled: !!id,
  })
}

/**
 * Invalidate the whole asset namespace. Edits ripple further than the row touched:
 * changing an acquisition re-allocates every sibling's cost, and a transition can
 * move a whole batch, so narrower invalidation would leave stale figures on screen.
 */
function useInvalidateAssets() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: assetKeys.all })
}

export function useQuickAddAsset() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: (body: AssetQuickAddRequest) => assetsApi.quickAdd(body),
    onSuccess: invalidate,
  })
}

export function useUpdateAsset() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetUpdate }) => assetsApi.update(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteAsset() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: (id: string) => assetsApi.remove(id),
    onSuccess: invalidate,
  })
}

export function useUpdateAcquisition() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AcquisitionUpdate }) =>
      acquisitionsApi.update(id, body),
    onSuccess: invalidate,
  })
}

export function useAssignSerials() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: BulkSerialRequest }) =>
      assetsApi.assignSerials(id, body),
    onSuccess: invalidate,
  })
}

export function useAssetTransition(kind: 'submit' | 'approve' | 'reject') {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: TransitionRequest }) =>
      assetsApi[kind](id, body),
    onSuccess: invalidate,
  })
}

/** Costing preview. A mutation rather than a query: it is a POST driven by typing. */
export function useCostPreview() {
  return useMutation({
    mutationFn: (body: CostPreviewRequest) => assetsApi.costPreview(body),
  })
}

export function useAssetDocuments(assetId: string | undefined) {
  return useQuery({
    queryKey: assetKeys.documents(assetId ?? ''),
    queryFn: () => assetsApi.listDocuments(assetId as string),
    enabled: !!assetId,
  })
}

export function useUploadAssetDocument() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: ({
      assetId,
      acquisitionId,
      formData,
    }: {
      assetId?: string
      acquisitionId?: string
      formData: FormData
    }) =>
      acquisitionId
        ? assetsApi.uploadAcquisitionDocument(acquisitionId, formData)
        : assetsApi.uploadDocument(assetId as string, formData),
    onSuccess: invalidate,
  })
}

export function useDetachAssetDocument() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: (linkId: string) => assetsApi.detachDocument(linkId),
    onSuccess: invalidate,
  })
}
