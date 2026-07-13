import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderApp } from '@/test/renderApp'
import { companyTokenStorage, auditorTokenStorage } from '@/auth/tokenStorage'

const TOKENS = { accessToken: 'valid-access', refreshToken: 'valid-refresh' }

/**
 * Mock backend. Returns a profile for whichever `/me` endpoint is hit with a
 * Bearer token, and empty lists for everything else. The two `/me` routes are
 * distinct, so a token can only satisfy the identity whose namespace it lives in.
 */
function installFetchMock() {
  const json = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })

  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization ?? ''
    const bearer = auth.startsWith('Bearer ')

    if (url.endsWith('/auth/company/me')) {
      return bearer
        ? json({ id: 'c1', email: 'admin@acme.test', full_name: 'Ada Admin', role: 'admin' })
        : json({ detail: 'Not authenticated' }, 401)
    }
    if (url.endsWith('/auth/auditor/me')) {
      return bearer
        ? json({ id: 'a1', email: 'andy@audit.test', name: 'Andy Auditor' })
        : json({ detail: 'Not authenticated' }, 401)
    }
    if (url.endsWith('/refresh')) return json({ detail: 'invalid' }, 401)
    // Any other authenticated data call (dashboard widgets, lists).
    return json([])
  }) as typeof fetch
}

beforeEach(() => {
  installFetchMock()
})

describe('CompanyGuard', () => {
  it('redirects to the company login when there is no session', async () => {
    renderApp('/app')
    expect(await screen.findByRole('heading', { name: 'Company Sign In' })).toBeInTheDocument()
  })

  it('does NOT authenticate the company tree with an auditor token', async () => {
    // Auditor token lives in the auditor namespace; the company guard never reads it.
    auditorTokenStorage.set(TOKENS)
    renderApp('/app')
    expect(await screen.findByRole('heading', { name: 'Company Sign In' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Dashboard' })).not.toBeInTheDocument()
  })

  it('renders the company shell with a valid company token', async () => {
    companyTokenStorage.set(TOKENS)
    renderApp('/app')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  // docVault exposes NO auditor-facing routes — it lives entirely under the
  // company tree, so an auditor token cannot reach it at the routing layer.
  it('rejects an auditor token at the docVault route', async () => {
    auditorTokenStorage.set(TOKENS)
    renderApp('/app/docvault')
    expect(await screen.findByRole('heading', { name: 'Company Sign In' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'DocVault' })).not.toBeInTheDocument()
  })
})

describe('AuditorGuard', () => {
  it('redirects to the auditor login when there is no session', async () => {
    renderApp('/auditor/app')
    expect(await screen.findByRole('heading', { name: 'Auditor Sign In' })).toBeInTheDocument()
  })

  it('does NOT authenticate the auditor tree with a company token', async () => {
    companyTokenStorage.set(TOKENS)
    renderApp('/auditor/app')
    expect(await screen.findByRole('heading', { name: 'Auditor Sign In' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Engagements' })).not.toBeInTheDocument()
  })

  it('renders the auditor shell with a valid auditor token', async () => {
    auditorTokenStorage.set(TOKENS)
    renderApp('/auditor/app')
    expect(await screen.findByRole('heading', { name: 'Engagements' })).toBeInTheDocument()
  })
})
