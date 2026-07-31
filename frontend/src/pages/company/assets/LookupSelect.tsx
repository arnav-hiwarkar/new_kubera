import { Field, Select } from '@/components/ui'
import { useAssetLookups } from '@/api/hooks/assetMasters'
import type { AssetLookupKind } from '@/api/types'

export interface LookupSelectProps {
  kind: AssetLookupKind
  label: string
  value: string | null
  onChange: (id: string | null) => void
  required?: boolean
  error?: string
  disabled?: boolean
  hint?: string
}

/** Select over one dimension of asset_lookups (branch / cost centre / department /
 *  location). Empty means "not set" and is sent as null, not ''. */
export function LookupSelect({
  kind,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
  hint,
}: LookupSelectProps) {
  const { data = [], isLoading } = useAssetLookups(kind)

  const emptyHint =
    !isLoading && data.length === 0
      ? `No ${label.toLowerCase()} values yet — add them under Asset masters.`
      : hint

  return (
    <Field label={label} required={required} error={error} hint={emptyHint}>
      <Select
        value={value ?? ''}
        error={!!error}
        disabled={disabled || isLoading}
        aria-label={label}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">Not set</option>
        {data.map((l) => (
          <option key={l.id} value={l.id}>
            {l.code ? `${l.code} — ${l.name}` : l.name}
          </option>
        ))}
      </Select>
    </Field>
  )
}
