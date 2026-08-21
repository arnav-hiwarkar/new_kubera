import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { GraphHud } from './GraphHud'
import type { GraphData, GraphNode } from '../types/graph'
import type { BucketResponse } from '@/api/types'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('GraphHud', () => {
  const mockBuckets: BucketResponse[] = [
    {
      id: 'b1',
      name: 'Financial Statements',
      company_id: 'c1',
      created_by: 'u1',
      visibility: 'everyone',
      access_user_ids: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'b2',
      name: 'Tax Returns',
      company_id: 'c1',
      created_by: 'u1',
      visibility: 'restricted',
      access_user_ids: [],
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    },
  ]

  const mockNodes: GraphNode[] = [
    {
      id: 'bucket_b1',
      rawId: 'b1',
      type: 'bucket',
      name: 'Financial Statements',
      bucketId: 'b1',
      bucketName: 'Financial Statements',
      color: '#38BDF8',
      size: 14,
    },
    {
      id: 'doc_d1',
      rawId: 'd1',
      type: 'document',
      name: 'Q3 Balance Sheet.pdf',
      bucketId: 'b1',
      bucketName: 'Financial Statements',
      status: 'verified',
      tags: ['finance', '2026', 'quarterly'],
      color: '#10B981',
      size: 6,
    },
    {
      id: 'doc_d2',
      rawId: 'd2',
      type: 'document',
      name: 'Audit Notes.docx',
      bucketId: 'b2',
      bucketName: 'Tax Returns',
      status: 'action_required',
      tags: ['audit', 'tax'],
      color: '#EF4444',
      size: 6,
    },
  ]

  const mockData: GraphData = {
    nodes: mockNodes,
    links: [],
    bucketMap: new Map([
      ['b1', mockBuckets[0]],
      ['b2', mockBuckets[1]],
    ]),
    totalDocuments: 2,
    totalBuckets: 2,
  }

  const baseProps = {
    data: mockData,
    buckets: mockBuckets,
    colorMode: 'bucket' as const,
    onColorModeChange: vi.fn(),
    visibleBucketIds: new Set(['all']),
    onToggleBucket: vi.fn(),
    onShowAllBuckets: vi.fn(),
    onSelectNode: vi.fn(),
    searchQuery: '',
    onSearchQueryChange: vi.fn(),
  }

  // Controlled wrapper simulating the page-owned query state
  function ControlledGraphHud(props: Partial<typeof baseProps> & { onSelectNode?: (n: GraphNode) => void }) {
    const [query, setQuery] = useState('')
    return (
      <MemoryRouter>
        <GraphHud
          {...baseProps}
          {...props}
          searchQuery={query}
          onSearchQueryChange={setQuery}
        />
      </MemoryRouter>
    )
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders back button and navigates to /app/docvault on click', () => {
    render(
      <MemoryRouter>
        <GraphHud {...baseProps} />
      </MemoryRouter>,
    )

    const backBtn = screen.getByTestId('back-button')
    expect(backBtn).toBeDefined()
    expect(screen.getByText('Back to DocVault')).toBeDefined()

    fireEvent.click(backBtn)
    expect(mockNavigate).toHaveBeenCalledWith('/app/docvault')
  })

  it('renders breadcrumb badge with correct counts', () => {
    render(
      <MemoryRouter>
        <GraphHud {...baseProps} />
      </MemoryRouter>,
    )

    const badge = screen.getByTestId('graph-breadcrumb-badge')
    expect(badge.textContent).toContain('DocVault 3D Graph')
    expect(badge.textContent).toContain('2 Buckets')
    expect(badge.textContent).toContain('2 Docs')
  })

  it('filters nodes in autocomplete search and calls onSelectNode when clicked', () => {
    render(<ControlledGraphHud />)

    const searchInput = screen.getByTestId('graph-search-input')
    fireEvent.change(searchInput, { target: { value: 'Balance' } })

    const dropdown = screen.getByTestId('search-results-dropdown')
    expect(dropdown).toBeDefined()

    const resultItems = screen.getAllByTestId('search-result-item')
    expect(resultItems.length).toBe(1)
    expect(resultItems[0].textContent).toContain('Q3 Balance Sheet.pdf')

    fireEvent.click(resultItems[0])
    expect(baseProps.onSelectNode).toHaveBeenCalledWith(mockNodes[1])
  })

  it('filters nodes by tag in autocomplete search', () => {
    render(<ControlledGraphHud />)

    const searchInput = screen.getByTestId('graph-search-input')
    fireEvent.change(searchInput, { target: { value: 'quarterly' } })

    const resultItems = screen.getAllByTestId('search-result-item')
    expect(resultItems.length).toBe(1)
    expect(resultItems[0].textContent).toContain('Q3 Balance Sheet.pdf')
  })

  it('shows no results message when search has no matches', () => {
    render(<ControlledGraphHud />)

    const searchInput = screen.getByTestId('graph-search-input')
    fireEvent.change(searchInput, { target: { value: 'NonexistentDoc' } })

    const noResults = screen.getByTestId('search-no-results')
    expect(noResults.textContent).toContain('No matching documents or buckets found')
  })

  it('lifts typed query to parent and selects first result on Enter', async () => {
    const user = userEvent.setup()
    const onSelectNode = vi.fn()
    render(<ControlledGraphHud onSelectNode={onSelectNode} />)
    const input = screen.getByTestId('graph-search-input')
    await user.type(input, 'tax')
    await user.keyboard('{Enter}')
    expect(onSelectNode).toHaveBeenCalled()
  })

  it('clears the query via Escape key', async () => {
    const user = userEvent.setup()
    render(<ControlledGraphHud />)
    const input = screen.getByTestId('graph-search-input')
    await user.type(input, 'tax')
    await user.keyboard('{Escape}')
    expect((input as HTMLInputElement).value).toBe('')
  })

  it('switches color mode when clicking mode buttons', () => {
    render(
      <MemoryRouter>
        <GraphHud {...baseProps} />
      </MemoryRouter>,
    )

    const statusBtn = screen.getByTestId('color-mode-status')
    fireEvent.click(statusBtn)
    expect(baseProps.onColorModeChange).toHaveBeenCalledWith('status')

    const bucketBtn = screen.getByTestId('color-mode-bucket')
    fireEvent.click(bucketBtn)
    expect(baseProps.onColorModeChange).toHaveBeenCalledWith('bucket')
  })

  it('opens bucket filter dropdown and toggles bucket checkboxes', () => {
    render(
      <MemoryRouter>
        <GraphHud {...baseProps} />
      </MemoryRouter>,
    )

    const filterBtn = screen.getByTestId('bucket-filter-button')
    fireEvent.click(filterBtn)

    const dropdown = screen.getByTestId('bucket-filter-dropdown')
    expect(dropdown).toBeDefined()

    const b1Checkbox = screen.getByTestId('bucket-checkbox-b1')
    fireEvent.click(b1Checkbox)
    expect(baseProps.onToggleBucket).toHaveBeenCalledWith('b1')
  })

  it('calls onShowAllBuckets when Show All button is clicked', () => {
    render(
      <MemoryRouter>
        <GraphHud {...baseProps} visibleBucketIds={new Set(['b1'])} />
      </MemoryRouter>,
    )

    const filterBtn = screen.getByTestId('bucket-filter-button')
    fireEvent.click(filterBtn)

    const showAllBtn = screen.getByTestId('show-all-buckets-btn')
    fireEvent.click(showAllBtn)
    expect(baseProps.onShowAllBuckets).toHaveBeenCalledTimes(1)
  })
})
