import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { DocumentsTab } from './DocumentsTab'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

vi.mock('@/api/hooks/assets', () => ({
  useUploadAssetDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDetachAssetDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAttachAssetDocument: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
}))

const baseDetail = {
  asset: { id: 'asset-1', acquisition_id: null },
  documents: [],
} as any

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('DocumentsTab attach-from-DocVault gate', () => {
  it('hides "Attach from DocVault" when the user lacks docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['assets'] }
    renderWithProviders(<DocumentsTab detail={baseDetail} />)
    expect(screen.queryByText('Attach from DocVault')).not.toBeInTheDocument()
  })

  it('shows "Attach from DocVault" when the user has docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['assets', 'docvault'] }
    renderWithProviders(<DocumentsTab detail={baseDetail} />)
    expect(screen.getByText('Attach from DocVault')).toBeInTheDocument()
  })
})
