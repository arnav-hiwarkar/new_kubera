import { useCallback, useEffect, useMemo, useState } from 'react'

/**
 * Local draft state for one tab of the asset detail page.
 *
 * Each tab edits a slice of the record and saves independently, so the page never
 * holds one enormous form object and a user can fill the Depreciation tab without
 * the Acquisition tab's half-typed values riding along. `save` sends only the keys
 * that actually changed, which matters because the backend rejects locked fields
 * by name — sending an unchanged `unit_basic_price` on a capitalized asset would
 * trip that guard for no reason.
 */
export function useSectionForm<T extends Record<string, unknown>>(
  initial: T,
  onSave: (patch: Partial<T>) => Promise<unknown>,
) {
  const [values, setValues] = useState<T>(initial)
  const [saving, setSaving] = useState(false)

  // Re-seed when the server copy changes (after a save, or a sibling switch).
  const signature = JSON.stringify(initial)
  useEffect(() => {
    setValues(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])

  const set = useCallback(<K extends keyof T>(key: K, value: T[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }))
  }, [])

  const patch = useMemo(() => {
    const out: Partial<T> = {}
    for (const key of Object.keys(values) as (keyof T)[]) {
      const next = values[key]
      const prev = initial[key]
      // Treat '' and null as the same absent value so merely focusing and blurring
      // an empty input does not mark the section dirty.
      const normalize = (v: unknown) => (v === '' || v === undefined ? null : v)
      if (JSON.stringify(normalize(next)) !== JSON.stringify(normalize(prev))) {
        out[key] = next
      }
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, signature])

  const dirty = Object.keys(patch).length > 0

  const save = useCallback(async () => {
    if (!dirty) return
    setSaving(true)
    try {
      await onSave(patch)
    } finally {
      setSaving(false)
    }
  }, [dirty, onSave, patch])

  const reset = useCallback(() => setValues(initial), [signature]) // eslint-disable-line react-hooks/exhaustive-deps

  return { values, set, setValues, patch, dirty, save, saving, reset }
}

/** Turn '' into null for optional API fields; leave real values alone. */
export function emptyToNull<T>(value: T | '' | undefined): T | null {
  return value === '' || value === undefined ? null : value
}

/** Parse a numeric input's string into a number, or null when blank. */
export function numOrNull(value: string): number | null {
  if (value.trim() === '') return null
  const n = Number(value)
  return Number.isNaN(n) ? null : n
}
