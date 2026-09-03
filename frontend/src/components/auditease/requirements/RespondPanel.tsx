import React, { useState, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Lock,
  Send,
  Upload,
  X,
  FolderPlus,
  HardDrive,
  AlertCircle,
  FileUp,
} from 'lucide-react'
import { Button, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useRespondToRequirement } from '@/api/hooks/auditease'
import { useDocuments } from '@/api/hooks/docvault'
import { useQueryClient } from '@tanstack/react-query'
import type { RequirementRequestResponse } from '@/api/types'
import { formatFileSize } from './progress'
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
import { cn } from '@/lib/cn'

interface RespondPanelProps {
  engagementId: string
  req: RequirementRequestResponse
  onSuccess?: () => void
  className?: string
}

export const RespondPanel: React.FC<RespondPanelProps> = ({
  engagementId,
  req,
  onSuccess,
  className,
}) => {
  const toast = useToast()
  const queryClient = useQueryClient()
  const respondMutation = useRespondToRequirement()
  const { data: vaultDocs = [] } = useDocuments()

  const [textAnswer, setTextAnswer] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [showVaultPickerModal, setShowVaultPickerModal] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const isClosed = req.status === 'closed'

  if (isClosed) {
    return (
      <div
        className={cn(
          'flex items-center gap-2.5 rounded-lg border border-border bg-bg-raised/40 p-3 text-xs text-text-muted',
          className
        )}
      >
        <Lock className="w-4 h-4 text-text-muted shrink-0" />
        <span>
          This requirement is <strong className="text-text-primary">closed</strong>. If you need to submit additional documents or answers, ask your auditor to reopen it.
        </span>
      </div>
    )
  }

  const handleFilesAdded = (files: FileList | File[]) => {
    const fileArray = Array.from(files)
    if (fileArray.length > 0) {
      setSelectedFiles((prev) => [...prev, ...fileArray])
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFilesAdded(e.target.files)
      // reset input value so re-selecting same file triggers change
      e.target.value = ''
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!isDragActive) setIsDragActive(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    // only deactivate if leaving the container
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    setIsDragActive(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesAdded(e.dataTransfer.files)
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const removeDoc = (docId: string) => {
    setSelectedDocIds((prev) => prev.filter((id) => id !== docId))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    const text = textAnswer.trim()
    if (!text && selectedFiles.length === 0 && selectedDocIds.length === 0) {
      setError('Please provide a written answer or attach at least one document.')
      return
    }

    const formData = new FormData()
    if (text) {
      formData.append('text_answer', text)
    }
    for (const file of selectedFiles) {
      formData.append('files', file)
    }
    for (const docId of selectedDocIds) {
      formData.append('document_ids', docId)
    }

    try {
      await respondMutation.mutateAsync({
        engagementId,
        reqId: req.id,
        formData,
      })
      // Invalidate requirements, docvault library and activity
      queryClient.invalidateQueries({ queryKey: ['auditease', 'requirements', engagementId] })
      queryClient.invalidateQueries({ queryKey: ['docvault', 'documents'] })
      queryClient.invalidateQueries({ queryKey: ['company', 'activity'] })

      toast.success(
        `Response submitted for ${req.requirement_id_str || 'requirement'}`
      )
      setTextAnswer('')
      setSelectedFiles([])
      setSelectedDocIds([])
      setShowVaultPickerModal(false)
      onSuccess?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit response')
    }
  }

  const nextRound = (req.submission_count ?? 0) + 1
  const totalStagedCount = selectedFiles.length + selectedDocIds.length

  return (
    <form
      onSubmit={handleSubmit}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={cn(
        'relative rounded-xl border transition-all duration-200 p-4 space-y-3.5',
        isDragActive
          ? 'border-accent bg-accent/5 ring-2 ring-accent/30 shadow-md'
          : 'border-border bg-bg-raised/20 dark:bg-bg-raised/10 shadow-xs hover:border-border-strong',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-text-primary flex items-center gap-2">
          <span>Submit Response</span>
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-accent/10 text-accent">
            Round {nextRound}
          </span>
        </h4>
        <span className="text-[11px] text-text-muted">
          Provide explanation, documents from your machine, or select from DocVault
        </span>
      </div>

      {/* Written answer */}
      <Textarea
        value={textAnswer}
        onChange={(e) => setTextAnswer(e.target.value)}
        placeholder="Type your explanation, summary, or response notes here…"
        rows={3}
        className="w-full text-xs bg-bg-surface focus:bg-bg-surface"
      />

      {/* Interactive Dropzone & Attachments Bar */}
      <div className="space-y-2.5">
        <div
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'group relative flex flex-col sm:flex-row items-center justify-between p-3.5 rounded-lg border border-dashed transition-all cursor-pointer select-none',
            isDragActive
              ? 'border-accent bg-accent/10 text-accent scale-[1.01]'
              : 'border-border hover:border-accent/60 bg-bg-surface/80 hover:bg-bg-surface'
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileChange}
            className="hidden"
          />

          <div className="flex items-center gap-3 min-w-0">
            <div
              className={cn(
                'w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-colors',
                isDragActive
                  ? 'bg-accent text-white'
                  : 'bg-bg-raised text-text-muted group-hover:text-accent group-hover:bg-accent/10'
              )}
            >
              <FileUp className="w-4 h-4" />
            </div>

            <div className="min-w-0 text-left">
              <div className="text-xs font-semibold text-text-primary group-hover:text-accent transition-colors">
                {isDragActive ? 'Drop files here to attach' : 'Upload documents from your machine'}
              </div>
              <div className="text-[11px] text-text-muted">
                Drag & drop files directly here, or click to browse
              </div>
            </div>
          </div>

          <div className="mt-2 sm:mt-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              className="gap-1.5 text-xs h-8 shadow-xs"
            >
              <Upload className="w-3.5 h-3.5 text-text-muted" />
              <span>Browse device</span>
            </Button>

            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setShowVaultPickerModal(true)}
              className="gap-1.5 text-xs h-8 shadow-xs"
            >
              <FolderPlus className="w-3.5 h-3.5 text-accent" />
              <span>Select from DocVault</span>
            </Button>
          </div>
        </div>

        {/* Staged Attachments Preview List */}
        {totalStagedCount > 0 && (
          <div className="space-y-1.5 pt-1">
            <div className="flex items-center justify-between text-[11px] text-text-muted">
              <span>
                {totalStagedCount} document{totalStagedCount === 1 ? '' : 's'} staged for submission:
              </span>
              <span className="text-[10px] text-text-muted">
                Uploaded files will be saved in engagement DocVault bucket
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5">
              <AnimatePresence initial={false}>
                {/* Local Machine Uploads */}
                {selectedFiles.map((file, idx) => (
                  <motion.span
                    key={`file-${idx}-${file.name}`}
                    layout
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ duration: 0.12 }}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-bg-surface text-text-primary border border-border shadow-xs group"
                  >
                    <Upload className="w-3 h-3 text-emerald-500 shrink-0" />
                    <span className="truncate max-w-[200px] font-medium" title={file.name}>
                      {file.name}
                    </span>
                    <span className="text-[10px] text-text-muted">
                      ({formatFileSize(file.size)})
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(idx)}
                      className="p-0.5 text-text-muted hover:text-red-500 rounded transition-colors"
                      title="Remove file"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </motion.span>
                ))}

                {/* Picked DocVault Documents */}
                {selectedDocIds.map((docId) => {
                  const doc = vaultDocs.find((d) => d.id === docId)
                  return (
                    <motion.span
                      key={`vault-${docId}`}
                      layout
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: 0.12 }}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-accent/10 text-accent border border-accent/30 shadow-xs group"
                    >
                      <HardDrive className="w-3 h-3 text-accent shrink-0" />
                      <span className="truncate max-w-[200px] font-medium" title={doc?.title || 'Vault doc'}>
                        {doc?.title || 'Vault doc'}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeDoc(docId)}
                        className="p-0.5 text-accent/70 hover:text-red-500 rounded transition-colors"
                        title="Remove vault document"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </motion.span>
                  )
                })}
              </AnimatePresence>
            </div>
          </div>
        )}
      </div>

      {/* Error alert */}
      {error && (
        <div className="flex items-center gap-2 p-2.5 rounded-lg bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border border-red-200 dark:border-red-800 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Footer Submit */}
      <div className="flex items-center justify-between pt-1 border-t border-border/40">
        <div className="text-[11px] text-text-muted">
          {totalStagedCount > 0
            ? `${totalStagedCount} file${totalStagedCount === 1 ? '' : 's'} ready to send`
            : 'At least one file or written answer is required'}
        </div>

        <Button
          type="submit"
          size="sm"
          disabled={
            respondMutation.isPending ||
            (!textAnswer.trim() && selectedFiles.length === 0 && selectedDocIds.length === 0)
          }
          className="gap-1.5 text-xs font-semibold"
        >
          <Send className="w-3.5 h-3.5" />
          <span>{respondMutation.isPending ? 'Submitting…' : 'Submit response'}</span>
        </Button>
      </div>

      {/* DocVault Picker Modal */}
      {showVaultPickerModal && (
        <DocVaultPickerModal
          open={showVaultPickerModal}
          onClose={() => setShowVaultPickerModal(false)}
          selectedDocIds={selectedDocIds}
          onConfirm={(ids) => setSelectedDocIds(ids)}
        />
      )}
    </form>
  )
}
