/**
 * The shape of a calculation trace. Mirrors `CalcTraceSchema` on the backend, and is
 * hand-written so the drawer does not depend on regenerating `schema.d.ts`.
 */

export type CalcUnit = 'money' | 'percent' | 'days' | 'months' | 'count' | 'none'

export interface CalcStep {
  key: string
  group: string
  label: string
  /** Empty for a plain input rather than a derivation — the renderer omits the line. */
  formula: string
  substitution: string
  /** Already formatted. The renderer adds the unit's symbol and never rounds. */
  result: string
  unit: CalcUnit
  /** The figure the page displays. Anchors the trace to the row it was opened from. */
  emphasis: boolean
  note?: string | null
}

export interface CalcTrace {
  title: string
  basis: string
  steps: CalcStep[]
  is_projection: boolean
  computed_at?: string | null
}

/** One book in the drawer. Two tabs means Companies Act and Income Tax side by side. */
export interface TraceTab {
  id: string
  label: string
  trace: CalcTrace
}

/**
 * Operators, duplicated from `app/services/calc_trace_builders.py`. A trace built here
 * sits in the same drawer as one built there, so they have to read identically.
 */
export const MUL = ' × '
export const DIV = ' ÷ '
export const SUB = ' − '
export const ADD = ' + '
