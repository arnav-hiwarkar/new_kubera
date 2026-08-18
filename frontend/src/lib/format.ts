/** Human-readable byte size, e.g. 2.1 MB. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(1)} ${units[i]}`
}

/** Short date, e.g. "Jun 3, 2026". */
export function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

/** Relative time from now, e.g. "just now", "2h ago", "3d ago". */
export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diff = Date.now() - then
  const sec = Math.round(diff / 1000)
  if (sec < 45) return 'just now'
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 7) return `${day}d ago`
  const wk = Math.round(day / 7)
  if (day < 30) return `${wk}w ago`
  return formatDate(iso)
}

function numeric(value: number | string | null | undefined): number | null {
  const n = typeof value === 'string' ? Number(value) : (value ?? 0)
  return Number.isNaN(n) ? null : n
}

function magnitude(value: number): string {
  return Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatSigned(value: number | string | null | undefined): string {
  const n = numeric(value)
  if (n === null) return '—'
  return n < 0 ? `-${magnitude(n)}` : magnitude(n)
}

export function formatAccounting(value: number | string | null | undefined): string {
  const n = numeric(value)
  if (n === null) return '—'
  return n < 0 ? `(${magnitude(n)})` : magnitude(n)
}

export function formatDrCr(value: number | string | null | undefined): {
  amount: string
  side: 'Dr' | 'Cr'
} {
  const n = numeric(value) ?? 0
  return { amount: magnitude(n), side: n < 0 ? 'Cr' : 'Dr' }
}

export type AmountStyle = 'drcr' | 'signed' | 'accounting'

export function formatAmount(
  value: number | string | null | undefined,
  { style = 'signed' }: { style?: AmountStyle } = {},
): string {
  if (style === 'accounting') return formatAccounting(value)
  if (style === 'drcr') {
    const result = formatDrCr(value)
    return `${result.amount} ${result.side}`
  }
  return formatSigned(value)
}

/** General money formatting is plain signed; accounting parentheses are opt-in. */
export function formatMoney(value: number | string | null | undefined): string {
  return formatSigned(value)
}

/** Indian currency / number formatting (en-IN grouping), e.g. "12,34,567.50" or "₹ 12,34,567.50". */
export function formatIndian(
  value: number | string | null | undefined,
  { symbol = false, decimals = 2 }: { symbol?: boolean; decimals?: number } = {},
): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = numeric(value)
  if (n === null) return '—'
  const isNeg = n < 0
  const absVal = Math.abs(n)
  const formatted = absVal.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  const prefix = symbol ? '₹ ' : ''
  return isNeg ? `-${prefix}${formatted}` : `${prefix}${formatted}`
}

