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

/** Accounting-style amount, e.g. 1,234.50 or (1,234.50) for negatives. */
export function formatMoney(value: number | string | null | undefined): string {
  const n = typeof value === 'string' ? Number(value) : (value ?? 0)
  if (Number.isNaN(n)) return '—'
  const abs = Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return n < 0 ? `(${abs})` : abs
}
