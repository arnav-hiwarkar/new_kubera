import { useCallback, useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'
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
        'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed px-6 py-10 text-center transition-all duration-200',
        dragging
          ? 'scale-[1.01] border-accent bg-accent-subtle'
          : 'border-border-strong bg-bg-inset hover:border-accent/50 hover:bg-bg-raised',
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
      <span
        className={cn(
          'flex h-11 w-11 items-center justify-center rounded-2xl transition-colors',
          dragging ? 'bg-accent text-white' : 'bg-accent-subtle text-accent',
        )}
      >
        <UploadCloud className="h-5 w-5" />
      </span>
      <p className="text-sm font-medium text-text-primary">
        Drop file{multiple ? 's' : ''} here or <span className="text-accent">browse</span>
      </p>
      {hint && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  )
}
