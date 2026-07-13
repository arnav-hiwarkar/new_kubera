/** Frontend-owned shape stored in `metadata_schema` (backend stores JSONB as-is). */
export type FieldType = 'text' | 'number' | 'date' | 'dropdown'

export interface FieldDef {
  key: string
  label: string
  type: FieldType
  options?: string[]
  required?: boolean
}

export const FIELD_TYPES: FieldType[] = ['text', 'number', 'date', 'dropdown']

/** Derive a snake_case key from a human field label. */
export function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

/** Defensively read the field list out of a loosely-typed metadata_schema. */
export function readFields(schema: unknown): FieldDef[] {
  const raw = (schema as { fields?: unknown } | null)?.fields
  if (!Array.isArray(raw)) return []
  const out: FieldDef[] = []
  for (const item of raw) {
    const f = item as { key?: unknown; label?: unknown; type?: unknown; options?: unknown; required?: unknown }
    if (typeof f.label !== 'string') continue
    const type = FIELD_TYPES.includes(f.type as FieldType) ? (f.type as FieldType) : 'text'
    out.push({
      key: typeof f.key === 'string' && f.key ? f.key : slugify(f.label),
      label: f.label,
      type,
      options: Array.isArray(f.options) ? f.options.map(String) : [],
      required: Boolean(f.required),
    })
  }
  return out
}
