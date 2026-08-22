import { useEffect, useState } from 'react'
import { Lock, Pencil, Plus } from 'lucide-react'
import {
  Button,
  DataTable,
  Field,
  Input,
  Modal,
  Select,
  useToast,
  type Column,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import {
  useCreateItBlock,
  useImpactPreview,
  useItBlocks,
  useUpdateItBlock,
} from '@/api/hooks/assetMasters'
import { humanize } from '@/api/enums'
import type { ItAssetBlockResponse } from '@/api/types'
import { ImpactNotice } from './ImpactNotice'

const BLOCK_CLASSES = ['building', 'furniture', 'plant_machinery', 'intangible'] as const

/**
 * Company-owned copies of the Appendix I blocks. The rates are still statutory
 * in origin, but a company can now adjust them deliberately — which is why every
 * edit shows a live impact verdict and requires an acknowledgement when
 * depreciation runs would be affected.
 */
export function ItBlocksTab() {
  const { data: blocks = [], isLoading } = useItBlocks()
  const create = useCreateItBlock()
  const update = useUpdateItBlock()
  const toast = useToast()

  const [editor, setEditor] = useState<
    { mode: 'create' } | { mode: 'edit'; block: ItAssetBlockResponse } | null
  >(null)
  const open = editor !== null
  const editingId = editor?.mode === 'edit' ? editor.block.id : null

  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [rate, setRate] = useState('')
  const [blockClass, setBlockClass] = useState('plant_machinery')
  const [order, setOrder] = useState('0')
  const [active, setActive] = useState(true)
  const [error, setError] = useState('')
  const [acked, setAcked] = useState(false)

  const preview = useImpactPreview(editingId ? 'it_block' : null, editingId)
  const needsAck = !!preview.data && preview.data.classification !== 'none'

  // Reset the acknowledgement whenever a modal opens so each edit re-earns it.
  useEffect(() => setAcked(false), [open])

  const openCreate = () => {
    setCode('')
    setName('')
    setRate('')
    setBlockClass('plant_machinery')
    setOrder('0')
    setActive(true)
    setError('')
    setEditor({ mode: 'create' })
  }

  const openEdit = (b: ItAssetBlockResponse) => {
    setCode(b.code)
    setName(b.name)
    setRate(String(b.dep_rate))
    setBlockClass(b.block_class)
    setOrder(String(b.display_order))
    setActive(b.is_active)
    setError('')
    setEditor({ mode: 'edit', block: b })
  }

  const handleSave = async () => {
    if (!code.trim() || !name.trim()) {
      setError('Code and description are required')
      return
    }
    if (rate === '' || Number.isNaN(Number(rate))) {
      setError('Rate must be a number')
      return
    }
    try {
      if (editor?.mode === 'edit') {
        await update.mutateAsync({
          id: editor.block.id,
          body: {
            code: code.trim(),
            name: name.trim(),
            dep_rate: Number(rate),
            block_class: blockClass as ItAssetBlockResponse['block_class'],
            display_order: order === '' ? undefined : Number(order),
            is_active: active,
          },
        })
        toast.success('Block updated')
      } else {
        await create.mutateAsync({
          code: code.trim(),
          name: name.trim(),
          dep_rate: Number(rate),
          block_class: blockClass as ItAssetBlockResponse['block_class'],
          display_order: order === '' ? 0 : Number(order),
        })
        toast.success('Block created')
      }
      setEditor(null)
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === 'string') {
        setError(e.detail)
        return
      }
      setError(e instanceof Error ? e.message : 'Could not save the block')
    }
  }

  const columns: Column<ItAssetBlockResponse>[] = [
    {
      key: 'code',
      header: 'Block',
      sortValue: (b) => b.code,
      cell: (b) => (
        <span className="inline-flex items-center gap-1.5 font-mono text-xs">
          {b.code}
          {b.company_id === null && (
            <Lock className="h-3 w-3 text-text-muted" aria-label="Statutory, read-only" />
          )}
        </span>
      ),
    },
    { key: 'name', header: 'Description', sortValue: (b) => b.name },
    {
      key: 'block_class',
      header: 'Class',
      sortValue: (b) => b.block_class,
      cell: (b) => humanize(b.block_class),
    },
    {
      key: 'dep_rate',
      header: 'Rate',
      align: 'right',
      sortValue: (b) => b.dep_rate,
      cell: (b) => `${b.dep_rate}%`,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      cell: (b) => (
        <Button variant="ghost" size="sm" aria-label={`Edit ${b.name}`} onClick={() => openEdit(b)}>
          <Pencil className="h-4 w-4" />
          Edit
        </Button>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Income Tax Act Appendix I blocks. Tax depreciation is computed at block level,
        not per asset, so each asset points at the block it belongs to. Your company
        owns its own copy of the statutory set and can adjust it when needed.
      </p>
      <DataTable
        columns={columns}
        data={blocks}
        rowKey={(b) => b.id}
        loading={isLoading}
        pageSize={20}
        searchAccessors={(b) => `${b.code} ${b.name}`}
        searchPlaceholder="Search blocks…"
        emptyTitle="No blocks"
        toolbar={
          <Button size="sm" onClick={openCreate}>
            <Plus className="mr-1.5 h-4 w-4" />
            New block
          </Button>
        }
      />

      <Modal
        open={open}
        onClose={() => setEditor(null)}
        title={editor?.mode === 'edit' ? `Edit ${editor.block.code}` : 'New block'}
        size="lg"
        footer={
          <>
            {needsAck && (
              <label className="mr-auto flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  aria-label="I understand"
                  checked={acked}
                  onChange={(e) => setAcked(e.target.checked)}
                />
                I understand the effects described above
              </label>
            )}
            <Button variant="ghost" onClick={() => setEditor(null)}>
              Cancel
            </Button>
            <Button onClick={handleSave} loading={create.isPending || update.isPending} disabled={needsAck && !acked}>
              Save
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {error && <p className="text-sm text-status-action">{error}</p>}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Code" required hint="Short identifier shown in reports, e.g. PM-15">
              <Input value={code} aria-label="Code" onChange={(e) => setCode(e.target.value.toUpperCase())} />
            </Field>
            <Field label="Rate (%)" required>
              <Input
                type="number"
                min={0}
                max={100}
                step="0.01"
                value={rate}
                aria-label="Rate"
                onChange={(e) => setRate(e.target.value)}
              />
            </Field>
          </div>

          <Field label="Description" required>
            <Input value={name} aria-label="Name" onChange={(e) => setName(e.target.value)} />
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Class" hint="Orders the block-wise tax summary">
              <Select
                value={blockClass}
                aria-label="Class"
                onChange={(e) => setBlockClass(e.target.value)}
              >
                {BLOCK_CLASSES.map((c) => (
                  <option key={c} value={c}>
                    {humanize(c)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Display order">
              <Input
                type="number"
                value={order}
                aria-label="Display order"
                onChange={(e) => setOrder(e.target.value)}
              />
            </Field>
          </div>

          {editor?.mode === 'edit' && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={active}
                aria-label="Active"
                onChange={(e) => setActive(e.target.checked)}
              />
              Active — inactive blocks are hidden when assigning assets
            </label>
          )}

          <ImpactNotice kind="it_block" id={editingId} />
        </div>
      </Modal>
    </div>
  )
}
