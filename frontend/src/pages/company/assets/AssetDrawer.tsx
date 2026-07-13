import { useEffect, useState } from 'react'
import { Drawer, Button, Field, Input, Select, StatusBadge, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useCreateAsset, useUpdateAsset } from '@/api/hooks/assets'
import { ASSET_CATEGORY, ASSET_STATUS, humanize } from '@/api/enums'
import { formatMoney } from '@/lib/format'
import type { AssetResponse, CustomFieldResponse, UserResponse, DocumentResponse } from '@/api/types'

interface AssetDrawerProps {
  open: boolean
  onClose: () => void
  /** null → create mode; otherwise edit (admin) or read-only view (non-admin). */
  asset: AssetResponse | null
  isAdmin: boolean
  users: UserResponse[]
  documents: DocumentResponse[]
  activeFields: CustomFieldResponse[]
}

type FieldErrors = Record<string, string>

function ReadRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
      <span className="text-sm text-text-primary">{children}</span>
    </div>
  )
}

export function AssetDrawer({ open, onClose, asset, isAdmin, users, documents, activeFields }: AssetDrawerProps) {
  const toast = useToast()
  const createAsset = useCreateAsset()
  const updateAsset = useUpdateAsset()

  const [assetName, setAssetName] = useState('')
  const [serial, setSerial] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('active')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [purchaseCost, setPurchaseCost] = useState('')
  const [depreciation, setDepreciation] = useState('')
  const [custodianId, setCustodianId] = useState('')
  const [documentId, setDocumentId] = useState('')
  const [custom, setCustom] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (!open) return
    setAssetName(asset?.asset_name ?? '')
    setSerial(asset?.serial_number ?? '')
    setCategory(asset?.category ?? '')
    setStatus(asset?.status ?? 'active')
    setPurchaseDate(asset?.purchase_date ?? '')
    setPurchaseCost(asset?.purchase_cost != null ? String(asset.purchase_cost) : '')
    setDepreciation(asset?.depreciation_rate != null ? String(asset.depreciation_rate) : '')
    setCustodianId(asset?.custodian_id ?? '')
    setDocumentId(asset?.document_id ?? '')
    const cf: Record<string, string> = {}
    const existing = (asset?.custom_fields ?? {}) as Record<string, unknown>
    for (const f of activeFields) {
      const v = existing[f.field_key]
      cf[f.field_key] = v == null ? '' : String(v)
    }
    setCustom(cf)
    setErrors({})
  }, [open, asset, activeFields])

  const readOnly = !isAdmin

  const setCustomValue = (key: string, val: string) => setCustom((c) => ({ ...c, [key]: val }))

  const buildCustomFields = () => {
    const out: Record<string, string> = {}
    for (const f of activeFields) {
      const v = custom[f.field_key]?.trim()
      if (v) out[f.field_key] = v
    }
    return out
  }

  const validate = (): boolean => {
    const errs: FieldErrors = {}
    if (!assetName.trim()) errs.asset_name = 'Required'
    if (!category) errs.category = 'Required'
    for (const f of activeFields) {
      if (f.is_required && !custom[f.field_key]?.trim()) errs[f.field_key] = 'Required'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    const body = {
      asset_name: assetName.trim(),
      serial_number: serial.trim() || null,
      category: category as AssetResponse['category'],
      status: status as AssetResponse['status'],
      purchase_date: purchaseDate || null,
      purchase_cost: purchaseCost ? Number(purchaseCost) : null,
      depreciation_rate: depreciation ? Number(depreciation) : null,
      custodian_id: custodianId || null,
      document_id: documentId || null,
      custom_fields: buildCustomFields(),
    }
    try {
      if (asset) {
        await updateAsset.mutateAsync({ id: asset.id, body })
        toast.success('Asset updated')
      } else {
        await createAsset.mutateAsync(body)
        toast.success('Asset created')
      }
      onClose()
    } catch (e) {
      // Surface backend custom-field validation errors when present.
      if (e instanceof ApiError && e.detail && typeof e.detail === 'object') {
        const cfe = (e.detail as { custom_field_errors?: string[] }).custom_field_errors
        if (cfe?.length) {
          toast.error(cfe.join('; '))
          return
        }
      }
      toast.error(e instanceof Error ? e.message : 'Failed to save asset')
    }
  }

  const userName = (id: string | null | undefined) =>
    id ? users.find((u) => u.id === id)?.full_name ?? '—' : 'Unassigned'

  const busy = createAsset.isPending || updateAsset.isPending

  const renderCustomInput = (f: CustomFieldResponse) => {
    const val = custom[f.field_key] ?? ''
    if (f.field_type === 'dropdown') {
      return (
        <Select value={val} error={!!errors[f.field_key]} onChange={(e) => setCustomValue(f.field_key, e.target.value)}>
          <option value="">— Select —</option>
          {(f.dropdown_options ?? []).map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </Select>
      )
    }
    const type = f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : 'text'
    return (
      <Input
        type={type}
        value={val}
        error={!!errors[f.field_key]}
        onChange={(e) => setCustomValue(f.field_key, e.target.value)}
      />
    )
  }

  const footer = readOnly ? (
    <Button variant="ghost" onClick={onClose}>Close</Button>
  ) : (
    <>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button onClick={handleSubmit} loading={busy}>{asset ? 'Save' : 'Create asset'}</Button>
    </>
  )

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={asset ? asset.asset_name : 'New asset'}
      subtitle={asset ? <StatusBadge status={asset.status} /> : 'Add an asset to the register'}
      footer={footer}
    >
      {readOnly && asset ? (
        <div className="flex flex-col gap-4">
          <ReadRow label="Serial number">{asset.serial_number || '—'}</ReadRow>
          <div className="grid grid-cols-2 gap-3">
            <ReadRow label="Category">{humanize(asset.category)}</ReadRow>
            <ReadRow label="Status">{humanize(asset.status)}</ReadRow>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <ReadRow label="Purchase date">{asset.purchase_date || '—'}</ReadRow>
            <ReadRow label="Purchase cost">{asset.purchase_cost != null ? formatMoney(asset.purchase_cost) : '—'}</ReadRow>
          </div>
          <ReadRow label="Custodian">{userName(asset.custodian_id)}</ReadRow>
          {activeFields.map((f) => (
            <ReadRow key={f.id} label={f.field_name}>
              {String((asset.custom_fields as Record<string, unknown>)?.[f.field_key] ?? '—') || '—'}
            </ReadRow>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <Field label="Asset name" required error={errors.asset_name}>
            <Input value={assetName} error={!!errors.asset_name} onChange={(e) => setAssetName(e.target.value)} placeholder="e.g. MacBook Pro 16&quot;" />
          </Field>
          <Field label="Serial number">
            <Input value={serial} onChange={(e) => setSerial(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category" required error={errors.category}>
              <Select value={category} error={!!errors.category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">— Select —</option>
                {ASSET_CATEGORY.map((c) => (
                  <option key={c} value={c}>{humanize(c)}</option>
                ))}
              </Select>
            </Field>
            <Field label="Status">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                {ASSET_STATUS.map((s) => (
                  <option key={s} value={s}>{humanize(s)}</option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Purchase date">
              <Input type="date" value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
            </Field>
            <Field label="Purchase cost">
              <Input type="number" min={0} value={purchaseCost} onChange={(e) => setPurchaseCost(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Depreciation rate" hint="Percent">
              <Input type="number" min={0} max={100} value={depreciation} onChange={(e) => setDepreciation(e.target.value)} />
            </Field>
            <Field label="Custodian">
              <Select value={custodianId} onChange={(e) => setCustodianId(e.target.value)}>
                <option value="">Unassigned</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Linked document" hint="Optional docVault document">
            <Select value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
              <option value="">None</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>{d.title}</option>
              ))}
            </Select>
          </Field>

          {activeFields.length > 0 && (
            <div className="rounded-card border border-border p-3">
              <h4 className="mb-3 text-sm font-semibold text-text-primary">Custom fields</h4>
              <div className="flex flex-col gap-3">
                {activeFields.map((f) => (
                  <Field key={f.id} label={f.field_name} required={f.is_required} error={errors[f.field_key]}>
                    {renderCustomInput(f)}
                  </Field>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Drawer>
  )
}
