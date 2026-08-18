import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { DocVaultGraphPage } from './DocVaultGraphPage'
import { DocVaultPage } from '../DocVaultPage'
import { docvaultApi } from '@/api/endpoints/docvault'
import type { BucketResponse, DocumentResponse } from '@/api/types'

const mockForceGraphInstance = {
  backgroundColor: vi.fn().mockReturnThis(),
  showNavInfo: vi.fn().mockReturnThis(),
  nodeRelSize: vi.fn().mockReturnThis(),
  nodeVal: vi.fn().mockReturnThis(),
  linkWidth: vi.fn().mockReturnThis(),
  linkOpacity: vi.fn().mockReturnThis(),
  linkColor: vi.fn().mockReturnThis(),
  linkDirectionalParticles: vi.fn().mockReturnThis(),
  linkDirectionalParticleWidth: vi.fn().mockReturnThis(),
  linkDirectionalParticleSpeed: vi.fn().mockReturnThis(),
  linkDirectionalParticleColor: vi.fn().mockReturnThis(),
  nodeThreeObject: vi.fn().mockReturnThis(),
  onNodeHover: vi.fn().mockReturnThis(),
  onNodeClick: vi.fn().mockReturnThis(),
  onBackgroundClick: vi.fn().mockReturnThis(),
  onNodeDrag: vi.fn().mockReturnThis(),
  onNodeDragEnd: vi.fn().mockReturnThis(),
  d3Force: vi.fn().mockReturnValue({
    distance: vi.fn().mockReturnThis(),
    strength: vi.fn().mockReturnThis(),
    alphaTarget: vi.fn().mockReturnThis(),
    restart: vi.fn().mockReturnThis(),
  }),
  d3AlphaTarget: vi.fn().mockReturnThis(),
  d3ReheatSimulation: vi.fn().mockReturnThis(),
  camera: vi.fn().mockReturnValue({
    position: { distanceTo: vi.fn().mockReturnValue(150) },
  }),
  scene: vi.fn().mockReturnValue({
    add: vi.fn(),
  }),
  graphData: vi.fn().mockReturnThis(),
  width: vi.fn().mockReturnThis(),
  height: vi.fn().mockReturnThis(),
  cameraPosition: vi.fn().mockReturnValue({ x: 0, y: 0, z: 300 }),
  zoomToFit: vi.fn(),
  pauseAnimation: vi.fn(),
  resumeAnimation: vi.fn(),
  _destructor: vi.fn(),
}

vi.mock('3d-force-graph', () => {
  return {
    default: () => () => mockForceGraphInstance,
  }
})

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: { id: 'u-1', role: 'admin', email: 'admin@acme.test', full_name: 'Ada Admin' },
    status: 'authenticated',
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}))

vi.mock('@/api/endpoints/docvault', () => ({
  docvaultApi: {
    listBuckets: vi.fn().mockResolvedValue([]),
    listDocuments: vi.fn().mockResolvedValue([]),
    uploadDocument: vi.fn().mockResolvedValue({}),
    deleteDocument: vi.fn().mockResolvedValue(undefined),
    updateDocument: vi.fn().mockResolvedValue({}),
    uploadVersion: vi.fn().mockResolvedValue({}),
    downloadDocument: vi.fn().mockResolvedValue(new Blob()),
  },
}))

