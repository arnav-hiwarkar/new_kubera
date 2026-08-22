import { useEffect, useState } from 'react'
import { Pencil, Plus } from 'lucide-react'
import {
  Button,
  Card,
  Field,
  Input,
  Modal,
  Select,
  Spinner,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import {
  useCategoryTree,
  useCreateCategory,
  useItBlocks,
  useImpactPreview,
  useUpdateCategory,
} from '@/api/hooks/assetMasters'
import { DEPRECIATION_METHOD, ITC_TREATMENT, humanize } from '@/api/enums'
import type { AssetCategoryResponse } from '@/api/types'
import { months } from '../assetFormat'
import { ImpactNotice } from './ImpactNotice'

type Editor =
  | { mode: 'create' }
  | { mode: 'edit'; category: AssetCategoryResponse; parentOnly: boolean }

export function CategoriesTab() {
  const { tree, isLoading } = useCategoryTree()
  const { data: blocks = [] } = useItBlocks()
  const create = useCreateCategory()
  const update = useUpdateCategory()
  const toast = useToast()

  const [editor, setEditor] = useState<Editor | null>(null)
  const open = editor !== null
  const editingId =
    editor && editor.mode === 'edit' ? editor.category.id : null

  const [parentId, setParentId] = useState('')
  const [name, setName] = useState('')
  const [life, setLife] = useState('')
  const [method, setMethod] = useState('slm')
  const [residual, setResidual] = useState('5')
  const [blockId, setBlockId] = useState('')
  const [itc, setItc] = useState('')
  const [prefix, setPrefix] = useState('')
  const [error, setError] = useState('')
  const [acked, setAcked] = useState(false)

  const preview = useImpactPreview(editingId ? 'category' : null, editingId)
  const needsAck = !!preview.data && preview.data.classification !== 'none'

  // Reset the acknowledgement whenever a modal opens so each edit re-earns it.
  useEffect(() => setAcked(false), [open])

  const reset = () => {
    setParentId('')
    setName('')
    setLife('')
    setMethod('slm')
    setResidual('5')
    setBlockId('')
    setItc('')
    setPrefix('')
    setError('')
  }

  const openCreate = () => {
    reset()
    setEditor({ mode: 'create' })
  }

  const openEdit = (category: AssetCategoryResponse, parentOnly: boolean) => {
    setName(category.name)
    setPrefix(category.tag_prefix ?? '')
    setLife(
      category.default_useful_life_months != null
        ? String(category.default_useful_life_months)
        : '',
    )
    setMethod(category.default_dep_method ?? 'slm')
    setResidual(category.default_residual_pct != null ? String(category.default_residual_pct) : '')
    setBlockId(category.default_it_block_id ?? '')
    setItc(category.default_itc_treatment ?? '')
    setError('')
    setEditor({ mode: 'edit', category, parentOnly })
  }

  const handleSave = async () => {
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    try {
      if (editor?.mode === 'create') {
        await create.mutateAsync({
          name: name.trim(),
          parent_id: parentId || null,
          default_useful_life_months: life ? Number(life) : null,
          default_dep_method: parentId ? (method as 'slm' | 'wdv') : null,
          default_residual_pct: parentId && residual ? Number(residual) : null,
          default_it_block_id: blockId || null,
          default_itc_treatment: (itc || null) as 'eligible' | 'blocked' | 'partial' | null,
          tag_prefix: prefix.trim() || null,
          applicable_field_groups: [],
          display_order: 0,
        })
        toast.success('Category created')
      } else if (editor?.mode === 'edit') {
        if (editor.parentOnly) {
          await update.mutateAsync({
            id: editor.category.id,
            body: { name: name.trim(), tag_prefix: prefix.trim() || null },
          })
        } else {
          await update.mutateAsync({
            id: editor.category.id,
            body: {
              name: name.trim(),
              tag_prefix: prefix.trim() || null,
              default_useful_life_months: life ? Number(life) : null,
              default_dep_method: method as 'slm' | 'wdv',
              default_residual_pct: residual ? Number(residual) : null,
              default_it_block_id: blockId || null,
              default_itc_treatment: (itc || null) as 'eligible' | 'blocked' | 'partial' | null,
            },
          })
        }
        toast.success('Category updated')
      }
      setEditor(null)
      reset()
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === 'string') {
        setError(e.detail)
        return
      }
      setError(e instanceof Error ? e.message : 'Could not save the category')
    }
  }

  if (isLoading) return <Spinner />

  const defaultsVisible =
    editor?.mode === 'create' ? !!parentId : editor ? !editor.parentOnly : false

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="max-w-2xl text-sm text-text-muted">
            Categories carry the defaults that keep the asset form short — Schedule II
            useful life, SLM/WDV, residual value, the income-tax block and the tag prefix.
            Your company owns its own editable copy of the statutory set.
          </p>
          <Button onClick={openCreate}>
            <Plus className="mr-1.5 h-4 w-4" />
            New category
          </Button>
        </div>
      </Card>

      <div className="flex flex-col gap-3">
        {tree.map((group) => (
          <Card key={group.parent.id} className="p-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-md font-semibold text-text-primary">{group.parent.name}</h3>
              {group.parent.tag_prefix && (
                <span className="rounded-pill bg-bg-raised px-2 py-0.5 font-mono text-xs text-text-muted">
                  {group.parent.tag_prefix}
                </span>
              )}
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Edit ${group.parent.name}`}
                className="ml-auto"
                onClick={() => openEdit(group.parent, true)}
              >
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
            </div>
            {group.children.length === 0 ? (
              <p className="text-sm text-text-muted">No subcategories.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                    <th className="py-1.5 font-medium">Subcategory</th>
                    <th className="py-1.5 font-medium">Useful life</th>
                    <th className="py-1.5 font-medium">Method</th>
                    <th className="py-1.5 font-medium">Residual</th>
                    <th className="py-1.5 font-medium">Tax block</th>
                    <th className="py-1.5 font-medium">ITC</th>
                    <th className="py-1.5" aria-label="Row actions" />
                  </tr>
                </thead>
                <tbody>
                  {group.children.map((c) => (
                    <tr key={c.id} className="border-b border-border/50 last:border-0">
                      <td className="py-1.5 pr-3">
                        <span className="text-text-primary">{c.name}</span>
                        {c.schedule_ii_reference && (
                          <span
                            className="ml-1.5 cursor-help text-xs text-text-muted"
                            title={c.schedule_ii_reference}
                          >
                            ⓘ
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-text-secondary">
                        {months(c.default_useful_life_months)}
                      </td>
                      <td className="py-1.5 pr-3 text-text-secondary">
                        {c.default_dep_method?.toUpperCase() ?? '—'}
                      </td>
                      <td className="py-1.5 pr-3 text-text-secondary">
                        {c.default_residual_pct != null ? `${c.default_residual_pct}%` : '—'}
                      </td>
                      <td className="py-1.5 pr-3 text-text-secondary">
                        {c.default_it_block_code
                          ? `${c.default_it_block_code} · ${c.default_it_block_rate}%`
                          : '—'}
                      </td>
                      <td className="py-1.5 pr-3 text-text-secondary">
                        {c.default_itc_treatment ? humanize(c.default_itc_treatment) : '—'}
                      </td>
                      <td className="py-1.5 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Edit ${c.name}`}
                          onClick={() => openEdit(c, false)}
                        >
                          <Pencil className="h-4 w-4" />
                          Edit
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        ))}
      </div>

      <Modal
        open={open}
        onClose={() => setEditor(null)}
        title={
          editor?.mode === 'create'
            ? 'New category'
            : editor
              ? `Edit ${editor.category.name}`
              : ''
        }
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
            <Button
              onClick={handleSave}
              loading={create.isPending || update.isPending}
              disabled={needsAck && !acked}
            >
              {editor?.mode === 'create' ? 'Create' : 'Save'}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {error && <p className="text-sm text-status-action">{error}</p>}

          {editor?.mode === 'create' && (
            <Field
              label="Parent category"
              hint="Leave blank to create a top-level category. The tree is two levels deep."
            >
              <Select value={parentId} onChange={(e) => setParentId(e.target.value)} aria-label="Parent category">
                <option value="">None — this is a top-level category</option>
                {tree.map((g) => (
                  <option key={g.parent.id} value={g.parent.id}>
                    {g.parent.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <Field label="Name" required>
            <Input value={name} onChange={(e) => setName(e.target.value)} aria-label="Name" />
          </Field>

          <Field label="Tag prefix" hint="Used to generate asset codes, e.g. COMP-000137">
            <Input
              value={prefix}
              maxLength={12}
              onChange={(e) => setPrefix(e.target.value.toUpperCase())}
              aria-label="Tag prefix"
            />
          </Field>

          {defaultsVisible && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Field label="Useful life (months)">
                  <Input
                    type="number"
                    min={1}
                    value={life}
                    onChange={(e) => setLife(e.target.value)}
                    aria-label="Useful life (months)"
                  />
                </Field>
                <Field label="Method">
                  <Select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Method">
                    {DEPRECIATION_METHOD.map((m) => (
                      <option key={m} value={m}>
                        {m.toUpperCase()}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Residual %">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step="0.01"
                    value={residual}
                    onChange={(e) => setResidual(e.target.value)}
                    aria-label="Residual %"
                  />
                </Field>
              </div>

              <Field label="Income-tax block">
                <Select value={blockId} onChange={(e) => setBlockId(e.target.value)} aria-label="Income-tax block">
                  <option value="">Not set</option>
                  {blocks.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.code} — {b.name} ({b.dep_rate}%)
                    </option>
                  ))}
                </Select>
              </Field>

              <Field
                label="Default ITC treatment"
                hint="Set to Blocked for assets whose GST credit is disallowed, e.g. motor cars."
              >
                <Select value={itc} onChange={(e) => setItc(e.target.value)} aria-label="Default ITC treatment">
                  <option value="">Not set</option>
                  {ITC_TREATMENT.map((t) => (
                    <option key={t} value={t}>
                      {humanize(t)}
                    </option>
                  ))}
                </Select>
              </Field>
            </>
          )}

          <ImpactNotice kind="category" id={editingId} />
        </div>
      </Modal>
    </div>
  )
}
