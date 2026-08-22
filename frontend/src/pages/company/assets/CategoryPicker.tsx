import { useEffect, useMemo, useState } from 'react'
import { Field, Select } from '@/components/ui'
import { useCategoryTree } from '@/api/hooks/assetMasters'
import { months } from './assetFormat'

export interface CategoryPickerProps {
  value: string
  onChange: (categoryId: string) => void
  error?: string
  required?: boolean
  disabled?: boolean
}

/**
 * Two-step category → subcategory picker.
 *
 * `parentId` is its own piece of state: picking a parent with several
 * subcategories must visibly stick while the leaf is still empty — deriving
 * the parent from the (empty) leaf value snapped the selection back to the
 * placeholder, which read as "most categories are not clickable".
 */
export function CategoryPicker({ value, onChange, error, required, disabled }: CategoryPickerProps) {
  const { tree, isLoading } = useCategoryTree()
  const [parentId, setParentId] = useState('')

  const groupOfValue = useMemo(
    () =>
      tree.find((g) => g.parent.id === value) ??
      tree.find((g) => g.children.some((c) => c.id === value)),
    [tree, value],
  )

  // Sync local selection when an external value names a different group
  // (form reset, prefill); ignore same-group changes to avoid loops.
  useEffect(() => {
    setParentId(groupOfValue ? groupOfValue.parent.id : '')
  }, [groupOfValue?.parent.id])

  const group = tree.find((g) => g.parent.id === parentId)
  // Zero-child groups select themselves; otherwise show the leaf only if it
  // belongs to this group.
  const shownLeaf =
    group && group.children.length > 0 && group.children.some((c) => c.id === value)
      ? value
      : ''

  const hintLeaf = group?.children.find((c) => c.id === shownLeaf)
  const hint = hintLeaf
    ? [
        hintLeaf.default_useful_life_months ? `Useful life ${months(hintLeaf.default_useful_life_months)}` : null,
        hintLeaf.default_dep_method ? hintLeaf.default_dep_method.toUpperCase() : null,
        hintLeaf.default_it_block_code ? `IT block ${hintLeaf.default_it_block_code}` : null,
        hintLeaf.default_it_block_rate != null ? `${hintLeaf.default_it_block_rate}%` : null,
        hintLeaf.default_itc_treatment === 'blocked' ? 'ITC blocked' : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : 'Picking a subcategory fills in useful life, method, residual value and the tax block.'

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Category" required={required} error={error}>
        <Select
          value={parentId}
          error={!!error}
          disabled={disabled || isLoading}
          aria-label="Category"
          onChange={(e) => {
            const id = e.target.value
            setParentId(id)
            const g = tree.find((x) => x.parent.id === id)
            if (g && g.children.length === 1) onChange(g.children[0].id)
            else if (g && g.children.length === 0) onChange(g.parent.id)
            else onChange('')
          }}
        >
          <option value="">Select a category…</option>
          {tree.map((g) => (
            <option key={g.parent.id} value={g.parent.id}>{g.parent.name}</option>
          ))}
        </Select>
      </Field>

      <Field label="Subcategory" required={required} hint={hint}>
        <Select
          value={shownLeaf}
          disabled={disabled || !group || group.children.length === 0}
          aria-label="Subcategory"
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            {group && group.children.length === 0 ? 'No subcategories' : 'Select a subcategory…'}
          </option>
          {(group?.children ?? []).map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </Select>
      </Field>
    </div>
  )
}
