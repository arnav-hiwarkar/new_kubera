import { companyClient } from '@/api/clients/company'
import type {
  AssetCategoryCreate,
  AssetCategoryResponse,
  AssetCategoryUpdate,
  AssetLookupCreate,
  AssetLookupKind,
  AssetLookupResponse,
  AssetLookupUpdate,
  ItAssetBlockResponse,
  SupplierCreate,
  SupplierResponse,
  SupplierUpdate,
} from '@/api/types'

const BASE = '/api/v1/asset-masters'

export const assetMastersApi = {
  /** Seeded Schedule II rows (company_id null) plus this company's own. */
  listCategories: () => companyClient.get<AssetCategoryResponse[]>(`${BASE}/categories`),
  createCategory: (body: AssetCategoryCreate) =>
    companyClient.post<AssetCategoryResponse>(`${BASE}/categories`, { body }),
  updateCategory: (id: string, body: AssetCategoryUpdate) =>
    companyClient.patch<AssetCategoryResponse>(`${BASE}/categories/${id}`, { body }),

  listItBlocks: () => companyClient.get<ItAssetBlockResponse[]>(`${BASE}/it-blocks`),

  listSuppliers: () => companyClient.get<SupplierResponse[]>(`${BASE}/suppliers`),
  createSupplier: (body: SupplierCreate) =>
    companyClient.post<SupplierResponse>(`${BASE}/suppliers`, { body }),
  updateSupplier: (id: string, body: SupplierUpdate) =>
    companyClient.patch<SupplierResponse>(`${BASE}/suppliers/${id}`, { body }),

  listLookups: (kind?: AssetLookupKind) =>
    companyClient.get<AssetLookupResponse[]>(`${BASE}/lookups`, {
      query: kind ? { kind } : undefined,
    }),
  createLookup: (body: AssetLookupCreate) =>
    companyClient.post<AssetLookupResponse>(`${BASE}/lookups`, { body }),
  updateLookup: (id: string, body: AssetLookupUpdate) =>
    companyClient.patch<AssetLookupResponse>(`${BASE}/lookups/${id}`, { body }),
}
