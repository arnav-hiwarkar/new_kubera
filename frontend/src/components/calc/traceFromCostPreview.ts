import { formatMoney } from '@/lib/format'
import { ADD, DIV, MUL, SUB, type CalcStep, type CalcTrace } from './types'

/**
 * Turns an acquisition's cost figures into a calculation trace.
 *
 * There is no backend trace for costing: `CostPreviewResponse` and the saved
 * acquisition already carry every intermediate, and there is no historical version to
 * reconcile. This is presentation over data the caller already holds.
 */

/** Every field this needs. `CostPreviewResponse` and `AcquisitionResponse` both satisfy it. */
export interface CostTraceInput {
  quantity?: number | null
  gross_basic_price?: string | number | null
  discount_amount?: string | number | null
  net_basic_price?: string | number | null
  gst_rate?: string | number | null
  gst_split_basis?: string | null
  cgst_amount?: string | number | null
  sgst_amount?: string | number | null
  igst_amount?: string | number | null
  total_gst?: string | number | null
  recoverable_gst?: string | number | null
  capitalizable_gst?: string | number | null
  freight_cost?: string | number | null
  installation_cost?: string | number | null
  other_capitalizable_cost?: string | number | null
  landed_cost?: string | number | null
  total_acquisition_outlay?: string | number | null
  per_unit_cost?: string | number | null
  itc_treatment?: string | null
}

export interface CostTraceOptions {
  title?: string
  /** Passed in rather than looked up, to keep this component free of page imports. */
  gstBasisLabel?: string
}

const GROUP_PRICE = 'Price'
const GROUP_GST = 'GST'
const GROUP_COST = 'Capitalized cost'

/** Decimals arrive as strings from Pydantic; 0 is the right reading of an absent cost. */
function n(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const parsed = typeof value === 'string' ? Number(value) : value
  return Number.isNaN(parsed) ? 0 : parsed
}

const m = (value: string | number | null | undefined) => formatMoney(n(value))
const p = (value: string | number | null | undefined) => n(value).toFixed(2)

