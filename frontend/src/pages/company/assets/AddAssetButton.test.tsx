import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AddAssetButton } from './AddAssetButton'

const navigate = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('./QuickAddAssetModal', () => ({ QuickAddAssetModal: () => <div data-testid="quick-add" /> }))

describe('AddAssetButton', () => {
  it('offers new vs existing and routes existing to its page', () => {
    render(<AddAssetButton />)
    fireEvent.click(screen.getByRole('button', { name: /add asset/i }))
    fireEvent.click(screen.getByText('Existing asset'))
    expect(navigate).toHaveBeenCalledWith('/app/assets/new/existing')
  })

  it('opens the quick-add modal for a new asset', () => {
    render(<AddAssetButton />)
    fireEvent.click(screen.getByRole('button', { name: /add asset/i }))
    fireEvent.click(screen.getByText('New asset'))
    expect(screen.getByTestId('quick-add')).toBeInTheDocument()
  })
})