const mockBuckets: BucketResponse[] = [
  {
    id: 'b-1',
    company_id: 'co-1',
    name: 'Finance & Tax',
    visibility: 'everyone',
    access_user_ids: [],
    created_by: 'u-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'b-2',
    company_id: 'co-1',
    name: 'Legal & Board',
    visibility: 'restricted',
    access_user_ids: ['u-1'],
    created_by: 'u-1',
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
]

const mockDocuments: DocumentResponse[] = [
  {
    id: 'doc-1',
    company_id: 'co-1',
    current_version_id: 'v-1',
    bucket_id: 'b-1',
    status: 'uploaded',
    title: 'Q3 Tax Return',
    doc_type_id: null,
    tags: ['tax', 'q3'],
    is_editable: true,
    created_by: 'u-1',
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    versions: [
      {
        id: 'v-1',
        document_id: 'doc-1',
        original_filename: 'q3_tax.pdf',
        mime_type: 'application/pdf',
        size_bytes: 524288,
        checksum: 'checksum-1',
        uploaded_by: 'u-1',
        uploaded_at: '2026-06-01T00:00:00Z',
        version_number: 1,
      },
    ],
  },
  {
    id: 'doc-2',
    company_id: 'co-1',
    current_version_id: 'v-2',
    bucket_id: 'b-2',
    status: 'verified',
    title: 'Board Resolution 2026-A',
    doc_type_id: null,
    tags: ['board', 'minutes'],
    is_editable: true,
    created_by: 'u-1',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    versions: [
      {
        id: 'v-2',
        document_id: 'doc-2',
        original_filename: 'resolution.pdf',
        mime_type: 'application/pdf',
        size_bytes: 1048576,
        checksum: 'checksum-2',
        uploaded_by: 'u-1',
        uploaded_at: '2026-07-01T00:00:00Z',
        version_number: 1,
      },
    ],
  },
]

function renderGraphPage(initialEntries = ['/app/docvault/graph']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/app/docvault/graph" element={<DocVaultGraphPage />} />
            <Route path="/app/docvault" element={<DocVaultPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('DocVaultGraphPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docvaultApi.listBuckets).mockResolvedValue(mockBuckets)
    vi.mocked(docvaultApi.listDocuments).mockResolvedValue(mockDocuments)
  })

  it('renders graph page container, HUD, canvas, navigation controls, and legend', async () => {
    const { getByTestId } = renderGraphPage()

    await waitFor(() => {
      expect(getByTestId('docvault-graph-page')).toBeInTheDocument()
      expect(getByTestId('graph-canvas-container')).toBeInTheDocument()
      expect(getByTestId('graph-search-input')).toBeInTheDocument()
      expect(getByTestId('graph-legend')).toBeInTheDocument()
      expect(getByTestId('nav-zoom-in')).toBeInTheDocument()
    })
  })

  it('updates search query and opens autocomplete results dropdown', async () => {
    const user = userEvent.setup()
    const { findByTestId, findAllByTestId } = renderGraphPage()

    const searchInput = await findByTestId('graph-search-input')
    await user.type(searchInput, 'Tax')

    const dropdown = await findByTestId('search-results-dropdown')
    expect(dropdown).toBeInTheDocument()

    const items = await findAllByTestId('search-result-item')
    expect(items.length).toBeGreaterThan(0)
  })

  it('opens DocumentDrawer when selecting a document node from search', async () => {
    const user = userEvent.setup()
    const { findByTestId, findAllByTestId } = renderGraphPage()

    const searchInput = await findByTestId('graph-search-input')
    await user.type(searchInput, 'Q3 Tax Return')

    const items = await findAllByTestId('search-result-item')
    expect(items.length).toBeGreaterThan(0)
    await user.click(items[0])

    // Document drawer opens with document title
    await waitFor(() => {
      expect(screen.getByDisplayValue('Q3 Tax Return')).toBeInTheDocument()
    })
  })

  it('opens BucketSummaryCard when selecting a bucket node from search', async () => {
    const user = userEvent.setup()
    const { findByTestId, findAllByTestId } = renderGraphPage()

    const searchInput = await findByTestId('graph-search-input')
    await user.type(searchInput, 'Finance & Tax')

    const items = await findAllByTestId('search-result-item')
    expect(items.length).toBeGreaterThan(0)
    await user.click(items[0])

    // BucketSummaryCard opens
    const card = await findByTestId('bucket-summary-card')
    expect(card).toBeInTheDocument()
    expect(screen.getByTestId('bucket-summary-title')).toHaveTextContent('Finance & Tax')

    // Close bucket summary card
    const closeBtn = screen.getByTestId('bucket-summary-close')
    await user.click(closeBtn)
    expect(screen.queryByTestId('bucket-summary-card')).not.toBeInTheDocument()
  })

  it('handles navigation controls interaction (zoom, reset, recenter, physics)', async () => {
    const user = userEvent.setup()
    const { findByTestId } = renderGraphPage()

    const zoomInBtn = await findByTestId('nav-zoom-in')
    const zoomOutBtn = await findByTestId('nav-zoom-out')
    const resetCameraBtn = await findByTestId('nav-reset-camera')
    const recenterBtn = await findByTestId('nav-recenter')
    const togglePhysicsBtn = await findByTestId('nav-toggle-physics')

    await user.click(zoomInBtn)
    await user.click(zoomOutBtn)
    await user.click(resetCameraBtn)
    expect(mockForceGraphInstance.zoomToFit).toHaveBeenCalled()

    await user.click(recenterBtn)
    expect(mockForceGraphInstance.cameraPosition).toHaveBeenCalled()

    await user.click(togglePhysicsBtn)
    expect(mockForceGraphInstance.pauseAnimation).toHaveBeenCalled()
  })

  it('toggles color mode between bucket and status', async () => {
    const user = userEvent.setup()
    const { findByTestId } = renderGraphPage()

    const statusBtn = await findByTestId('color-mode-status')
    await user.click(statusBtn)
    expect(statusBtn.className).toContain('bg-emerald-600')

    const bucketBtn = await findByTestId('color-mode-bucket')
    await user.click(bucketBtn)
    expect(bucketBtn.className).toContain('bg-emerald-600')
  })

  it('filters by bucket via HUD bucket dropdown', async () => {
    const user = userEvent.setup()
    const { findByTestId } = renderGraphPage()

    const filterBtn = await findByTestId('bucket-filter-button')
    await user.click(filterBtn)

    const dropdown = await findByTestId('bucket-filter-dropdown')
    expect(dropdown).toBeInTheDocument()

    const checkbox = await findByTestId('bucket-checkbox-b-1')
    await user.click(checkbox)

    const showAllBtn = await findByTestId('show-all-buckets-btn')
    await user.click(showAllBtn)
    expect(screen.queryByTestId('bucket-filter-dropdown')).not.toBeInTheDocument()
  })
})

describe('DocVaultPage -> Graph Page navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docvaultApi.listBuckets).mockResolvedValue(mockBuckets)
    vi.mocked(docvaultApi.listDocuments).mockResolvedValue(mockDocuments)
  })

  it('renders "3D Graph View" button in DocVaultPage header and navigates to graph view', async () => {
    const user = userEvent.setup()
    renderGraphPage(['/app/docvault'])

    const graphBtn = await screen.findByRole('button', { name: /3D Graph View/i })
    expect(graphBtn).toBeInTheDocument()

    await user.click(graphBtn)

    await waitFor(() => {
      expect(screen.getByTestId('docvault-graph-page')).toBeInTheDocument()
    })
  })
})
