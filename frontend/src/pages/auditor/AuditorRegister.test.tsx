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

describe('AuditorRegister Form and Validation', () => {
  it('pre-fills email and invitation code from URL query parameters', () => {
    renderApp('/auditor/register?email=invited@firm.com&token=invite-secret-abc')

    const emailInput = screen.getByLabelText(/Email/i) as HTMLInputElement
    const tokenInput = screen.getByLabelText(/Invitation code/i) as HTMLInputElement

    expect(emailInput.value).toBe('invited@firm.com')
    expect(tokenInput.value).toBe('invite-secret-abc')
  })

  it('shows validation error when invitation code is missing', async () => {
    renderApp('/auditor/register')
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/Name/i), 'Auditor')
    await user.type(screen.getByLabelText(/Email/i), 'auditor@test.test')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByText('Invitation code is required')).toBeInTheDocument()
  })

  it('submits invite_token in the registration payload', async () => {
    let capturedBody: any = null
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/auth/auditor/register')) {
        capturedBody = JSON.parse(init?.body as string)
        return new Response(JSON.stringify({ id: '123', email: 'auditor@test.test', name: 'Auditor' }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/auth/auditor/login')) {
        return new Response(
          JSON.stringify({ access_token: 'acc', refresh_token: 'ref', token_type: 'bearer' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      }
      return new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })
    }) as typeof fetch

    renderApp('/auditor/register?email=auditor@test.test&token=secret-token-xyz')
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/Name/i), 'Auditor')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(capturedBody).toEqual({
      name: 'Auditor',
      email: 'auditor@test.test',
      password: 'Valid1!Pass',
      invite_token: 'secret-token-xyz',
    })
  })
})

describe('AuditorRegister Rate Limit', () => {
  it('displays the parsed Retry-After header as minutes on 429 response', async () => {
    // 3600 seconds = 60 minutes
    installFetchMock(429, { 'Retry-After': '3600' })
    renderApp('/auditor/register')
    
    const user = userEvent.setup()
    
    await user.type(screen.getByLabelText(/Name/i), 'Auditor')
    await user.type(screen.getByLabelText(/Email/i), 'auditor@test.test')
    await user.type(screen.getByLabelText(/Invitation code/i), 'token123')
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
    await user.type(screen.getByLabelText(/Invitation code/i), 'token123')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByText('Too many attempts. Please try again later.')).toBeInTheDocument()
  })

  it('displays standard error on 400 response', async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/auditor/register')) {
        return new Response(JSON.stringify({ detail: 'Invalid or expired invitation details' }), {
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
    await user.type(screen.getByLabelText(/Invitation code/i), 'token123')
    await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Create account/i }))

    expect(await screen.findByText('Invalid or expired invitation details')).toBeInTheDocument()
  })
})
