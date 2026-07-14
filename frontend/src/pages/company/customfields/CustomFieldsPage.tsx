import { useEffect, useState } from 'react'
import { SlidersHorizontal, Check } from 'lucide-react'
import {
  PageHeader,
  Button,
  DataTable,
  StatusBadge,
  Modal,
  ConfirmDialog,
  Field,
  Input,
  Select,
  Textarea,
  Tabs,
  useToast,
  type Column,
} from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import {
  useCustomFields,
  useCreateCustomField,
  useUpdateCustomField,
  useDeactivateCustomField,
  useReactivateCustomField,
} from '@/api/hooks/customFields'
import { CUSTOM_FIELD_TYPE, humanize } from '@/api/enums'
import { cn } from '@/lib/cn'
import type { CustomFieldResponse } from '@/api/types'
import type { components } from '@/api/schema'

type Module = components['schemas']['CustomFieldModule']
type FieldType = components['schemas']['CustomFieldType']

const MODULE_TABS: { id: Module; label: string }[] = [
  { id: 'asset_management', label: 'Assets' },
  { id: 'sales_tracking', label: 'Sales' },
]

/** Derive a snake_case key from a human field name. */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

export function CustomFieldsPage() {
  const { profile } = useCompanyAuth()
  const [module, setModule] = useState<Module>('asset_management')
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<CustomFieldResponse | null>(null)
  const [confirmField, setConfirmField] = useState<CustomFieldResponse | null>(null)

  const { data: fields = [], isLoading } = useCustomFields(module, true)
  const deactivate = useDeactivateCustomField()
  const reactivate = useReactivateCustomField()
  const toast = useToast()

  if (profile?.role !== 'admin') {
    return (
      <div>
        <PageHeader
          eyebrow="OPERATIONS"
          icon={<SlidersHorizontal />}
          title="Custom Fields"
          description="Configure extra fields per module"
        />
        <p className="text-sm text-text-secondary">This section is available to admins only.</p>
      </div>
    )
  }

  const handleDeactivate = async () => {
    const f = confirmField
    if (!f) return
    try {
      await deactivate.mutateAsync({ module, fieldId: f.id })
      toast.success('Field deactivated')
      setConfirmField(null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to deactivate field')
    }
  }

  const handleReactivate = async (f: CustomFieldResponse) => {
    try {
      await reactivate.mutateAsync({ module, fieldId: f.id })
      toast.success('Field reactivated')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reactivate field')
    }
  }

  const columns: Column<CustomFieldResponse>[] = [
    {
      key: 'field_name',
      header: 'Field name',
      sortValue: (f) => f.field_name.toLowerCase(),
      cell: (f) => (
        <span className={cn('font-medium text-text-primary', !f.is_active && 'text-text-muted')}>
          {f.field_name}
        </span>
      ),
    },
    {
      key: 'field_key',
      header: 'Key',
      cell: (f) => <span className="font-mono text-xs text-text-muted">{f.field_key}</span>,
    },
    { key: 'field_type', header: 'Type', cell: (f) => humanize(f.field_type) },
    {
      key: 'is_required',
      header: 'Required',
      align: 'center',
      cell: (f) =>
        f.is_required ? <Check className="mx-auto h-4 w-4 text-accent" /> : '—',
    },
    {
      key: 'dropdown_options',
      header: 'Options',
      cell: (f) => (f.dropdown_options?.length ? f.dropdown_options.join(', ') : '—'),
    },
    {
      key: 'is_active',
      header: 'Status',
      cell: (f) => <StatusBadge status={f.is_active ? 'active' : 'archived'} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      cell: (f) => (
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setEditing(f)}>
            Edit
          </Button>
          {f.is_active ? (
            <Button variant="danger" onClick={() => setConfirmField(f)}>
              Deactivate
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => handleReactivate(f)}>
              Reactivate
            </Button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="OPERATIONS"
        icon={<SlidersHorizontal />}
        title="Custom Fields"
        description="Configure extra fields captured per module"
        actions={<Button onClick={() => setCreateOpen(true)}>New Field</Button>}
      />

      <Tabs
        tabs={MODULE_TABS}
        value={module}
        onChange={(id) => setModule(id as Module)}
        accent="company"
      />

      <DataTable
        columns={columns}
        data={fields}
        rowKey={(f) => f.id}
        loading={isLoading}
        searchAccessors={(f) => `${f.field_name} ${f.field_key}`}
        searchPlaceholder="Search fields…"
        emptyTitle="No custom fields yet"
        emptyDescription="Add a field to capture extra data for this module."
      />

      <CreateFieldModal
        open={createOpen}
        module={module}
        onClose={() => setCreateOpen(false)}
      />
      <EditFieldModal
        field={editing}
        module={module}
        onClose={() => setEditing(null)}
      />
      <ConfirmDialog
        open={!!confirmField}
        title="Deactivate field"
        message={
          confirmField
            ? `Deactivate "${confirmField.field_name}"? It will stop being captured for new records.`
            : ''
        }
        confirmLabel="Deactivate"
        destructive
        loading={deactivate.isPending}
        onConfirm={handleDeactivate}
        onCancel={() => setConfirmField(null)}
      />
    </div>
  )
}

function CreateFieldModal({
  open,
  module,
  onClose,
}: {
  open: boolean
  module: Module
  onClose: () => void
}) {
  const toast = useToast()
  const create = useCreateCustomField()

  const [fieldName, setFieldName] = useState('')
  const [fieldKey, setFieldKey] = useState('')
  const [keyEdited, setKeyEdited] = useState(false)
  const [fieldType, setFieldType] = useState<FieldType>('text')
  const [isRequired, setIsRequired] = useState(false)
  const [displayOrder, setDisplayOrder] = useState('0')
  const [optionsText, setOptionsText] = useState('')
  const [keyError, setKeyError] = useState('')

  // Reset the form each time the modal opens.
  useEffect(() => {
    if (!open) return
    setFieldName('')
    setFieldKey('')
    setKeyEdited(false)
    setFieldType('text')
    setIsRequired(false)
    setDisplayOrder('0')
    setOptionsText('')
    setKeyError('')
  }, [open])

  const onNameChange = (value: string) => {
    setFieldName(value)
    if (!keyEdited) setFieldKey(slugify(value))
  }

  const parseOptions = () =>
    optionsText
      .split('\n')
      .map((o) => o.trim())
      .filter(Boolean)

  const handleSubmit = async () => {
    setKeyError('')
    if (!fieldName.trim()) return toast.error('Field name is required')
    if (!fieldKey.trim()) return toast.error('Field key is required')
    try {
      await create.mutateAsync({
        module,
        body: {
          field_name: fieldName.trim(),
          field_key: fieldKey.trim(),
          field_type: fieldType,
          is_required: isRequired,
          display_order: Number(displayOrder) || 0,
          dropdown_options: fieldType === 'dropdown' ? parseOptions() : null,
        },
      })
      toast.success('Custom field created')
      onClose()
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to create field'
      if (/already exists/i.test(msg) || /409/.test(msg)) {
        setKeyError('Field key already exists')
      } else {
        toast.error(msg)
      }
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New Custom Field"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={create.isPending}>
            Create
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Field name" required>
          <Input value={fieldName} onChange={(e) => onNameChange(e.target.value)} placeholder="e.g. Serial number" />
        </Field>
        <Field label="Field key" hint="Used as the storage key" error={keyError}>
          <Input
            value={fieldKey}
            error={!!keyError}
            onChange={(e) => {
              setKeyEdited(true)
              setFieldKey(e.target.value)
            }}
            placeholder="serial_number"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <Select value={fieldType} onChange={(e) => setFieldType(e.target.value as FieldType)}>
              {CUSTOM_FIELD_TYPE.map((t) => (
                <option key={t} value={t}>
                  {humanize(t)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Display order">
            <Input
              type="number"
              value={displayOrder}
              onChange={(e) => setDisplayOrder(e.target.value)}
            />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={isRequired}
            onChange={(e) => setIsRequired(e.target.checked)}
          />
          Required field
        </label>
        {fieldType === 'dropdown' && (
          <Field label="Dropdown options" hint="One option per line">
            <Textarea
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              rows={4}
              placeholder={'Option A\nOption B'}
            />
          </Field>
        )}
      </div>
    </Modal>
  )
}

function EditFieldModal({
  field,
  module,
  onClose,
}: {
  field: CustomFieldResponse | null
  module: Module
  onClose: () => void
}) {
  const toast = useToast()
  const update = useUpdateCustomField()

  const [fieldName, setFieldName] = useState('')
  const [isRequired, setIsRequired] = useState(false)
  const [displayOrder, setDisplayOrder] = useState('0')
  const [optionsText, setOptionsText] = useState('')

  useEffect(() => {
    if (!field) return
    setFieldName(field.field_name)
    setIsRequired(field.is_required)
    setDisplayOrder(String(field.display_order))
    setOptionsText((field.dropdown_options ?? []).join('\n'))
  }, [field])

  const isDropdown = field?.field_type === 'dropdown'

  const handleSubmit = async () => {
    if (!field) return
    if (!fieldName.trim()) return toast.error('Field name is required')
    try {
      await update.mutateAsync({
        module,
        fieldId: field.id,
        body: {
          field_name: fieldName.trim(),
          is_required: isRequired,
          display_order: Number(displayOrder) || 0,
          ...(isDropdown
            ? {
                dropdown_options: optionsText
                  .split('\n')
                  .map((o) => o.trim())
                  .filter(Boolean),
              }
            : {}),
        },
      })
      toast.success('Custom field updated')
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to update field')
    }
  }

  return (
    <Modal
      open={!!field}
      onClose={onClose}
      title="Edit Custom Field"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={update.isPending}>
            Save
          </Button>
        </>
      }
    >
      {field && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Key</span>
              <span className="font-mono text-sm text-text-primary">{field.field_key}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Type</span>
              <span className="text-sm text-text-primary">{humanize(field.field_type)}</span>
            </div>
          </div>
          <Field label="Field name" required>
            <Input value={fieldName} onChange={(e) => setFieldName(e.target.value)} />
          </Field>
          <Field label="Display order">
            <Input
              type="number"
              value={displayOrder}
              onChange={(e) => setDisplayOrder(e.target.value)}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={isRequired}
              onChange={(e) => setIsRequired(e.target.checked)}
            />
            Required field
          </label>
          {isDropdown && (
            <Field label="Dropdown options" hint="One option per line">
              <Textarea
                value={optionsText}
                onChange={(e) => setOptionsText(e.target.value)}
                rows={4}
              />
            </Field>
          )}
        </div>
      )}
    </Modal>
  )
}
