import React from 'react'
import { clsx } from 'clsx'
import { FileText, Download, AlertCircle } from 'lucide-react'
import type { RequirementResponseDocumentOut } from '@/api/types'
import { formatFileSize } from './progress'

interface DocumentChipProps {
  doc: RequirementResponseDocumentOut
  onDownload?: (docId: string, filename: string) => void
  isDownloading?: boolean
  className?: string
}

export const DocumentChip: React.FC<DocumentChipProps> = ({
  doc,
  onDownload,
  isDownloading = false,
  className,
}) => {
  const isDeleted = !doc.document_id

  if (isDeleted) {
    return (
      <span
        className={clsx(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-normal',
          'bg-zinc-100 text-zinc-400 border border-dashed border-zinc-300 dark:bg-zinc-800/60 dark:text-zinc-500 dark:border-zinc-700',
          className
        )}
        title="This document was deleted from DocVault"
      >
        <AlertCircle className="w-3.5 h-3.5 text-zinc-400" />
        <span className="truncate max-w-[200px]">{doc.filename}</span>
        <span className="italic text-[10px] text-zinc-400 dark:text-zinc-500">(deleted)</span>
      </span>
    )
  }

  const formattedSize = formatFileSize(doc.size_bytes)

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-colors',
        'bg-white text-zinc-700 border-zinc-200 shadow-sm dark:bg-zinc-800 dark:text-zinc-200 dark:border-zinc-700',
        className
      )}
    >
      <FileText className="w-3.5 h-3.5 text-blue-500 shrink-0" />
      <span className="truncate max-w-[220px]" title={doc.filename}>
        {doc.filename}
      </span>
      {formattedSize && (
        <span className="text-[10px] text-zinc-400 dark:text-zinc-500 shrink-0">
          ({formattedSize})
        </span>
      )}
      {onDownload && doc.document_id && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onDownload(doc.document_id!, doc.filename)
          }}
          disabled={isDownloading}
          className="ml-0.5 p-0.5 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 rounded transition-colors"
          title={`Download ${doc.filename}`}
          aria-label={`Download ${doc.filename}`}
        >
          <Download className="w-3 h-3" />
        </button>
      )}
    </span>
  )
}
