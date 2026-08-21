import { useState, useMemo } from 'react'
import { ChevronDown, ChevronUp, Layers, Info } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { BucketResponse } from '@/api/types'
import type { ColorMode, GraphData } from '../types/graph'
import { STATUS_COLORS, getBucketColor } from '../lib/palette'

export interface GraphLegendProps {
  colorMode: ColorMode
  buckets?: BucketResponse[]
  data?: GraphData
  className?: string
  defaultOpen?: boolean
  showTagLinks?: boolean
  onToggleTagLinks?: (v: boolean) => void
}

const STATUS_ITEMS = [
  { key: 'verified', label: 'Verified', color: STATUS_COLORS.verified },
  { key: 'uploaded', label: 'Uploaded', color: STATUS_COLORS.uploaded },
  { key: 'submitted', label: 'Submitted', color: STATUS_COLORS.submitted },
  { key: 'pending_approval', label: 'Pending Approval', color: STATUS_COLORS.pending_approval },
  { key: 'action_required', label: 'Action Required', color: STATUS_COLORS.action_required },
  { key: 'overdue', label: 'Overdue', color: STATUS_COLORS.overdue },
  { key: 'archived', label: 'Archived', color: STATUS_COLORS.archived },
]

export function GraphLegend({
  colorMode,
  buckets = [],
  data,
  className = '',
  defaultOpen = true,
  showTagLinks,
  onToggleTagLinks,
}: GraphLegendProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  // Derive unique buckets for the legend
  const bucketList = useMemo(() => {
    if (buckets && buckets.length > 0) {
      return buckets
    }
    const list: BucketResponse[] = []
    if (data?.bucketMap) {
      data.bucketMap.forEach((b) => list.push(b))
    }
    return list
  }, [buckets, data?.bucketMap])

  return (
    <div
      data-testid="graph-legend"
      className={cn(
        'fixed bottom-6 left-6 z-30 w-64 rounded-xl bg-bg-surface/85 backdrop-blur-md border border-border shadow-2xl text-text-primary text-xs overflow-hidden transition-all duration-200',
        className,
      )}
    >
      {/* Legend Header */}
      <div
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center justify-between px-3.5 py-2.5 bg-bg-surface/90 cursor-pointer select-none border-b border-border hover:bg-bg-raised/80 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-text-muted" />
          <span className="font-semibold text-text-primary">Legend</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-inset text-text-muted font-mono">
            {colorMode === 'bucket' ? 'By Bucket' : 'By Status'}
          </span>
        </div>

        <button
          type="button"
          data-testid="legend-toggle-btn"
          aria-label={isOpen ? 'Collapse legend' : 'Expand legend'}
          className="p-0.5 text-text-muted hover:text-text-primary transition-colors focus:outline-none"
        >
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </button>
      </div>

      {/* Legend Body */}
      {isOpen && (
        <div className="p-3 space-y-3 max-h-72 overflow-y-auto">
          {/* Node Types Section */}
          <div className="space-y-1.5 pb-2.5 border-b border-border">
            <div className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
              Node Types
            </div>
            <div className="grid grid-cols-1 gap-1 text-[11px]">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-sky-400 ring-2 ring-sky-400/30 flex-shrink-0" />
                <span className="text-text-secondary font-medium">Bucket Hub</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0 ml-0.5" />
                <span className="text-text-secondary">Document Node</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3.5 h-[1.5px] bg-slate-500 rounded flex-shrink-0" />
                <span className="text-text-muted">Shared Tag Connection</span>
              </div>
            </div>
            {onToggleTagLinks && (
              <label
                data-testid="legend-tag-links-toggle"
                className="flex items-center justify-between cursor-pointer select-none pt-1"
              >
                <span className="text-[11px] text-text-secondary">Shared-tag links</span>
                <input
                  type="checkbox"
                  checked={showTagLinks ?? true}
                  onChange={(e) => onToggleTagLinks(e.target.checked)}
                  className="accent-[var(--accent)] w-3.5 h-3.5"
                />
              </label>
            )}
          </div>

          {/* Color Mode Section */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-semibold text-text-muted uppercase tracking-wider flex items-center justify-between">
              <span>{colorMode === 'bucket' ? 'Bucket Colors' : 'Status Colors'}</span>
              <Info className="w-3 h-3 text-text-muted" />
            </div>

            {colorMode === 'bucket' ? (
              <div className="space-y-1 text-[11px]">
                {bucketList.length > 0 ? (
                  bucketList.map((b, idx) => {
                    const color = getBucketColor(b.id, idx)
                    return (
                      <div key={b.id} className="flex items-center gap-2">
                        <span
                          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: color }}
                        />
                        <span className="truncate text-text-secondary">{b.name}</span>
                      </div>
                    )
                  })
                ) : (
                  <div className="text-text-muted italic text-[11px]">No buckets available</div>
                )}
                <div className="flex items-center gap-2 pt-0.5">
                  <span className="w-2.5 h-2.5 rounded-full flex-shrink-0 bg-slate-400" />
                  <span className="truncate text-text-muted">Uncategorized</span>
                </div>
              </div>
            ) : (
              <div className="space-y-1 text-[11px]">
                {STATUS_ITEMS.map((item) => (
                  <div key={item.key} className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-text-secondary">{item.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
