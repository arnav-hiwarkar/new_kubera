import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assetMastersApi } from '@/api/endpoints/assetMasters'
import type {
  AssetCategoryCreate,
  AssetCategoryResponse,
  AssetCategoryUpdate,
  AssetLookupCreate,
  AssetLookupKind,
  AssetLookupUpdate,
  SupplierCreate,
  SupplierUpdate,
} from '@/api/types'

export const assetMasterKeys = {
  all: ['asset-masters'] as const,
  categories: ['asset-masters', 'categories'] as const,
  itBlocks: ['asset-masters', 'it-blocks'] as const,
  suppliers: ['asset-masters', 'suppliers'] as const,
  lookups: (kind?: AssetLookupKind) => ['asset-masters', 'lookups', kind ?? 'all'] as const,
}

/** Master data barely changes within a session; cache it hard so the asset form
 *  does not refetch five lookup lists on every tab switch. */
const STATIC = { staleTime: 5 * 60 * 1000 }

export function useAssetCategories() {
  return useQuery({
    queryKey: assetMasterKeys.categories,
    queryFn: () => assetMastersApi.listCategories(),
    ...STATIC,
  })
}

export type CategoryTree = {
  parent: AssetCategoryResponse
  children: AssetCategoryResponse[]
}[]

/**
 * Group the flat category list into parent → children for the cascading picker.
 * Parents with no children are still returned (a company may add a flat category),
 * and orphans whose parent is missing are surfaced rather than silently dropped.
 */
export function useCategoryTree() {
  const query = useAssetCategories()
  const tree = useMemo<CategoryTree>(() => {
    const all = query.data ?? []
    const parents = all.filter((c) => c.parent_id === null)
    const byParent = new Map<string, AssetCategoryResponse[]>()
    for (const c of all) {
      if (!c.parent_id) continue
      const list = byParent.get(c.parent_id) ?? []
      list.push(c)
      byParent.set(c.parent_id, list)
    }
    const known = new Set(parents.map((p) => p.id))
    const orphans = all.filter((c) => c.parent_id && !known.has(c.parent_id))
    return [
      ...parents.map((parent) => ({
        parent,
        children: (byParent.get(parent.id) ?? []).sort(
          (a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name),
        ),
      })),
      ...(orphans.length ? [{ parent: { ...orphans[0], id: '__orphans__', name: 'Other' }, children: orphans }] : []),
    ]
  }, [query.data])
  return { ...query, tree }
}

/** Lookup id → display name, for rendering assignment columns without N joins. */
export function useLookupNames() {
  const { data = [] } = useAssetLookups()
  return useMemo(() => {
    const m: Record<string, string> = {}
    for (const l of data) m[l.id] = l.name
    return m
  }, [data])
}

export function useCategoryNames() {
  const { data = [] } = useAssetCategories()
  return useMemo(() => {
    const m: Record<string, string> = {}
    for (const c of data) m[c.id] = c.name
    return m
  }, [data])
}

export function useItBlocks() {
  return useQuery({
    queryKey: assetMasterKeys.itBlocks,
    queryFn: () => assetMastersApi.listItBlocks(),
    ...STATIC,
  })
}

export function useSuppliers() {
  return useQuery({
    queryKey: assetMasterKeys.suppliers,
    queryFn: () => assetMastersApi.listSuppliers(),
    ...STATIC,
  })
}

export function useAssetLookups(kind?: AssetLookupKind) {
  return useQuery({
    queryKey: assetMasterKeys.lookups(kind),
    queryFn: () => assetMastersApi.listLookups(kind),
    ...STATIC,
  })
}

function useInvalidateMasters() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: assetMasterKeys.all })
}

export function useCreateCategory() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: (body: AssetCategoryCreate) => assetMastersApi.createCategory(body),
    onSuccess: invalidate,
  })
}

export function useUpdateCategory() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetCategoryUpdate }) =>
      assetMastersApi.updateCategory(id, body),
    onSuccess: invalidate,
  })
}

export function useCreateSupplier() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: (body: SupplierCreate) => assetMastersApi.createSupplier(body),
    onSuccess: invalidate,
  })
}

export function useUpdateSupplier() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SupplierUpdate }) =>
      assetMastersApi.updateSupplier(id, body),
    onSuccess: invalidate,
  })
}

export function useCreateLookup() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: (body: AssetLookupCreate) => assetMastersApi.createLookup(body),
    onSuccess: invalidate,
  })
}

export function useUpdateLookup() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetLookupUpdate }) =>
      assetMastersApi.updateLookup(id, body),
    onSuccess: invalidate,
  })
}
