import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderApp } from '@/test/renderApp'
import { companyTokenStorage } from '@/auth/tokenStorage'

const TOKENS = { accessToken: 'valid-access', refreshToken: 'valid-refresh' }

const adminProfile = {
  id: 'admin-1',
  email: 'admin@acme.test',
  full_name: 'Ada Admin',
  role: 'admin',
}

const completeCompanyProfile = {
  id: 'company-1',
  name: 'Acme Corp',
  legal_name: null,
  cin: null,
  pan: null,
  gstin: null,
  tan: null,
  address_line1: null,
  address_line2: null,
  city: null,
  state: null,
  pincode: null,
  contact_email: null,
  contact_phone: null,
  date_of_incorporation: null,
  website: null,
  industry: null,
  profile_completed: true,
  has_logo: false,
}

function installFetchMock(profile: Record<string, unknown> = adminProfile) {
  const requestedUrls: string[] = []
  const json = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })

  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    requestedUrls.push(url)

    if (url.endsWith('/auth/company/me')) return json(profile)
    if (url.endsWith('/api/v1/company/profile')) return json(completeCompanyProfile)
    return json([])
  }) as typeof fetch

  return requestedUrls
}

beforeEach(() => {
  companyTokenStorage.set(TOKENS)
})

describe('Sales and KRA soft hide', () => {
  it('removes both apps and all sales content from dashboard discovery surfaces', async () => {
    const requestedUrls = installFetchMock()
    renderApp('/app')

    expect(await screen.findByRole('heading', { name: /Ada/ })).toBeInTheDocument()

    expect(screen.queryByRole('link', { name: 'Sales' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'KRA & Appraisals' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SecretarialEase' })).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: /Sales/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /KRA & Appraisals/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /SecretarialEase.*Registers & meetings/ })).toBeInTheDocument()

    expect(screen.getByText('Team members')).toBeInTheDocument()
    expect(screen.queryByText('Sales pipeline')).not.toBeInTheDocument()
    expect(screen.queryByText('Pipeline value')).not.toBeInTheDocument()
    expect(screen.queryByText('Total deals')).not.toBeInTheDocument()
    expect(screen.queryByText('Won value')).not.toBeInTheDocument()

    await waitFor(() => expect(requestedUrls.some((url) => url.endsWith('/api/v1/users'))).toBe(true))
    expect(requestedUrls.some((url) => url.includes('/api/v1/sales/aggregate'))).toBe(false)
  })

  it('omits both apps from command search and keeps SecretarialEase searchable', async () => {
    installFetchMock()
    const user = userEvent.setup()
    renderApp('/app')

    await screen.findByRole('heading', { name: /Ada/ })
    await user.click(screen.getByRole('button', { name: /Search/ }))

    const search = await screen.findByPlaceholderText('Search pages and actions…')
    expect(screen.queryByRole('button', { name: /^Sales Operations/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^KRA & Appraisals Operations/ })).not.toBeInTheDocument()

    await user.type(search, 'sales')
    expect(screen.getByText('No matches for “sales”')).toBeInTheDocument()

    await user.clear(search)
    await user.type(search, 'kra')
    expect(screen.getByText('No matches for “kra”')).toBeInTheDocument()

    await user.clear(search)
    await user.type(search, 'secretarial')
    expect(screen.getByRole('button', { name: /^SecretarialEase Operations/ })).toBeInTheDocument()
  })

  it('links the replacement dashboard tile to SecretarialEase', async () => {
    installFetchMock()
    const user = userEvent.setup()
    renderApp('/app')

    await screen.findByRole('heading', { name: /Ada/ })
    await user.click(screen.getByRole('button', { name: /SecretarialEase.*Registers & meetings/ }))

    expect(await screen.findByRole('heading', { name: 'SecretarialEase' })).toBeInTheDocument()
  })

  it.each([
    ['/app/sales', 'Sales'],
    ['/app/kra', 'KRA & Appraisals'],
  ])('preserves authorized direct access to %s', async (path, heading) => {
    installFetchMock()
    renderApp(path)

    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: heading })).not.toBeInTheDocument()
  })

  it('preserves the existing route guard for users without Sales access', async () => {
    installFetchMock({
      id: 'employee-1',
      email: 'employee@acme.test',
      full_name: 'Eve Employee',
      role: 'employee',
      accessible_modules: ['dashboard'],
    })
    renderApp('/app/sales')

    expect(await screen.findByRole('heading', { name: /Eve/ })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sales' })).not.toBeInTheDocument()
  })
})
