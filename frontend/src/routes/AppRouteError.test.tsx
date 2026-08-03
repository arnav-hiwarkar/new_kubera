import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { AppRouteError } from './AppRouteError'

function BrokenPage(): never {
  throw new Error('sensitive minified stack detail')
}

afterEach(() => vi.restoreAllMocks())

describe('AppRouteError', () => {
  it('contains unexpected errors without exposing their details', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const router = createMemoryRouter([
      {
        path: '/app/auditease/example',
        element: <BrokenPage />,
        errorElement: <AppRouteError audience="company" />,
      },
      { path: '/app/auditease', element: <h1>Engagements</h1> },
    ], { initialEntries: ['/app/auditease/example'] })

    render(<RouterProvider router={router} />)
    expect(await screen.findByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
    expect(screen.queryByText(/sensitive minified stack detail/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload application' })).toBeInTheDocument()

    expect(screen.getByRole('button', { name: 'Return to engagements' })).toBeInTheDocument()
  })
})
