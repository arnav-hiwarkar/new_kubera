import { describe, expect, it, vi, beforeEach } from 'vitest'

const post = vi.fn()
vi.mock('@/api/clients/company', () => ({ companyClient: { get: vi.fn(), post, delete: vi.fn() } }))

const { depreciationApi } = await import('@/api/endpoints/depreciation')
const { depreciationKeys } = await import('@/api/hooks/depreciation')

describe('depreciationApi.explain', () => {
  beforeEach(() => post.mockReset())

  it('posts the asset and financial year to the explain endpoint', async () => {
    post.mockResolvedValue({ companies_act: { steps: [] }, income_tax: null })
    await depreciationApi.explain('asset-1', 'fy-1')

    expect(post).toHaveBeenCalledWith('/api/v1/depreciation/explain', {
      body: { asset_id: 'asset-1', financial_year_id: 'fy-1' },
    })
  })
})

describe('depreciationKeys.explain', () => {
  it('keys a projection by both asset and year, so switching year refetches', () => {
    expect(depreciationKeys.explain('a1', 'fy1')).not.toEqual(
      depreciationKeys.explain('a1', 'fy2'),
    )
    expect(depreciationKeys.explain('a1', 'fy1')).toEqual(depreciationKeys.explain('a1', 'fy1'))
  })
})
