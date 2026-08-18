import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BucketSummaryCard } from './BucketSummaryCard'
import type { GraphNode } from '../types/graph'
import type { BucketResponse } from '@/api/types'

describe('BucketSummaryCard', () => {
  const mockBucket: BucketResponse = {
    id: 'b1',
    name: 'Legal Documents',
    company_id: 'c1',
    created_by: 'u1',
    visibility: 'everyone',
    access_user_ids: [],
    created_at: '2026-02-15T10:00:00Z',
    updated_at: '2026-02-15T10:00:00Z',
  }

  const mockNode: GraphNode = {
    id: 'bucket_b1',
    rawId: 'b1',
    type: 'bucket',
    name: 'Legal Documents',
    bucketId: 'b1',
    bucketName: 'Legal Documents',
    color: '#38BDF8',
    size: 14,
    rawBucket: mockBucket,
  }

  it('renders nothing when node is null', () => {
    const { container } = render(
      <BucketSummaryCard node={null} onClose={vi.fn()} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when node is a document node', () => {
    const docNode: GraphNode = {
      id: 'doc_1',
      rawId: 'd1',
      type: 'document',
      name: 'Contract.pdf',
      bucketId: 'b1',
      bucketName: 'Legal Documents',
      color: '#10B981',
      size: 6,
    }

    const { container } = render(
      <BucketSummaryCard node={docNode} onClose={vi.fn()} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders bucket details with "everyone" visibility', () => {
    const onClose = vi.fn()
    render(
      <BucketSummaryCard
        node={mockNode}
        bucket={mockBucket}
        documentCount={5}
        onClose={onClose}
      />,
    )

    expect(screen.getByTestId('bucket-summary-card')).toBeDefined()
    expect(screen.getByTestId('bucket-summary-title').textContent).toBe('Legal Documents')
    expect(screen.getByTestId('bucket-cluster-badge').textContent).toContain('Bucket Hub')
    expect(screen.getByTestId('bucket-cluster-badge').textContent).toContain('5 docs')
    expect(screen.getByTestId('bucket-visibility-badge').textContent).toContain('Everyone')
  })

  it('renders restricted visibility badge correctly', () => {
    const restrictedBucket: BucketResponse = {
      ...mockBucket,
      visibility: 'restricted',
    }
    const restrictedNode: GraphNode = {
      ...mockNode,
      rawBucket: restrictedBucket,
    }

    render(
      <BucketSummaryCard
        node={restrictedNode}
        bucket={restrictedBucket}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByTestId('bucket-visibility-badge').textContent).toContain('Restricted')
  })

  it('renders formatted created date when available', () => {
    render(
      <BucketSummaryCard
        node={mockNode}
        bucket={mockBucket}
        onClose={vi.fn()}
      />,
    )

    const dateElem = screen.getByTestId('bucket-created-date')
    expect(dateElem).toBeDefined()
    expect(dateElem.textContent).not.toBe('')
  })

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn()
    render(
      <BucketSummaryCard
        node={mockNode}
        bucket={mockBucket}
        onClose={onClose}
      />,
    )

    const closeBtn = screen.getByTestId('bucket-summary-close')
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onFocusCluster when focus cluster button is clicked', () => {
    const onFocusCluster = vi.fn()
    render(
      <BucketSummaryCard
        node={mockNode}
        bucket={mockBucket}
        onClose={vi.fn()}
        onFocusCluster={onFocusCluster}
      />,
    )

    const focusBtn = screen.getByTestId('focus-cluster-btn')
    fireEvent.click(focusBtn)
    expect(onFocusCluster).toHaveBeenCalledWith(mockNode)
  })
})
