import { useCallback, useState } from 'react'
import type { GraphNode } from '../types/graph'

export interface GraphControlsApi {
  flyToNode: (node: GraphNode) => void
  resetCamera: () => void
  recenter: () => void
  zoomIn: () => void
  zoomOut: () => void
  togglePhysics: () => void
  isPaused: boolean
}

export function useGraphControls(
  graphRef: React.RefObject<any> | React.MutableRefObject<any> | { current: any } | null | undefined,
): GraphControlsApi {
  const [isPaused, setIsPaused] = useState(false)

  const flyToNode = useCallback(
    (node: GraphNode) => {
      const graph = graphRef?.current
      if (!graph || node.x === undefined || node.y === undefined || node.z === undefined) return

      const distance = node.type === 'bucket' ? 180 : 120
      const currentDist = Math.hypot(node.x, node.y, node.z || 0) || 1
      const distRatio = 1 + distance / currentDist

      graph.cameraPosition(
        {
          x: node.x * distRatio,
          y: node.y * distRatio,
          z: (node.z || 0) * distRatio,
        },
        {
          x: node.x,
          y: node.y,
          z: node.z || 0,
        },
        1200,
      )
    },
    [graphRef],
  )

  const resetCamera = useCallback(() => {
    const graph = graphRef?.current
    if (!graph) return
    graph.zoomToFit(1000, 80)
  }, [graphRef])

  const recenter = useCallback(() => {
    const graph = graphRef?.current
    if (!graph) return
    graph.cameraPosition({ x: 0, y: 0, z: 350 }, { x: 0, y: 0, z: 0 }, 1000)
  }, [graphRef])

  const zoomIn = useCallback(() => {
    const graph = graphRef?.current
    if (!graph) return
    const current = graph.cameraPosition?.()
    if (!current) return
    graph.cameraPosition(
      {
        x: current.x * 0.75,
        y: current.y * 0.75,
        z: current.z * 0.75,
      },
      undefined,
      400,
    )
  }, [graphRef])

  const zoomOut = useCallback(() => {
    const graph = graphRef?.current
    if (!graph) return
    const current = graph.cameraPosition?.()
    if (!current) return
    graph.cameraPosition(
      {
        x: current.x * 1.35,
        y: current.y * 1.35,
        z: current.z * 1.35,
      },
      undefined,
      400,
    )
  }, [graphRef])

  const togglePhysics = useCallback(() => {
    const graph = graphRef?.current
    if (!graph) return
    setIsPaused((prev) => {
      const next = !prev
      if (next) {
        graph.pauseAnimation?.()
      } else {
        graph.resumeAnimation?.()
      }
      return next
    })
  }, [graphRef])

  return {
    flyToNode,
    resetCamera,
    recenter,
    zoomIn,
    zoomOut,
    togglePhysics,
    isPaused,
  }
}
