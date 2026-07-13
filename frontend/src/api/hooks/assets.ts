import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assetsApi, type AssetFilters } from '@/api/endpoints/assets'
import type { AssetCreate, AssetUpdate } from '@/api/types'

export const assetKeys = {
  all: ['assets'] as const,
  list: (filters?: AssetFilters) => ['assets', 'list', filters ?? {}] as const,
}

export function useAssets(filters?: AssetFilters) {
  return useQuery({
    queryKey: assetKeys.list(filters),
    queryFn: () => assetsApi.list(filters),
  })
}

function useInvalidateAssets() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: assetKeys.all })
}

export function useCreateAsset() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: (body: AssetCreate) => assetsApi.create(body),
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

/** Reads the uploaded file's sheets/headers for the import mapping step. */
export function useInspectAssetImport() {
  return useMutation({
    mutationFn: (formData: FormData) => assetsApi.inspectImport(formData),
  })
}

export function useImportAssets() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: (formData: FormData) => assetsApi.import(formData),
    onSuccess: invalidate,
  })
}
