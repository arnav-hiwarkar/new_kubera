import { useCallback, useState } from 'react'

/**
 * Which register columns are shown, persisted per browser.
 *
 * The register has ~15 useful columns and no single default suits both finance and
 * operations, so the choice is the user's. localStorage rather than a server-side
 * preference: it is a display nicety, not data worth a table and a migration.
 *
 * Kept out of AssetColumnPicker.tsx so that file only exports a component (React
 * Fast Refresh cannot handle a module that mixes components and hooks).
 */
const STORAGE_KEY = 'kubera.assets.columns'

export const DEFAULT_COLUMNS = [
  'asset_code',
  'asset_name',
  'category',
  'lifecycle_status',
  'original_cost',
  'location',
  'custodian',
]

export function useColumnPreference() {
  const [visible, setVisibleState] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return DEFAULT_COLUMNS
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) && parsed.length > 0 ? (parsed as string[]) : DEFAULT_COLUMNS
    } catch {
      // Private browsing or a corrupt value — fall back rather than break the page.
      return DEFAULT_COLUMNS
    }
  })

  const setVisible = useCallback((next: string[]) => {
    setVisibleState(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* non-fatal: the table still works, the choice just won't persist */
    }
  }, [])

  return { visible, setVisible }
}
