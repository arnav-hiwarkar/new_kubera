import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { OwnerLeadsPage } from './OwnerLeadsPage'

describe('OwnerLeadsPage', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders locked authentication screen initially', () => {
    render(<OwnerLeadsPage />)
    expect(screen.getByText('Kubera Operator Vault')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Enter INTERNAL_API_KEY/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Unlock Portal/i })).toBeInTheDocument()
  })

  it('authenticates and displays leads on valid API key', async () => {
    const mockLeads = [
      {
        id: 'lead-1',
        email: 'cfo@corp.com',
        company_name: 'Corp Ltd',
        phone: '+91 9876543210',
        entities_count: 2,
        notes: 'Need AuditEase',
        status: 'new',
        created_at: '2026-08-26T12:00:00Z',
      },
    ]

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockLeads,
    } as any)

    render(<OwnerLeadsPage />)

    const input = screen.getByPlaceholderText(/Enter INTERNAL_API_KEY/i)
    fireEvent.change(input, { target: { value: 'secret-operator-key' } })
    fireEvent.click(screen.getByRole('button', { name: /Unlock Portal/i }))

    await waitFor(() => {
      expect(screen.getByText('cfo@corp.com')).toBeInTheDocument()
      expect(screen.getByText('Corp Ltd')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Provision/i })).toBeInTheDocument()
    })
  })
})
