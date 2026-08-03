import { Layers, Network, Scale } from 'lucide-react'
import type { TBTotalsResponse } from '@/api/types'
import { StatCard } from '@/components/ui'
import { formatMoney } from '@/lib/format'

export function BalanceStatCards({
  totals,
  loading,
  accent = 'company',
}: {
  totals?: TBTotalsResponse
  loading?: boolean
  accent?: 'company' | 'auditor'
}) {
  const count = totals?.ledger_count ?? 0
  const mapped = totals?.mapped_count ?? 0
  const mappedRatio = count ? Math.round((mapped / count) * 100) : 0
  const ready = totals?.statement_ready ?? false
  const balanced = totals?.balanced ?? false
  const status = !count ? '—' : !ready ? 'Needs review' : balanced ? 'Yes' : 'No'

  return (
    <>
      <StatCard label="Ledgers" value={count} icon={<Layers />} tone="info" loading={loading} />
      <StatCard
        label="Mapped"
        value={mappedRatio}
        suffix="%"
        icon={<Network />}
        tone={accent === 'company' ? 'accent' : 'info'}
        loading={loading}
        sub={`${mapped} of ${count} ledgers`}
      />
      <StatCard
        label="Balanced"
        display={
          <span className={!count ? 'text-text-muted' : ready && balanced ? 'text-status-verified' : 'text-status-pending'}>
            {status}
          </span>
        }
        icon={<Scale />}
        tone={!count ? 'neutral' : ready && balanced ? (accent === 'company' ? 'accent' : 'info') : 'warning'}
        sub={
          count && !ready
            ? 'Map ledgers and resolve signs'
            : count && !balanced
              ? `Difference ${formatMoney(totals?.difference ?? 0)}`
              : undefined
        }
      />
    </>
  )
}
