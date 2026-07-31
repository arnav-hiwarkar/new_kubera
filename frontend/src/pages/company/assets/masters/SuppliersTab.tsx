import { useState } from 'react'
import { Plus } from 'lucide-react'
import {
  Button,
  DataTable,
  Field,
  Input,
  Modal,
  useToast,
  type Column,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { useCreateSupplier, useSuppliers } from '@/api/hooks/assetMasters'
import type { SupplierResponse } from '@/api/types'

const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$/

export function SuppliersTab() {
  const { data: suppliers = [], isLoading } = useSuppliers()
  const create = useCreateSupplier()
  const toast = useToast()

  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    code: '',
    name: '',
    gstin: '',
    state: '',
    contact_person: '',
    phone: '',
    email: '',
    city: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }))

  const handleCreate = async () => {
    const errs: Record<string, string> = {}
    if (!form.code.trim()) errs.code = 'Required'
    if (!form.name.trim()) errs.name = 'Required'
    // Validated here as well as server-side so a typo is caught before the round trip.
    if (form.gstin.trim() && !GSTIN_RE.test(form.gstin.trim().toUpperCase())) {
      errs.gstin = 'Not a valid 15-character GSTIN'
    }
    setErrors(errs)
    if (Object.keys(errs).length > 0) return

    try {
      await create.mutateAsync({
        code: form.code.trim(),
        name: form.name.trim(),
        gstin: form.gstin.trim() ? form.gstin.trim().toUpperCase() : null,
        state: form.state.trim() || null,
        contact_person: form.contact_person.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        city: form.city.trim() || null,
      })
      toast.success('Supplier added')
      setOpen(false)
      setForm({ code: '', name: '', gstin: '', state: '', contact_person: '', phone: '', email: '', city: '' })
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === 'string') {
        setErrors({ code: e.detail })
        return
      }
      toast.error(e instanceof Error ? e.message : 'Could not add the supplier')
    }
  }

  const columns: Column<SupplierResponse>[] = [
    { key: 'code', header: 'Code', sortValue: (s) => s.code, cell: (s) => <span className="font-mono text-xs">{s.code}</span> },
    { key: 'name', header: 'Name', sortValue: (s) => s.name.toLowerCase() },
    {
      key: 'gstin',
      header: 'GSTIN',
      cell: (s) => (s.gstin ? <span className="font-mono text-xs">{s.gstin}</span> : '—'),
    },
    {
      key: 'state_code',
      header: 'State',
      cell: (s) => s.state ?? (s.state_code ? `Code ${s.state_code}` : '—'),
    },
    { key: 'contact_person', header: 'Contact', cell: (s) => s.contact_person ?? '—' },
    { key: 'email', header: 'Email', cell: (s) => s.email ?? '—' },
  ]

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        A supplier's GSTIN gives its state, which is what decides whether a purchase is
        CGST + SGST or IGST. Without it the register has to assume intra-state.
      </p>

      <DataTable
        columns={columns}
        data={suppliers}
        rowKey={(s) => s.id}
        loading={isLoading}
        searchAccessors={(s) => `${s.code} ${s.name} ${s.gstin ?? ''}`}
        searchPlaceholder="Search suppliers…"
        emptyTitle="No suppliers"
        emptyDescription="Add the vendors you buy assets from."
        toolbar={
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            New supplier
          </Button>
        }
      />

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New supplier"
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} loading={create.isPending}>
              Add supplier
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Supplier code" required error={errors.code}>
              <Input
                value={form.code}
                error={!!errors.code}
                aria-label="Supplier code"
                onChange={(e) => set('code', e.target.value)}
              />
            </Field>
            <Field label="Supplier name" required error={errors.name}>
              <Input
                value={form.name}
                error={!!errors.name}
                aria-label="Supplier name"
                onChange={(e) => set('name', e.target.value)}
              />
            </Field>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field
              label="GSTIN"
              error={errors.gstin}
              hint="Optional, but sets the place of supply"
            >
              <Input
                value={form.gstin}
                error={!!errors.gstin}
                placeholder="27ABCDE1234F1Z5"
                aria-label="GSTIN"
                onChange={(e) => set('gstin', e.target.value.toUpperCase())}
              />
            </Field>
            <Field label="State">
              <Input value={form.state} aria-label="State" onChange={(e) => set('state', e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Contact person">
              <Input
                value={form.contact_person}
                aria-label="Contact person"
                onChange={(e) => set('contact_person', e.target.value)}
              />
            </Field>
            <Field label="Phone">
              <Input value={form.phone} aria-label="Phone" onChange={(e) => set('phone', e.target.value)} />
            </Field>
            <Field label="Email">
              <Input value={form.email} aria-label="Email" onChange={(e) => set('email', e.target.value)} />
            </Field>
          </div>
          <Field label="City">
            <Input value={form.city} aria-label="City" onChange={(e) => set('city', e.target.value)} />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
