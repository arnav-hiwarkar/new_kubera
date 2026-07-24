import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { ImportMappingModal } from './ImportMappingModal'

vi.mock('@/api/endpoints/auditease', () => ({
  auditeaseCompanyApi: {
    listMappingSources: vi.fn(),
    importMappings: vi.fn(),
  },
}))

function renderModal(mappedTargetCount = 2) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ImportMappingModal
          open
          onClose={vi.fn()}
          engagementId="target-1"
          mappedTargetCount={mappedTargetCount}
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(auditeaseCompanyApi.listMappingSources as ReturnType<typeof vi.fn>).mockResolvedValue([
    {
      engagement_id: 'source-1',
      period_label: 'FY 2024',
      status: 'closed',
      total_ledger_count: 10,
      mapped_ledger_count: 8,
    },
  ])
  ;(auditeaseCompanyApi.importMappings as ReturnType<typeof vi.fn>).mockResolvedValue({
    total_target_ledgers: 10,
    source_mapped_count: 8,
    assigned_count: 7,
    updated_count: 7,
    already_correct_count: 1,
    preserved_existing_count: 1,
    unused_source_count: 1,
    unresolved_count: 2,
    issues: [
      {
        target_ledger_id: 'ledger-1',
        ledger_code: 'NO',
        ledger_name: 'Unmatched ledger',
        reason: 'unmatched',
      },
      {
        target_ledger_id: 'ledger-2',
        ledger_code: 'DUP',
        ledger_name: 'Conflicting ledger',
        reason: 'ambiguous_source_mapping',
      },
    ],
  })
})

describe('ImportMappingModal', () => {
  it('overwrites existing mappings by default and renders detailed issues', async () => {
    const user = userEvent.setup()
    renderModal()

    expect(await screen.findByRole('option', { name: /FY 2024/ })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Preserve existing mappings/ })).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: /^Import mapping$/ }))

    await waitFor(() =>
      expect(auditeaseCompanyApi.importMappings).toHaveBeenCalledWith('target-1', {
        source_engagement_id: 'source-1',
        overwrite_existing: true,
      }),
    )
    expect(await screen.findByText('Mapping import complete')).toBeInTheDocument()
    expect(screen.getByText('Assigned')).toBeInTheDocument()
    expect(screen.getByText('Already correct')).toBeInTheDocument()
    expect(screen.getByText('Unmatched ledger')).toBeInTheDocument()
    expect(screen.getByText('No matching source ledger')).toBeInTheDocument()
    expect(screen.getByText('Identical source ledgers map to different groups')).toBeInTheDocument()
  })

  it('sends the explicit preserve choice', async () => {
    const user = userEvent.setup()
    renderModal()

    await screen.findByRole('option', { name: /FY 2024/ })
    await user.click(screen.getByRole('checkbox', { name: /Preserve existing mappings/ }))
    await user.click(screen.getByRole('button', { name: /^Import mapping$/ }))

    await waitFor(() =>
      expect(auditeaseCompanyApi.importMappings).toHaveBeenCalledWith('target-1', {
        source_engagement_id: 'source-1',
        overwrite_existing: false,
      }),
    )
  })

  it('shows an empty state when no engagement has mapped ledgers', async () => {
    (auditeaseCompanyApi.listMappingSources as ReturnType<typeof vi.fn>).mockResolvedValue([])
    renderModal()

    expect(await screen.findByText('No mapping source available')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Import mapping$/ })).toBeDisabled()
  })
})
