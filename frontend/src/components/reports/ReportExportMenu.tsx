import React, { useState, useRef, useEffect } from 'react'
import { Download, FileSpreadsheet, FileText, Archive, ChevronDown, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'

export interface ReportExportMenuProps {
  onExportExcel?: () => Promise<void> | void
  onExportPdf?: () => Promise<void> | void
  onArchiveDocVault?: () => Promise<void> | void
  disabled?: boolean
  className?: string
}

export const ReportExportMenu: React.FC<ReportExportMenuProps> = ({
  onExportExcel,
  onExportPdf,
  onArchiveDocVault,
  disabled = false,
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const handleAction = async (actionName: string, actionFn?: () => Promise<void> | void) => {
    if (!actionFn || loadingAction) return
    try {
      setLoadingAction(actionName)
      await actionFn()
    } finally {
      setLoadingAction(null)
      setIsOpen(false)
    }
  }

  return (
    <div className={`relative inline-block text-left ${className || ''}`} ref={menuRef}>
      <Button
        variant="secondary"
        size="sm"
        disabled={disabled || !!loadingAction}
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-1.5"
      >
        {loadingAction ? (
          <Loader2 className="h-4 w-4 animate-spin text-accent" />
        ) : (
          <Download className="h-4 w-4 text-text-secondary" />
        )}
        <span>Export</span>
        <ChevronDown className="h-3.5 w-3.5 text-text-muted transition-transform duration-150" />
      </Button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-1 w-52 origin-top-right rounded-lg border border-border-strong bg-bg-surface p-1 shadow-lg ring-1 ring-black/5 focus:outline-none">
          {onExportExcel && (
            <button
              type="button"
              disabled={!!loadingAction}
              onClick={() => handleAction('excel', onExportExcel)}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-text-primary hover:bg-bg-raised disabled:opacity-50"
            >
              <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
              <div className="flex flex-col">
                <span className="font-medium">Download Excel</span>
                <span className="text-xs text-text-muted">.xlsx spreadsheet</span>
              </div>
            </button>
          )}

          {onExportPdf && (
            <button
              type="button"
              disabled={!!loadingAction}
              onClick={() => handleAction('pdf', onExportPdf)}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-text-primary hover:bg-bg-raised disabled:opacity-50"
            >
              <FileText className="h-4 w-4 text-rose-600" />
              <div className="flex flex-col">
                <span className="font-medium">Download PDF</span>
                <span className="text-xs text-text-muted">Statutory formatted PDF</span>
              </div>
            </button>
          )}

          {onArchiveDocVault && (
            <>
              <div className="my-1 border-t border-border-subtle" />
              <button
                type="button"
                disabled={!!loadingAction}
                onClick={() => handleAction('vault', onArchiveDocVault)}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-text-primary hover:bg-bg-raised disabled:opacity-50"
              >
                <Archive className="h-4 w-4 text-amber-600" />
                <div className="flex flex-col">
                  <span className="font-medium">Save to docVault</span>
                  <span className="text-xs text-text-muted">Encrypted vault archive</span>
                </div>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
