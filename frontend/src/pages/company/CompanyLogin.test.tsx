import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderApp } from '@/test/renderApp'
import { companyTokenStorage } from '@/auth/tokenStorage'

function installFetchMock(status = 401, headers: Record<string, string> = {}) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/auth/company/login')) {
      return new Response(JSON.stringify({ detail: 'Too many attempts. Please try again later.' }), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers },
      })
    }
    return new Response('{}', { status: 200 })
  }) as typeof fetch
}

beforeEach(() => {
  companyTokenStorage.clear()
})

describe('CompanyLogin Rate Limit', () => {
  it('displays the parsed Retry-After header as minutes on 429 response', async () => {
    // 300 seconds = 5 minutes
    installFetchMock(429, { 'Retry-After': '300' })
    renderApp('/login')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Email/i), 'admin@acme.test')
    await user.type(screen.getByLabelText(/Password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /Sign In/i }))

    expect(await screen.findByText('Too many attempts. Please try again in 5 minutes.')).toBeInTheDocument()
  })
  
  it('displays fallback message if Retry-After is missing on 429', async () => {
    installFetchMock(429, {}) // No Retry-After header
    renderApp('/login')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Email/i), 'admin@acme.test')
    await user.type(screen.getByLabelText(/Password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /Sign In/i }))

    expect(await screen.findByText('Too many attempts. Please try again later.')).toBeInTheDocument()
  })

  it('displays standard error on 401 response', async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/company/login')) {
        return new Response(JSON.stringify({ detail: 'Invalid credentials' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response('{}', { status: 200 })
    }) as typeof fetch

    renderApp('/login')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Email/i), 'admin@acme.test')
    await user.type(screen.getByLabelText(/Password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /Sign In/i }))

    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument()
  })
})
