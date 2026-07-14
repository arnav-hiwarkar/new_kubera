import type { ReactNode } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { cn } from '@/lib/cn'
import { CountUp } from './CountUp'
import { Sparkline } from './Sparkline'

type Tone = 'accent' | 'gold' | 'info' | 'warning' | 'danger' | 'neutral'

const toneChip: Record<Tone, string> = {
  accent: 'bg-accent-subtle text-accent',
  gold: 'bg-gold-subtle text-gold',
  info: 'bg-status-uploaded/10 text-status-uploaded',
  warning: 'bg-status-pending/10 text-status-pending',
  danger: 'bg-status-action/10 text-status-action',
  neutral: 'bg-bg-raised text-text-secondary',
}

const toneSpark: Record<Tone, string> = {
  accent: 'text-accent',
  gold: 'text-gold',
  info: 'text-status-uploaded',
  warning: 'text-status-pending',
  danger: 'text-status-action',
  neutral: 'text-text-muted',
}

export interface StatCardProps {
  label: string
  /** Numeric value → animated count-up. Or pass a ReactNode via `display`. */
  value?: number
  display?: ReactNode
  icon?: ReactNode
  tone?: Tone
  prefix?: string
  suffix?: string
  decimals?: number
  /** Secondary line under the value. */
  sub?: ReactNode
  /** Percentage change badge (e.g. +12.4). Sign drives color/arrow. */
  delta?: number
  /** Optional mini trend line. */
  spark?: number[]
  loading?: boolean
  className?: string
  onClick?: () => void
}

export function StatCard({
  label,
  value,
  display,
  icon,
  tone = 'accent',
  prefix,
  suffix,
  decimals = 0,
  sub,
  delta,
  spark,
  loading,
  className,
  onClick,
}: StatCardProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'group relative overflow-hidden rounded-card border border-border bg-bg-surface p-5 shadow-card transition-all duration-200 ease-spring',
        onClick && 'cursor-pointer hover:-translate-y-0.5 hover:border-border-strong hover:shadow-raised',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-text-secondary">{label}</p>
        {icon && (
          <span className={cn('flex h-9 w-9 items-center justify-center rounded-xl [&_svg]:h-[18px] [&_svg]:w-[18px]', toneChip[tone])}>
            {icon}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          {loading ? (
            <div className="skeleton h-8 w-20 rounded-md" />
          ) : (
            <p className="text-2xl font-bold tracking-display text-text-primary">
              {display ?? (
                <CountUp value={value ?? 0} prefix={prefix} suffix={suffix} decimals={decimals} />
              )}
            </p>
          )}
          {sub && <p className="mt-1 truncate text-sm text-text-muted">{sub}</p>}
        </div>
        {spark && spark.length > 1 && (
          <Sparkline data={spark} className={toneSpark[tone]} />
        )}
      </div>

      {typeof delta === 'number' && (
        <span
          className={cn(
            'absolute right-4 top-14 inline-flex items-center gap-0.5 rounded-pill px-1.5 py-0.5 text-xs font-semibold',
            delta >= 0 ? 'bg-status-verified/12 text-status-verified' : 'bg-status-action/12 text-status-action',
          )}
        >
          {delta >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {Math.abs(delta).toFixed(1)}%
        </span>
      )}
    </div>
  )
}
