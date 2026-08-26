const TONES: Record<number, string> = {
  1: 'border-border bg-bg-surface text-text-muted',
  2: 'border-border-strong bg-bg-surface text-text-secondary',
  3: 'border-sky-300/60 bg-sky-50 text-sky-700 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-300',
  4: 'border-orange-300/60 bg-orange-50 text-orange-700 dark:border-orange-700 dark:bg-orange-950 dark:text-orange-300',
  5: 'border-red-300/60 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300',
}

/** P1 is quiet by design — the default priority should not shout. */
export function PriorityChip({ priority }: { priority: number }) {
  const p = Math.min(5, Math.max(1, Math.round(priority)))
  return (
    <span
      className={`inline-flex items-center rounded-pill border px-2 py-0.5 text-xs font-semibold ${TONES[p]}`}
    >
      P{p}
    </span>
  )
}
