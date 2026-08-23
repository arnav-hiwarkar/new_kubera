import { cn } from '@/lib/cn'
import type { CalcStep } from './types'

const PREFIX: Partial<Record<CalcStep['unit'], string>> = { money: '₹' }
const SUFFIX: Partial<Record<CalcStep['unit'], string>> = {
  percent: '%',
  days: ' days',
  months: ' mo',
}

/**
 * One line of a calculation.
 *
 * The result arrives already formatted; this only adds the unit's symbol. Nothing here
 * may reformat a number — that is how a drawer ends up disagreeing with the row that
 * opened it.
 */
export function CalcStepRow({ step, focused }: { step: CalcStep; focused?: boolean }) {
  return (
    <div
      id={`calc-step-${step.key}`}
      data-focused={focused ? 'true' : undefined}
      className={cn(
        'rounded-md border px-3 py-2 transition-colors',
        step.emphasis
          ? 'border-border-strong bg-bg-raised'
          : 'border-transparent bg-bg-inset/40',
        focused && 'ring-1 ring-accent',
      )}
    >
      <div className="flex items-baseline justify-between gap-4">
        <span
          className={cn(
            'text-sm',
            step.emphasis ? 'font-semibold text-text-primary' : 'text-text-secondary',
          )}
        >
          {step.label}
        </span>
        <span
          className={cn(
            'tabular-nums whitespace-nowrap',
            step.emphasis ? 'text-md font-semibold text-text-primary' : 'text-sm text-text-primary',
          )}
        >
          {PREFIX[step.unit] ?? ''}
          {step.result}
          {SUFFIX[step.unit] ?? ''}
        </span>
      </div>
      {/* An input step has no formula. Rendering blank lines for it would imply the
          value was derived from something. */}
      {step.formula && <p className="mt-0.5 text-xs text-text-muted">{step.formula}</p>}
      {step.substitution && (
        <p className="text-xs tabular-nums text-text-secondary">{step.substitution}</p>
      )}
      {step.note && <p className="mt-1 text-xs italic text-text-muted">{step.note}</p>}
    </div>
  )
}
