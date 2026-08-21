import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GraphLegend } from './GraphLegend'
import type { BucketResponse } from '@/api/types'

describe('GraphLegend', () => {
  const mockBuckets: BucketResponse[] = [
    {
      id: 'b1',
      name: 'Operations',
      company_id: 'c1',
      created_by: 'u1',
      visibility: 'everyone',
      access_user_ids: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ]

  it('renders legend in bucket color mode with bucket list', () => {
    render(<GraphLegend colorMode="bucket" buckets={mockBuckets} />)

    expect(screen.getByTestId('graph-legend')).toBeDefined()
    expect(screen.getByText('Legend')).toBeDefined()
    expect(screen.getByText('By Bucket')).toBeDefined()
    expect(screen.getByText('Bucket Hub')).toBeDefined()
    expect(screen.getByText('Document Node')).toBeDefined()
    expect(screen.getByText('Operations')).toBeDefined()
  })

  it('renders legend in status color mode with status list', () => {
    render(<GraphLegend colorMode="status" buckets={mockBuckets} />)

    expect(screen.getByText('By Status')).toBeDefined()
    expect(screen.getByText('Status Colors')).toBeDefined()
    expect(screen.getByText('Verified')).toBeDefined()
    expect(screen.getByText('Action Required')).toBeDefined()
  })

  it('toggles collapse and expand on header click', () => {
    render(<GraphLegend colorMode="bucket" buckets={mockBuckets} defaultOpen={true} />)

    expect(screen.getByText('Node Types')).toBeDefined()

    const toggleBtn = screen.getByTestId('legend-toggle-btn')
    fireEvent.click(toggleBtn)

    expect(screen.queryByText('Node Types')).toBeNull()
  })

  it('renders tag-links toggle and reports changes', async () => {
    const user = userEvent.setup()
    const onToggleTagLinks = vi.fn()
    render(<GraphLegend colorMode="bucket" showTagLinks onToggleTagLinks={onToggleTagLinks} />)
    const toggle = screen.getByTestId('legend-tag-links-toggle')
    const checkbox = within(toggle).getByRole('checkbox')
    expect(checkbox).toBeChecked()
    await user.click(checkbox)
    expect(onToggleTagLinks).toHaveBeenCalledWith(false)
  })
})
