import React, { useState, useMemo, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Search,
  Folder,
  FolderOpen,
  FileText,
  Check,
  Layers,
  HardDrive,
  Lock,
  X,
  Tag,
  CheckSquare,
  Square,
  Sparkles,
} from 'lucide-react'
import { Button, Modal, Input } from '@/components/ui'
import { useBuckets, useDocuments } from '@/api/hooks/docvault'
import { formatFileSize } from '@/components/auditease/requirements/progress'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/cn'

interface DocVaultPickerModalProps {
  open: boolean
  onClose: () => void
  selectedDocIds: string[]
  onConfirm: (selectedIds: string[]) => void
  multiple?: boolean
  title?: string
  confirmLabel?: string
}

export const DocVaultPickerModal: React.FC<DocVaultPickerModalProps> = ({
  open,
  onClose,
  selectedDocIds: initialSelected,
  onConfirm,
  multiple = true,
  title = 'Select Documents from DocVault',
  confirmLabel = 'Attach Selected',
}) => {
  const { data: buckets = [], isLoading: loadingBuckets } = useBuckets()
  const { data: documents = [], isLoading: loadingDocs } = useDocuments()

  const [search, setSearch] = useState('')
  const [selectedBucketId, setSelectedBucketId] = useState<string | 'all' | 'uncategorized'>('all')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [viewOnlySelected, setViewOnlySelected] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>(initialSelected)

  // Sync initialSelected when modal opens
  useEffect(() => {
    if (open) {
      setSelectedIds(initialSelected)
      setSearch('')
      setSelectedBucketId('all')
      setSelectedTag(null)
      setViewOnlySelected(false)
    }
  }, [open, initialSelected])

  // Bucket id to name map
  const bucketMap = useMemo(() => {
    const map = new Map<string, { name: string; visibility: string }>()
    for (const b of buckets) {
      map.set(b.id, { name: b.name, visibility: b.visibility })
    }
    return map
  }, [buckets])

  // Extract all unique tags across active documents
  const allTags = useMemo(() => {
    const tagSet = new Set<string>()
    for (const d of documents) {
      if (d.status !== 'archived' && d.tags) {
        for (const t of d.tags) {
          if (t && !t.startsWith('engagement:')) tagSet.add(t)
        }
      }
    }
    return Array.from(tagSet).sort()
  }, [documents])

  // Count documents per bucket
  const bucketCounts = useMemo(() => {
    const counts = new Map<string, number>()
    let uncategorized = 0
    let totalActive = 0

    for (const d of documents) {
      if (d.status === 'archived') continue
      totalActive += 1
      if (!d.bucket_id) {
        uncategorized += 1
      } else {
        counts.set(d.bucket_id, (counts.get(d.bucket_id) || 0) + 1)
      }
    }
    return { counts, uncategorized, totalActive }
  }, [documents])

  // Filtered documents list
  const filteredDocuments = useMemo(() => {
    let list = documents.filter((d) => d.status !== 'archived')

    // Filter by viewOnlySelected toggle
    if (viewOnlySelected) {
      list = list.filter((d) => selectedIds.includes(d.id))
    }

    // Filter by bucket
    if (selectedBucketId === 'uncategorized') {
      list = list.filter((d) => !d.bucket_id)
    } else if (selectedBucketId !== 'all') {
      list = list.filter((d) => d.bucket_id === selectedBucketId)
    }

    // Filter by selected tag
    if (selectedTag) {
      list = list.filter((d) => d.tags?.includes(selectedTag))
    }

    // Filter by search query
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((d) => {
        const titleMatch = d.title?.toLowerCase().includes(q)
        const tagMatch = d.tags?.some((t) => t.toLowerCase().includes(q))
        const filenameMatch = d.versions?.some((v) =>
          v.original_filename?.toLowerCase().includes(q)
        )
        const bInfo = d.bucket_id ? bucketMap.get(d.bucket_id) : null
        const bucketMatch = bInfo?.name?.toLowerCase().includes(q)
        return titleMatch || tagMatch || filenameMatch || bucketMatch
      })
    }

    return list
  }, [documents, selectedBucketId, selectedTag, search, viewOnlySelected, selectedIds, bucketMap])

  const handleToggleDoc = (docId: string) => {
    if (!multiple) {
      setSelectedIds([docId])
      return
    }
    setSelectedIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    )
  }

  const handleSelectAllVisible = () => {
    if (filteredDocuments.length === 0) return
    const allFilteredIds = filteredDocuments.map((d) => d.id)
    const allSelected = allFilteredIds.every((id) => selectedIds.includes(id))
    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !allFilteredIds.includes(id)))
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...allFilteredIds])))
    }
  }

  const handleRemoveSelectedId = (docId: string, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setSelectedIds((prev) => prev.filter((id) => id !== docId))
  }

  const handleClearAllSelected = () => {
    setSelectedIds([])
  }

  const handleApply = () => {
    onConfirm(selectedIds)
    onClose()
  }

  const selectedCount = selectedIds.length
  const allFilteredSelected =
    filteredDocuments.length > 0 &&
    filteredDocuments.every((d) => selectedIds.includes(d.id))

  // Map of selected document objects for the selection tray
  const selectedDocObjects = useMemo(() => {
    return selectedIds
      .map((id) => documents.find((d) => d.id === id))
      .filter((d): d is NonNullable<typeof d> => !!d)
  }, [selectedIds, documents])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="xl"
      className="p-0 overflow-hidden"
    >
      <div className="flex flex-col h-[75vh] max-h-[640px]">
        {/* Top Search & Filter Bar */}
        <div className="p-4 border-b border-border bg-bg-surface flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search across title, file name, tags, or bucket…"
              className="pl-9 pr-8 text-xs h-9 w-full bg-bg-raised/60 focus:bg-bg-surface"
              autoFocus
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="absolute right-2.5 top-2.5 text-text-muted hover:text-text-primary p-0.5 rounded"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* View Mode Toggle: All vs Selected Only */}
            <button
              type="button"
              onClick={() => setViewOnlySelected((prev) => !prev)}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn text-xs font-medium transition-all',
                viewOnlySelected
                  ? 'bg-accent text-white shadow-xs'
                  : 'bg-bg-raised text-text-secondary hover:text-text-primary hover:bg-bg-raised/80 border border-border/60'
              )}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Selected ({selectedCount})</span>
            </button>

            {/* Select/Deselect All Visible */}
            {multiple && filteredDocuments.length > 0 && !viewOnlySelected && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleSelectAllVisible}
                className="gap-1.5 text-xs h-9"
              >
                {allFilteredSelected ? (
                  <>
                    <CheckSquare className="w-3.5 h-3.5 text-accent" />
                    <span>Deselect all visible</span>
                  </>
                ) : (
                  <>
                    <Square className="w-3.5 h-3.5 text-text-muted" />
                    <span>Select all ({filteredDocuments.length})</span>
                  </>
                )}
              </Button>
            )}
          </div>
        </div>

        {/* Main Content Layout: Left Bucket Rail + Right Explorer */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Left Bucket Rail */}
          <aside className="w-56 border-r border-border bg-bg-raised/30 flex flex-col p-3 overflow-y-auto shrink-0 space-y-1">
            <div className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              Buckets
            </div>

            {/* All Documents */}
            <button
              type="button"
              onClick={() => {
                setSelectedBucketId('all')
                setViewOnlySelected(false)
              }}
              className={cn(
                'relative w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs font-medium transition-all text-left group',
                selectedBucketId === 'all' && !viewOnlySelected
                  ? 'bg-accent/10 text-accent font-semibold'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised'
              )}
            >
              <div className="flex items-center gap-2 min-w-0">
                {selectedBucketId === 'all' && !viewOnlySelected ? (
                  <FolderOpen className="w-4 h-4 text-accent shrink-0" />
                ) : (
                  <Folder className="w-4 h-4 text-text-muted group-hover:text-text-secondary shrink-0" />
                )}
                <span className="truncate">All Documents</span>
              </div>
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded text-[10px] font-mono',
                  selectedBucketId === 'all' && !viewOnlySelected
                    ? 'bg-accent text-white'
                    : 'bg-bg-raised text-text-muted'
                )}
              >
                {bucketCounts.totalActive}
              </span>
            </button>

            {/* User Accessible Buckets */}
            {buckets.map((b) => {
              const count = bucketCounts.counts.get(b.id) || 0
              const isSelected = selectedBucketId === b.id && !viewOnlySelected
              const isRestricted = b.visibility === 'restricted'

              return (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => {
                    setSelectedBucketId(b.id)
                    setViewOnlySelected(false)
                  }}
                  className={cn(
                    'relative w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs font-medium transition-all text-left group',
                    isSelected
                      ? 'bg-accent/10 text-accent font-semibold'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised'
                  )}
                  title={b.name}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {isSelected ? (
                      <FolderOpen className="w-4 h-4 text-accent shrink-0" />
                    ) : (
                      <Folder className="w-4 h-4 text-text-muted group-hover:text-text-secondary shrink-0" />
                    )}
                    <span className="truncate">{b.name}</span>
                    {isRestricted && (
                      <span title="Restricted Bucket">
                        <Lock className="w-3 h-3 text-amber-500 shrink-0" />
                      </span>
                    )}
                  </div>
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded text-[10px] font-mono',
                      isSelected
                        ? 'bg-accent text-white'
                        : 'bg-bg-raised text-text-muted'
                    )}
                  >
                    {count}
                  </span>
                </button>
              )
            })}

            {/* Uncategorized Documents (if any) */}
            {bucketCounts.uncategorized > 0 && (
              <button
                type="button"
                onClick={() => {
                  setSelectedBucketId('uncategorized')
                  setViewOnlySelected(false)
                }}
                className={cn(
                  'relative w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs font-medium transition-all text-left group',
                  selectedBucketId === 'uncategorized' && !viewOnlySelected
                    ? 'bg-accent/10 text-accent font-semibold'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised'
                )}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <HardDrive className="w-4 h-4 text-text-muted shrink-0" />
                  <span className="truncate">Uncategorized</span>
                </div>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-bg-raised text-text-muted">
                  {bucketCounts.uncategorized}
                </span>
              </button>
            )}
          </aside>

          {/* Right Document Explorer Area */}
          <main className="flex-1 flex flex-col min-w-0 bg-bg-surface overflow-hidden">
            {/* Tag Filter Chips Bar */}
            {allTags.length > 0 && (
              <div className="px-4 py-2 border-b border-border/60 flex items-center gap-1.5 overflow-x-auto bg-bg-raised/10 shrink-0">
                <span className="text-[10px] font-semibold uppercase text-text-muted flex items-center gap-1 shrink-0">
                  <Tag className="w-3 h-3" /> Tags:
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedTag(null)}
                  className={cn(
                    'px-2 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap transition-colors',
                    selectedTag === null
                      ? 'bg-accent text-white font-semibold'
                      : 'bg-bg-raised text-text-secondary hover:text-text-primary'
                  )}
                >
                  All Tags
                </button>
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => setSelectedTag(selectedTag === tag ? null : tag)}
                    className={cn(
                      'px-2 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap transition-colors flex items-center gap-1',
                      selectedTag === tag
                        ? 'bg-accent text-white font-semibold'
                        : 'bg-bg-raised text-text-secondary hover:text-text-primary'
                    )}
                  >
                    <span>#{tag}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Document Cards List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
              {loadingDocs || loadingBuckets ? (
                <div className="flex flex-col items-center justify-center py-20 text-center text-text-muted text-xs">
                  <div className="h-6 w-6 border-2 border-accent border-t-transparent rounded-full animate-spin mb-2" />
                  <span>Loading DocVault library…</span>
                </div>
              ) : filteredDocuments.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center space-y-2.5">
                  <div className="w-12 h-12 rounded-full bg-bg-raised flex items-center justify-center text-text-muted">
                    <HardDrive className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-text-primary">
                      {viewOnlySelected
                        ? 'No documents currently selected'
                        : search.trim() || selectedTag
                        ? 'No matching documents found'
                        : 'This bucket has no documents'}
                    </p>
                    <p className="text-[11px] text-text-muted max-w-xs">
                      {viewOnlySelected
                        ? 'Check documents from the library to stage them for attachment.'
                        : 'Try adjusting your search criteria, clearing tag filters, or selecting a different bucket.'}
                    </p>
                  </div>
                  {(search.trim() || selectedTag || viewOnlySelected) && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setSearch('')
                        setSelectedTag(null)
                        setViewOnlySelected(false)
                        setSelectedBucketId('all')
                      }}
                      className="text-xs mt-1"
                    >
                      Reset filters
                    </Button>
                  )}
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  <div className="grid grid-cols-1 gap-2">
                    {filteredDocuments.map((doc) => {
                      const isSelected = selectedIds.includes(doc.id)
                      const currentVersion =
                        doc.versions?.find((v) => v.id === doc.current_version_id) ||
                        doc.versions?.[0]
                      const bucketInfo = doc.bucket_id ? bucketMap.get(doc.bucket_id) : null
                      const bucketName = bucketInfo?.name || 'Uncategorized'
                      const versionNo =
                        currentVersion?.version_number ??
                        Math.max(0, ...(doc.versions?.map((v) => v.version_number) || [1]))

                      return (
                        <motion.div
                          key={doc.id}
                          layout
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, scale: 0.98 }}
                          transition={{ duration: 0.15 }}
                          onClick={() => handleToggleDoc(doc.id)}
                          className={cn(
                            'group relative flex items-center justify-between p-3 rounded-lg border transition-all cursor-pointer select-none',
                            isSelected
                              ? 'border-accent bg-accent/5 dark:bg-accent/10 shadow-xs ring-1 ring-accent/30'
                              : 'border-border bg-bg-surface hover:border-border-strong hover:bg-bg-raised/40 shadow-xs'
                          )}
                        >
                          <div className="flex items-center gap-3.5 min-w-0 flex-1">
                            {/* Checkbox indicator */}
                            <div
                              className={cn(
                                'w-5 h-5 rounded-md border flex items-center justify-center transition-all shrink-0',
                                isSelected
                                  ? 'bg-accent border-accent text-white shadow-xs scale-105'
                                  : 'border-border-strong bg-bg-raised/60 group-hover:border-text-muted'
                              )}
                            >
                              {isSelected && <Check className="w-3.5 h-3.5 stroke-[2.5]" />}
                            </div>

                            <div className="w-8 h-8 rounded-lg bg-bg-raised flex items-center justify-center shrink-0 text-text-secondary group-hover:text-accent transition-colors">
                              <FileText className="w-4 h-4" />
                            </div>

                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span
                                  className={cn(
                                    'text-xs font-semibold truncate max-w-[340px]',
                                    isSelected ? 'text-text-primary' : 'text-text-primary'
                                  )}
                                  title={doc.title}
                                >
                                  {doc.title}
                                </span>
                                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-bg-raised text-text-secondary shrink-0">
                                  v{versionNo}
                                </span>
                                {bucketName && (
                                  <span className="hidden sm:inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium bg-bg-raised text-text-muted shrink-0 truncate max-w-[140px]">
                                    {bucketName}
                                  </span>
                                )}
                              </div>

                              <div className="flex items-center gap-2.5 text-[11px] text-text-muted mt-0.5">
                                {currentVersion?.original_filename && (
                                  <span className="truncate max-w-[220px]" title={currentVersion.original_filename}>
                                    {currentVersion.original_filename}
                                  </span>
                                )}
                                {currentVersion?.size_bytes !== undefined && (
                                  <span>({formatFileSize(currentVersion.size_bytes)})</span>
                                )}
                                {doc.tags && doc.tags.length > 0 && (
                                  <span className="hidden md:inline-flex items-center gap-1">
                                    {doc.tags
                                      .filter((t) => !t.startsWith('engagement:'))
                                      .slice(0, 3)
                                      .map((t) => (
                                        <span
                                          key={t}
                                          className="px-1.5 py-0.2 rounded-full bg-bg-raised text-[9px] text-text-secondary"
                                        >
                                          #{t}
                                        </span>
                                      ))}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          <div className="shrink-0 text-[11px] text-text-muted pl-3">
                            {doc.updated_at ? formatDate(doc.updated_at) : ''}
                          </div>
                        </motion.div>
                      )
                    })}
                  </div>
                </AnimatePresence>
              )}
            </div>
          </main>
        </div>

        {/* Docked Selection Tray / Footer Bar */}
        <div className="border-t border-border bg-bg-surface p-3.5 px-5 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2 min-w-0 overflow-hidden">
            {selectedCount > 0 ? (
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-semibold text-text-primary whitespace-nowrap">
                  {selectedCount} document{selectedCount === 1 ? '' : 's'} staged
                </span>
                <button
                  type="button"
                  onClick={handleClearAllSelected}
                  className="text-[11px] text-text-muted hover:text-accent underline ml-1"
                >
                  Clear all
                </button>

                {/* Horizontal scroll of staged document pills */}
                <div className="hidden md:flex items-center gap-1.5 overflow-x-auto pl-2 max-w-[420px]">
                  {selectedDocObjects.slice(0, 4).map((d) => (
                    <span
                      key={d.id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-accent/10 text-accent font-medium max-w-[130px] truncate"
                    >
                      <span className="truncate">{d.title}</span>
                      <button
                        type="button"
                        onClick={(e) => handleRemoveSelectedId(d.id, e)}
                        className="hover:text-red-500 rounded p-0.5"
                      >
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </span>
                  ))}
                  {selectedDocObjects.length > 4 && (
                    <span className="text-[10px] text-text-muted">
                      +{selectedDocObjects.length - 4} more
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <span className="text-xs text-text-muted">
                Select documents from the library to attach to this response.
              </span>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 shrink-0">
            <Button variant="secondary" size="sm" onClick={onClose} className="text-xs">
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              disabled={selectedCount === 0}
              className="gap-1.5 text-xs font-semibold"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>{confirmLabel} ({selectedCount})</span>
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
