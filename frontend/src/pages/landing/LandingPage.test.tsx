import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LandingPage } from './LandingPage'

describe('LandingPage', () => {
  it('renders brand header, hero headline, and main sections', () => {
    render(<LandingPage />)

    // Brand & Header
    expect(screen.getAllByText('KUBERA').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/A Product by ETHDC/i).length).toBeGreaterThan(0)

    // Hero & Footer tagline
    expect(
      screen.getAllByText(/A secure treasury for the records that keep your company/i).length
    ).toBeGreaterThan(0)

    // Why Kubera section
    expect(screen.getAllByText(/Compliance shouldn’t live in someone’s inbox/i).length).toBeGreaterThan(0)

    // Four modules section
    expect(screen.getByText(/Four modules, one vault/i)).toBeInTheDocument()

    // Value section
    expect(screen.getByText(/The value, in plain terms/i)).toBeInTheDocument()

    // Pricing section
    expect(screen.getByText(/Introductory pricing, sized to your business/i)).toBeInTheDocument()
    expect(screen.getByText('₹60,000')).toBeInTheDocument()
    expect(screen.getByText('₹100,000')).toBeInTheDocument()
  })

  it('switches tabs in the module showcase', async () => {
    render(<LandingPage />)

    // Initially docVault is active
    expect(screen.getByText(/Module 01: Repository Management/i)).toBeInTheDocument()

    // Click Fixed Asset Register tab
    fireEvent.click(screen.getByRole('button', { name: /Fixed Asset Register/i }))
    await waitFor(() => {
      expect(screen.getByText(/Module 02: Asset Life Cycle/i)).toBeInTheDocument()
    })

    // Click AuditEase tab
    fireEvent.click(screen.getByRole('button', { name: /AuditEase/i }))
    await waitFor(() => {
      expect(screen.getByText(/Module 03: Audit Management/i)).toBeInTheDocument()
    })
  })

  it('opens and closes the Request Access modal', async () => {
    render(<LandingPage />)

    // Click Request Access in header
    const buttons = screen.getAllByRole('button', { name: /Request Access/i })
    fireEvent.click(buttons[0])

    expect(screen.getByRole('dialog', { name: /Request Access & Demonstration/i })).toBeInTheDocument()

    // Close modal
    const closeBtn = screen.getByRole('button', { name: /Close/i })
    fireEvent.click(closeBtn)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })
})
