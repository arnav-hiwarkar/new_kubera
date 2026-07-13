import { useCallback, useRef, useState } from 'react'
import { cn } from '@/lib/cn'

export interface FileUploadDropzoneProps {
  onFilesSelected: (files: File[]) => void
  accept?: string
  multiple?: boolean
  hint?: string
  disabled?: boolean
}

export function FileUploadDropzone({
  onFilesSelected,
  accept,
  multiple = false,
  hint,
  disabled,
}: FileUploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list || list.length === 0) return
      onFilesSelected(Array.from(list))
    },
    [onFilesSelected],
  )

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        if (!disabled) handleFiles(e.dataTransfer.files)
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) inputRef.current?.click()
      }}
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-8 text-center transition-colors',
        dragging ? 'border-accent bg-accent-subtle' : 'border-border bg-bg-surface hover:bg-bg-raised/50',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <p className="text-sm font-medium text-text-primary">
        Drop file{multiple ? 's' : ''} here or <span className="text-accent">browse</span>
      </p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </div>
  )
}
