import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RequirementsOverview } from './RequirementsOverview'
import type { RequirementRequestResponse } from '@/api/types'

describe('RequirementsOverview', () => {
  const mockItems: RequirementRequestResponse[] = [
    {
      id: '1',
      engagement_id: 'eng-1',
      raised_by: 'u1',
      seq_number: 1,
      requirement_id_str: 'REQ-001',
      description: 'Req 1',
      priority: 1,
      status: 'closed',
      document_count: 0,
      linked_query_count: 0,
      submission_count: 1,
      submissions: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: '2',
      engagement_id: 'eng-1',
      raised_by: 'u1',
      seq_number: 2,
      requirement_id_str: 'REQ-002',
      description: 'Req 2',
      priority: 2,
      status: 'open',
      document_count: 0,
      linked_query_count: 0,
      submission_count: 2,
      submissions: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: '3',
      engagement_id: 'eng-1',
      raised_by: 'u1',
      seq_number: 3,
      requirement_id_str: 'REQ-003',
      description: 'Req 3',
      priority: 1,
      status: 'open',
      document_count: 0,
      linked_query_count: 0,
      submission_count: 0,
      submissions: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ]

  it('renders overview header and stats', () => {
    render(<RequirementsOverview items={mockItems} />)
    expect(screen.getByText('Requirements Overview')).toBeInTheDocument()
    expect(screen.getByText('(3 total)')).toBeInTheDocument()
    expect(screen.getByText('33% Closed')).toBeInTheDocument()
    expect(screen.getByText('(1 of 3)')).toBeInTheDocument()
  })

  it('handles filter button clicks', () => {
    const onSelect = vi.fn()
    render(<RequirementsOverview items={mockItems} onSelectFilter={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /closed/i }))
    expect(onSelect).toHaveBeenCalledWith('closed')

    fireEvent.click(screen.getByRole('button', { name: /responded/i }))
    expect(onSelect).toHaveBeenCalledWith('responded')

    fireEvent.click(screen.getByRole('button', { name: /awaiting/i }))
    expect(onSelect).toHaveBeenCalledWith('awaiting')
  })
})
