import { useMemo, useState } from 'react'
import { Card } from '@/components/ui'
import { CalculationDrawer, ExplainLink, type TraceTab } from '@/components/calc'
import { ApiError } from '@/api/http'
import { useExplainDepreciation } from '@/api/hooks/depreciation'
import { useFinancialYears } from '@/api/hooks/financialYears'
import { dateOrDash, money, num } from '../assetFormat'
import { DerivedRow } from './SectionShell'

/**
 * The figures the register derives from the depreciation inputs above it.
 *
 * These are not a run's output, so the drawer here always projects: it answers "what
 * would this asset depreciate, on the inputs currently on screen". The current
 * financial year is used, since a derived parameter is not tied to a particular year.
 */
export function DepreciationDerivedCard({
  assetId,
  originalCost,
  residualPct,
  warrantyExpiryDate,
}: {
  assetId: string
  originalCost: string | null
  residualPct: string | null
  warrantyExpiryDate: string | null
}) {
  const { data: fys = [] } = useFinancialYears()
  const fyId = fys.find((f) => f.status === 'open')?.id ?? fys[0]?.id ?? ''

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [focusStep, setFocusStep] = useState<string | undefined>(undefined)

  const projection = useExplainDepreciation(assetId, fyId, drawerOpen)

  const tabs: TraceTab[] = useMemo(() => {
    const data = projection.data
    if (!data) return []
    return [
      { id: 'ca', label: 'Companies Act', trace: data.companies_act },
      ...(data.income_tax ? [{ id: 'it', label: 'Income Tax', trace: data.income_tax }] : []),
    ]
  }, [projection.data])

  const error =
    projection.error instanceof ApiError && typeof projection.error.detail === 'string'
      ? projection.error.detail
      : projection.error instanceof Error
        ? projection.error.message
        : null

  const open = (step?: string) => {
    setFocusStep(step)
    setDrawerOpen(true)
  }

  const cost = num(originalCost)
  const residual = num(residualPct)
  const residualAmount = cost !== null && residual !== null ? (cost * residual) / 100 : null
  const depreciableBase = cost !== null && residualAmount !== null ? cost - residualAmount : null

  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-text-primary">Derived Parameters</h4>
        <ExplainLink onClick={() => open()} />
      </div>
      <DerivedRow label="Original accounting cost" value={money(originalCost)} />
      <DerivedRow
        label="Residual value"
        value={residualAmount === null ? '—' : money(String(residualAmount))}
        hint={residual !== null ? `${residual}% of original cost` : undefined}
        onExplain={() => open('residual_value')}
      />
      <DerivedRow
        label="Depreciable base"
        value={depreciableBase === null ? '—' : money(String(depreciableBase))}
        hint="Cost less residual value"
        emphasis
        onExplain={() => open('depreciable_base')}
      />
      <DerivedRow label="Warranty expiry" value={dateOrDash(warrantyExpiryDate)} />

      <CalculationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        tabs={tabs}
        focusStep={focusStep}
        loading={projection.isLoading}
        error={error}
        emptyNote="There is no financial year to compute against yet."
      />
    </Card>
  )
}
