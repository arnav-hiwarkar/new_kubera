import { motion } from 'framer-motion'
import { CountUp } from '@/components/ui'
import {
  computeCounts,
  percentComplete,
  type RequirementLite,
  type RequestStatusFilter,
} from './progress'

export type { RequestStatusFilter } from './progress'

const BUCKETS: { key: RequestStatusFilter; label: string; bar: string; dot: string }[] = [
  { key: 'accepted', label: 'Accepted', bar: 'bg-status-verified', dot: 'bg-status-verified' },
  { key: 'submitted', label: 'Submitted', bar: 'bg-status-uploaded', dot: 'bg-status-uploaded' },
  { key: 'clarification_needed', label: 'Clarification', bar: 'bg-status-pending', dot: 'bg-status-pending' },
  { key: 'pending', label: 'Pending', bar: 'bg-border-strong', dot: 'bg-text-muted' },
]

export function RequirementsProgress({
  requirements,
  activeFilter,
  onFilterChange,
}: {
  requirements: RequirementLite[]
  activeFilter: RequestStatusFilter | null
  onFilterChange: (f: RequestStatusFilter | null) => void
}) {
  const counts = computeCounts(requirements)
  const total = requirements.length || 1
  return (
    <div className="rounded-card border border-border bg-bg-surface p-4 shadow-card">
      <p className="text-sm font-medium text-text-secondary">
        <CountUp
          value={percentComplete(requirements)}
          suffix="%"
          className="font-semibold text-text-primary"
        />{' '}
        complete · {requirements.length} requirement{requirements.length === 1 ? '' : 's'}
      </p>
      <div className="mt-3 flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-bg-raised">
        {BUCKETS.map((b) =>
          counts[b.key] > 0 ? (
            <motion.div
              key={b.key}
              className={`${b.bar} h-full rounded-full`}
              initial={{ width: 0 }}
              animate={{ width: `${(counts[b.key] / total) * 100}%` }}
              transition={{ type: 'spring', stiffness: 120, damping: 20 }}
            />
          ) : null,
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            onClick={() => onFilterChange(activeFilter === b.key ? null : b.key)}
            className={`flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-xs font-medium transition-all duration-150 ease-spring ${
              activeFilter === b.key
                ? 'border-border-strong bg-bg-raised text-text-primary'
                : 'border-transparent text-text-secondary hover:bg-bg-raised'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${b.dot}`} />
            {b.label}
            <span className="tabular-nums">
              <CountUp value={counts[b.key]} duration={500} />
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
