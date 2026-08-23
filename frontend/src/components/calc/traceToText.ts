import type { CalcTrace } from './types'

const PREFIX: Record<string, string> = { money: '₹' }
const SUFFIX: Record<string, string> = { percent: '%', days: ' days', months: ' mo' }

/**
 * A pasteable rendering of a trace.
 *
 * The audience for this feature is people answering an auditor's query, so the trace
 * has to leave the app as text rather than a screenshot.
 */
export function traceToText(trace: CalcTrace): string {
  const lines: string[] = [trace.title, trace.basis]
  lines.push(
    trace.is_projection
      ? 'PROJECTION from current inputs — not the recorded figure.'
      : `Computed ${trace.computed_at ?? 'unknown'}`,
  )

  let group = ''
  for (const step of trace.steps) {
    if (step.group !== group) {
      group = step.group
      lines.push('', group)
    }
    const value = `${PREFIX[step.unit] ?? ''}${step.result}${SUFFIX[step.unit] ?? ''}`
    lines.push(`  ${step.label}: ${value}`)
    if (step.formula) lines.push(`    ${step.formula}`)
    if (step.substitution) lines.push(`    = ${step.substitution}`)
    if (step.note) lines.push(`    (${step.note})`)
  }

  return lines.join('\n')
}
