import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CalculationDrawer } from './CalculationDrawer'
import { traceToText } from './traceToText'
import type { CalcTrace } from './types'

const CA: CalcTrace = {
  title: 'Depreciation — Companies Act Schedule II — FY 2024-25',
  basis: 'SLM — straight line; useful life 60 months; residual 5.00%; original cost 100,000.00',
  is_projection: false,
  computed_at: '2025-04-01T10:00:00Z',
  steps: [
    { key: 'original_cost', group: 'Inputs', label: 'Original cost', formula: '', substitution: '', result: '100,000.00', unit: 'money', emphasis: false },
    { key: 'depreciable_base', group: 'Rate', label: 'Depreciable base', formula: 'Original cost − Residual value', substitution: '100,000.00 − 5,000.00', result: '95,000.00', unit: 'money', emphasis: false },
    { key: 'depreciation_for_year', group: 'Charge for the year', label: 'Depreciation for the year', formula: 'Lower of the charge and the remaining depreciable base', substitution: 'lower of 19,000.00 and 95,000.00', result: '19,000.00', unit: 'money', emphasis: true, note: null },
    { key: 'effective_rate_pct', group: 'Roll-forward', label: 'Effective rate on cost', formula: 'Depreciation for the year ÷ Original cost', substitution: '19,000.00 ÷ 100,000.00', result: '19.00', unit: 'percent', emphasis: false },
  ],
}

const IT: CalcTrace = {
  title: 'Depreciation — Income Tax Act, block — FY 2024-25',
  basis: 'Block Plant & Machinery (General); prescribed rate 15.00%',
  is_projection: false,
  computed_at: '2025-04-01T10:00:00Z',
  steps: [
    { key: 'total_depreciation', group: 'Rate application', label: 'Total depreciation for the block', formula: 'Full-rate depreciation + Half-rate depreciation', substitution: '90,000.00 + 3,000.00', result: '93,000.00', unit: 'money', emphasis: true },
  ],
}

const TABS = [
  { id: 'ca', label: 'Companies Act', trace: CA },
  { id: 'it', label: 'Income Tax', trace: IT },
]

describe('CalculationDrawer', () => {
  it('renders each step as label, formula, substitution and result', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)

    expect(screen.getByText('Depreciable base')).toBeTruthy()
    expect(screen.getByText('Original cost − Residual value')).toBeTruthy()
    expect(screen.getByText('100,000.00 − 5,000.00')).toBeTruthy()
    expect(screen.getByText('₹95,000.00')).toBeTruthy()
  })

  it('adds the unit symbol without touching the digits', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.getByText('19.00%')).toBeTruthy()
  })

  it('renders a heading per group', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.getByText('Inputs')).toBeTruthy()
    expect(screen.getByText('Rate')).toBeTruthy()
    expect(screen.getByText('Charge for the year')).toBeTruthy()
  })

  it('shows the basis so the inputs a trace used are visible', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.getByText(/useful life 60 months/)).toBeTruthy()
  })

  it('shows tabs only when there are two books', () => {
    const { unmount } = render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.queryByText('Income Tax')).toBeNull()
    unmount()

    render(<CalculationDrawer open onClose={vi.fn()} tabs={TABS} />)
    expect(screen.getByText('Income Tax')).toBeTruthy()
  })

  it('opens on the tab that contains the focused step', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={TABS} focusStep="total_depreciation" />)
    // The Income Tax tab's content is showing, not the Companies Act one.
    expect(screen.getByText('Total depreciation for the block')).toBeTruthy()
    expect(screen.queryByText('Depreciable base')).toBeNull()
  })

  it('marks the focused step so the eye lands on it', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} focusStep="depreciable_base" />)
    const row = document.getElementById('calc-step-depreciable_base')
    expect(row).toBeTruthy()
    expect(row?.getAttribute('data-focused')).toBe('true')
  })

  it('labels a projection unmistakably', () => {
    render(
      <CalculationDrawer
        open
        onClose={vi.fn()}
        tabs={[{ ...TABS[0], trace: { ...CA, is_projection: true, computed_at: null } }]}
      />,
    )
    expect(screen.getByText(/not the recorded figure/i)).toBeTruthy()
    expect(screen.getByText(/Recompute the run to record this/i)).toBeTruthy()
  })

  it('shows when a recorded run was computed', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.queryByText(/not the recorded figure/i)).toBeNull()
    expect(screen.getByText(/Computed/)).toBeTruthy()
  })

  it('states the run status, so a draft is not read as the filed figure', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} contextNote="Draft run" />)
    expect(screen.getByText(/Draft run/)).toBeTruthy()
  })

  it('renders a 422 message as an explanation', () => {
    render(
      <CalculationDrawer
        open
        onClose={vi.fn()}
        tabs={[]}
        error="Asset X is marked pre-cutover but carries neither an opening WDV nor opening accumulated depreciation."
      />,
    )
    expect(screen.getByText(/pre-cutover/)).toBeTruthy()
  })

  it('offers a projection when a run predates traces', () => {
    const onShowProjection = vi.fn()
    render(
      <CalculationDrawer
        open
        onClose={vi.fn()}
        tabs={[]}
        emptyNote="This run was recorded before calculation traces were kept."
        onShowProjection={onShowProjection}
      />,
    )
    expect(screen.getByText(/before calculation traces were kept/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /projection/i }))
    expect(onShowProjection).toHaveBeenCalled()
  })

  it('renders nothing when closed', () => {
    render(<CalculationDrawer open={false} onClose={vi.fn()} tabs={TABS} />)
    expect(screen.queryByText('Depreciable base')).toBeNull()
  })
})

describe('traceToText', () => {
  it('renders a pasteable plain-text version', () => {
    const text = traceToText(CA)
    expect(text).toContain('Depreciation — Companies Act Schedule II — FY 2024-25')
    expect(text).toContain('SLM — straight line')
    expect(text).toContain('Rate')
    expect(text).toContain('Depreciable base')
    expect(text).toContain('Original cost − Residual value')
    expect(text).toContain('100,000.00 − 5,000.00')
    expect(text).toContain('95,000.00')
  })

  it('marks a projection in the text too, so a paste cannot mislead', () => {
    const text = traceToText({ ...CA, is_projection: true, computed_at: null })
    expect(text).toMatch(/projection/i)
  })
})
