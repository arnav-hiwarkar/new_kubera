import React, { useState, useRef } from 'react'
import { MessagesSquare, Upload, X, FileText } from 'lucide-react'
import { Button, Modal, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAuditorCreateQuery } from '@/api/hooks/auditorEngagements'
import type { RequirementRequestResponse } from '@/api/types'
import { formatFileSize } from './progress'

interface InitiateQueryModalProps {
  open: boolean
  onClose: () => void
  engagementId: string
  req: RequirementRequestResponse
  onSuccess?: (queryId: string) => void
}

export const InitiateQueryModal: React.FC<InitiateQueryModalProps> = ({
  open,
  onClose,
  engagementId,
  req,
  onSuccess,
}) => {
  const toast = useToast()
  const createQueryMutation = useAuditorCreateQuery()

  const [message, setMessage] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleClose = () => {
    setMessage('')
    setFile(null)
    setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    onClose()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    const text = message.trim()
    if (!text) {
      setError('Please provide an initial query message.')
      return
    }

    const formData = new FormData()
    formData.append('initial_message', text)
    formData.append('requirement_id', req.id)
    if (file) {
      formData.append('file', file)
    }

    try {
      const res = await createQueryMutation.mutateAsync({
        engagementId,
        formData,
      })
      toast.success(
        `Query opened for ${req.requirement_id_str || 'requirement'}`
      )
      handleClose()
      onSuccess?.(res.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to open query')
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Initiate Query from Requirement"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Requirement Context Banner */}
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-xs dark:border-blue-900/60 dark:bg-blue-950/30 space-y-1.5">
          <div className="flex items-center gap-1.5 font-semibold text-blue-900 dark:text-blue-200">
            <span className="font-mono bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded text-[11px]">
              {req.requirement_id_str || 'REQ'}
            </span>
            <span>Linked Requirement</span>
          </div>
          <p className="text-zinc-700 dark:text-zinc-300 line-clamp-2 leading-relaxed">
            {req.description}
          </p>
        </div>

        {/* Message Input */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-text-secondary">
            Query Message <span className="text-red-500">*</span>
          </label>
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={`Ask a specific question or request clarification regarding ${
              req.requirement_id_str || 'this requirement'
            }…`}
            rows={4}
            className="w-full text-xs"
            disabled={createQueryMutation.isPending}
            autoFocus
          />
        </div>

        {/* File attachment */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 bg-white text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 cursor-pointer transition-colors shadow-xs">
              <Upload className="w-3.5 h-3.5 text-zinc-500" />
              <span>Attach Supporting File</span>
              <input
                ref={fileInputRef}
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
                disabled={createQueryMutation.isPending}
              />
            </label>
            <span className="text-[11px] text-zinc-400">Optional</span>
          </div>

          {file && (
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:border-zinc-700">
              <FileText className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span className="truncate max-w-[200px]" title={file.name}>
                {file.name}
              </span>
              <span className="text-[10px] text-zinc-400">
                ({formatFileSize(file.size)})
              </span>
              <button
                type="button"
                onClick={() => {
                  setFile(null)
                  if (fileInputRef.current) fileInputRef.current.value = ''
                }}
                className="p-0.5 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 rounded ml-1"
                title="Remove file"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>

        {error && (
          <p className="text-xs font-medium text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        {/* Modal Actions */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleClose}
            disabled={createQueryMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            size="sm"
            disabled={createQueryMutation.isPending || !message.trim()}
            className="gap-1.5"
          >
            <MessagesSquare className="w-3.5 h-3.5" />
            <span>
              {createQueryMutation.isPending ? 'Opening…' : 'Initiate Query'}
            </span>
          </Button>
        </div>
      </form>
    </Modal>
  )
}
