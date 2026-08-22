import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ItBlocksTab } from './ItBlocksTab'
import { ToastProvider } from '@/components/ui/Toast'

const block = {
  id: 'blk-1',
  company_id: 'c1',
  code: 'PM-15',
  name: 'P&M general',
  dep_rate: 15,
  block_class: 'plant_machinery',
  is_active: true,
  display_order: 50,
}
// Module scope so the assertion below can reach it through the mock closure.
const updateItBlock = vi.fn().mockResolvedValue(block)

vi.mock('@/api/hooks/assetMasters', () => ({
  useItBlocks: () => ({ data: [block], isLoading: false }),
  useCreateItBlock: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateItBlock: () => ({ mutateAsync: updateItBlock, isPending: false }),
  useImpactPreview: () => ({
    data: {
      kind: 'it_block',
      id: 'blk-1',
      assets_referencing: 4,
      draft_run_fy_labels: [],
      finalized_run_fy_labels: ['2024-25'],
      classification: 'future_only',
      message: 'Future depreciation runs will use the new values.',
    },
    isLoading: false,
  }),
}))

describe('ItBlocksTab — editable blocks', () => {
  it('shows the impact verdict inside the edit modal and gates save on ack', async () => {
    render(
      <ToastProvider>
        <ItBlocksTab />
      </ToastProvider>,
    )
    fireEvent.click(screen.getAllByRole('button', { name: /edit/i })[0])
    expect(await screen.findByText(/future depreciation runs/i)).toBeInTheDocument()

    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/i understand/i))
    expect(save).toBeEnabled()

    fireEvent.change(screen.getByLabelText(/rate/i), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(updateItBlock).toHaveBeenCalledWith(
        expect.objectContaining({ body: expect.objectContaining({ dep_rate: 40 }) }),
      ),
    )
  })
})
