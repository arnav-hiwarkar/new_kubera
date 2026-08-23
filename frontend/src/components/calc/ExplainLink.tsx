import { Calculator } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Opens a calculation trace. Sized to sit in a Card header or beside a derived value
 * without competing with the figure it explains.
 */
export function ExplainLink({
  onClick,
  label = 'See the calculation',
  className,
}: {
  onClick: () => void
  label?: string
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded-btn px-1.5 py-1 text-xs font-medium text-accent',
        'hover:bg-bg-raised focus:outline-none focus:ring-1 focus:ring-accent',
        className,
      )}
    >
      <Calculator className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}
