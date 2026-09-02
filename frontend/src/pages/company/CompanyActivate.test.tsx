import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderApp } from '@/test/renderApp'

function installFetchMock(status = 401, headers: Record<string, string> = {}) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/auth/company/activate')) {
      return new Response(JSON.stringify({ detail: 'Too many attempts. Please try again later.' }), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers },
      })
    }
    return new Response('{}', { status: 200 })
  }) as typeof fetch
}

describe('CompanyActivate Rate Limit', () => {
  it('displays the parsed Retry-After header as minutes on 429 response', async () => {
    installFetchMock(429, { 'Retry-After': '900' }) // 15 mins
    renderApp('/activate?email=test@test.com&key=abc')
    
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Registered email/i), 'test@test.com')
    await user.type(screen.getByLabelText(/Product key/i), '12345')
    await user.type(screen.getByLabelText(/Your name/i), 'Ada Admin')
    await user.type(screen.getAllByLabelText(/Password/i)[0], 'Valid1!Pass')
    await user.type(screen.getByLabelText(/Confirm password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Activate & set password/i }))

    expect(await screen.findByText('Too many attempts. Please try again in 15 minutes.')).toBeInTheDocument()
  })
  it('displays fallback message if Retry-After is missing on 429', async () => {
    installFetchMock(429, {})
    renderApp('/activate?email=test@test.com&key=abc')
    
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Registered email/i), 'test@test.com')
    await user.type(screen.getByLabelText(/Product key/i), '12345')
    await user.type(screen.getByLabelText(/Your name/i), 'Ada Admin')
    await user.type(screen.getAllByLabelText(/Password/i)[0], 'Valid1!Pass')
    await user.type(screen.getByLabelText(/Confirm password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Activate & set password/i }))

    expect(await screen.findByText('Too many attempts. Please try again later.')).toBeInTheDocument()
  })

  it('displays standard error on 401 response', async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/company/activate')) {
        return new Response(JSON.stringify({ detail: 'Invalid key' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response('{}', { status: 200 })
    }) as typeof fetch

    renderApp('/activate?email=test@test.com&key=abc')
    
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Registered email/i), 'test@test.com')
    await user.type(screen.getByLabelText(/Product key/i), '12345')
    await user.type(screen.getByLabelText(/Your name/i), 'Ada Admin')
    await user.type(screen.getAllByLabelText(/Password/i)[0], 'Valid1!Pass')
    await user.type(screen.getByLabelText(/Confirm password/i), 'Valid1!Pass')
    await user.click(screen.getByRole('button', { name: /Activate & set password/i }))

    expect(await screen.findByText('Invalid key')).toBeInTheDocument()
  })
})
