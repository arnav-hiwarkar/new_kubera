import { useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Spinner, Tabs } from '@/components/ui'
import { CalcStepRow } from './CalcStepRow'
import { traceToText } from './traceToText'
import type { CalcStep, TraceTab } from './types'

export interface CalculationDrawerProps {
  open: boolean
  onClose: () => void
  tabs: TraceTab[]
  /** Step key to scroll to and highlight. Also selects the tab containing it. */
  focusStep?: string
  loading?: boolean
  /** A 422's message — what is missing, rather than a failure. */
  error?: string | null
  /** Shown when there are no traces, e.g. a run recorded before traces existed. */
  emptyNote?: string
  /** When given, the empty state offers a projection instead. */
  onShowProjection?: () => void
  /** Provenance line, e.g. "Draft run" — so a draft is never read as the filed figure. */
  contextNote?: string
}

function groupSteps(steps: CalcStep[]): { group: string; steps: CalcStep[] }[] {
  const groups: { group: string; steps: CalcStep[] }[] = []
  for (const step of steps) {
    const last = groups[groups.length - 1]
    if (last && last.group === step.group) last.steps.push(step)
    else groups.push({ group: step.group, steps: [step] })
  }
  return groups
}

/**
 * Renders a calculation trace. Knows nothing about assets, depreciation or costing —
 * anything that can produce a trace can use it.
 */
export function CalculationDrawer({
  open,
  onClose,
  tabs,
  focusStep,
  loading,
  error,
  emptyNote,
  onShowProjection,
  contextNote,
}: CalculationDrawerProps) {
  // The tab holding the focused step is the one worth opening on.
  const preferred = useMemo(() => {
    if (focusStep) {
      const holder = tabs.find((t) => t.trace.steps.some((s) => s.key === focusStep))
      if (holder) return holder.id
    }
    return tabs[0]?.id ?? ''
  }, [tabs, focusStep])

  const [active, setActive] = useState(preferred)
  useEffect(() => setActive(preferred), [preferred])

  const current = tabs.find((t) => t.id === active) ?? tabs[0]
  const trace = current?.trace

  useEffect(() => {
    if (!open || !focusStep || !trace) return
    // The drawer animates in, so the node is not scrollable on the same frame.
    const id = window.setTimeout(() => {
      document
        .getElementById(`calc-step-${focusStep}`)
        ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 120)
    return () => window.clearTimeout(id)
  }, [open, focusStep, trace])

  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    if (!trace) return
    await navigator.clipboard.writeText(traceToText(trace))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="How this was calculated"
      subtitle={trace?.title}
      width="lg"
      footer={
        <div className="flex items-center justify-end gap-2">
          {trace && (
            <Button variant="ghost" size="sm" onClick={handleCopy}>
              {copied ? 'Copied' : 'Copy calculation'}
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      {tabs.length > 1 && (
        <Tabs
          className="mb-3"
          layoutGroup="calc-drawer"
          tabs={tabs.map((t) => ({ id: t.id, label: t.label }))}
          value={active}
          onChange={setActive}
        />
      )}

      {loading && <Spinner className="mx-auto my-8 h-5 w-5" />}

      {!loading && error && (
        <div className="rounded-card border border-border-strong bg-bg-inset p-3">
          <p className="text-sm font-medium text-text-primary">
            This figure cannot be computed yet
          </p>
          <p className="mt-1 text-sm text-text-secondary">{error}</p>
        </div>
      )}

      {!loading && !error && !trace && (
        <div className="rounded-card border border-border bg-bg-inset p-3">
          <p className="text-sm text-text-secondary">
            {emptyNote ?? 'There is no calculation to show yet.'}
          </p>
          {onShowProjection && (
            <Button className="mt-3" variant="secondary" size="sm" onClick={onShowProjection}>
              Show a projection from current inputs
            </Button>
          )}
        </div>
      )}

      {!loading && !error && trace && (
        <div className="flex flex-col gap-3">
          {/* A projection has to be impossible to mistake for the recorded figure. */}
          {trace.is_projection ? (
            <div className="rounded-card border border-dashed border-status-pending bg-status-pending/5 px-3 py-2">
              <p className="text-xs font-medium text-status-pending">
                Projection from the asset’s current inputs — not the recorded figure.
              </p>
              <p className="mt-0.5 text-xs text-text-muted">
                Recompute the run to record this.
              </p>
            </div>
          ) : (
            <p className="text-xs text-text-muted">
              Computed {trace.computed_at ?? 'at an unrecorded time'}
              {contextNote ? ` · ${contextNote}` : ''}
            </p>
          )}

          <p className="text-xs text-text-secondary">{trace.basis}</p>

          {groupSteps(trace.steps).map(({ group, steps }) => (
            <section key={group} className="flex flex-col gap-1.5">
              <h4 className="mt-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
                {group}
              </h4>
              {steps.map((step) => (
                <CalcStepRow key={step.key} step={step} focused={step.key === focusStep} />
              ))}
            </section>
          ))}
        </div>
      )}
    </Drawer>
  )
}
