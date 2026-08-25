import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import type { GraphData, GraphLink, GraphNode } from '../types/graph'
import { createNodeSprite } from '../lib/textSprite'
import { getGraphTheme, type GraphThemeMode } from '../lib/theme'
import { buildNeighborSet, dimOpacity, resolveDimState } from '../lib/dimState'
import { DynamicFogController, LABEL_FADE_START, LABEL_FADE_END } from '../lib/dynamicFog'

export interface GraphCanvasProps {
  data: GraphData
  selectedNodeId?: string | null
  onSelectNode?: (node: GraphNode | null) => void
  hoveredNodeId?: string | null
  onHoverNode?: (node: GraphNode | null) => void
  graphInstanceRef?: React.MutableRefObject<ForceGraph3DInstance | null> | React.RefObject<ForceGraph3DInstance | null> | { current: ForceGraph3DInstance | null }
  className?: string
  theme?: GraphThemeMode
  searchQuery?: string
  isolatedClusterId?: string | null
  onIsolateCluster?: (bucketRawId: string) => void
}

interface ForceSimulationLike {
  alphaTarget?: (alpha: number) => ForceSimulationLike
  restart?: () => ForceSimulationLike
  distance?: (fn: (link: GraphLink) => number) => ForceSimulationLike
  strength?: (fnOrVal: number | ((link: GraphLink) => number)) => ForceSimulationLike
}

const PULSE_STATUSES = new Set(['action_required', 'overdue'])

function sameCluster(docA: string, docB: string, nodes: GraphNode[]): boolean {
  const m = new Map(nodes.map((n) => [n.id, n]))
  const a = m.get(docA)
  const b = m.get(docB)
  return (a?.bucketId ?? 'uncategorized') === (b?.bucketId ?? 'uncategorized')
}

