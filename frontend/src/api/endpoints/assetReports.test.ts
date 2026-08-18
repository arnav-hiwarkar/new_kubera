import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { assetReportsApi } from '@/api/endpoints/assetReports'
import { companyTokenStorage } from '@/auth/tokenStorage'

/**
 * Every asset-report call must carry the company access token from
 * `companyTokenStorage`.
 *
 * These endpoints previously hand-rolled `fetch` and read the token from
 * `localStorage.getItem('company_token')` — a key that has never existed, because
 * the real one is `kubera.company.tokens` and holds a JSON blob. The header sent was
 * therefore `Bearer ` with empty credentials, and FastAPI's HTTPBearer answered 403
 * "Not authenticated" for the preview, every export and the pack download. Nothing
 * covered this page, so it shipped.
 */
const TOKENS = { accessToken: 'test-access-token', refreshToken: 'test-refresh-token' }

let calls: Array<{ url: string; init?: RequestInit }>

function authHeaderOf(init?: RequestInit): string | undefined {
  const headers = (init?.headers ?? {}) as Record<string, string>
  return headers.Authorization
}

beforeEach(() => {
  localStorage.clear()
  companyTokenStorage.set(TOKENS)
  calls = []
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init })
    if (String(input).includes('preview-html')) {
      return new Response('<html><body>report</body></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      })
    }
    return new Response(new Blob(['binary']), { status: 200 })
  }) as typeof fetch
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('assetReportsApi authentication', () => {
  it('sends the stored company token on the HTML preview', async () => {
    const html = await assetReportsApi.previewHtml('fixed_asset_register', 'fy-1')

    expect(authHeaderOf(calls[0].init)).toBe(`Bearer ${TOKENS.accessToken}`)
    // and it must come back as text, not be JSON.parsed into an exception
    expect(html).toContain('<html>')
  })

  it('sends the stored company token on export', async () => {
    const blob = await assetReportsApi.exportBlob('fixed_asset_register', 'fy-1', 'xlsx')

    expect(authHeaderOf(calls[0].init)).toBe(`Bearer ${TOKENS.accessToken}`)
    expect(blob).toBeInstanceOf(Blob)
  })

  it('sends the stored company token on the pack download', async () => {
    const blob = await assetReportsApi.packBlob('fy-1', 'pdf')

    expect(authHeaderOf(calls[0].init)).toBe(`Bearer ${TOKENS.accessToken}`)
    expect(blob).toBeInstanceOf(Blob)
  })

  it('never reads a bare company_token key', async () => {
    // The exact regression: a token present under the real namespaced key, and
    // nothing under the old bogus one, must still authenticate.
    expect(localStorage.getItem('company_token')).toBeNull()

    await assetReportsApi.previewHtml('fixed_asset_register', 'fy-1')

    expect(authHeaderOf(calls[0].init)).toBe(`Bearer ${TOKENS.accessToken}`)
    expect(authHeaderOf(calls[0].init)).not.toBe('Bearer ')
  })

  it('forwards filters as query parameters', async () => {
    await assetReportsApi.exportBlob('fixed_asset_register', 'fy-1', 'xlsx', 'lakhs', {
      category_id: 'cat-9',
      condition: 'good',
    })

    expect(calls[0].url).toContain('category_id=cat-9')
    expect(calls[0].url).toContain('condition=good')
    expect(calls[0].url).toContain('unit=lakhs')
  })
})
