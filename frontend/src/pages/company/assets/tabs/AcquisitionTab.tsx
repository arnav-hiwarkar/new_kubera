import { useMemo, useState } from 'react'
import { Card, Field, Input, Select, Switch, Textarea, useToast } from '@/components/ui'
import { CalculationDrawer, ExplainLink, traceFromCostPreview } from '@/components/calc'
import { ApiError } from '@/api/http'
import type { AssetDetail } from '@/api/hooks/assets'
import { useUpdateAcquisition } from '@/api/hooks/assets'
import { useSuppliers } from '@/api/hooks/assetMasters'
import { DISCOUNT_TYPE, humanize } from '@/api/enums'
import type { AcquisitionUpdate } from '@/api/types'
import { GST_BASIS_LABEL, money } from '../assetFormat'
import { numOrNull, useSectionForm } from '../useSectionForm'
import { DerivedRow, SectionShell } from './SectionShell'

export function AcquisitionTab({
  detail,
  costLocked,
}: {
  detail: AssetDetail
  costLocked: boolean
}) {
  const acq = detail.acquisition
  const toast = useToast()
  const update = useUpdateAcquisition()
  const { data: suppliers = [] } = useSuppliers()

  const form = useSectionForm(
    {
      supplier_id: acq?.supplier_id ?? null,
      invoice_number: acq?.invoice_number ?? '',
      invoice_date: acq?.invoice_date ?? null,
      po_number: acq?.po_number ?? '',
      purchase_date: acq?.purchase_date ?? null,
      quantity: acq?.quantity ?? 1,
      unit_basic_price: acq?.unit_basic_price ?? null,
      discount_type: acq?.discount_type ?? 'amount',
      discount_value: acq?.discount_value ?? null,
      freight_cost: acq?.freight_cost ?? null,
      installation_cost: acq?.installation_cost ?? null,
      other_capitalizable_cost: acq?.other_capitalizable_cost ?? null,
      grn_number: acq?.grn_number ?? '',
      grn_date: acq?.grn_date ?? null,
      delivery_challan_number: acq?.delivery_challan_number ?? '',
      eway_bill_number: acq?.eway_bill_number ?? '',
      irn: acq?.irn ?? '',
      is_imported: acq?.is_imported ?? false,
      bill_of_entry_number: acq?.bill_of_entry_number ?? '',
      bill_of_entry_date: acq?.bill_of_entry_date ?? null,
      customs_duty: acq?.customs_duty ?? null,
      foreign_currency: acq?.foreign_currency ?? '',
      foreign_currency_value: acq?.foreign_currency_value ?? null,
      exchange_rate: acq?.exchange_rate ?? null,
      is_leased: acq?.is_leased ?? false,
      lease_type: acq?.lease_type ?? '',
      lessor_name: acq?.lessor_name ?? '',
      lease_start_date: acq?.lease_start_date ?? null,
      lease_end_date: acq?.lease_end_date ?? null,
      lease_rental: acq?.lease_rental ?? null,
      project_budget_reference: acq?.project_budget_reference ?? '',
      remarks: acq?.remarks ?? '',
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

  // Every intermediate is already on `acq`, so this is presentation, not a fetch.
  const costTrace = useMemo(
    () =>
      traceFromCostPreview(acq ?? {}, {
        title: 'Acquisition cost build-up',
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

  return (
    <SectionShell
      title="Acquisition & costs"
      description={`Invoice-level details, shared by all ${acq.quantity} unit${acq.quantity === 1 ? '' : 's'} in this batch. Enter it once.`}
      dirty={form.dirty}
      saving={form.saving}
      onSave={form.save}
      onReset={form.reset}
      readOnlyNote={
        costLocked
          ? 'Cost fields are locked because assets from this batch are capitalized. Record a cost adjustment instead of editing them.'
          : undefined
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Supplier" required>
          <Select
            value={values.supplier_id ?? ''}
            disabled={costLocked}
            aria-label="Supplier"
            onChange={(e) => set('supplier_id', e.target.value || null)}
          >
            <option value="">Not set</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} — {s.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Supplier GSTIN"
          hint={
            acq.supplier_gstin_snapshot
              ? 'Recorded from the supplier master at entry time'
              : 'Comes from the selected supplier'
          }
        >
          <Input value={acq.supplier_gstin_snapshot ?? ''} disabled aria-label="Supplier GSTIN" />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Invoice number" required>
          <Input
            value={values.invoice_number}
            aria-label="Invoice number"
            onChange={(e) => set('invoice_number', e.target.value)}
          />
        </Field>
        <Field label="Invoice date" required>
          <Input
            type="date"
            value={values.invoice_date ?? ''}
            aria-label="Invoice date"
            onChange={(e) => set('invoice_date', e.target.value || null)}
          />
        </Field>
        <Field label="Purchase order number" required>
          <Input
            value={values.po_number}
            aria-label="Purchase order number"
            onChange={(e) => set('po_number', e.target.value)}
          />
        </Field>
        <Field label="Purchase / receipt date" required>
          <Input
            type="date"
            value={values.purchase_date ?? ''}
            aria-label="Purchase / receipt date"
            onChange={(e) => set('purchase_date', e.target.value || null)}
          />
        </Field>
      </div>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Price</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <Field
            label="Quantity"
            required
            hint={costLocked ? undefined : 'Changing this adds or removes draft units'}
          >
            <Input
              type="number"
              min={1}
              step={1}
              value={values.quantity}
              disabled={costLocked}
              aria-label="Quantity"
              onChange={(e) => set('quantity', Number(e.target.value) || 1)}
            />
          </Field>
          <Field label="Basic price / unit" required>
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.unit_basic_price ?? ''}
              disabled={costLocked}
              aria-label="Basic price per unit"
              onChange={(e) => set('unit_basic_price', money2(e.target.value))}
            />
          </Field>
          <Field label="Discount type">
            <Select
              value={values.discount_type}
              disabled={costLocked}
              aria-label="Discount type"
              onChange={(e) => set('discount_type', e.target.value as typeof values.discount_type)}
            >
              {DISCOUNT_TYPE.map((d) => (
                <option key={d} value={d}>
                  {humanize(d)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={values.discount_type === 'percent' ? 'Discount %' : 'Discount amount'}>
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.discount_value ?? ''}
              disabled={costLocked}
              aria-label="Discount value"
              onChange={(e) => set('discount_value', money2(e.target.value))}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">
          Other capitalizable costs
        </legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Freight / transportation">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.freight_cost ?? ''}
              disabled={costLocked}
              aria-label="Freight / transportation"
              onChange={(e) => set('freight_cost', money2(e.target.value))}
            />
          </Field>
          <Field label="Installation & commissioning">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.installation_cost ?? ''}
              disabled={costLocked}
              aria-label="Installation and commissioning"
              onChange={(e) => set('installation_cost', money2(e.target.value))}
            />
          </Field>
          <Field label="Other capitalizable">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={values.other_capitalizable_cost ?? ''}
              disabled={costLocked}
              aria-label="Other capitalizable costs"
              onChange={(e) => set('other_capitalizable_cost', money2(e.target.value))}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Receipt documents</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="GRN number">
            <Input
              value={values.grn_number}
              aria-label="GRN number"
              onChange={(e) => set('grn_number', e.target.value)}
            />
          </Field>
          <Field label="GRN date">
            <Input
              type="date"
              value={values.grn_date ?? ''}
              aria-label="GRN date"
              onChange={(e) => set('grn_date', e.target.value || null)}
            />
          </Field>
          <Field label="Delivery challan number">
            <Input
              value={values.delivery_challan_number}
              aria-label="Delivery challan number"
              onChange={(e) => set('delivery_challan_number', e.target.value)}
            />
          </Field>
          <Field label="E-way bill number">
            <Input
              value={values.eway_bill_number}
              aria-label="E-way bill number"
              onChange={(e) => set('eway_bill_number', e.target.value)}
            />
          </Field>
          <Field label="IRN" className="sm:col-span-2">
            <Input value={values.irn} aria-label="IRN" onChange={(e) => set('irn', e.target.value)} />
          </Field>
        </div>
      </fieldset>

      {/* Conditional groups: revealed by an explicit fact about the purchase rather
          than sitting on screen empty for the 95% of assets that are not imported. */}
      <div className="rounded-card border border-border p-4">
        <Switch
          checked={!!values.is_imported}
          onChange={(v) => set('is_imported', v)}
          label="Imported"
          disabled={costLocked}
        />
        {values.is_imported && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Bill of entry number">
              <Input
                value={values.bill_of_entry_number}
                aria-label="Bill of entry number"
                onChange={(e) => set('bill_of_entry_number', e.target.value)}
              />
            </Field>
            <Field label="Bill of entry date">
              <Input
                type="date"
                value={values.bill_of_entry_date ?? ''}
                aria-label="Bill of entry date"
                onChange={(e) => set('bill_of_entry_date', e.target.value || null)}
              />
            </Field>
            <Field label="Customs duty">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={values.customs_duty ?? ''}
                aria-label="Customs duty"
                onChange={(e) => set('customs_duty', money2(e.target.value))}
              />
            </Field>
            <Field label="Currency" hint="3-letter code">
              <Input
                value={values.foreign_currency}
                maxLength={3}
                aria-label="Foreign currency"
                onChange={(e) => set('foreign_currency', e.target.value.toUpperCase())}
              />
            </Field>
            <Field label="Value in foreign currency">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={values.foreign_currency_value ?? ''}
                aria-label="Value in foreign currency"
                onChange={(e) => set('foreign_currency_value', money2(e.target.value))}
              />
            </Field>
            <Field label="Exchange rate">
              <Input
                type="number"
                min={0}
                step="0.000001"
                value={values.exchange_rate ?? ''}
                aria-label="Exchange rate"
                onChange={(e) => set('exchange_rate', money2(e.target.value))}
              />
            </Field>
          </div>
        )}
      </div>

      <div className="rounded-card border border-border p-4">
        <Switch
          checked={!!values.is_leased}
          onChange={(v) => set('is_leased', v)}
          label="Leased or financed"
          disabled={costLocked}
        />
        {values.is_leased && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Lease type">
              <Input
                value={values.lease_type}
                placeholder="Finance / operating"
                aria-label="Lease type"
                onChange={(e) => set('lease_type', e.target.value)}
              />
            </Field>
            <Field label="Lessor name">
              <Input
                value={values.lessor_name}
                aria-label="Lessor name"
                onChange={(e) => set('lessor_name', e.target.value)}
              />
            </Field>
            <Field label="Rental">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={values.lease_rental ?? ''}
                aria-label="Lease rental"
                onChange={(e) => set('lease_rental', money2(e.target.value))}
              />
            </Field>
            <Field label="Lease start">
              <Input
                type="date"
                value={values.lease_start_date ?? ''}
                aria-label="Lease start"
                onChange={(e) => set('lease_start_date', e.target.value || null)}
              />
            </Field>
            <Field label="Lease end">
              <Input
                type="date"
                value={values.lease_end_date ?? ''}
                aria-label="Lease end"
                onChange={(e) => set('lease_end_date', e.target.value || null)}
              />
            </Field>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Project / budget reference" hint="Optional">
          <Input
            value={values.project_budget_reference}
            aria-label="Project / budget reference"
            onChange={(e) => set('project_budget_reference', e.target.value)}
          />
        </Field>
        <Field label="Remarks" hint="Optional">
          <Textarea
            value={values.remarks}
            aria-label="Acquisition remarks"
            onChange={(e) => set('remarks', e.target.value)}
          />
        </Field>
      </div>

      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-text-primary">Cost build-up</h4>
          <ExplainLink onClick={() => openCalc()} />
        </div>
        <DerivedRow label="Gross basic price" value={money(acq.gross_basic_price)} />
        <DerivedRow label="Less discount" value={money(acq.discount_amount)} />
        <DerivedRow label="Net basic price" value={money(acq.net_basic_price)} hint="Taxable value" />
        <DerivedRow
          label="Add capitalizable GST"
          value={money(acq.capitalizable_gst)}
          hint="GST that cannot be recovered becomes part of cost"
          onExplain={() => openCalc('capitalizable_gst')}
        />
        <DerivedRow label="Add freight" value={money(acq.freight_cost)} />
        <DerivedRow label="Add installation" value={money(acq.installation_cost)} />
        <DerivedRow label="Add other capitalizable" value={money(acq.other_capitalizable_cost)} />
        <div className="mt-1 border-t border-border pt-1">
          <DerivedRow
            label="Total capitalized value"
            value={money(acq.landed_cost)}
            hint="What goes on the balance sheet and depreciates"
            emphasis
            onExplain={() => openCalc('landed_cost')}
          />
          <DerivedRow
            label="Per-unit cost"
            value={money(acq.per_unit_cost)}
            hint={`Allocated across ${acq.quantity} unit${acq.quantity === 1 ? '' : 's'}, summing exactly to the total`}
            onExplain={() => openCalc('per_unit_cost')}
          />
          <DerivedRow
            label="Total acquisition outlay"
            value={money(acq.total_acquisition_outlay)}
            hint="Total cash paid, including recoverable GST — not the depreciation base"
            onExplain={() => openCalc('total_acquisition_outlay')}
          />
        </div>

        <CalculationDrawer
          open={calcOpen}
          onClose={() => setCalcOpen(false)}
          tabs={[{ id: 'cost', label: 'Cost build-up', trace: costTrace }]}
          focusStep={calcStep}
        />
      </Card>
    </SectionShell>
  )
}
