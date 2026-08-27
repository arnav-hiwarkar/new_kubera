import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AvatarCropperModal } from './AvatarCropperModal'

describe('AvatarCropperModal', () => {
  it('renders modal when open with image and zoom controls', () => {
    render(
      <AvatarCropperModal
        isOpen={true}
        imageSrc="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        onClose={vi.fn()}
        onCropComplete={vi.fn()}
      />
    )

    expect(screen.getByText('Adjust Profile Picture')).toBeInTheDocument()
    expect(screen.getByLabelText('Zoom in')).toBeInTheDocument()
    expect(screen.getByLabelText('Zoom out')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply & Save' })).toBeInTheDocument()
  })

  it('calls onClose when cancel button is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <AvatarCropperModal
        isOpen={true}
        imageSrc="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        onClose={onClose}
        onCropComplete={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
