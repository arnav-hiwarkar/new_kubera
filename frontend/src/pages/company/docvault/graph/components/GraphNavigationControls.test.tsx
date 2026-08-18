import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { GraphNavigationControls } from './GraphNavigationControls'

describe('GraphNavigationControls', () => {
  it('renders all 5 navigation dock buttons with correct aria-labels and titles', () => {
    const controls = {
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
      resetCamera: vi.fn(),
      recenter: vi.fn(),
      togglePhysics: vi.fn(),
      flyToNode: vi.fn(),
      isPaused: false,
    }

    render(<GraphNavigationControls controls={controls} />)

    const zoomInBtn = screen.getByTestId('nav-zoom-in')
    const zoomOutBtn = screen.getByTestId('nav-zoom-out')
    const resetCameraBtn = screen.getByTestId('nav-reset-camera')
    const recenterBtn = screen.getByTestId('nav-recenter')
    const togglePhysicsBtn = screen.getByTestId('nav-toggle-physics')

    expect(zoomInBtn.getAttribute('aria-label')).toBe('Zoom In')
    expect(zoomOutBtn.getAttribute('aria-label')).toBe('Zoom Out')
    expect(resetCameraBtn.getAttribute('aria-label')).toBe('Reset Camera')
    expect(recenterBtn.getAttribute('aria-label')).toBe('Recenter')
    expect(togglePhysicsBtn.getAttribute('aria-label')).toBe('Pause Physics')

    fireEvent.click(zoomInBtn)
    expect(controls.zoomIn).toHaveBeenCalledTimes(1)

    fireEvent.click(zoomOutBtn)
    expect(controls.zoomOut).toHaveBeenCalledTimes(1)

    fireEvent.click(resetCameraBtn)
    expect(controls.resetCamera).toHaveBeenCalledTimes(1)

    fireEvent.click(recenterBtn)
    expect(controls.recenter).toHaveBeenCalledTimes(1)

    fireEvent.click(togglePhysicsBtn)
    expect(controls.togglePhysics).toHaveBeenCalledTimes(1)
  })

  it('updates toggle physics label when paused', () => {
    render(
      <GraphNavigationControls
        isPaused={true}
        onTogglePhysics={vi.fn()}
      />,
    )

    const togglePhysicsBtn = screen.getByTestId('nav-toggle-physics')
    expect(togglePhysicsBtn.getAttribute('aria-label')).toBe('Resume Physics')
  })
})
