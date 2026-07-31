import { Field, Input, Textarea } from '@/components/ui'
import { useUpdateAsset } from '@/api/hooks/assets'
import { useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { AssetDetail } from '@/api/hooks/assets'
import type { AssetUpdate } from '@/api/types'
import { CategoryPicker } from '../CategoryPicker'
import { useSectionForm } from '../useSectionForm'
import { SectionShell } from './SectionShell'

export function IdentityTab({
  detail,
  locked,
  fieldGroups,
}: {
  detail: AssetDetail
  locked: boolean
  fieldGroups: string[]
}) {
  const asset = detail.asset
  const toast = useToast()
  const update = useUpdateAsset()

  const form = useSectionForm(
    {
      asset_code: asset.asset_code ?? '',
      asset_name: asset.asset_name,
      category_id: asset.category_id ?? '',
      description: asset.description ?? '',
      manufacturer: asset.manufacturer ?? '',
      manufacturer_contact: asset.manufacturer_contact ?? '',
      brand_model: asset.brand_model ?? '',
      manufacturer_serial_number: asset.manufacturer_serial_number ?? '',
      registration_number: asset.registration_number ?? '',
      engine_number: asset.engine_number ?? '',
      chassis_number: asset.chassis_number ?? '',
      imei: asset.imei ?? '',
      mac_address: asset.mac_address ?? '',
      technical_specs: asset.technical_specs ?? '',
      remarks: asset.remarks ?? '',
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
  const isDraft = asset.lifecycle_status === 'draft'

  return (
    <SectionShell
      title="Identity"
      description="What this asset is. The tag is generated from the category prefix and is fixed once the asset is capitalized."
      dirty={form.dirty}
      saving={form.saving}
      onSave={form.save}
      onReset={form.reset}
      readOnlyNote={
        locked
          ? 'This asset is capitalized. Identity and description can still be corrected by an admin, but the tag and category are fixed.'
          : undefined
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          label="Asset code / tag"
          hint={isDraft ? 'Editable while this is a draft' : 'Fixed — the asset is past draft'}
        >
          <Input
            value={values.asset_code}
            disabled={!isDraft}
            aria-label="Asset code / tag"
            onChange={(e) => set('asset_code', e.target.value)}
          />
        </Field>
        <Field label="Asset name" required>
          <Input
            value={values.asset_name}
            disabled={locked}
            aria-label="Asset name"
            onChange={(e) => set('asset_name', e.target.value)}
          />
        </Field>
      </div>

      <CategoryPicker
        value={values.category_id}
        onChange={(id) => set('category_id', id)}
        disabled={locked}
        required
      />

      <Field label="Asset description" required>
        <Textarea
          value={values.description}
          aria-label="Asset description"
          onChange={(e) => set('description', e.target.value)}
        />
      </Field>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Manufacturer" required>
          <Input
            value={values.manufacturer}
            disabled={locked}
            aria-label="Manufacturer"
            onChange={(e) => set('manufacturer', e.target.value)}
          />
        </Field>
        <Field label="Brand / model" required>
          <Input
            value={values.brand_model}
            disabled={locked}
            aria-label="Brand / model"
            onChange={(e) => set('brand_model', e.target.value)}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Manufacturer serial number" hint="Where applicable">
          <Input
            value={values.manufacturer_serial_number}
            aria-label="Manufacturer serial number"
            onChange={(e) => set('manufacturer_serial_number', e.target.value)}
          />
        </Field>
        <Field label="Manufacturer contact" hint="Optional">
          <Input
            value={values.manufacturer_contact}
            aria-label="Manufacturer contact"
            onChange={(e) => set('manufacturer_contact', e.target.value)}
          />
        </Field>
      </div>

      {/* Only shown when the category says this kind of asset has them — a laptop
          has no chassis number and a chair has no MAC address. */}
      {fieldGroups.includes('registration') && (
        <fieldset className="rounded-card border border-border p-4">
          <legend className="px-1 text-sm font-medium text-text-secondary">Vehicle registration</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Registration number">
              <Input
                value={values.registration_number}
                aria-label="Registration number"
                onChange={(e) => set('registration_number', e.target.value)}
              />
            </Field>
            <Field label="Engine number">
              <Input
                value={values.engine_number}
                aria-label="Engine number"
                onChange={(e) => set('engine_number', e.target.value)}
              />
            </Field>
            <Field label="Chassis number">
              <Input
                value={values.chassis_number}
                aria-label="Chassis number"
                onChange={(e) => set('chassis_number', e.target.value)}
              />
            </Field>
          </div>
        </fieldset>
      )}

      {fieldGroups.includes('network_ids') && (
        <fieldset className="rounded-card border border-border p-4">
          <legend className="px-1 text-sm font-medium text-text-secondary">Network identifiers</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="IMEI">
              <Input value={values.imei} aria-label="IMEI" onChange={(e) => set('imei', e.target.value)} />
            </Field>
            <Field label="MAC address">
              <Input
                value={values.mac_address}
                aria-label="MAC address"
                onChange={(e) => set('mac_address', e.target.value)}
              />
            </Field>
          </div>
        </fieldset>
      )}

      <Field label="Technical specifications" hint="Optional">
        <Textarea
          value={values.technical_specs}
          aria-label="Technical specifications"
          onChange={(e) => set('technical_specs', e.target.value)}
        />
      </Field>

      <Field label="Remarks" hint="Optional">
        <Textarea
          value={values.remarks}
          aria-label="Remarks"
          onChange={(e) => set('remarks', e.target.value)}
        />
      </Field>
    </SectionShell>
  )
}
