import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderApp } from '@/test/renderApp'
import { auditorTokenStorage } from '@/auth/tokenStorage'

function installFetchMock(status = 401, headers: Record<string, string> = {}) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/auth/auditor/register')) {
      return new Response(JSON.stringify({ detail: 'Too many attempts. Please try again later.' }), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers },
      })
    }
    return new Response('{}', { status: 200 })
  }) as typeof fetch
}

beforeEach(() => {
  auditorTokenStorage.clear()
})

describe('AuditorRegister Rate Limit', () => {
  it('displays the parsed Retry-After header as minutes on 429 response', async () => {
    // 3600 seconds = 60 minutes
    installFetchMock(429, { 'Retry-After': '3600' })
    renderApp('/auditor/register')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Name/i), 'Auditor')
    await user.type(screen.getByLabelText(/Email/i), 'auditor@test.test')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByText('Too many attempts. Please try again in 60 minutes.')).toBeInTheDocument()
  })
  it('displays fallback message if Retry-After is missing on 429', async () => {
    installFetchMock(429, {})
    renderApp('/auditor/register')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Name/i), 'Auditor')
    await user.type(screen.getByLabelText(/Email/i), 'auditor@test.test')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByText('Too many attempts. Please try again later.')).toBeInTheDocument()
  })

  it('displays standard error on 401 response', async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/auditor/register')) {
        return new Response(JSON.stringify({ detail: 'Invalid data' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response('{}', { status: 200 })
    }) as typeof fetch

    renderApp('/auditor/register')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Name/i), 'Auditor')
    await user.type(screen.getByLabelText(/Email/i), 'auditor@test.test')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByText('Invalid data')).toBeInTheDocument()
  })
})
