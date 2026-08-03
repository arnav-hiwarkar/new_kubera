import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiContractError } from '@/api/contracts/trialBalance'
import { ApiError } from '@/api/http'
import { TrialBalanceLoadError } from './TrialBalanceLoadError'

describe('TrialBalanceLoadError', () => {
  it('shows a reload action for a frontend/backend contract mismatch', () => {
    render(<TrialBalanceLoadError error={new ApiContractError('TrialBalanceViewResponse/v2')} onRetry={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'AuditEase was updated' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload application' })).toBeInTheDocument()
    expect(screen.queryByText(/reduce is not a function/i)).not.toBeInTheDocument()
  })

  it('retries an ordinary API failure without reloading the route', async () => {
    const retry = vi.fn()
    render(<TrialBalanceLoadError error={new ApiError(503, 'Service unavailable')} onRetry={retry} />)
    expect(screen.getByText('Service unavailable')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
  })
})
