import { X, Lock, Users, Folder, Calendar, Layers } from 'lucide-react'
import { cn } from '@/lib/cn'
import { formatDate } from '@/lib/format'
import type { BucketResponse } from '@/api/types'
import type { GraphNode } from '../types/graph'

export interface BucketSummaryCardProps {
  node: GraphNode | null
  bucket?: BucketResponse | null
  documentCount?: number
  onClose: () => void
  onFocusCluster?: (node: GraphNode) => void
  className?: string
}

export function BucketSummaryCard({
  node,
  bucket,
  documentCount,
  onClose,
  onFocusCluster,
  className = '',
}: BucketSummaryCardProps) {
  if (!node || node.type !== 'bucket') {
    return null
  }

  const rawBucket = bucket ?? node.rawBucket
  const bucketName = rawBucket?.name || node.name || 'Bucket Hub'
  const visibility = rawBucket?.visibility ?? 'everyone'
  const isRestricted = visibility === 'restricted'
  const createdAt = rawBucket?.created_at

  return (
    <div
      data-testid="bucket-summary-card"
      className={cn(
        'fixed top-20 right-6 z-30 w-80 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-700/70 p-4 text-slate-100 shadow-2xl animate-in fade-in slide-in-from-top-2 duration-200',
        className,
      )}
    >
      {/* Header with Title and Close Button */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="w-3.5 h-3.5 rounded-full flex-shrink-0 shadow-sm"
            style={{ backgroundColor: node.color }}
          />
          <div className="min-w-0">
            <h3
              data-testid="bucket-summary-title"
              className="text-sm font-semibold text-white truncate"
              title={bucketName}
            >
              {bucketName}
            </h3>
            <span
              data-testid="bucket-cluster-badge"
              className="inline-flex items-center gap-1 text-[11px] text-slate-400"
            >
              <Layers className="w-3 h-3 text-slate-400" />
              <span>Bucket Hub</span>
              {documentCount !== undefined && (
                <>
                  <span className="text-slate-500">&middot;</span>
                  <span className="text-slate-300">
                    {documentCount} {documentCount === 1 ? 'doc' : 'docs'}
                  </span>
                </>
              )}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          data-testid="bucket-summary-close"
          className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors focus:outline-none focus:ring-1 focus:ring-slate-500"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Metadata Badges & Details */}
      <div className="space-y-2 pt-2 border-t border-slate-800 text-xs">
        {/* Visibility */}
        <div className="flex items-center justify-between">
          <span className="text-slate-400">Visibility:</span>
          <span
            data-testid="bucket-visibility-badge"
            className={cn(
              'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium',
              isRestricted
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
            )}
          >
            {isRestricted ? (
              <>
                <Lock className="w-3 h-3" />
                <span>Restricted</span>
              </>
            ) : (
              <>
                <Users className="w-3 h-3" />
                <span>Everyone</span>
              </>
            )}
          </span>
        </div>

        {/* Created Date */}
        {createdAt && (
          <div className="flex items-center justify-between">
            <span className="text-slate-400 flex items-center gap-1">
              <Calendar className="w-3 h-3 text-slate-500" />
              Created:
            </span>
            <span data-testid="bucket-created-date" className="text-slate-200 font-mono text-[11px]">
              {formatDate(createdAt)}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      {onFocusCluster && (
        <div className="mt-4 pt-3 border-t border-slate-800/80">
          <button
            type="button"
            data-testid="focus-cluster-btn"
            onClick={() => onFocusCluster(node)}
            className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-emerald-600/80 hover:bg-emerald-600 text-white font-medium text-xs transition-colors shadow-md focus:outline-none focus:ring-1 focus:ring-emerald-400"
          >
            <Folder className="w-3.5 h-3.5" />
            <span>Focus Cluster</span>
          </button>
        </div>
      )}
    </div>
  )
}
