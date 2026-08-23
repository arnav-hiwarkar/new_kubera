import { Field, Input, Select, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { AssetDetail } from '@/api/hooks/assets'
import { useUpdateAsset } from '@/api/hooks/assets'
import { useItBlocks, useAssetCategories } from '@/api/hooks/assetMasters'
import type { AssetUpdate } from '@/api/types'
import { DEPRECIATION_METHOD } from '@/api/enums'
import { dateOrDash, months } from '../assetFormat'
import { numOrNull, useSectionForm } from '../useSectionForm'
import { SectionShell } from './SectionShell'
import { DepreciationDerivedCard } from './DepreciationDerivedCard'
import { DepreciationRunCard } from './DepreciationRunCard'

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
              Depreciation continues from the balances below instead of being recomputed
              from the capitalization date. The opening WDV you enter is what the asset
              depreciates from — enter the real carrying amount, which may differ from
              cost less accumulated depreciation if the asset was impaired or revalued.
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
            <Field
              label="Opening WDV (tax)"
              required
              hint="The tax written-down value differs from the book value and cannot be derived from it"
            >
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

      <DepreciationRunCard assetId={asset.id} itBlockId={values.it_block_id} />

      <DepreciationDerivedCard
        assetId={asset.id}
        originalCost={asset.original_cost}
        residualPct={values.residual_pct}
        warrantyExpiryDate={asset.warranty_expiry_date}
      />
    </SectionShell>
  )
}

