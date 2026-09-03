import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { DocumentsTab } from './DocumentsTab'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

const attachMutate = vi.fn().mockResolvedValue({})

vi.mock('@/api/hooks/assets', () => ({
  useUploadAssetDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDetachAssetDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAttachAssetDocument: () => ({ mutateAsync: attachMutate, isPending: false }),
}))

vi.mock('@/components/docvault/DocVaultPickerModal', () => ({
  DocVaultPickerModal: ({ onConfirm }: { onConfirm: (ids: string[]) => void }) => (
    <button onClick={() => onConfirm(['doc-9'])}>confirm-pick</button>
  ),
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

  it('routes an acquisition role to the acquisition endpoint, not the asset one', async () => {
    attachMutate.mockClear()
    ;(globalThis as any).__testProfile = { role: 'admin', accessible_modules: [] }
    const detail = { asset: { id: 'asset-1', acquisition_id: 'acq-7' }, documents: [] } as any
    renderWithProviders(<DocumentsTab detail={detail} />)

    await userEvent.selectOptions(screen.getByLabelText('Attach as'), 'invoice')
    await userEvent.click(screen.getByText('Attach from DocVault'))
    await userEvent.click(screen.getByText('confirm-pick'))

    await waitFor(() => expect(attachMutate).toHaveBeenCalledTimes(1))
    expect(attachMutate).toHaveBeenCalledWith({
      assetId: undefined,
      acquisitionId: 'acq-7',
      body: { document_id: 'doc-9', doc_role: 'invoice' },
    })
  })

  it('routes an asset role to the asset endpoint', async () => {
    attachMutate.mockClear()
    ;(globalThis as any).__testProfile = { role: 'admin', accessible_modules: [] }
    const detail = { asset: { id: 'asset-1', acquisition_id: 'acq-7' }, documents: [] } as any
    renderWithProviders(<DocumentsTab detail={detail} />)

    await userEvent.click(screen.getByText('Attach from DocVault'))
    await userEvent.click(screen.getByText('confirm-pick'))

    await waitFor(() => expect(attachMutate).toHaveBeenCalledTimes(1))
    expect(attachMutate).toHaveBeenCalledWith({
      assetId: 'asset-1',
      acquisitionId: undefined,
      body: { document_id: 'doc-9', doc_role: 'asset_photo' },
    })
  })
})
