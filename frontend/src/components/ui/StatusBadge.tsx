import { cn } from '@/lib/cn'
import { STATUS_TONE, humanize, type BadgeTone } from '@/api/enums'

const toneStyles: Record<BadgeTone, string> = {
  neutral: 'text-status-archived badge-bg-archived',
  info: 'text-status-uploaded badge-bg-uploaded',
  warning: 'text-status-pending badge-bg-pending',
  success: 'text-status-verified badge-bg-verified',
  danger: 'text-status-action badge-bg-action',
  special: 'text-status-submitted badge-bg-submitted',
}

export interface StatusBadgeProps {
  /** A backend status/enum value (e.g. "pending_approval"). Tone is derived from it. */
  status: string
  /** Override the auto-derived tone if needed. */
  tone?: BadgeTone
  className?: string
}

/**
 * Renders a colored status pill. Color is derived from the backend status enums
 * via STATUS_TONE (see src/api/enums.ts), so it stays consistent across modules.
 */
export function StatusBadge({ status, tone, className }: StatusBadgeProps) {
  const resolved = tone ?? STATUS_TONE[status] ?? 'neutral'
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium',
        toneStyles[resolved],
        className,
      )}
    >
      {humanize(status)}
    </span>
  )
}
