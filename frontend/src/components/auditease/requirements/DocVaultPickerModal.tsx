import React, { useState, useMemo } from 'react'
import { clsx } from 'clsx'
import { Search, Folder, FileText, Check, Layers, HardDrive } from 'lucide-react'
import { Button, Modal, Input } from '@/components/ui'
import { useBuckets, useDocuments } from '@/api/hooks/docvault'
import { formatFileSize } from './progress'

interface DocVaultPickerModalProps {
  open: boolean
  onClose: () => void
  selectedDocIds: string[]
  onConfirm: (selectedIds: string[]) => void
  multiple?: boolean
}

export const DocVaultPickerModal: React.FC<DocVaultPickerModalProps> = ({
  open,
  onClose,
  selectedDocIds: initialSelected,
  onConfirm,
  multiple = true,
}) => {
  const { data: buckets = [], isLoading: loadingBuckets } = useBuckets()
  const { data: documents = [], isLoading: loadingDocs } = useDocuments()

  const [search, setSearch] = useState('')
  const [selectedBucketId, setSelectedBucketId] = useState<string | 'all'>('all')
  const [selectedIds, setSelectedIds] = useState<string[]>(initialSelected)

  // Sync initialSelected when modal opens
  React.useEffect(() => {
    if (open) {
      setSelectedIds(initialSelected)
      setSearch('')
      setSelectedBucketId('all')
    }
  }, [open, initialSelected])

  const bucketMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const b of buckets) {
      map.set(b.id, b.name)
    }
    return map
  }, [buckets])

  const filteredDocuments = useMemo(() => {
    let list = documents

    if (selectedBucketId !== 'all') {
      list = list.filter((d) => d.bucket_id === selectedBucketId)
    }

    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((d) => {
        const titleMatch = d.title?.toLowerCase().includes(q)
        const tagMatch = d.tags?.some((t) => t.toLowerCase().includes(q))
        const filenameMatch = d.versions?.some((v) =>
          v.original_filename?.toLowerCase().includes(q)
        )
        const bucketName = d.bucket_id ? bucketMap.get(d.bucket_id)?.toLowerCase() : ''
        const bucketMatch = bucketName?.includes(q)
        return titleMatch || tagMatch || filenameMatch || bucketMatch
      })
    }

    return list
  }, [documents, selectedBucketId, search, bucketMap])

  const handleToggleDoc = (docId: string) => {
    if (!multiple) {
      setSelectedIds([docId])
      return
    }
    setSelectedIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    )
  }

  const handleSelectAll = () => {
    if (filteredDocuments.length === 0) return
    const allFilteredIds = filteredDocuments.map((d) => d.id)
    const allSelected = allFilteredIds.every((id) => selectedIds.includes(id))
    if (allSelected) {
      // Unselect filtered
      setSelectedIds((prev) => prev.filter((id) => !allFilteredIds.includes(id)))
    } else {
      // Select all filtered
      setSelectedIds((prev) => Array.from(new Set([...prev, ...allFilteredIds])))
    }
  }

  const handleApply = () => {
    onConfirm(selectedIds)
    onClose()
  }

  const selectedCount = selectedIds.length

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Select Documents from DocVault"
    >
      <div className="space-y-4 min-w-[320px] sm:min-w-[540px]">
        {/* Search and Navigation Bar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by title, filename, tags, or bucket…"
              className="pl-9 text-xs"
              autoFocus
            />
          </div>

          {/* Bucket Quick Filter */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
            <button
              type="button"
              onClick={() => setSelectedBucketId('all')}
              className={clsx(
                'px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-colors',
                selectedBucketId === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
              )}
            >
              All Buckets ({documents.length})
            </button>
            {buckets.map((b) => {
              const docCount = documents.filter((d) => d.bucket_id === b.id).length
              return (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => setSelectedBucketId(b.id)}
                  className={clsx(
                    'px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1',
                    selectedBucketId === b.id
                      ? 'bg-blue-600 text-white'
                      : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                  )}
                >
                  <Folder className="w-3 h-3" />
                  <span>{b.name}</span>
                  <span className="text-[10px] opacity-75">({docCount})</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Selection Stats and Bulk Toggle */}
        <div className="flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400 border-b border-border pb-2">
          <span>
            Showing {filteredDocuments.length} of {documents.length} documents
            {selectedCount > 0 && ` · ${selectedCount} selected`}
          </span>
          {multiple && filteredDocuments.length > 0 && (
            <button
              type="button"
              onClick={handleSelectAll}
              className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
            >
              {filteredDocuments.every((d) => selectedIds.includes(d.id))
                ? 'Deselect all visible'
                : 'Select all visible'}
            </button>
          )}
        </div>

        {/* Document Grid / List */}
        <div className="max-h-[380px] overflow-y-auto space-y-2 pr-1">
          {loadingDocs || loadingBuckets ? (
            <div className="text-center py-12 text-xs text-zinc-400">
              Loading DocVault documents…
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <HardDrive className="w-8 h-8 text-zinc-300 dark:text-zinc-600 mx-auto" />
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {search.trim()
                  ? 'No documents match your search criteria.'
                  : 'No documents found in this bucket.'}
              </p>
            </div>
          ) : (
            filteredDocuments.map((doc) => {
              const isSelected = selectedIds.includes(doc.id)
              const currentVersion = doc.versions?.find(
                (v) => v.id === doc.current_version_id
              ) || doc.versions?.[0]
              const bucketName = doc.bucket_id ? bucketMap.get(doc.bucket_id) : 'Unbucketed'

              return (
                <div
                  key={doc.id}
                  onClick={() => handleToggleDoc(doc.id)}
                  className={clsx(
                    'flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all',
                    isSelected
                      ? 'border-blue-500 bg-blue-50/60 dark:bg-blue-950/40 dark:border-blue-700 shadow-xs'
                      : 'border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-700'
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {/* Checkbox indicator */}
                    <div
                      className={clsx(
                        'w-4 h-4 rounded border flex items-center justify-center transition-colors shrink-0',
                        isSelected
                          ? 'bg-blue-600 border-blue-600 text-white'
                          : 'border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800'
                      )}
                    >
                      {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                    </div>

                    <FileText className="w-4 h-4 text-blue-500 shrink-0" />

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 truncate max-w-[280px]">
                          {doc.title}
                        </span>
                        {bucketName && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                            {bucketName}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 text-[11px] text-zinc-400 mt-0.5">
                        {currentVersion?.original_filename && (
                          <span className="truncate max-w-[200px]">
                            {currentVersion.original_filename}
                          </span>
                        )}
                        {currentVersion?.size_bytes !== undefined && (
                          <span>({formatFileSize(currentVersion.size_bytes)})</span>
                        )}
                        {doc.tags && doc.tags.length > 0 && (
                          <span className="hidden sm:inline-flex items-center gap-1">
                            {doc.tags.slice(0, 2).map((t) => (
                              <span
                                key={t}
                                className="px-1 py-0.2 rounded bg-zinc-100 dark:bg-zinc-800 text-[9px] text-zinc-500"
                              >
                                #{t}
                              </span>
                            ))}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="shrink-0 text-[11px] text-zinc-400">
                    {doc.updated_at
                      ? new Date(doc.updated_at).toLocaleDateString()
                      : ''}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Modal Actions */}
        <div className="flex items-center justify-between pt-3 border-t border-border">
          <div className="text-xs text-zinc-500 dark:text-zinc-400">
            {selectedCount === 0
              ? 'No documents chosen'
              : `${selectedCount} document${selectedCount === 1 ? '' : 's'} selected`}
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              disabled={selectedCount === 0}
              className="gap-1.5"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Attach Selected ({selectedCount})</span>
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
