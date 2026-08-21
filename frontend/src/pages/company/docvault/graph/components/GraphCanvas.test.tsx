import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { GraphCanvas } from './GraphCanvas'
import type { GraphData } from '../types/graph'

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
  linkCurvature: vi.fn().mockReturnThis(),
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
    traverse: vi.fn(),
  }),
  postProcessingComposer: vi.fn(() => ({ addPass: vi.fn() })),
  onRenderFramePre: vi.fn(),
  linkVisibility: vi.fn().mockReturnThis(),
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

describe('GraphCanvas', () => {
  const mockData: GraphData = {
    nodes: [
      {
        id: 'bucket_1',
        rawId: 'b1',
        type: 'bucket',
        name: 'Finance',
        bucketId: 'b1',
        bucketName: 'Finance',
        color: '#38BDF8',
        size: 14,
        x: 0,
        y: 0,
        z: 0,
      },
      {
        id: 'doc_1',
        rawId: 'd1',
        type: 'document',
        name: 'Doc 1',
        bucketId: 'b1',
        bucketName: 'Finance',
        color: '#10B981',
        size: 6,
        x: 10,
        y: 10,
        z: 10,
      },
    ],
    links: [
      {
        source: 'bucket_1',
        target: 'doc_1',
        kind: 'bucket-doc',
        strength: 0.8,
        color: 'rgba(100, 160, 255, 0.35)',
      },
    ],
    bucketMap: new Map(),
    totalDocuments: 1,
    totalBuckets: 1,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders canvas container and initializes force graph instance', () => {
    const graphInstanceRef = { current: null }
    const { getByTestId } = render(
      <GraphCanvas
        data={mockData}
        graphInstanceRef={graphInstanceRef}
        onSelectNode={vi.fn()}
        onHoverNode={vi.fn()}
      />,
    )

    const container = getByTestId('graph-canvas-container')
    expect(container).toBeDefined()
    expect(mockForceGraphInstance.backgroundColor).toHaveBeenCalledWith('#0a0e0c')
    expect(mockForceGraphInstance.graphData).toHaveBeenCalledWith({
      nodes: mockData.nodes,
      links: mockData.links,
    })
    expect(graphInstanceRef.current).toBe(mockForceGraphInstance)
  })

  it('unmounts cleanly and calls _destructor', () => {
    const { unmount } = render(
      <GraphCanvas
        data={mockData}
        onSelectNode={vi.fn()}
        onHoverNode={vi.fn()}
      />,
    )

    unmount()
    expect(mockForceGraphInstance._destructor).toHaveBeenCalledTimes(1)
  })
})
