import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ToastProvider } from '@/components/ui/Toast'

vi.mock('@/api/hooks/assets', () => ({
  useUpdateAcquisition: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/api/hooks/assetMasters', () => ({
  useSuppliers: () => ({ data: [] }),
}))

const acq = {
  id: 'acq-1',
  quantity: 3,
  gross_basic_price: '100000.00',
  discount_amount: '5000.00',
  net_basic_price: '95000.00',
  gst_rate: '18.00',
  gst_split_basis: 'intra_state',
  cgst_amount: '8550.00',
  sgst_amount: '8550.00',
  igst_amount: '0.00',
  total_gst: '17100.00',
  recoverable_gst: '17100.00',
  capitalizable_gst: '0.00',
  freight_cost: '2000.00',
  installation_cost: '1500.00',
  other_capitalizable_cost: '0.00',
  landed_cost: '98500.00',
  total_acquisition_outlay: '115600.00',
  per_unit_cost: '32833.34',
  itc_treatment: 'eligible',
  gst_amounts_overridden: false,
}

describe('cost build-up drawer', () => {
  it('explains the landed cost from the acquisition tab', async () => {
    const { AcquisitionTab } = await import('./AcquisitionTab')
    render(
      <ToastProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <AcquisitionTab detail={{ asset: { id: 'a1' }, acquisition: acq } as any} costLocked={false} />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /how was total capitalized value calculated/i }))

    const drawer = await waitFor(() => within(screen.getByRole('dialog')))
    expect(drawer.getByText('Total capitalized value')).toBeTruthy()
    const row = document.getElementById('calc-step-landed_cost')
    expect(row?.getAttribute('data-focused')).toBe('true')
    // Built from data already on the page — no projection banner.
    expect(screen.queryByText(/not the recorded figure/i)).toBeNull()
  })

  it('shows the per-unit allocation for a multi-unit acquisition', async () => {
    const { AcquisitionTab } = await import('./AcquisitionTab')
    render(
      <ToastProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <AcquisitionTab detail={{ asset: { id: 'a1' }, acquisition: acq } as any} costLocked={false} />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))
    const drawer = await waitFor(() => within(screen.getByRole('dialog')))
    expect(drawer.getByText('Per-unit cost')).toBeTruthy()
    expect(drawer.getByText(/98,500\.00 ÷ 3/)).toBeTruthy()
  })

  it('explains the GST split from the tax tab', async () => {
    const { TaxTab } = await import('./TaxTab')
    render(
      <ToastProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <TaxTab detail={{ asset: { id: 'a1' }, acquisition: acq } as any} costLocked={false} />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /how was total gst calculated/i }))

    await waitFor(() =>
      expect(document.getElementById('calc-step-total_gst')?.getAttribute('data-focused')).toBe('true'),
    )
    expect(within(screen.getByRole('dialog')).getByText('Intra-state — CGST + SGST')).toBeTruthy()
  })
})
