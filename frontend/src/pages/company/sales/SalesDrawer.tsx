import { useEffect, useState } from 'react'
import { Drawer, Button, Field, Input, Select, StatusBadge, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useCreateSale, useUpdateSale } from '@/api/hooks/sales'
import { SALES_STATUS, humanize } from '@/api/enums'
import type {
  SalesRecordResponse,
  SalesRecordCreate,
  CustomFieldResponse,
  UserResponse,
} from '@/api/types'

interface SalesDrawerProps {
  open: boolean
  onClose: () => void
  /** null → create mode; otherwise edit. */
  sale: SalesRecordResponse | null
  me: { id: string; role: string }
  users: UserResponse[]
  activeFields: CustomFieldResponse[]
}

type FieldErrors = Record<string, string>

export function SalesDrawer({ open, onClose, sale, me, users, activeFields }: SalesDrawerProps) {
  const toast = useToast()
  const createSale = useCreateSale()
  const updateSale = useUpdateSale()

  const [clientName, setClientName] = useState('')
  const [productService, setProductService] = useState('')
  const [amount, setAmount] = useState('')
  const [status, setStatus] = useState('lead')
  const [closingDate, setClosingDate] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [custom, setCustom] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<FieldErrors>({})

  const showOwnerPicker = me.role === 'admin' || me.role === 'manager'

  useEffect(() => {
    if (!open) return
    setClientName(sale?.client_name ?? '')
    setProductService(sale?.product_service ?? '')
    setAmount(sale?.amount != null ? String(sale.amount) : '')
    setStatus(sale?.status ?? 'lead')
    setClosingDate(sale?.closing_date ?? '')
    setOwnerId(sale?.user_id ?? '')
    const cf: Record<string, string> = {}
    const existing = (sale?.custom_fields ?? {}) as Record<string, unknown>
    for (const f of activeFields) {
      const v = existing[f.field_key]
      cf[f.field_key] = v == null ? '' : String(v)
    }
    setCustom(cf)
    setErrors({})
  }, [open, sale, activeFields])

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
    if (!clientName.trim()) errs.client_name = 'Required'
    if (!productService.trim()) errs.product_service = 'Required'
    if (!amount.trim()) errs.amount = 'Required'
    for (const f of activeFields) {
      if (f.is_required && !custom[f.field_key]?.trim()) errs[f.field_key] = 'Required'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    const body: SalesRecordCreate = {
      client_name: clientName.trim(),
      product_service: productService.trim(),
      amount: Number(amount),
      status: status as SalesRecordResponse['status'],
      closing_date: closingDate || null,
      user_id: showOwnerPicker ? ownerId || null : null,
      custom_fields: buildCustomFields(),
    }
    try {
      if (sale) {
        await updateSale.mutateAsync({ id: sale.id, body })
        toast.success('Sale updated')
      } else {
        await createSale.mutateAsync(body)
        toast.success('Sale created')
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
      toast.error(e instanceof Error ? e.message : 'Failed to save sale')
    }
  }

  const busy = createSale.isPending || updateSale.isPending

  // Owner options: role-scoped users, plus ensure self is present.
  const ownerOptions = (() => {
    const seen = new Set(users.map((u) => u.id))
    const opts = users.map((u) => ({ id: u.id, name: u.full_name }))
    if (!seen.has(me.id)) opts.unshift({ id: me.id, name: 'Me' })
    return opts
  })()

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

  const footer = (
    <>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button onClick={handleSubmit} loading={busy}>{sale ? 'Save' : 'Create sale'}</Button>
    </>
  )

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={sale ? sale.client_name : 'New sale'}
      subtitle={sale ? <StatusBadge status={sale.status} /> : 'Log a new deal'}
      footer={footer}
    >
      <div className="flex flex-col gap-4">
        <Field label="Client name" required error={errors.client_name}>
          <Input value={clientName} error={!!errors.client_name} onChange={(e) => setClientName(e.target.value)} />
        </Field>
        <Field label="Product / service" required error={errors.product_service}>
          <Input value={productService} error={!!errors.product_service} onChange={(e) => setProductService(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Amount" required error={errors.amount}>
            <Input type="number" min={0} value={amount} error={!!errors.amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {SALES_STATUS.map((s) => (
                <option key={s} value={s}>{humanize(s)}</option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Closing date">
            <Input type="date" value={closingDate} onChange={(e) => setClosingDate(e.target.value)} />
          </Field>
          {showOwnerPicker && (
            <Field label="Owner">
              <Select value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
                <option value="">Me</option>
                {ownerOptions.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </Select>
            </Field>
          )}
        </div>

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
    </Drawer>
  )
}
