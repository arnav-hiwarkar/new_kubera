import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { useImpactPreview, type ImpactKind } from '@/api/hooks/assetMasters'

export interface ImpactNoticeProps {
  kind: ImpactKind
  id: string | null
}

/** Live verdict rendered inside every masters edit modal BEFORE saving: what
 *  this edit will and will not change. Non-`none` classifications make the
 *  modal require an explicit acknowledgement before Save enables. */
export function ImpactNotice({ kind, id }: ImpactNoticeProps) {
  const { data, isLoading } = useImpactPreview(id ? kind : null, id)
  if (!data || isLoading || !id) return null
  return (
    <div className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
      data.classification === 'none'
        ? 'border-border bg-bg-raised text-text-secondary'
        : 'border-status-pending/40 bg-status-pending/10 text-text-primary'
    }`}>
      {data.classification === 'none'
        ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
      <div>
        <p>{data.message}</p>
        {(data.draft_run_fy_labels.length > 0 || data.finalized_run_fy_labels.length > 0) && (
          <p className="mt-1 text-xs text-text-muted">
            Draft runs: {data.draft_run_fy_labels.join(', ') || '—'} ·
            Finalized: {data.finalized_run_fy_labels.join(', ') || '—'}
          </p>
        )}
      </div>
    </div>
  )
}
