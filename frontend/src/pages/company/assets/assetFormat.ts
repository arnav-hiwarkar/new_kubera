import { formatMoney } from '@/lib/format'

/**
 * The backend stores money and rates as Decimal, which Pydantic serializes to JSON
 * as a *string* (never a float — that would lose paise). These helpers are the only
 * place that conversion happens, so no component does `Number(x)` inline and
 * accidentally renders "NaN" for a null.
 */

export function num(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'string' ? Number(value) : value
  return Number.isNaN(n) ? null : n
}

/** Money for display, with an em dash for genuinely absent values. */
export function money(value: string | number | null | undefined): string {
  const n = num(value)
  return n === null ? '—' : `₹${formatMoney(n)}`
}

/** Money for a numeric input's value — empty string when absent, never "null". */
export function inputValue(value: string | number | null | undefined): string {
  const n = num(value)
  return n === null ? '' : String(n)
}

export function pct(value: string | number | null | undefined): string {
  const n = num(value)
  return n === null ? '—' : `${n}%`
}

export function months(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value % 12 === 0) return `${value / 12} yr${value === 12 ? '' : 's'}`
  return `${value} mo`
}

export function dateOrDash(value: string | null | undefined): string {
  if (!value) return '—'
  // Backend sends plain YYYY-MM-DD; parsing that as a Date shifts it by the local
  // timezone offset, so format the parts directly.
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) return value
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${d} ${monthNames[m - 1]} ${y}`
}

/** How a GST split was arrived at, in words the user can act on. */
export const GST_BASIS_LABEL: Record<string, string> = {
  intra_state: 'Intra-state — CGST + SGST',
  inter_state: 'Inter-state — IGST',
  assumed_intra_state: 'Assumed intra-state (supplier or branch state unknown)',
  manual: 'Manually entered to match the invoice',
}

export const DOC_ROLE_LABEL: Record<string, string> = {
  invoice: 'Supplier invoice',
  purchase_order: 'Purchase order',
  grn: 'GRN / delivery challan',
  eway_bill: 'E-way bill',
  approval: 'Approval document',
  asset_photo: 'Asset photograph',
  serial_photo: 'Serial-number photograph',
  warranty: 'Warranty document',
  insurance: 'Insurance policy',
  amc: 'AMC / service contract',
  test_certificate: 'Installation / testing certificate',
  manual: 'Technical manual',
  customs: 'Customs / bill of entry',
  lease: 'Lease agreement',
  other: 'Other',
}
