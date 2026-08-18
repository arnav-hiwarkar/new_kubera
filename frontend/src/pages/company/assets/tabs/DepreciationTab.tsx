import { useState } from 'react'
import { Card, Field, Input, Select, Textarea, Button, Spinner, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { AssetDetail } from '@/api/hooks/assets'
import { useUpdateAsset } from '@/api/hooks/assets'
import { useItBlocks, useAssetCategories } from '@/api/hooks/assetMasters'
import { useFinancialYears } from '@/api/hooks/financialYears'
import { useDepreciationRuns, useCreateDepreciationRun, useAssetDepreciationLines, useFinalizeDepreciationRun } from '@/api/hooks/depreciation'
import { DEPRECIATION_METHOD } from '@/api/enums'
import type { AssetUpdate } from '@/api/types'
import { dateOrDash, money, months, num } from '../assetFormat'
import { numOrNull, useSectionForm } from '../useSectionForm'
import { DerivedRow, SectionShell } from './SectionShell'
import { Play, CheckCircle } from 'lucide-react'

export function DepreciationTab({
  detail,
  locked,
}: {
  detail: AssetDetail
  locked: boolean
}) {
  const asset = detail.asset
  const toast = useToast()
  const update = useUpdateAsset()
  const { data: blocks = [] } = useItBlocks()
  const { data: categories = [] } = useAssetCategories()
  const { data: fys = [] } = useFinancialYears()
  const { data: runs = [] } = useDepreciationRuns()
  const createRun = useCreateDepreciationRun()
  const finalizeRun = useFinalizeDepreciationRun()

  const [selectedFyId, setSelectedFyId] = useState<string>(fys[0]?.id || '')

  const activeFyId = selectedFyId || fys[0]?.id || ''
  const latestRunForFy = runs.find((r) => r.financial_year_id === activeFyId)
  const { data: runLines = [], isLoading: linesLoading } = useAssetDepreciationLines(
    latestRunForFy?.id || '',
  )
  const assetLine = runLines.find((l) => l.asset_id === asset.id)

  const handleRunDepreciation = async () => {
    if (!activeFyId) {
      toast.error('Please create or select a financial year first')
      return
    }
    try {
      await createRun.mutateAsync({ financialYearId: activeFyId })
      toast.success('Depreciation run computed successfully')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to run depreciation')
    }
  }

  const handleFinalize = async () => {
    if (!latestRunForFy) return
    try {
      await finalizeRun.mutateAsync(latestRunForFy.id)
      toast.success('Depreciation run finalized')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to finalize run')
    }
  }

  const category = categories.find((c) => c.id === asset.category_id)
  const categoryLife = category?.default_useful_life_months ?? null

  const form = useSectionForm(
    {
      useful_life_months: asset.useful_life_months,
      dep_method: asset.dep_method,
      residual_pct: asset.residual_pct,
      useful_life_override_reason: asset.useful_life_override_reason ?? '',
      it_block_id: asset.it_block_id,
      it_dep_rate: asset.it_dep_rate,
      it_put_to_use_date: asset.it_put_to_use_date,
      available_for_use_date: asset.available_for_use_date,
      capitalization_date: asset.capitalization_date,
      warranty_start_date: asset.warranty_start_date,
      warranty_months: asset.warranty_months,
      is_pre_cutover: asset.is_pre_cutover,
      opening_accumulated_depreciation: asset.opening_accumulated_depreciation,
      opening_wdv: asset.opening_wdv,
      opening_it_wdv: asset.opening_it_wdv,
    },
    async (patch) => {
      try {
        await update.mutateAsync({ id: asset.id, body: patch as AssetUpdate })
        toast.success('Saved')
      } catch (e) {
        if (e instanceof ApiError) {
          const d = e.detail as { message?: string; locked_fields?: string[] } | string
          if (typeof d === 'object' && d?.message) {
            toast.error(`${d.message} (${(d.locked_fields ?? []).join(', ')})`)
            return
          }
          toast.error(typeof d === 'string' ? d : e.message)
          return
        }
        toast.error(e instanceof Error ? e.message : 'Save failed')
      }
    },
  )
  const { values, set } = form

  const lifeDiffers =
    categoryLife !== null &&
    values.useful_life_months !== null &&
    Number(values.useful_life_months) !== categoryLife

  const cost = num(asset.original_cost)
  const residual = num(values.residual_pct)
  const residualAmount = cost !== null && residual !== null ? (cost * residual) / 100 : null
  const depreciableBase = cost !== null && residualAmount !== null ? cost - residualAmount : null

  return (
    <SectionShell
      title="Depreciation"
      description="Two books, from one set of inputs: Companies Act (Schedule II, per asset) and Income Tax Act (Appendix I, block-wise)."
      dirty={form.dirty}
      saving={form.saving}
      onSave={form.save}
      onReset={form.reset}
      readOnlyNote={
        locked
          ? 'These inputs are locked because the asset is capitalized and has begun depreciating. A revised useful life applies prospectively and is recorded as an adjustment.'
          : undefined
      }
    >
      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Companies Act — Schedule II</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field
            label="Useful life (months)"
            required
            hint={categoryLife !== null ? `Category default: ${months(categoryLife)}` : undefined}
          >
            <Input
              type="number"
              min={1}
              value={values.useful_life_months ?? ''}
              disabled={locked}
              aria-label="Useful life (months)"
              onChange={(e) => set('useful_life_months', numOrNull(e.target.value))}
            />
          </Field>
          <Field label="Method" required>
            <Select
              value={values.dep_method ?? ''}
              disabled={locked}
              aria-label="Depreciation method"
              onChange={(e) => set('dep_method', (e.target.value || null) as typeof values.dep_method)}
            >
              <option value="">Not set</option>
              {DEPRECIATION_METHOD.map((m) => (
                <option key={m} value={m}>
                  {m === 'slm' ? 'SLM — Straight Line' : 'WDV — Written Down Value'}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Residual value %" required hint="Schedule II normally caps this at 5%">
            <Input
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={values.residual_pct ?? ''}
              disabled={locked}
              aria-label="Residual value %"
              onChange={(e) => {
                const n = numOrNull(e.target.value)
                set('residual_pct', n === null ? null : String(n))
              }}
            />
          </Field>
        </div>

        {lifeDiffers && (
          <Field
            className="mt-3"
            label="Reason for differing useful life"
            required
            hint={`Required because this differs from the category default of ${months(categoryLife)}.`}
          >
            <Textarea
              value={values.useful_life_override_reason}
              disabled={locked}
              aria-label="Reason for differing useful life"
              onChange={(e) => set('useful_life_override_reason', e.target.value)}
            />
          </Field>
        )}
      </fieldset>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Income Tax Act — Appendix I</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Asset block" required>
            <Select
              value={values.it_block_id ?? ''}
              disabled={locked}
              aria-label="Income-tax asset block"
              onChange={(e) => {
                const id = e.target.value || null
                set('it_block_id', id)
                const block = blocks.find((b) => b.id === id)
                if (block) set('it_dep_rate', String(block.dep_rate))
              }}
            >
              <option value="">Not set</option>
              {blocks.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.code} — {b.name} ({b.dep_rate}%)
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Depreciation rate %" required>
            <Input
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={values.it_dep_rate ?? ''}
              disabled={locked}
              aria-label="Income-tax depreciation rate"
              onChange={(e) => {
                const n = numOrNull(e.target.value)
                set('it_dep_rate', n === null ? null : String(n))
              }}
            />
          </Field>
          <Field label="Put-to-use date" required hint="Before or after 180 days changes the first year's rate">
            <Input
              type="date"
              value={values.it_put_to_use_date ?? ''}
              disabled={locked}
              aria-label="Income-tax put-to-use date"
              onChange={(e) => set('it_put_to_use_date', e.target.value || null)}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Dates</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Available-for-use date" required hint="Depreciation starts here, pro-rata">
            <Input
              type="date"
              value={values.available_for_use_date ?? ''}
              disabled={locked}
              aria-label="Available-for-use date"
              onChange={(e) => set('available_for_use_date', e.target.value || null)}
            />
          </Field>
          <Field label="Capitalization date" required>
            <Input
              type="date"
              value={values.capitalization_date ?? ''}
              disabled={locked}
              aria-label="Capitalization date"
              onChange={(e) => set('capitalization_date', e.target.value || null)}
            />
          </Field>
          <Field label="Warranty start date">
            <Input
              type="date"
              value={values.warranty_start_date ?? ''}
              aria-label="Warranty start date"
              onChange={(e) => set('warranty_start_date', e.target.value || null)}
            />
          </Field>
          <Field
            label="Warranty period (months)"
            hint={
              asset.warranty_expiry_date
                ? `Expires ${dateOrDash(asset.warranty_expiry_date)}`
                : 'Expiry is calculated, not typed'
            }
          >
            <Input
              type="number"
              min={0}
              value={values.warranty_months ?? ''}
              aria-label="Warranty period (months)"
              onChange={(e) => set('warranty_months', numOrNull(e.target.value))}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Cutover / opening balances</legend>
        <label className="flex items-start gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            className="mt-1"
            checked={!!values.is_pre_cutover}
            disabled={locked}
            aria-label="Owned before the register cutover"
            onChange={(e) => set('is_pre_cutover', e.target.checked)}
          />
          <span>
            This asset was already owned before the company started using the register.
            <span className="block text-xs text-text-muted">
              Depreciation then continues from the balances below instead of being
              recomputed from the capitalization date.
            </span>
          </span>
        </label>

        {values.is_pre_cutover && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Opening accumulated depreciation" required>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={values.opening_accumulated_depreciation ?? ''}
                disabled={locked}
                aria-label="Opening accumulated depreciation"
                onChange={(e) => {
                  const n = numOrNull(e.target.value)
                  set('opening_accumulated_depreciation', n === null ? null : String(n))
                }}
              />
            </Field>
            <Field label="Opening WDV (books)" required>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={values.opening_wdv ?? ''}
                disabled={locked}
                aria-label="Opening WDV (books)"
                onChange={(e) => {
                  const n = numOrNull(e.target.value)
                  set('opening_wdv', n === null ? null : String(n))
                }}
              />
            </Field>
            <Field label="Opening WDV (tax)">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={values.opening_it_wdv ?? ''}
                disabled={locked}
                aria-label="Opening WDV (tax)"
                onChange={(e) => {
                  const n = numOrNull(e.target.value)
                  set('opening_it_wdv', n === null ? null : String(n))
                }}
              />
            </Field>
          </div>
        )}
      </fieldset>

      {/* Depreciation Calculation & Live Schedule */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <h4 className="text-sm font-semibold text-text-primary">Depreciation Calculation &amp; Schedule</h4>
            <p className="text-xs text-text-muted">
              Schedule II computation for the financial year
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              aria-label="Select Financial Year"
              value={activeFyId}
              onChange={(e) => setSelectedFyId(e.target.value)}
              className="h-8 rounded-btn border border-border-strong bg-bg-surface px-2.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {fys.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label} ({f.status})
                </option>
              ))}
            </select>
            <Button
              size="sm"
              onClick={handleRunDepreciation}
              loading={createRun.isPending}
              disabled={!activeFyId}
            >
              <Play className="mr-1 h-3.5 w-3.5" />
              Compute
            </Button>
            {latestRunForFy && latestRunForFy.status === 'draft' && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleFinalize}
                loading={finalizeRun.isPending}
              >
                <CheckCircle className="mr-1 h-3.5 w-3.5" />
                Finalize
              </Button>
            )}
          </div>
        </div>

        {linesLoading ? (
          <Spinner className="mx-auto my-6 h-5 w-5" />
        ) : assetLine ? (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
            <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
              <span className="text-text-muted">Opening Gross Block</span>
              <p className="mt-0.5 font-semibold text-text-primary tabular-nums">{money(String(assetLine.opening_gross_block))}</p>
            </div>
            <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
              <span className="text-text-muted">Additions / Disposals</span>
              <p className="mt-0.5 font-semibold text-text-primary tabular-nums">
                +{money(String(assetLine.additions))} / -{money(String(assetLine.disposals))}
              </p>
            </div>
            <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
              <span className="text-text-muted">Depreciation (FY)</span>
              <p className="mt-0.5 font-semibold text-status-action tabular-nums">{money(String(assetLine.depreciation_for_year))}</p>
            </div>
            <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
              <span className="text-text-muted">Closing Carrying Amount (NBV)</span>
              <p className="mt-0.5 font-semibold text-status-verified tabular-nums">{money(String(assetLine.closing_carrying_amount))}</p>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-xs text-text-muted">
            No calculation run recorded yet for this financial year. Click "Compute" above to execute the depreciation engine.
          </p>
        )}
      </Card>

      <Card className="p-4">
        <h4 className="mb-2 text-sm font-semibold text-text-primary">Derived Parameters</h4>
        <DerivedRow label="Original accounting cost" value={money(asset.original_cost)} />
        <DerivedRow
          label="Residual value"
          value={residualAmount === null ? '—' : money(String(residualAmount))}
          hint={residual !== null ? `${residual}% of original cost` : undefined}
        />
        <DerivedRow
          label="Depreciable base"
          value={depreciableBase === null ? '—' : money(String(depreciableBase))}
          hint="Cost less residual value"
          emphasis
        />
        <DerivedRow label="Warranty expiry" value={dateOrDash(asset.warranty_expiry_date)} />
      </Card>
    </SectionShell>
  )
}

