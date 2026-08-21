import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Search,
  X,
  Filter,
  Check,
  ChevronDown,
  Layers,
  FileText,
  Folder,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import type { BucketResponse } from '@/api/types'
import type { ColorMode, GraphData, GraphNode } from '../types/graph'
import { getBucketColor } from '../lib/palette'

export interface GraphHudProps {
  data: GraphData
  buckets?: BucketResponse[]
  colorMode: ColorMode
  onColorModeChange: (mode: ColorMode) => void
  visibleBucketIds: Set<string>
  onToggleBucket: (bucketId: string) => void
  onShowAllBuckets: () => void
  onSelectNode: (node: GraphNode) => void
  searchQuery: string
  onSearchQueryChange: (q: string) => void
  className?: string
}

export function GraphHud({
  data,
  buckets = [],
  colorMode,
  onColorModeChange,
  visibleBucketIds,
  onToggleBucket,
  onShowAllBuckets,
  onSelectNode,
  searchQuery,
  onSearchQueryChange,
  className = '',
}: GraphHudProps) {
  const navigate = useNavigate()

  // Search popover state (query itself is lifted to the page)
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const searchContainerRef = useRef<HTMLDivElement>(null)

  // Filter dropdown state
  const [isFilterOpen, setIsFilterOpen] = useState(false)
  const filterContainerRef = useRef<HTMLDivElement>(null)

  // Outside click listener for search and filter popovers
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(event.target as Node)
      ) {
        setIsSearchOpen(false)
      }
      if (
        filterContainerRef.current &&
        !filterContainerRef.current.contains(event.target as Node)
      ) {
        setIsFilterOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Derive unique buckets for the filter menu
  const allBuckets = useMemo(() => {
    if (buckets && buckets.length > 0) {
      return buckets
    }
    // Fallback to data.bucketMap
    const list: BucketResponse[] = []
    if (data.bucketMap) {
      data.bucketMap.forEach((b) => list.push(b))
    }
    return list
  }, [buckets, data.bucketMap])

  // Real-time search filtering
  const searchResults = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return []

    return data.nodes.filter((node) => {
      if (node.name.toLowerCase().includes(q)) return true
      if (node.bucketName?.toLowerCase().includes(q)) return true
      if (node.tags?.some((t) => t.toLowerCase().includes(q))) return true
      return false
    }).slice(0, 10)
  }, [data.nodes, searchQuery])

  // Count active bucket filters
  const showAll = visibleBucketIds.has('all')
  const totalBucketCount = data.totalBuckets || allBuckets.length || 0
  const totalDocCount = data.totalDocuments || data.nodes.filter((n) => n.type === 'document').length

  const handleSelectSearchResult = (node: GraphNode) => {
    onSelectNode(node)
    setIsSearchOpen(false)
    onSearchQueryChange('')
  }

  return (
    <header
      className={cn(
        'absolute top-4 left-4 right-4 z-20 pointer-events-none flex flex-wrap items-center justify-between gap-3',
        className,
      )}
    >
      {/* Left section: Back button & Breadcrumb badge */}
      <div className="pointer-events-auto flex items-center gap-2.5">
        <button
          type="button"
          onClick={() => navigate('/app/docvault')}
          aria-label="Back to DocVault"
          data-testid="back-button"
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-bg-surface/85 backdrop-blur-md border border-border text-text-primary hover:bg-bg-raised/80 transition-colors shadow-lg text-xs font-medium focus:outline-none focus:ring-1 focus:ring-border-strong"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to DocVault</span>
        </button>

        <div
          data-testid="graph-breadcrumb-badge"
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-surface/85 backdrop-blur-md border border-border text-text-secondary text-xs font-medium shadow-lg"
        >
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span>
            DocVault 3D Graph &middot; {totalBucketCount} Buckets &middot; {totalDocCount} Docs
          </span>
        </div>
      </div>

      {/* Center section: Real-time Autocomplete Search */}
      <div
        ref={searchContainerRef}
        className="pointer-events-auto relative flex-1 max-w-md min-w-[240px]"
      >
        <div className="relative flex items-center">
          <Search className="absolute left-3 w-4 h-4 text-text-muted pointer-events-none" />
          <input
            type="text"
            data-testid="graph-search-input"
            value={searchQuery}
            onChange={(e) => {
              onSearchQueryChange(e.target.value)
              setIsSearchOpen(true)
            }}
            onFocus={() => {
              if (searchQuery.trim()) setIsSearchOpen(true)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && searchResults.length > 0) {
                handleSelectSearchResult(searchResults[0])
              }
              if (e.key === 'Escape') {
                onSearchQueryChange('')
                setIsSearchOpen(false)
              }
            }}
            placeholder="Search documents, buckets, tags..."
            className="w-full pl-9 pr-8 py-2 rounded-lg bg-bg-surface/85 backdrop-blur-md border border-border text-text-primary placeholder-text-muted text-xs focus:outline-none focus:ring-2 focus:ring-accent-ring focus:border-accent transition-all shadow-lg"
          />
          {searchQuery && (
            <button
              type="button"
              data-testid="search-clear-btn"
              onClick={() => {
                onSearchQueryChange('')
                setIsSearchOpen(false)
              }}
              aria-label="Clear search"
              className="absolute right-2.5 p-0.5 text-text-muted hover:text-text-primary focus:outline-none"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Autocomplete Dropdown */}
        {isSearchOpen && searchQuery.trim().length > 0 && (
          <div
            data-testid="search-results-dropdown"
            className="absolute left-0 right-0 top-full mt-1.5 max-h-72 overflow-y-auto rounded-lg bg-bg-surface/95 backdrop-blur-md border border-border shadow-2xl p-1 text-text-primary text-xs z-30"
          >
            {searchResults.length === 0 ? (
              <div
                data-testid="search-no-results"
                className="px-3 py-3 text-center text-text-muted"
              >
                No matching documents or buckets found
              </div>
            ) : (
              searchResults.map((node) => {
                const isBucket = node.type === 'bucket'
                return (
                  <button
                    key={node.id}
                    type="button"
                    data-testid="search-result-item"
                    onClick={() => handleSelectSearchResult(node)}
                    className="w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-md hover:bg-bg-raised/80 text-left transition-colors group"
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: node.color }}
                      />
                      {isBucket ? (
                        <Folder className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
                      ) : (
                        <FileText className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
                      )}
                      <span className="truncate font-medium text-text-primary group-hover:text-text-primary">
                        {node.name}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {node.tags && node.tags.length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-inset text-text-muted border border-border">
                          {node.tags[0]}
                          {node.tags.length > 1 ? ` +${node.tags.length - 1}` : ''}
                        </span>
                      )}
                      <span
                        className={cn(
                          'text-[10px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider',
                          isBucket
                            ? 'bg-bg-inset text-text-secondary border border-border'
                            : 'bg-accent-subtle text-accent border border-accent/30',
                        )}
                      >
                        {isBucket ? 'Bucket' : 'Doc'}
                      </span>
                    </div>
                  </button>
                )
              })
            )}
          </div>
        )}
      </div>

      {/* Right section: Color mode selector & Bucket filter dropdown */}
      <div className="pointer-events-auto flex items-center gap-2">
        {/* Color Mode Selector */}
        <div
          role="group"
          aria-label="Color Mode"
          className="flex items-center p-1 rounded-lg bg-bg-surface/85 backdrop-blur-md border border-border shadow-lg text-xs"
        >
          <button
            type="button"
            data-testid="color-mode-bucket"
            onClick={() => onColorModeChange('bucket')}
            className={cn(
              'px-2.5 py-1 rounded-md transition-all font-medium',
              colorMode === 'bucket'
                ? 'bg-accent text-accent-contrast shadow-sm'
                : 'text-text-muted hover:text-text-primary',
            )}
          >
            By Bucket
          </button>
          <button
            type="button"
            data-testid="color-mode-status"
            onClick={() => onColorModeChange('status')}
            className={cn(
              'px-2.5 py-1 rounded-md transition-all font-medium',
              colorMode === 'status'
                ? 'bg-accent text-accent-contrast shadow-sm'
                : 'text-text-muted hover:text-text-primary',
            )}
          >
            By Status
          </button>
        </div>

        {/* Bucket Filter Dropdown */}
        <div ref={filterContainerRef} className="relative">
          <button
            type="button"
            data-testid="bucket-filter-button"
            onClick={() => setIsFilterOpen((prev) => !prev)}
            aria-expanded={isFilterOpen}
            aria-label="Filter Buckets"
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 rounded-lg bg-bg-surface/85 backdrop-blur-md border text-text-primary transition-colors shadow-lg text-xs font-medium focus:outline-none focus:ring-1 focus:ring-border-strong',
              !showAll && visibleBucketIds.size > 0
                ? 'border-accent/50 text-accent'
                : 'border-border',
            )}
          >
            <Filter className="w-3.5 h-3.5" />
            <span>Buckets</span>
            {!showAll && (
              <span className="ml-0.5 px-1.5 py-0.2 rounded-full bg-accent-subtle text-accent text-[10px] font-mono">
                {visibleBucketIds.size}
              </span>
            )}
            <ChevronDown className="w-3.5 h-3.5 ml-0.5" />
          </button>

          {isFilterOpen && (
            <div
              data-testid="bucket-filter-dropdown"
              className="absolute right-0 top-full mt-1.5 w-60 max-h-80 overflow-y-auto rounded-lg bg-bg-surface/95 backdrop-blur-md border border-border shadow-2xl p-2 text-text-primary text-xs z-30 flex flex-col gap-1"
            >
              <div className="flex items-center justify-between px-2 py-1 border-b border-border pb-1.5 mb-1">
                <span className="font-semibold text-text-secondary flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  Filter Buckets
                </span>
                <button
                  type="button"
                  data-testid="show-all-buckets-btn"
                  onClick={() => {
                    onShowAllBuckets()
                    setIsFilterOpen(false)
                  }}
                  className="text-[11px] text-accent hover:text-accent-hover font-medium transition-colors"
                >
                  Show All
                </button>
              </div>

              {allBuckets.map((bucket, idx) => {
                const isChecked = showAll || visibleBucketIds.has(bucket.id)
                const color = getBucketColor(bucket.id, idx)
                return (
                  <label
                    key={bucket.id}
                    className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-bg-raised/80 cursor-pointer select-none transition-colors"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <input
                        type="checkbox"
                        data-testid={`bucket-checkbox-${bucket.id}`}
                        checked={isChecked}
                        onChange={() => onToggleBucket(bucket.id)}
                        className="sr-only"
                      />
                      <div
                        className={cn(
                          'w-4 h-4 rounded border flex items-center justify-center transition-colors',
                          isChecked
                            ? 'bg-accent border-accent text-accent-contrast'
                            : 'border-border bg-bg-inset',
                        )}
                      >
                        {isChecked && <Check className="w-3 h-3 stroke-[3]" />}
                      </div>
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: color }}
                      />
                      <span className="truncate text-text-primary font-medium">
                        {bucket.name}
                      </span>
                    </div>
                  </label>
                )
              })}

              {/* Option for Uncategorized documents if any */}
              <label className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-bg-raised/80 cursor-pointer select-none transition-colors border-t border-border mt-1 pt-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  <input
                    type="checkbox"
                    data-testid="bucket-checkbox-uncategorized"
                    checked={showAll || visibleBucketIds.has('uncategorized')}
                    onChange={() => onToggleBucket('uncategorized')}
                    className="sr-only"
                  />
                  <div
                    className={cn(
                      'w-4 h-4 rounded border flex items-center justify-center transition-colors',
                      showAll || visibleBucketIds.has('uncategorized')
                        ? 'bg-accent border-accent text-accent-contrast'
                        : 'border-border bg-bg-inset',
                    )}
                  >
                    {(showAll || visibleBucketIds.has('uncategorized')) && (
                      <Check className="w-3 h-3 stroke-[3]" />
                    )}
                  </div>
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0 bg-text-muted"
                  />
                  <span className="truncate text-text-secondary font-medium">
                    Uncategorized
                  </span>
                </div>
              </label>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
