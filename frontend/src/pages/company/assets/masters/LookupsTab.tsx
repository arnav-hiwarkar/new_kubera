import { useState } from 'react'
import { Plus } from 'lucide-react'
import {
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Modal,
  Select,
  Spinner,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAssetLookups, useCreateLookup } from '@/api/hooks/assetMasters'
import { ASSET_LOOKUP_KIND } from '@/api/enums'
import type { AssetLookupKind } from '@/api/types'

const KIND_LABEL: Record<AssetLookupKind, string> = {
  branch: 'Branches',
  cost_centre: 'Cost centres',
  department: 'Departments',
  location: 'Locations',
}

const KIND_HELP: Record<AssetLookupKind, string> = {
  branch:
    'A branch with its own GST registration changes the place of supply, so give it a GSTIN if it has one.',
  cost_centre: 'Used to attribute depreciation to a cost centre.',
  department: 'The department responsible for the asset.',
  location: 'Where the asset physically sits. Locations can nest — a site, then rooms within it.',
}

export function LookupsTab() {
  const { data: all = [], isLoading } = useAssetLookups()
  const create = useCreateLookup()
  const toast = useToast()

  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<AssetLookupKind>('branch')
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [gstin, setGstin] = useState('')
  const [parentId, setParentId] = useState('')
  const [error, setError] = useState('')

  const handleCreate = async () => {
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    try {
      await create.mutateAsync({
        kind,
        name: name.trim(),
        code: code.trim() || null,
        gstin: kind === 'branch' && gstin.trim() ? gstin.trim().toUpperCase() : null,
        parent_id: kind === 'location' && parentId ? parentId : null,
        display_order: 0,
      })
      toast.success(`Added to ${KIND_LABEL[kind]}`)
      setOpen(false)
      setName('')
      setCode('')
      setGstin('')
      setParentId('')
      setError('')
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === 'string') {
        setError(e.detail)
        return
      }
      setError(e instanceof Error ? e.message : 'Could not add the value')
    }
  }

  if (isLoading) return <Spinner />

  const locations = all.filter((l) => l.kind === 'location')

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-text-muted">
          The dimensions assets are classified by. Defining them here rather than typing
          them per asset is what makes location and department reports usable.
        </p>
        <Button onClick={() => setOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          New value
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {ASSET_LOOKUP_KIND.map((k) => {
          const rows = all.filter((l) => l.kind === k)
          return (
            <Card key={k} className="p-4">
              <h3 className="text-md font-semibold text-text-primary">{KIND_LABEL[k]}</h3>
              <p className="mb-3 mt-0.5 text-xs text-text-muted">{KIND_HELP[k]}</p>
              {rows.length === 0 ? (
                <EmptyState title="Nothing yet" className="py-8" />
              ) : (
                <ul className="divide-y divide-border/60">
                  {rows.map((l) => {
                    const parent = l.parent_id ? all.find((p) => p.id === l.parent_id) : null
                    return (
                      <li key={l.id} className="flex items-center justify-between gap-2 py-1.5 text-sm">
                        <span className="text-text-primary">
                          {parent && <span className="text-text-muted">{parent.name} › </span>}
                          {l.name}
                        </span>
                        <span className="flex items-center gap-2 text-xs text-text-muted">
                          {l.code && <span className="font-mono">{l.code}</span>}
                          {l.gstin && <span className="font-mono">{l.gstin}</span>}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </Card>
          )
        })}
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New value"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} loading={create.isPending}>
              Add
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {error && <p className="text-sm text-status-action">{error}</p>}

          <Field label="Type" required>
            <Select
              value={kind}
              aria-label="Type"
              onChange={(e) => setKind(e.target.value as AssetLookupKind)}
            >
              {ASSET_LOOKUP_KIND.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Name" required>
            <Input value={name} aria-label="Name" onChange={(e) => setName(e.target.value)} />
          </Field>

          <Field label="Code" hint="Optional. Appears in generated asset tags for branches.">
            <Input value={code} aria-label="Code" onChange={(e) => setCode(e.target.value.toUpperCase())} />
          </Field>

          {kind === 'branch' && (
            <Field label="GSTIN" hint="If this branch has its own GST registration">
              <Input
                value={gstin}
                placeholder="29ABCDE1234F1Z5"
                aria-label="GSTIN"
                onChange={(e) => setGstin(e.target.value.toUpperCase())}
              />
            </Field>
          )}

          {kind === 'location' && locations.length > 0 && (
            <Field label="Within" hint="Optional — nest this location inside another">
              <Select value={parentId} aria-label="Within" onChange={(e) => setParentId(e.target.value)}>
                <option value="">Top level</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
      </Modal>
    </div>
  )
}
