import { useState, useRef, useEffect } from 'react'
import type { ForceGraph3DInstance } from '3d-force-graph'
import { X } from 'lucide-react'
import { useBuckets, useDocuments } from '@/api/hooks/docvault'
import { useTheme } from '@/lib/useTheme'
import type { ColorMode, GraphNode } from './types/graph'
import { useGraphData } from './hooks/useGraphData'
import { useGraphControls } from './hooks/useGraphControls'
import { GraphCanvas } from './components/GraphCanvas'
import { GraphHud } from './components/GraphHud'
import { GraphNavigationControls } from './components/GraphNavigationControls'
import { BucketSummaryCard } from './components/BucketSummaryCard'
import { GraphLegend } from './components/GraphLegend'
import { GraphDocumentInspector } from './components/GraphDocumentInspector'

export function DocVaultGraphPage() {
  const { data: buckets = [] } = useBuckets()
  const { data: documents = [] } = useDocuments()

  const [colorMode, setColorMode] = useState<ColorMode>('bucket')
  const [visibleBucketIds, setVisibleBucketIds] = useState<Set<string>>(new Set(['all']))
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const { theme } = useTheme()
  const [searchQuery, setSearchQuery] = useState('')
  const [isolatedClusterId, setIsolatedClusterId] = useState<string | null>(null)
  const [showTagLinks, setShowTagLinks] = useState(true)

  const graphInstanceRef = useRef<ForceGraph3DInstance | null>(null)
  const graphData = useGraphData(buckets, documents, colorMode, visibleBucketIds, showTagLinks)
  const graphControls = useGraphControls(graphInstanceRef)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedNode(null)
        setIsolatedClusterId(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const handleIsolateCluster = (bucketRawId: string) => {
    setIsolatedClusterId((prev) => (prev === bucketRawId ? null : bucketRawId))
  }

  const handleToggleBucket = (bucketId: string) => {
    setVisibleBucketIds((prev) => {
      const next = new Set(prev)
      if (next.has('all')) {
        next.clear()
        buckets.forEach((b) => {
          if (b.id !== bucketId) {
            next.add(b.id)
          }
        })
        if (bucketId !== 'uncategorized') {
          next.add('uncategorized')
        }
      } else {
        if (next.has(bucketId)) {
          next.delete(bucketId)
        } else {
          next.add(bucketId)
        }
      }
      return next
    })
  }

  const handleShowAllBuckets = () => {
    setVisibleBucketIds(new Set(['all']))
  }

  const handleSelectNode = (node: GraphNode | null) => {
    setSelectedNode(node)
    if (node) {
      graphControls.flyToNode(node)
    }
  }

  const selectedDoc =
    selectedNode && selectedNode.type === 'document'
      ? documents.find((d) => d.id === selectedNode.rawId) ?? selectedNode.rawDoc ?? null
      : null

  const selectedBucket =
    selectedNode && selectedNode.type === 'bucket'
      ? buckets.find((b) => b.id === selectedNode.rawId) ?? selectedNode.rawBucket ?? null
      : null

  const bucketDocCount =
    selectedNode?.type === 'bucket'
      ? documents.filter(
          (d) =>
            (selectedNode.rawId === 'uncategorized'
              ? !d.bucket_id
              : d.bucket_id === selectedNode.rawId) && d.status !== 'archived',
        ).length
      : undefined

  return (
    <div
      data-testid="docvault-graph-page"
      className="fixed inset-0 z-40 bg-[#0B0F17] flex flex-col w-screen h-screen overflow-hidden"
    >
      <GraphHud
        data={graphData}
        buckets={buckets}
        colorMode={colorMode}
        onColorModeChange={setColorMode}
        visibleBucketIds={visibleBucketIds}
        onToggleBucket={handleToggleBucket}
        onShowAllBuckets={handleShowAllBuckets}
        onSelectNode={handleSelectNode}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
      />

      <GraphCanvas
        data={graphData}
        selectedNodeId={selectedNode?.id ?? null}
        onSelectNode={handleSelectNode}
        hoveredNodeId={hoveredNode?.id ?? null}
        onHoverNode={setHoveredNode}
        graphInstanceRef={graphInstanceRef}
        className="w-full h-full"
        theme={theme}
        searchQuery={searchQuery}
        isolatedClusterId={isolatedClusterId}
        onIsolateCluster={handleIsolateCluster}
      />

      {isolatedClusterId && (
        <div
          data-testid="isolation-pill"
          className="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 rounded-full bg-bg-surface/90 backdrop-blur-md border border-border px-3 py-1.5 text-xs text-text-primary shadow-lg"
        >
          <span>
            Isolated:{' '}
            {buckets.find((b) => b.id === isolatedClusterId)?.name ??
              (isolatedClusterId === 'uncategorized' ? 'Uncategorized' : isolatedClusterId)}
          </span>
          <button
            type="button"
            data-testid="isolation-exit-btn"
            onClick={() => setIsolatedClusterId(null)}
            aria-label="Exit isolation"
            className="text-text-muted hover:text-text-primary"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <GraphNavigationControls controls={graphControls} />

      <BucketSummaryCard
        node={selectedNode}
        bucket={selectedBucket}
        documentCount={bucketDocCount}
        onClose={() => setSelectedNode(null)}
        onFocusCluster={(n) => graphControls.flyToNode(n)}
        onIsolate={() => setIsolatedClusterId(selectedNode!.rawId)}
        isIsolated={isolatedClusterId === selectedNode?.rawId}
      />

      <GraphLegend
        colorMode={colorMode}
        buckets={buckets}
        data={graphData}
        showTagLinks={showTagLinks}
        onToggleTagLinks={setShowTagLinks}
      />

      <GraphDocumentInspector
        document={selectedDoc}
        open={!!selectedDoc && selectedNode?.type === 'document'}
        onClose={() => setSelectedNode(null)}
        buckets={buckets}
      />
    </div>
  )
}

export default DocVaultGraphPage
