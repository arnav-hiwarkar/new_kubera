import { cn } from '@/lib/cn'
import { STATUS_TONE, humanize, type BadgeTone } from '@/api/enums'

const toneStyles: Record<BadgeTone, { pill: string; dot: string }> = {
  neutral: { pill: 'text-status-archived badge-bg-archived', dot: 'bg-status-archived' },
  info: { pill: 'text-status-uploaded badge-bg-uploaded', dot: 'bg-status-uploaded' },
  warning: { pill: 'text-status-pending badge-bg-pending', dot: 'bg-status-pending' },
  success: { pill: 'text-status-verified badge-bg-verified', dot: 'bg-status-verified' },
  danger: { pill: 'text-status-action badge-bg-action', dot: 'bg-status-action' },
  special: { pill: 'text-status-submitted badge-bg-submitted', dot: 'bg-status-submitted' },
}

export interface StatusBadgeProps {
  /** A backend status/enum value (e.g. "pending_approval"). Tone is derived from it. */
  status: string
  /** Override the auto-derived tone if needed. */
  tone?: BadgeTone
  /** Hide the leading status dot. */
  hideDot?: boolean
  className?: string
}

/**
 * Renders a colored status pill with a leading dot. Color is derived from the
 * backend status enums via STATUS_TONE (see src/api/enums.ts), so it stays
 * consistent across modules.
 */
export function StatusBadge({ status, tone, hideDot, className }: StatusBadgeProps) {
  const resolved = tone ?? STATUS_TONE[status] ?? 'neutral'
  const style = toneStyles[resolved]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2.5 py-0.5 text-xs font-semibold',
        style.pill,
        className,
      )}
    >
      {!hideDot && <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', style.dot)} />}
      {humanize(status)}
    </span>
  )
}
