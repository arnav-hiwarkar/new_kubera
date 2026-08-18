import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph'
import type { GraphData, GraphLink, GraphNode } from '../types/graph'
import { createNodeSprite, updateSpriteLOD } from '../lib/textSprite'

export interface GraphCanvasProps {
  data: GraphData
  selectedNodeId?: string | null
  onSelectNode?: (node: GraphNode | null) => void
  hoveredNodeId?: string | null
  onHoverNode?: (node: GraphNode | null) => void
  graphInstanceRef?: React.MutableRefObject<ForceGraph3DInstance | null> | React.RefObject<ForceGraph3DInstance | null> | { current: ForceGraph3DInstance | null }
  className?: string
}

interface ForceSimulationLike {
  alphaTarget?: (alpha: number) => ForceSimulationLike
  restart?: () => ForceSimulationLike
  distance?: (fn: (link: GraphLink) => number) => ForceSimulationLike
  strength?: (fnOrVal: number | ((link: GraphLink) => number)) => ForceSimulationLike
}

export function GraphCanvas({
  data,
  selectedNodeId = null,
  onSelectNode,
  hoveredNodeId = null,
  onHoverNode,
  graphInstanceRef,
  className = '',
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphObjRef = useRef<ForceGraph3DInstance | null>(null)
  const spritesRef = useRef<Map<string, THREE.Sprite>>(new Map())
  const dataRef = useRef<GraphData>(data)
  dataRef.current = data

  const onSelectNodeRef = useRef(onSelectNode)
  onSelectNodeRef.current = onSelectNode

  const onHoverNodeRef = useRef(onHoverNode)
  onHoverNodeRef.current = onHoverNode

  const selectedNodeIdRef = useRef(selectedNodeId)
  selectedNodeIdRef.current = selectedNodeId

  const hoveredNodeIdRef = useRef(hoveredNodeId)
  hoveredNodeIdRef.current = hoveredNodeId

  // Mount 3d-force-graph canvas
  useEffect(() => {
    if (!containerRef.current) return

    // Clear previous sprites
    spritesRef.current.clear()

    // Initialize 3d-force-graph
    const ForceGraphFactory = (ForceGraph3D as unknown as { default?: () => (elem: HTMLElement) => ForceGraph3DInstance }).default || (ForceGraph3D as unknown as () => (elem: HTMLElement) => ForceGraph3DInstance)
    const initFn = typeof ForceGraphFactory === 'function' ? ForceGraphFactory() : ForceGraphFactory
    const graph = (typeof initFn === 'function' ? initFn(containerRef.current) : initFn) as ForceGraph3DInstance

    graph
      .backgroundColor('#0B0F17')
      .showNavInfo(false)
      .nodeRelSize(4)
      .nodeVal((node) => ((node as GraphNode).type === 'bucket' ? 16 : 6))
      .linkWidth((link) => ((link as GraphLink).kind === 'bucket-doc' ? 1.5 : 0.8))
      .linkOpacity(0.4)
      .linkColor((link) => (link as GraphLink).color || 'rgba(100, 160, 255, 0.35)')
      .linkDirectionalParticles((link) => ((link as GraphLink).kind === 'bucket-doc' ? 2 : 0))
      .linkDirectionalParticleWidth(1.2)
      .linkDirectionalParticleSpeed(0.004)
      .linkDirectionalParticleColor((link) => (link as GraphLink).color || 'rgba(147, 197, 253, 0.8)')
      .nodeThreeObject((nodeObj) => {
        const node = nodeObj as GraphNode
        const group = new THREE.Group()
        const isBucket = node.type === 'bucket'
        const isSelected = selectedNodeIdRef.current === node.id
        const isHovered = hoveredNodeIdRef.current === node.id

        // Core Sphere
        const geometry = isBucket
          ? new THREE.SphereGeometry(node.size, 24, 24)
          : new THREE.SphereGeometry(node.size, 16, 16)

        const material = new THREE.MeshStandardMaterial({
          color: node.color,
          emissive: node.color,
          emissiveIntensity: isSelected ? 0.9 : isHovered ? 0.75 : isBucket ? 0.6 : 0.35,
          roughness: 0.3,
          metalness: 0.2,
        })
        const sphere = new THREE.Mesh(geometry, material)
        group.add(sphere)

        // Outer glow orbital ring for Bucket Hubs
        if (isBucket) {
          const ringGeom = new THREE.RingGeometry(node.size * 1.3, node.size * 1.45, 32)
          const ringMat = new THREE.MeshBasicMaterial({
            color: node.color,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.45,
          })
          const ring = new THREE.Mesh(ringGeom, ringMat)
          ring.rotation.x = Math.PI / 3
          group.add(ring)
        }

        // Selection halo ring if selected
        if (isSelected) {
          const selRingGeom = new THREE.RingGeometry(node.size * 1.5, node.size * 1.65, 32)
          const selRingMat = new THREE.MeshBasicMaterial({
            color: '#FFFFFF',
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.8,
          })
          const selRing = new THREE.Mesh(selRingGeom, selRingMat)
          group.add(selRing)
        }

        // Billboard text sprite
        const sprite = createNodeSprite(node)
        spritesRef.current.set(node.id, sprite)
        group.add(sprite)

        return group
      })
      .onNodeHover((node) => {
        if (containerRef.current) {
          containerRef.current.style.cursor = node ? 'grab' : 'default'
        }
        onHoverNodeRef.current?.((node as GraphNode) || null)
      })
      .onNodeClick((node) => {
        onSelectNodeRef.current?.((node as GraphNode) || null)
      })
      .onBackgroundClick(() => {
        onSelectNodeRef.current?.(null)
      })
      // Elastic cluster drag
      .onNodeDrag(() => {
        if (containerRef.current) {
          containerRef.current.style.cursor = 'grabbing'
        }
        // Keep physics simulation warm so connected cluster nodes follow organically
        const graphAny = graph as unknown as { d3AlphaTarget?: (a: number) => void; d3ReheatSimulation?: () => void }
        if (typeof graphAny.d3AlphaTarget === 'function') {
          graphAny.d3AlphaTarget(0.35)
          graphAny.d3ReheatSimulation?.()
        }
        const sim = graph.d3Force('simulation') as ForceSimulationLike | undefined
        if (sim && typeof sim.alphaTarget === 'function') {
          sim.alphaTarget(0.35)
          if (typeof sim.restart === 'function') sim.restart()
        }
      })
      .onNodeDragEnd((node) => {
        if (containerRef.current) {
          containerRef.current.style.cursor = 'grab'
        }
        const graphAny = graph as unknown as { d3AlphaTarget?: (a: number) => void }
        if (typeof graphAny.d3AlphaTarget === 'function') {
          graphAny.d3AlphaTarget(0)
        }
        const sim = graph.d3Force('simulation') as ForceSimulationLike | undefined
        if (sim && typeof sim.alphaTarget === 'function') {
          sim.alphaTarget(0)
        }
        // Clear fixed coordinates so node participates freely in physics
        if (node) {
          const gNode = node as GraphNode
          gNode.fx = undefined
          gNode.fy = undefined
          gNode.fz = undefined
        }
      })

    // Custom d3 forces for clustering
    const linkForce = graph.d3Force('link') as ForceSimulationLike | undefined
    if (linkForce && typeof linkForce.distance === 'function' && typeof linkForce.strength === 'function') {
      linkForce.distance((link: GraphLink) => (link.kind === 'bucket-doc' ? 45 : 100))
      linkForce.strength((link: GraphLink) => (link.kind === 'bucket-doc' ? 0.85 : 0.12))
    }

    const chargeForce = graph.d3Force('charge') as ForceSimulationLike | undefined
    if (chargeForce && typeof chargeForce.strength === 'function') {
      chargeForce.strength(-110)
    }

    // Set initial size
    if (containerRef.current) {
      graph.width(containerRef.current.clientWidth || window.innerWidth)
      graph.height(containerRef.current.clientHeight || window.innerHeight)
    }

    // Per-frame LOD update loop & Scene lighting
    const camera = graph.camera()
    const scene = graph.scene()

    if (scene) {
      scene.add(new THREE.AmbientLight(0xffffff, 0.7))
      const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
      dirLight.position.set(100, 200, 150)
      scene.add(dirLight)
    }

    // Load initial graph data
    graph.graphData({
      nodes: dataRef.current.nodes,
      links: dataRef.current.links,
    })

    const interval = setInterval(() => {
      if (!camera) return
      const camPos = camera.position
      if (!camPos) return

      dataRef.current.nodes.forEach((node) => {
        const sprite = spritesRef.current.get(node.id)
        if (sprite && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
          const dist = camPos.distanceTo(new THREE.Vector3(node.x, node.y, node.z))
          updateSpriteLOD(sprite, dist, node.type === 'bucket')
        }
      })
    }, 60)

    graphObjRef.current = graph
    if (graphInstanceRef) {
      (graphInstanceRef as React.MutableRefObject<ForceGraph3DInstance | null>).current = graph
    }

    const handleResize = () => {
      if (!containerRef.current || !graph) return
      graph.width(containerRef.current.clientWidth)
      graph.height(containerRef.current.clientHeight)
    }
    window.addEventListener('resize', handleResize)

    return () => {
      clearInterval(interval)
      window.removeEventListener('resize', handleResize)
      if (graph) {
        graph._destructor?.()
      }
      if (graphInstanceRef) {
        (graphInstanceRef as React.MutableRefObject<ForceGraph3DInstance | null>).current = null
      }
    }
  }, [graphInstanceRef])

  // Update graph data when data prop updates
  useEffect(() => {
    if (!graphObjRef.current) return
    graphObjRef.current.graphData({
      nodes: data.nodes,
      links: data.links,
    })
  }, [data])

  // Refresh node visual state on selection or hover change
  useEffect(() => {
    if (!graphObjRef.current) return
    graphObjRef.current.nodeThreeObject(graphObjRef.current.nodeThreeObject())
  }, [selectedNodeId, hoveredNodeId])

  return (
    <div
      ref={containerRef}
      className={`h-full w-full select-none overflow-hidden ${className}`}
      data-testid="graph-canvas-container"
    />
  )
}
