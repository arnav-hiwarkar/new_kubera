import { useMemo } from 'react'
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
 * This is the highest-leverage control on the create form: the leaf carries the
 * Schedule II useful life, SLM/WDV, residual %, income-tax block and rate, so
 * choosing here fills five statutory fields the user never has to see. The hint
 * below the select says so, otherwise those auto-filled values look like magic.
 */
export function CategoryPicker({ value, onChange, error, required, disabled }: CategoryPickerProps) {
  const { tree, isLoading } = useCategoryTree()

  const parentOf = useMemo(() => {
    for (const group of tree) {
      if (group.parent.id === value) return group.parent.id
      if (group.children.some((c) => c.id === value)) return group.parent.id
    }
    return ''
  }, [tree, value])

  const selectedGroup = tree.find((g) => g.parent.id === parentOf)
  const leaf = selectedGroup?.children.find((c) => c.id === value)

  const hint = leaf
    ? [
        leaf.default_useful_life_months ? `Useful life ${months(leaf.default_useful_life_months)}` : null,
        leaf.default_dep_method ? leaf.default_dep_method.toUpperCase() : null,
        leaf.default_it_block_code ? `IT block ${leaf.default_it_block_code}` : null,
        leaf.default_it_block_rate != null ? `${leaf.default_it_block_rate}%` : null,
        leaf.default_itc_treatment === 'blocked' ? 'ITC blocked' : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : 'Picking a subcategory fills in useful life, method, residual value and the tax block.'

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Category" required={required} error={error}>
        <Select
          value={parentOf}
          error={!!error}
          disabled={disabled || isLoading}
          aria-label="Category"
          onChange={(e) => {
            const groupId = e.target.value
            const group = tree.find((g) => g.parent.id === groupId)
            // Auto-select when there is only one subcategory — an extra click that
            // never carries information.
            if (group && group.children.length === 1) onChange(group.children[0].id)
            else if (group && group.children.length === 0) onChange(group.parent.id)
            else onChange('')
          }}
        >
          <option value="">Select a category…</option>
          {tree.map((g) => (
            <option key={g.parent.id} value={g.parent.id}>
              {g.parent.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Subcategory" required={required} hint={hint}>
        <Select
          value={leaf?.id ?? (selectedGroup && selectedGroup.children.length === 0 ? selectedGroup.parent.id : '')}
          disabled={disabled || !selectedGroup || selectedGroup.children.length === 0}
          aria-label="Subcategory"
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            {selectedGroup && selectedGroup.children.length === 0
              ? 'No subcategories'
              : 'Select a subcategory…'}
          </option>
          {(selectedGroup?.children ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
    </div>
  )
}