export function traceFromCostPreview(
  input: CostTraceInput,
  options: CostTraceOptions = {},
): CalcTrace {
  const steps: CalcStep[] = []

  const add = (
    step: Pick<CalcStep, 'key' | 'group' | 'label' | 'result'> & Partial<CalcStep>,
  ) => {
    steps.push({
      formula: '',
      substitution: '',
      unit: 'money',
      emphasis: false,
      note: null,
      ...step,
    })
  }

  const quantity = input.quantity ?? 1
  const basis = input.gst_split_basis ?? null
  const isManual = basis === 'manual'
  const isInterState = n(input.igst_amount) > 0

  // --- Price ---------------------------------------------------------------
  add({ key: 'gross_basic_price', group: GROUP_PRICE, label: 'Gross basic price', result: m(input.gross_basic_price) })
  add({ key: 'discount_amount', group: GROUP_PRICE, label: 'Less discount', result: m(input.discount_amount) })
  add({
    key: 'net_basic_price',
    group: GROUP_PRICE,
    label: 'Net basic price',
    formula: `Gross basic price${SUB}Discount`,
    substitution: `${m(input.gross_basic_price)}${SUB}${m(input.discount_amount)}`,
    result: m(input.net_basic_price),
  })

  // --- GST -----------------------------------------------------------------
  add({ key: 'gst_rate', group: GROUP_GST, label: 'GST rate', result: p(input.gst_rate), unit: 'percent' })
  add({
    key: 'gst_split_basis',
    group: GROUP_GST,
    label: 'Split basis',
    result: options.gstBasisLabel ?? basis ?? '—',
    unit: 'none',
    note: isManual
      ? 'These amounts were entered by hand to reconcile with the invoice, so no rate is applied.'
      : null,
  })

  // Half the rate each for an intra-state supply; the whole rate as IGST otherwise.
  const halfRate = p(n(input.gst_rate) / 2)
  if (isInterState) {
    add({
      key: 'igst_amount',
      group: GROUP_GST,
      label: 'IGST',
      formula: isManual ? '' : `Net basic price${MUL}GST rate`,
      substitution: isManual ? '' : `${m(input.net_basic_price)}${MUL}${p(input.gst_rate)}%`,
      result: m(input.igst_amount),
    })
  } else {
    add({
      key: 'cgst_amount',
      group: GROUP_GST,
      label: 'CGST',
      formula: isManual ? '' : `Net basic price${MUL}Half the GST rate`,
      substitution: isManual ? '' : `${m(input.net_basic_price)}${MUL}${halfRate}%`,
      result: m(input.cgst_amount),
    })
    add({
      key: 'sgst_amount',
      group: GROUP_GST,
      label: 'SGST',
      formula: isManual ? '' : `Net basic price${MUL}Half the GST rate`,
      substitution: isManual ? '' : `${m(input.net_basic_price)}${MUL}${halfRate}%`,
      result: m(input.sgst_amount),
    })
  }

  add({
    key: 'total_gst',
    group: GROUP_GST,
    label: 'Total GST',
    formula: isInterState ? 'IGST' : `CGST${ADD}SGST`,
    substitution: isInterState
      ? m(input.igst_amount)
      : `${m(input.cgst_amount)}${ADD}${m(input.sgst_amount)}`,
    result: m(input.total_gst),
    emphasis: true,
  })
  add({
    key: 'recoverable_gst',
    group: GROUP_GST,
    label: 'Recoverable GST (input tax credit)',
    result: m(input.recoverable_gst),
    note: 'Recoverable tax is not part of the asset’s cost, so it does not depreciate.',
  })
  add({
    key: 'capitalizable_gst',
    group: GROUP_GST,
    label: 'Capitalizable GST',
    formula: `Total GST${SUB}Recoverable GST`,
    substitution: `${m(input.total_gst)}${SUB}${m(input.recoverable_gst)}`,
    result: m(input.capitalizable_gst),
    note:
      input.itc_treatment === 'blocked'
        ? 'Credit is blocked for this class of asset (CGST Act s.17(5)), so the tax is capitalized into cost and depreciates.'
        : 'Tax for which no credit is available becomes part of cost and depreciates.',
  })

  // --- Capitalized cost ----------------------------------------------------
  // Zero components are omitted: an unspent line adds nothing but length.
  if (n(input.freight_cost) !== 0) {
    add({ key: 'freight_cost', group: GROUP_COST, label: 'Add freight', result: m(input.freight_cost) })
  }
  if (n(input.installation_cost) !== 0) {
    add({ key: 'installation_cost', group: GROUP_COST, label: 'Add installation', result: m(input.installation_cost) })
  }
  if (n(input.other_capitalizable_cost) !== 0) {
    add({
      key: 'other_capitalizable_cost',
      group: GROUP_COST,
      label: 'Add other capitalizable cost',
      result: m(input.other_capitalizable_cost),
    })
  }
  add({
    key: 'landed_cost',
    group: GROUP_COST,
    label: 'Total capitalized value',
    formula: `Net basic price${ADD}Capitalizable GST${ADD}Freight${ADD}Installation${ADD}Other capitalizable`,
    substitution: [
      m(input.net_basic_price),
      m(input.capitalizable_gst),
      m(input.freight_cost),
      m(input.installation_cost),
      m(input.other_capitalizable_cost),
    ].join(ADD),
    result: m(input.landed_cost),
    emphasis: true,
  })
  if (quantity > 1) {
    add({
      key: 'per_unit_cost',
      group: GROUP_COST,
      label: 'Per-unit cost',
      formula: `Total capitalized value${DIV}Quantity`,
      substitution: `${m(input.landed_cost)}${DIV}${quantity}`,
      result: m(input.per_unit_cost),
      note: 'Rounded so the units sum to exactly the total, to the paisa.',
    })
  }
  add({
    key: 'total_acquisition_outlay',
    group: GROUP_COST,
    label: 'Total acquisition outlay',
    formula: `Total capitalized value${ADD}Recoverable GST`,
    substitution: `${m(input.landed_cost)}${ADD}${m(input.recoverable_gst)}`,
    result: m(input.total_acquisition_outlay),
    note: 'Total cash paid, including recoverable tax — not the depreciation base.',
  })

  return {
    title: options.title ?? 'Acquisition cost build-up',
    basis: `Quantity ${quantity}; GST at ${p(input.gst_rate)}%`,
    steps,
    is_projection: false,
    computed_at: null,
  }
}
