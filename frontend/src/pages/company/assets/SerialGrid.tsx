import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Input, StatusBadge, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAssignSerials } from '@/api/hooks/assets'
import type { AssetSibling } from '@/api/types'

/**
 * Per-unit serial entry for an exploded batch.
 *
 * Exploding 50 chairs into 50 rows is the right data model, but typing 50 serials
 * one detail page at a time is not. This grid fills them in one request.
 */
export function SerialGrid({
  anchorAssetId,
  siblings,
  currentAssetId,
}: {
  anchorAssetId: string
  siblings: AssetSibling[]
  currentAssetId: string
}) {
  const toast = useToast()
  const assign = useAssignSerials()
  const [serials, setSerials] = useState<Record<string, string>>({})

  const signature = siblings.map((s) => `${s.id}:${s.manufacturer_serial_number ?? ''}`).join('|')
  useEffect(() => {
    const next: Record<string, string> = {}
    for (const s of siblings) next[s.id] = s.manufacturer_serial_number ?? ''
    setSerials(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])

  const dirty = siblings.some((s) => (serials[s.id] ?? '') !== (s.manufacturer_serial_number ?? ''))

  const handleSave = async () => {
    const assignments = siblings
      .filter((s) => (serials[s.id] ?? '') !== (s.manufacturer_serial_number ?? ''))
      .map((s) => ({ asset_id: s.id, manufacturer_serial_number: serials[s.id] || null }))
    if (assignments.length === 0) return
    try {
      await assign.mutateAsync({ id: anchorAssetId, body: { assignments } })
      toast.success(`Updated ${assignments.length} unit${assignments.length === 1 ? '' : 's'}`)
    } catch (e) {
      toast.error(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : e instanceof Error
            ? e.message
            : 'Could not save serials',
      )
    }
  }

  if (siblings.length <= 1) return null

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-text-primary">
            Batch of {siblings.length} units
          </h4>
          <p className="text-xs text-text-muted">
            All units share this acquisition's invoice and costs. Serials are per unit.
          </p>
        </div>
        {dirty && (
          <Button size="sm" onClick={handleSave} loading={assign.isPending}>
            Save serials
          </Button>
        )}
      </div>

      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-bg-surface">
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
              <th className="py-2 pr-2 font-medium">#</th>
              <th className="py-2 pr-2 font-medium">Tag</th>
              <th className="py-2 pr-2 font-medium">Status</th>
              <th className="py-2 font-medium">Serial number</th>
            </tr>
          </thead>
          <tbody>
            {siblings.map((s) => (
              <tr
                key={s.id}
                className={s.id === currentAssetId ? 'bg-accent-subtle/40' : undefined}
              >
                <td className="py-1.5 pr-2 tabular-nums text-text-muted">{s.unit_index}</td>
                <td className="py-1.5 pr-2">
                  <Link
                    to={`/app/assets/${s.id}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {s.asset_code ?? '—'}
                  </Link>
                </td>
                <td className="py-1.5 pr-2">
                  <StatusBadge status={s.lifecycle_status} />
                </td>
                <td className="py-1.5">
                  <Input
                    className="h-8"
                    value={serials[s.id] ?? ''}
                    aria-label={`Serial number for unit ${s.unit_index}`}
                    onChange={(e) => setSerials((prev) => ({ ...prev, [s.id]: e.target.value }))}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
