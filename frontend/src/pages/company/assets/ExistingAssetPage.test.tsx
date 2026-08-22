import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ExistingAssetPage } from './ExistingAssetPage'
import { ToastProvider } from '@/components/ui/Toast'

const navigate = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('@/api/hooks/assetMasters', () => ({
  useCategoryTree: () => ({
    isLoading: false,
    tree: [
      { parent: { id: 'mv', name: 'Motor vehicles' }, children: [
        { id: 'car', name: 'Motor cars (other than those used in a hire business)',
          default_useful_life_months: 96, default_dep_method: 'slm',
          default_residual_pct: 5, default_it_block_code: 'PM-15-MV',
          default_it_block_rate: 15, default_itc_treatment: 'blocked' },
      ]},
    ],
  }),
}))
vi.mock('./LookupSelect', () => ({ LookupSelect: () => <div /> }))
const mutateAsync = vi.fn().mockResolvedValue({ id: 'a-1' })
vi.mock('@/api/hooks/assets', () => ({
  useCreateExistingAsset: () => ({ mutateAsync, isPending: false }),
}))

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}
function pick(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('ExistingAssetPage', () => {
  // Module-level mocks persist across cases; the negative navigate assertion
  // in the second test needs a clean slate.
  beforeEach(() => {
    navigate.mockClear()
    mutateAsync.mockClear()
  })

  it('submits opening balances and navigates to the new asset', async () => {
    render(
      <ToastProvider>
        <ExistingAssetPage />
      </ToastProvider>,
    )
    fill('Asset name', 'Tata Ace')
    pick('Category', 'mv') // single child auto-selects
    fill('Original cost', '850000')
    fill('Put-to-use date', '2022-06-20')
    fill('Capitalization date', '2022-06-30')
    fill('Opening accumulated depreciation', '200000')
    fill('Opening WDV (books)', '650000')
    fill('Opening WDV (tax)', '610000')
    fireEvent.click(screen.getByRole('button', { name: /save draft/i }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/app/assets/a-1'))
    expect(mutateAsync).toHaveBeenCalledTimes(1)
    const body = mutateAsync.mock.calls[0][0]
    expect(body.category_path).toEqual(['Motor vehicles', 'Motor cars (other than those used in a hire business)'])
    expect(body.opening_it_wdv).toBe('610000')
  })

  it('blocks save with a message when openings are missing for a pre-FY asset', async () => {
    render(
      <ToastProvider>
        <ExistingAssetPage />
      </ToastProvider>,
    )
    fill('Asset name', 'Old lathe')
    pick('Category', 'mv')
    fill('Original cost', '100')
    fill('Put-to-use date', '2020-01-01')
    fireEvent.click(screen.getByRole('button', { name: /save draft/i }))
    // '/required/i' alone also matches two static hints; anchor on the message itself.
    expect(await screen.findByText(/all required/i)).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalled()
  })
})
