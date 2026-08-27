import React, { useState } from 'react'
import { clsx } from 'clsx'
import { Lock, Send, Upload, X, FileText, FolderPlus } from 'lucide-react'
import { Button, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useRespondToRequirement } from '@/api/hooks/auditease'
import { useDocuments } from '@/api/hooks/docvault'
import type { RequirementRequestResponse } from '@/api/types'
import { formatFileSize } from './progress'

import { DocVaultPickerModal } from './DocVaultPickerModal'

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
  const respondMutation = useRespondToRequirement()
  const { data: vaultDocs = [] } = useDocuments()

  const [textAnswer, setTextAnswer] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [showVaultPickerModal, setShowVaultPickerModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isClosed = req.status === 'closed'

  if (isClosed) {
    return (
      <div
        className={clsx(
          'flex items-center gap-2.5 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-400',
          className
        )}
      >
        <Lock className="w-4 h-4 text-zinc-400 shrink-0" />
        <span>
          This requirement is <strong>closed</strong>. If you need to submit additional information, ask your auditor to reopen it.
        </span>
      </div>
    )
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setSelectedFiles((prev) => [...prev, ...newFiles])
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
      setError('Please provide a written answer or attach at least one file.')
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

  return (
    <form
      onSubmit={handleSubmit}
      className={clsx(
        'rounded-lg border border-blue-200/80 bg-blue-50/30 p-3.5 dark:border-blue-900/50 dark:bg-blue-950/20 space-y-3',
        className
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
          <span>Submit Response</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
            Round {nextRound}
          </span>
        </h4>
        <span className="text-[11px] text-zinc-400">
          Provide explanation, documents, or both
        </span>
      </div>

      <Textarea
        value={textAnswer}
        onChange={(e) => setTextAnswer(e.target.value)}
        placeholder="Type your explanation or response details here…"
        rows={3}
        className="w-full text-xs"
      />

      {/* File & Vault attachments */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 bg-white text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 cursor-pointer transition-colors shadow-xs">
            <Upload className="w-3.5 h-3.5 text-zinc-500" />
            <span>Attach Files</span>
            <input
              type="file"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
          </label>

          <button
            type="button"
            onClick={() => setShowVaultPickerModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 bg-white text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 cursor-pointer transition-colors shadow-xs"
          >
            <FolderPlus className="w-3.5 h-3.5 text-zinc-500" />
            <span>Select from DocVault</span>
          </button>

          <span className="text-[11px] text-zinc-400">
            {selectedFiles.length + selectedDocIds.length > 0
              ? `${selectedFiles.length + selectedDocIds.length} document(s) attached`
              : 'Upload files or select existing vault documents'}
          </span>
        </div>

        {/* Selected files & vault documents preview */}
        {(selectedFiles.length > 0 || selectedDocIds.length > 0) && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {selectedFiles.map((file, idx) => (
              <span
                key={`file-${idx}`}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-white text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:border-zinc-700 shadow-xs"
              >
                <FileText className="w-3 h-3 text-blue-500 shrink-0" />
                <span className="truncate max-w-[180px]" title={file.name}>
                  {file.name}
                </span>
                <span className="text-[10px] text-zinc-400">
                  ({formatFileSize(file.size)})
                </span>
                <button
                  type="button"
                  onClick={() => removeFile(idx)}
                  className="p-0.5 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 rounded"
                  title="Remove file"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
            {selectedDocIds.map((docId) => {
              const doc = vaultDocs.find((d) => d.id === docId)
              return (
                <span
                  key={`vault-${docId}`}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-blue-50 text-blue-800 border border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800 shadow-xs"
                >
                  <FileText className="w-3 h-3 text-blue-600 shrink-0" />
                  <span className="truncate max-w-[180px]" title={doc?.title || 'Vault doc'}>
                    {doc?.title || 'Vault doc'}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeDoc(docId)}
                    className="p-0.5 text-blue-400 hover:text-blue-600 dark:hover:text-blue-200 rounded"
                    title="Remove vault document"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )
            })}
          </div>
        )}
      </div>

      {error && <p className="text-xs font-medium text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex items-center justify-end pt-1">
        <Button
          type="submit"
          size="sm"
          disabled={respondMutation.isPending || (!textAnswer.trim() && selectedFiles.length === 0 && selectedDocIds.length === 0)}
          className="gap-1.5 text-xs"
        >
          <Send className="w-3.5 h-3.5" />
          <span>{respondMutation.isPending ? 'Submitting…' : 'Submit response'}</span>
        </Button>
      </div>

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
