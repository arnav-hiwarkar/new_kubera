import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from './Sidebar'

const COLLAPSE_KEY = 'kubera.sidebar.collapsed'

function wrap(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

beforeEach(() => {
  localStorage.clear()
})

describe('Sidebar company branding footer', () => {
  it('shows the logo (not the name) when expanded and a logo is uploaded', () => {
    wrap(<Sidebar brand="Kubera" sections={[]} orgName="Acme Corp" orgLogoUrl="blob:logo" />)
    const img = screen.getByAltText('Acme Corp') as HTMLImageElement
    expect(img).toBeInTheDocument()
    expect(img.src).toContain('blob:logo')
    expect(screen.queryByText('Acme Corp')).not.toBeInTheDocument()
  })

  it('shows the company name when expanded and no logo is uploaded', () => {
    wrap(<Sidebar brand="Kubera" sections={[]} orgName="Acme Corp" orgLogoUrl={null} />)
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.queryByAltText('Acme Corp')).not.toBeInTheDocument()
  })

  it('shows a small logo when collapsed and a logo is uploaded', () => {
    localStorage.setItem(COLLAPSE_KEY, '1')
    wrap(<Sidebar brand="Kubera" sections={[]} orgName="Acme Corp" orgLogoUrl="blob:logo" />)
    expect(screen.getByAltText('Acme Corp')).toBeInTheDocument()
  })

  it('shows no branding footer when collapsed and no logo', () => {
    localStorage.setItem(COLLAPSE_KEY, '1')
    wrap(<Sidebar brand="Kubera" sections={[]} orgName="Acme Corp" orgLogoUrl={null} />)
    expect(screen.queryByText('Acme Corp')).not.toBeInTheDocument()
    expect(screen.queryByAltText('Acme Corp')).not.toBeInTheDocument()
    // The collapse toggle is still present.
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument()
  })
})
