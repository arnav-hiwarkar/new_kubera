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
  onIsolate?: () => void
  isIsolated?: boolean
  className?: string
}

export function BucketSummaryCard({
  node,
  bucket,
  documentCount,
  onClose,
  onFocusCluster,
  onIsolate,
  isIsolated = false,
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
        'fixed top-20 right-6 z-30 w-80 rounded-xl bg-bg-surface/90 backdrop-blur-md border border-border p-4 text-text-primary shadow-2xl animate-in fade-in slide-in-from-top-2 duration-200',
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
              className="text-sm font-semibold text-text-primary truncate"
              title={bucketName}
            >
              {bucketName}
            </h3>
            <span
              data-testid="bucket-cluster-badge"
              className="inline-flex items-center gap-1 text-[11px] text-text-muted"
            >
              <Layers className="w-3 h-3 text-text-muted" />
              <span>Bucket Hub</span>
              {documentCount !== undefined && (
                <>
                  <span className="text-text-muted">&middot;</span>
                  <span className="text-text-secondary">
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
          className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-raised transition-colors focus:outline-none focus:ring-1 focus:ring-border-strong"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Metadata Badges & Details */}
      <div className="space-y-2 pt-2 border-t border-border text-xs">
        {/* Visibility */}
        <div className="flex items-center justify-between">
          <span className="text-text-muted">Visibility:</span>
          <span
            data-testid="bucket-visibility-badge"
            className={cn(
              'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium',
              isRestricted
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'bg-accent-subtle text-accent border border-accent/30',
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
            <span className="text-text-muted flex items-center gap-1">
              <Calendar className="w-3 h-3 text-text-muted" />
              Created:
            </span>
            <span data-testid="bucket-created-date" className="text-text-primary font-mono text-[11px]">
              {formatDate(createdAt)}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="mt-4 pt-3 border-t border-border flex flex-col gap-2">
        {onFocusCluster && (
          <button
            type="button"
            data-testid="focus-cluster-btn"
            onClick={() => onFocusCluster(node)}
            className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-accent hover:bg-accent-hover text-accent-contrast font-medium text-xs transition-colors shadow-md focus:outline-none focus:ring-1 focus:ring-accent-ring"
          >
            <Folder className="w-3.5 h-3.5" />
            <span>Focus Cluster</span>
          </button>
        )}
        {onIsolate && (
          <button
            type="button"
            data-testid="isolate-cluster-btn"
            onClick={onIsolate}
            className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg border border-border bg-bg-raised hover:bg-bg-inset text-text-primary font-medium text-xs transition-colors focus:outline-none focus:ring-1 focus:ring-accent-ring"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>{isIsolated ? 'Show all clusters' : 'Isolate cluster'}</span>
          </button>
        )}
      </div>
    </div>
  )
}
