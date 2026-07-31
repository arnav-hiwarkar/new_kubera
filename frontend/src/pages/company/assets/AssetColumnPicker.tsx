import { useEffect, useState } from 'react'
import { Button, Modal } from '@/components/ui'
import { DEFAULT_COLUMNS } from './useColumnPreference'

export interface AssetColumnPickerProps {
  open: boolean
  onClose: () => void
  options: { key: string; label: string }[]
  visible: string[]
  onChange: (next: string[]) => void
}

export function AssetColumnPicker({
  open,
  onClose,
  options,
  visible,
  onChange,
}: AssetColumnPickerProps) {
  const [draft, setDraft] = useState<string[]>(visible)

  useEffect(() => {
    if (open) setDraft(visible)
  }, [open, visible])

  const toggle = (key: string) =>
    setDraft((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))

  const apply = () => {
    // Keep the canonical option order so toggling never scrambles the table.
    onChange(options.filter((o) => draft.includes(o.key)).map((o) => o.key))
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Columns"
      footer={
        <>
          <Button variant="ghost" onClick={() => setDraft(DEFAULT_COLUMNS)}>
            Reset
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={apply} disabled={draft.length === 0}>
            Apply
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-text-muted">
        Choose what the register shows. Saved in this browser.
      </p>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {options.map((o) => (
          <label
            key={o.key}
            className="flex cursor-pointer items-center gap-2 rounded-input px-2 py-1.5 text-sm text-text-secondary hover:bg-bg-raised"
          >
            <input
              type="checkbox"
              checked={draft.includes(o.key)}
              onChange={() => toggle(o.key)}
              aria-label={o.label}
            />
            {o.label}
          </label>
        ))}
      </div>
      {draft.length === 0 && (
        <p className="mt-2 text-xs text-status-action">Pick at least one column.</p>
      )}
    </Modal>
  )
}
