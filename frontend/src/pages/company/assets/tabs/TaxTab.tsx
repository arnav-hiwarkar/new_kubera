import { useMemo, useState } from 'react'
import { Card, Field, Input, Select, Switch, useToast } from '@/components/ui'
import { CalculationDrawer, ExplainLink, traceFromCostPreview } from '@/components/calc'
import { ApiError } from '@/api/http'
import type { AssetDetail } from '@/api/hooks/assets'
import { useUpdateAcquisition } from '@/api/hooks/assets'
import { ITC_TREATMENT, humanize } from '@/api/enums'
import type { AcquisitionUpdate } from '@/api/types'
import { GST_BASIS_LABEL, money } from '../assetFormat'
import { numOrNull, useSectionForm } from '../useSectionForm'
import { DerivedRow, SectionShell } from './SectionShell'

const ITC_HELP: Record<string, string> = {
  eligible: 'Credit is available, so the GST is recoverable and stays OUT of the asset cost.',
  blocked:
    'Credit is blocked (CGST Act s.17(5) — motor cars and similar), so the whole GST is capitalized INTO the asset cost and depreciates.',
  partial: 'Only part of the credit is available; the rest is capitalized into cost.',
}

export function TaxTab({
  detail,
  costLocked,
}: {
  detail: AssetDetail
  costLocked: boolean
}) {
  const acq = detail.acquisition
  const toast = useToast()
  const update = useUpdateAcquisition()

  const form = useSectionForm(
    {
      hsn_sac_code: acq?.hsn_sac_code ?? '',
      gst_rate: acq?.gst_rate ?? null,
      itc_treatment: acq?.itc_treatment ?? null,
      itc_eligible_pct: acq?.itc_eligible_pct ?? null,
      gst_amounts_overridden: acq?.gst_amounts_overridden ?? false,
      cgst_amount: acq?.cgst_amount ?? null,
      sgst_amount: acq?.sgst_amount ?? null,
      igst_amount: acq?.igst_amount ?? null,
    },
    async (patch) => {
      if (!acq) return
      try {
        await update.mutateAsync({ id: acq.id, body: patch as AcquisitionUpdate })
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

  const [calcOpen, setCalcOpen] = useState(false)
  const [calcStep, setCalcStep] = useState<string | undefined>(undefined)

  // Same source data as the Acquisition tab's build-up, framed as the tax question.
  const costTrace = useMemo(
    () =>
      traceFromCostPreview(acq ?? {}, {
        title: 'GST and input tax credit',
        gstBasisLabel: acq?.gst_split_basis ? GST_BASIS_LABEL[acq.gst_split_basis] : undefined,
      }),
    [acq],
  )

  const openCalc = (step?: string) => {
    setCalcStep(step)
    setCalcOpen(true)
  }

  if (!acq) {
    return <p className="text-sm text-text-muted">This asset has no acquisition record.</p>
  }

  const money2 = (v: string) => {
    const n = numOrNull(v)
    return n === null ? null : String(n)
  }
  const overridden = !!values.gst_amounts_overridden

  return (
    <SectionShell
      title="Tax & GST"
      description="The split between CGST+SGST and IGST is decided by comparing the supplier's state with the receiving branch's."
      dirty={form.dirty}
      saving={form.saving}
      onSave={form.save}
      onReset={form.reset}
      readOnlyNote={
        costLocked
          ? 'GST fields are locked because assets from this batch are capitalized — changing them would move the depreciation base.'
          : undefined
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="HSN / SAC code" hint="Optional">
          <Input
            value={values.hsn_sac_code}
            aria-label="HSN / SAC code"
            onChange={(e) => set('hsn_sac_code', e.target.value)}
          />
        </Field>
        <Field label="GST rate %" required>
          <Input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={values.gst_rate ?? ''}
            disabled={costLocked}
            aria-label="GST rate"
            onChange={(e) => set('gst_rate', money2(e.target.value))}
          />
        </Field>
        <Field label="Place of supply" hint="Derived from the branch, or the company's own state">
          <Input value={acq.place_of_supply_state_code ?? '—'} disabled aria-label="Place of supply" />
        </Field>
      </div>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Input tax credit</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="ITC eligibility"
            required
            hint={values.itc_treatment ? ITC_HELP[values.itc_treatment] : undefined}
          >
            <Select
              value={values.itc_treatment ?? ''}
              disabled={costLocked}
              aria-label="ITC eligibility"
              onChange={(e) =>
                set('itc_treatment', (e.target.value || null) as typeof values.itc_treatment)
              }
            >
              <option value="">Not set</option>
              {ITC_TREATMENT.map((t) => (
                <option key={t} value={t}>
                  {humanize(t)}
                </option>
              ))}
            </Select>
          </Field>
          {values.itc_treatment === 'partial' && (
            <Field label="Eligible ITC %" required>
              <Input
                type="number"
                min={0}
                max={100}
                step="0.01"
                value={values.itc_eligible_pct ?? ''}
                disabled={costLocked}
                aria-label="Eligible ITC %"
                onChange={(e) => set('itc_eligible_pct', money2(e.target.value))}
              />
            </Field>
          )}
        </div>
      </fieldset>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Tax amounts</legend>
        <Switch
          checked={overridden}
          disabled={costLocked}
          onChange={(v) => set('gst_amounts_overridden', v)}
          label="Enter amounts manually to match the invoice"
        />
        <p className="mt-1 text-xs text-text-muted">
          {overridden
            ? 'These amounts are yours — recalculation will not overwrite them.'
            : `Calculated from the rate. ${GST_BASIS_LABEL[acq.gst_split_basis ?? ''] ?? ''}`}
        </p>

        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="CGST">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.cgst_amount ?? ''}
              disabled={costLocked || !overridden}
              aria-label="CGST"
              onChange={(e) => set('cgst_amount', money2(e.target.value))}
            />
          </Field>
          <Field label="SGST">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.sgst_amount ?? ''}
              disabled={costLocked || !overridden}
              aria-label="SGST"
              onChange={(e) => set('sgst_amount', money2(e.target.value))}
            />
          </Field>
          <Field label="IGST">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.igst_amount ?? ''}
              disabled={costLocked || !overridden}
              aria-label="IGST"
              onChange={(e) => set('igst_amount', money2(e.target.value))}
            />
          </Field>
        </div>
      </fieldset>

      {acq.gst_split_basis === 'assumed_intra_state' && (
        <p className="rounded-card border border-status-pending/40 bg-status-pending/5 px-3 py-2 text-sm text-text-secondary">
          The supplier's or the branch's state is unknown, so this has been treated as an
          intra-state supply. Set a GSTIN on the supplier or the branch to make the split
          definite.
        </p>
      )}

      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-text-primary">GST computation</h4>
          <ExplainLink onClick={() => openCalc()} />
        </div>
        <DerivedRow label="Taxable value" value={money(acq.net_basic_price)} />
        <DerivedRow label="CGST" value={money(acq.cgst_amount)} />
        <DerivedRow label="SGST" value={money(acq.sgst_amount)} />
        <DerivedRow label="IGST" value={money(acq.igst_amount)} />
        <DerivedRow
          label="Total GST"
          value={money(acq.total_gst)}
          emphasis
          onExplain={() => openCalc('total_gst')}
        />
        <div className="mt-1 border-t border-border pt-1">
          <DerivedRow
            label="Recoverable GST"
            value={money(acq.recoverable_gst)}
            hint="Claimed as credit — excluded from asset cost"
            onExplain={() => openCalc('recoverable_gst')}
          />
          <DerivedRow
            label="Capitalizable GST"
            value={money(acq.capitalizable_gst)}
            hint="Added to asset cost and depreciated"
            emphasis
            onExplain={() => openCalc('capitalizable_gst')}
          />
        </div>

        <CalculationDrawer
          open={calcOpen}
          onClose={() => setCalcOpen(false)}
          tabs={[{ id: 'gst', label: 'GST and input tax credit', trace: costTrace }]}
          focusStep={calcStep}
        />
      </Card>
    </SectionShell>
  )
}
