import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useGraphControls } from './useGraphControls'
import type { GraphNode } from '../types/graph'

describe('useGraphControls', () => {
  const createMockGraph = () => ({
    cameraPosition: vi.fn().mockReturnValue({ x: 100, y: 50, z: 200 }),
    zoomToFit: vi.fn(),
    pauseAnimation: vi.fn(),
    resumeAnimation: vi.fn(),
  })

  it('initializes with isPaused = false', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    expect(result.current.isPaused).toBe(false)
  })

  it('calls flyToNode for bucket node with distance 180 and 1200ms duration', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    const bucketNode: GraphNode = {
      id: 'bucket_1',
      rawId: 'b1',
      type: 'bucket',
      name: 'Financial Reports',
      bucketId: 'b1',
      bucketName: 'Financial Reports',
      color: '#38BDF8',
      size: 14,
      x: 30,
      y: 40,
      z: 0,
    }

    act(() => {
      result.current.flyToNode(bucketNode)
    })

    expect(mockGraph.cameraPosition).toHaveBeenCalledTimes(1)
    // distance is 180, currentDist is hypot(30, 40, 0) = 50.
    // distRatio = 1 + 180/50 = 4.6
    // x = 30 * 4.6 = 138, y = 40 * 4.6 = 184, z = 0
    const [camPos, lookAt, duration] = mockGraph.cameraPosition.mock.calls[0]
    expect(camPos.x).toBeCloseTo(138)
    expect(camPos.y).toBeCloseTo(184)
    expect(camPos.z).toBeCloseTo(0)
    expect(lookAt).toEqual({ x: 30, y: 40, z: 0 })
    expect(duration).toBe(1200)
  })

  it('calls flyToNode for document node with distance 120 and 1200ms duration', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    const docNode: GraphNode = {
      id: 'doc_1',
      rawId: 'd1',
      type: 'document',
      name: 'Q3 Report',
      bucketId: 'b1',
      bucketName: 'Financial Reports',
      color: '#10B981',
      size: 6,
      x: 60,
      y: 80,
      z: 0,
    }

    act(() => {
      result.current.flyToNode(docNode)
    })

    expect(mockGraph.cameraPosition).toHaveBeenCalledTimes(1)
    // distance is 120, currentDist is hypot(60, 80, 0) = 100.
    // distRatio = 1 + 120/100 = 2.2
    // x = 60 * 2.2 = 132, y = 80 * 2.2 = 176, z = 0
    const [camPos, lookAt, duration] = mockGraph.cameraPosition.mock.calls[0]
    expect(camPos.x).toBeCloseTo(132)
    expect(camPos.y).toBeCloseTo(176)
    expect(camPos.z).toBeCloseTo(0)
    expect(lookAt).toEqual({ x: 60, y: 80, z: 0 })
    expect(duration).toBe(1200)
  })

  it('ignores flyToNode if node coordinates are undefined', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    const nodeWithoutCoords: GraphNode = {
      id: 'doc_1',
      rawId: 'd1',
      type: 'document',
      name: 'Q3 Report',
      bucketId: 'b1',
      bucketName: 'Financial Reports',
      color: '#10B981',
      size: 6,
    }

    act(() => {
      result.current.flyToNode(nodeWithoutCoords)
    })

    expect(mockGraph.cameraPosition).not.toHaveBeenCalled()
  })

  it('calls resetCamera with zoomToFit(1000, 80)', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    act(() => {
      result.current.resetCamera()
    })

    expect(mockGraph.zoomToFit).toHaveBeenCalledWith(1000, 80)
  })

  it('calls recenter with target (0,0,0) and pos (0,0,350)', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    act(() => {
      result.current.recenter()
    })

    expect(mockGraph.cameraPosition).toHaveBeenCalledWith(
      { x: 0, y: 0, z: 350 },
      { x: 0, y: 0, z: 0 },
      1000,
    )
  })

  it('calls zoomIn scaling coordinates by 0.75 over 400ms', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    act(() => {
      result.current.zoomIn()
    })

    expect(mockGraph.cameraPosition).toHaveBeenCalledWith(
      { x: 75, y: 37.5, z: 150 },
      undefined,
      400,
    )
  })

  it('calls zoomOut scaling coordinates by 1.35 over 400ms', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    act(() => {
      result.current.zoomOut()
    })

    expect(mockGraph.cameraPosition).toHaveBeenCalledWith(
      { x: 135, y: 67.5, z: 270 },
      undefined,
      400,
    )
  })

  it('toggles physics pausing and resuming animation', () => {
    const mockGraph = createMockGraph()
    const graphRef = { current: mockGraph }
    const { result } = renderHook(() => useGraphControls(graphRef))

    expect(result.current.isPaused).toBe(false)

    act(() => {
      result.current.togglePhysics()
    })

    expect(mockGraph.pauseAnimation).toHaveBeenCalledTimes(1)
    expect(result.current.isPaused).toBe(true)

    act(() => {
      result.current.togglePhysics()
    })

    expect(mockGraph.resumeAnimation).toHaveBeenCalledTimes(1)
    expect(result.current.isPaused).toBe(false)
  })

  it('handles null graphRef without throwing', () => {
    const graphRef = { current: null }
    const { result } = renderHook(() => useGraphControls(graphRef))

    expect(() => {
      act(() => {
        result.current.resetCamera()
        result.current.recenter()
        result.current.zoomIn()
        result.current.zoomOut()
        result.current.togglePhysics()
      })
    }).not.toThrow()
  })
})
