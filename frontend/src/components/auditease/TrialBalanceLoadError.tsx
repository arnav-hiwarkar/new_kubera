import { AlertTriangle, RefreshCw } from 'lucide-react'
import { ApiContractError } from '@/api/contracts/trialBalance'
import { ApiError } from '@/api/http'
import { Button } from '@/components/ui'
import { cn } from '@/lib/cn'

function reloadApplication() {
  window.location.reload()
}

export function TrialBalanceLoadError({
  error,
  onRetry,
  className,
}: {
  error: unknown
  onRetry: () => void
  className?: string
}) {
  const contractMismatch = error instanceof ApiContractError
  const message = contractMismatch
    ? 'Reload the application to load the matching AuditEase version.'
    : error instanceof ApiError
      ? error.message
      : 'The trial balance could not be loaded. Your other engagement data remains available.'

  return (
    <div
      role="alert"
      className={cn(
        'rounded-card border border-status-action/30 bg-status-action/5 px-5 py-4',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-status-action" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-text-primary">
            {contractMismatch ? 'AuditEase was updated' : 'Trial balance unavailable'}
          </h3>
          <p className="mt-1 text-sm text-text-secondary">{message}</p>
          <div className="mt-3">
            {contractMismatch ? (
              <Button size="sm" onClick={reloadApplication}>
                <RefreshCw /> Reload application
              </Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={onRetry}>
                <RefreshCw /> Try again
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