export function GraphCanvas({
  data,
  selectedNodeId = null,
  onSelectNode,
  hoveredNodeId = null,
  onHoverNode,
  graphInstanceRef,
  className = '',
  theme = 'dark',
  searchQuery = '',
  isolatedClusterId = null,
  onIsolateCluster,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphObjRef = useRef<ForceGraph3DInstance | null>(null)
  const spritesRef = useRef<Map<string, THREE.Sprite>>(new Map())
  const fogControllerRef = useRef<DynamicFogController | null>(null)
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

  const themeRef = useRef(theme)
  themeRef.current = theme

  const searchQueryRef = useRef(searchQuery)
  searchQueryRef.current = searchQuery

  const isolatedClusterIdRef = useRef(isolatedClusterId)
  isolatedClusterIdRef.current = isolatedClusterId

  const onIsolateClusterRef = useRef(onIsolateCluster)
  onIsolateClusterRef.current = onIsolateCluster

  const lastClickRef = useRef<{ id: string; time: number }>({ id: '', time: 0 })

  const visualRegistryRef = useRef<Map<string, {
    group: THREE.Group
    sphereMat: THREE.MeshStandardMaterial
    baseEmissive: number
    baseScale: number
    sprite: THREE.Sprite
  }>>(new Map())

  // Mount 3d-force-graph canvas
  useEffect(() => {
    if (!containerRef.current) return

    // Clear previous sprites
    spritesRef.current.clear()
    visualRegistryRef.current.clear()

    const themeObj = getGraphTheme(themeRef.current)

    // Initialize 3d-force-graph
    const ForceGraphFactory = (ForceGraph3D as unknown as { default?: () => (elem: HTMLElement) => ForceGraph3DInstance }).default || (ForceGraph3D as unknown as () => (elem: HTMLElement) => ForceGraph3DInstance)
    const initFn = typeof ForceGraphFactory === 'function' ? ForceGraphFactory() : ForceGraphFactory
    const graph = (typeof initFn === 'function' ? initFn(containerRef.current) : initFn) as ForceGraph3DInstance

    graph
      .backgroundColor(themeObj.background)
      .showNavInfo(false)
      .nodeRelSize(4)
      .nodeVal((node) => ((node as GraphNode).type === 'bucket' ? 16 : 6))
      .linkWidth((link) => ((link as GraphLink).kind === 'bucket-doc' ? 1.5 : 0.8))
      .linkOpacity(0.4)
      .linkColor((link) => {
        const t = getGraphTheme(themeRef.current)
        return (link as GraphLink).kind === 'bucket-doc' ? t.linkBucketDoc : t.linkTag
      })
      .linkDirectionalParticles((link) => ((link as GraphLink).kind === 'bucket-doc' ? 2 : 0))
      .linkDirectionalParticleWidth(1.2)
      .linkDirectionalParticleSpeed(0.004)
      .linkDirectionalParticleColor(() => getGraphTheme(themeRef.current).particle)
      .linkCurvature((link) => ((link as GraphLink).kind === 'tag-shared' ? 0.25 : 0))
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
          emissiveIntensity: (isSelected ? 0.9 : isHovered ? 0.75 : isBucket ? 0.6 : 0.35) * getGraphTheme(themeRef.current).emissiveMultiplier,
          roughness: 0.3,
          metalness: 0.2,
        })
        const sphere = new THREE.Mesh(geometry, material)
        group.add(sphere)

        // Outer glow orbital ring for Bucket Hubs
        if (isBucket) {
          const ringGeom = new THREE.RingGeometry(node.size * 1.3, node.size * 1.45, 32)
          const ringMat = new THREE.MeshBasicMaterial({
            color: getGraphTheme(themeRef.current).bucketRing,
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
            color: getGraphTheme(themeRef.current).selectionRing,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.8,
          })
          const selRing = new THREE.Mesh(selRingGeom, selRingMat)
          group.add(selRing)
        }

        // Billboard text sprite
        const sprite = createNodeSprite(node, getGraphTheme(themeRef.current))
        sprite.position.set(0, node.size + (isBucket ? 6 : 4), 0)
        spritesRef.current.set(node.id, sprite)
        group.add(sprite)

        visualRegistryRef.current.set(node.id, {
          group,
          sphereMat: material,
          baseEmissive: material.emissiveIntensity,
          baseScale: 1,
          sprite,
        })

        return group
      })
      .onNodeHover((node) => {
        if (containerRef.current) {
          containerRef.current.style.cursor = node ? 'grab' : 'default'
        }
        onHoverNodeRef.current?.((node as GraphNode) || null)
      })
      .onNodeClick((node) => {
        const now = Date.now()
        const n = node as GraphNode
        if (lastClickRef.current.id === n.id && now - lastClickRef.current.time < 350) {
          lastClickRef.current = { id: '', time: 0 }
          if (n.type === 'bucket') onIsolateClusterRef.current?.(n.rawId)
          onSelectNodeRef.current?.(n)
          return
        }
        lastClickRef.current = { id: n.id, time: now }
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

    // Per-frame unified render loop & Scene lighting
    const scene = graph.scene()

    if (scene) {
      scene.add(new THREE.AmbientLight(0xffffff, themeObj.ambientIntensity))
      const dirLight = new THREE.DirectionalLight(0xffffff, themeObj.directionalIntensity)
      dirLight.position.set(100, 200, 150)
      scene.add(dirLight)
      scene.fog = new THREE.Fog(themeObj.background, themeObj.fogNear, themeObj.fogFar)
    }
    fogControllerRef.current = new DynamicFogController()

    // Bloom in dark mode only — degrade silently on failure
    if (themeRef.current === 'dark') {
      try {
        const composer = graph.postProcessingComposer()
        const width = containerRef.current?.clientWidth || window.innerWidth
        const height = containerRef.current?.clientHeight || window.innerHeight
        composer.addPass(new UnrealBloomPass(new THREE.Vector2(width, height), 0.35, 0.6, 0.55))
      } catch {
        // no bloom
      }
    }

    // Load initial graph data
    graph.graphData({
      nodes: dataRef.current.nodes,
      links: dataRef.current.links,
    })

    const applyFrame = () => {
      const cam = graph.camera()
      if (!cam) return
      const t = getGraphTheme(themeRef.current)
      const fog = scene ? (scene.fog as THREE.Fog | null) : null
      const labelScale =
        fog && fogControllerRef.current
          ? fogControllerRef.current.update(fog, cam.position, dataRef.current.nodes, t)
          : 1
      const labelFadeStart = LABEL_FADE_START * labelScale
      const labelFadeEnd = LABEL_FADE_END * labelScale
      const now = performance.now() / 1000
      const pulse = Math.sin((now * Math.PI * 2) / 1.4) // ~1.4s cycle

      const input = {
        query: searchQueryRef.current,
        hoveredNodeId: hoveredNodeIdRef.current,
        selectedNodeId: selectedNodeIdRef.current,
        isolatedClusterId: isolatedClusterIdRef.current,
      }
      const focusId = input.hoveredNodeId ?? input.selectedNodeId
      const neighbors = buildNeighborSet(dataRef.current.links, focusId)
      const isolatedActive = !!input.isolatedClusterId || !!input.query.trim()

      dataRef.current.nodes.forEach((node) => {
        const vis = visualRegistryRef.current.get(node.id)
        if (!vis) return

        // Dim / spotlight
        const state = resolveDimState(node, neighbors, input)
        const opacity = dimOpacity(state, isolatedActive)
        vis.group.traverse((obj) => {
          const mesh = obj as THREE.Mesh
          if (mesh.material && 'opacity' in mesh.material) {
            const mat = mesh.material as THREE.Material
            mat.transparent = true
            mat.opacity = opacity
          }
        })

        // Status pulse (only when not dimmed)
        const shouldPulse = node.type === 'document' && !!node.status && PULSE_STATUSES.has(node.status)
        if (shouldPulse && opacity === 1) {
          const s = 1 + 0.1 * pulse
          vis.group.scale.setScalar(s)
          vis.sphereMat.emissiveIntensity = vis.baseEmissive * (1 + 0.5 * pulse)
        } else {
          vis.group.scale.setScalar(1)
          vis.sphereMat.emissiveIntensity =
            vis.baseEmissive * t.emissiveMultiplier * (state === 'highlight' ? 1.25 : 1)
        }

        // Label LOD (existing behavior) × dim factor
        const sprite = vis.sprite
        if (sprite && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
          const dist = cam.position.distanceTo(new THREE.Vector3(node.x, node.y, node.z))
          const isBucket = node.type === 'bucket'
          let lodOpacity = 1
          if (!isBucket) {
            if (dist >= labelFadeEnd) lodOpacity = 0
            else if (dist > labelFadeStart)
              lodOpacity = (labelFadeEnd - dist) / (labelFadeEnd - labelFadeStart)
          }
          sprite.material.opacity = opacity * Math.max(0, Math.min(1, lodOpacity))
          sprite.visible = sprite.material.opacity > 0.001
        }
      })
    }

    // Prefer the library's frame hook; fall back to an interval.
    let intervalId: ReturnType<typeof setInterval> | undefined
    const g = graph as unknown as { onRenderFramePre?: (cb: () => void) => unknown }
    if (typeof g.onRenderFramePre === 'function') {
      g.onRenderFramePre(applyFrame)
    } else {
      intervalId = setInterval(applyFrame, 60)
    }

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
      if (intervalId !== undefined) clearInterval(intervalId)
      window.removeEventListener('resize', handleResize)
      fogControllerRef.current = null
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

  // Re-apply theme when the theme prop changes
  useEffect(() => {
    const graph = graphObjRef.current
    if (!graph) return
    const t = getGraphTheme(theme)
    graph.backgroundColor(t.background)
    const scene = graph.scene()
    if (scene) {
      const prevFog = scene.fog as THREE.Fog | null
      const nextFog = new THREE.Fog(t.background, t.fogNear, t.fogFar)
      if (prevFog) {
        nextFog.near = prevFog.near
        nextFog.far = prevFog.far
      }
      scene.fog = nextFog
      scene.traverse((obj) => {
        if ((obj as THREE.AmbientLight).isAmbientLight) (obj as THREE.AmbientLight).intensity = t.ambientIntensity
        if ((obj as THREE.DirectionalLight).isDirectionalLight) (obj as THREE.DirectionalLight).intensity = t.directionalIntensity
      })
    }
    // rebuild node objects so sprites/materials pick up new colors
    graph.nodeThreeObject(graph.nodeThreeObject())
  }, [theme])

  // Link dimming during focus
  useEffect(() => {
    const graph = graphObjRef.current
    if (!graph) return
    const anyG = graph as unknown as { linkVisibility?: unknown }
    if (typeof anyG.linkVisibility !== 'function') return
    const focusId = hoveredNodeId ?? selectedNodeId
    const neighbors = buildNeighborSet(dataRef.current.links, focusId)
    const active = !!(searchQuery.trim() || isolatedClusterId || focusId)
    if (!active) {
      graph.linkVisibility(() => true)
      return
    }
    graph.linkVisibility((link) => {
      const l = link as GraphLink
      const s = typeof l.source === 'string' ? l.source : l.source.id
      const t = typeof l.target === 'string' ? l.target : l.target.id
      if (isolatedClusterId) {
        return s === `bucket_${isolatedClusterId}` || t === `bucket_${isolatedClusterId}` ||
          (s.startsWith('doc_') && t.startsWith('doc_') &&
            sameCluster(s, t, dataRef.current.nodes))
      }
      return neighbors.has(s) || neighbors.has(t) || s === focusId || t === focusId
    })
  }, [hoveredNodeId, selectedNodeId, searchQuery, isolatedClusterId])

  return (
    <div
      ref={containerRef}
      className={`h-full w-full select-none overflow-hidden ${className}`}
      data-testid="graph-canvas-container"
    />
  )
}
