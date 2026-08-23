import { describe, expect, it } from 'vitest'
import { traceFromCostPreview } from './traceFromCostPreview'
import { ADD, DIV, MUL, SUB } from './types'

const INTRA_STATE = {
  quantity: 1,
  gross_basic_price: '100000.00',
  discount_amount: '5000.00',
  net_basic_price: '95000.00',
  gst_rate: '18.00',
  gst_split_basis: 'intra_state',
  cgst_amount: '8550.00',
  sgst_amount: '8550.00',
  igst_amount: '0.00',
  total_gst: '17100.00',
  recoverable_gst: '17100.00',
  capitalizable_gst: '0.00',
  freight_cost: '2000.00',
  installation_cost: '1500.00',
  other_capitalizable_cost: '0.00',
  landed_cost: '98500.00',
  total_acquisition_outlay: '115600.00',
  per_unit_cost: '98500.00',
  itc_treatment: 'eligible',
}

function step(trace: ReturnType<typeof traceFromCostPreview>, key: string) {
  const found = trace.steps.find((s) => s.key === key)
  if (!found) throw new Error(`no step ${key} in ${trace.steps.map((s) => s.key).join(', ')}`)
  return found
}

describe('traceFromCostPreview', () => {
  it('builds the price group with formula, substitution and result', () => {
    const trace = traceFromCostPreview(INTRA_STATE)

    const net = step(trace, 'net_basic_price')
    expect(net.formula).toBe(`Gross basic price${SUB}Discount`)
    expect(net.substitution).toBe(`100,000.00${SUB}5,000.00`)
    expect(net.result).toBe('95,000.00')
    expect(net.unit).toBe('money')
  })

  it('splits GST into CGST and SGST for an intra-state supply', () => {
    const trace = traceFromCostPreview(INTRA_STATE, { gstBasisLabel: 'Intra-state — CGST + SGST' })

    expect(step(trace, 'gst_split_basis').result).toBe('Intra-state — CGST + SGST')
    expect(step(trace, 'cgst_amount').substitution).toBe(`95,000.00${MUL}9.00%`)
    expect(step(trace, 'sgst_amount').result).toBe('8,550.00')
    expect(trace.steps.find((s) => s.key === 'igst_amount')).toBeUndefined()

    const total = step(trace, 'total_gst')
    expect(total.result).toBe('17,100.00')
    expect(total.emphasis).toBe(true)
  })

  it('shows recoverable GST as excluded from cost', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const recoverable = step(trace, 'recoverable_gst')
    expect(recoverable.result).toBe('17,100.00')
    expect(recoverable.note ?? '').toMatch(/not part of the asset/i)
  })

  it('explains blocked ITC as capitalized into cost', () => {
    const trace = traceFromCostPreview({
      ...INTRA_STATE,
      itc_treatment: 'blocked',
      recoverable_gst: '0.00',
      capitalizable_gst: '17100.00',
      landed_cost: '115600.00',
    })
    const capitalizable = step(trace, 'capitalizable_gst')
    expect(capitalizable.result).toBe('17,100.00')
    expect(capitalizable.note ?? '').toMatch(/17\(5\)/)
  })

  it('shows IGST alone for an inter-state supply', () => {
    const trace = traceFromCostPreview({
      ...INTRA_STATE,
      gst_split_basis: 'inter_state',
      cgst_amount: '0.00',
      sgst_amount: '0.00',
      igst_amount: '17100.00',
    })
    expect(step(trace, 'igst_amount').result).toBe('17,100.00')
    expect(trace.steps.find((s) => s.key === 'cgst_amount')).toBeUndefined()
  })

  it('flags a manual split as reconciled to the invoice, without a rate formula', () => {
    const trace = traceFromCostPreview({ ...INTRA_STATE, gst_split_basis: 'manual' })
    expect(step(trace, 'cgst_amount').formula).toBe('')
    expect(step(trace, 'gst_split_basis').note ?? '').toMatch(/invoice/i)
  })

  it('builds the capitalized cost total from its components', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const landed = step(trace, 'landed_cost')
    expect(landed.formula).toBe(
      `Net basic price${ADD}Capitalizable GST${ADD}Freight${ADD}Installation${ADD}Other capitalizable`,
    )
    expect(landed.substitution).toBe(
      `95,000.00${ADD}0.00${ADD}2,000.00${ADD}1,500.00${ADD}0.00`,
    )
    expect(landed.result).toBe('98,500.00')
    expect(landed.emphasis).toBe(true)
  })

  it('omits zero cost components so the total stays readable', () => {
    const trace = traceFromCostPreview({
      ...INTRA_STATE,
      freight_cost: '0.00',
      installation_cost: '0.00',
    })
    expect(trace.steps.find((s) => s.key === 'freight_cost')).toBeUndefined()
    expect(trace.steps.find((s) => s.key === 'installation_cost')).toBeUndefined()
  })

  it('shows per-unit allocation only when there is more than one unit', () => {
    const single = traceFromCostPreview(INTRA_STATE)
    expect(single.steps.find((s) => s.key === 'per_unit_cost')).toBeUndefined()

    const many = traceFromCostPreview({
      ...INTRA_STATE,
      quantity: 3,
      per_unit_cost: '32833.34',
    })
    const perUnit = step(many, 'per_unit_cost')
    expect(perUnit.formula).toBe(`Total capitalized value${DIV}Quantity`)
    expect(perUnit.substitution).toBe(`98,500.00${DIV}3`)
    expect(perUnit.note ?? '').toMatch(/sum/i)
  })

  it('distinguishes outlay from the depreciation base', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const outlay = step(trace, 'total_acquisition_outlay')
    expect(outlay.result).toBe('115,600.00')
    expect(outlay.note ?? '').toMatch(/not the depreciation base/i)
  })

  it('groups steps in contiguous runs and is never a projection', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const seen: string[] = []
    for (const s of trace.steps) {
      if (seen[seen.length - 1] !== s.group) {
        expect(seen).not.toContain(s.group)
        seen.push(s.group)
      }
    }
    expect(seen).toEqual(['Price', 'GST', 'Capitalized cost'])
    expect(trace.is_projection).toBe(false)
  })
})
