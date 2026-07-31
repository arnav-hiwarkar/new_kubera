import { useQuery } from '@tanstack/react-query'
import { Card, Spinner } from '@/components/ui'
import { useActivityLog } from '@/api/hooks/activity'
import type { AssetDetail } from '@/api/hooks/assets'
import { usersApi } from '@/api/endpoints/users'
import { formatRelative } from '@/lib/format'
import { dateOrDash, money } from '../assetFormat'
import { DerivedRow } from './SectionShell'

const ACTION_LABEL: Record<string, string> = {
  'asset.created': 'Created',
  'asset.updated': 'Updated',
  'asset.submitted': 'Submitted for approval',
  'asset.capitalized': 'Approved and capitalized',
  'asset.rejected': 'Sent back to draft',
  'asset.deleted': 'Deleted',
  'asset_document.uploaded': 'Document attached',
  'asset_acquisition.updated': 'Acquisition updated',
}

export function HistoryTab({ detail }: { detail: AssetDetail }) {
  const asset = detail.asset
  const { data: entries = [], isLoading } = useActivityLog({ entity_id: asset.id })

  // Resolve actor names where we can; the activity log stores only the actor id.
  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
  const nameById: Record<string, string> = {}
  for (const u of usersQuery.data ?? []) nameById[u.id] = u.full_name
  const who = (id: string | null | undefined) =>
    id ? (nameById[id] ?? `${id.slice(0, 8)}…`) : '—'

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4">
        <h4 className="mb-2 text-sm font-semibold text-text-primary">Attribution</h4>
        <DerivedRow label="Created by" value={who(asset.created_by)} />
        <DerivedRow
          label="Submitted by"
          value={
            asset.submitted_by
              ? `${who(asset.submitted_by)}${asset.submitted_at ? ` · ${formatRelative(asset.submitted_at)}` : ''}`
              : 'Not submitted'
          }
        />
        <DerivedRow
          label="Approved by"
          value={
            asset.approved_by
              ? `${who(asset.approved_by)}${asset.approved_at ? ` · ${formatRelative(asset.approved_at)}` : ''}`
              : 'Not approved'
          }
        />
        <DerivedRow label="Capitalization date" value={dateOrDash(asset.capitalization_date)} />
        <DerivedRow label="Capitalized cost" value={money(asset.original_cost)} emphasis />
      </Card>

      <Card className="p-4">
        <h4 className="mb-3 text-sm font-semibold text-text-primary">Audit trail</h4>
        {isLoading ? (
          <Spinner />
        ) : entries.length === 0 ? (
          <p className="text-sm text-text-muted">No recorded activity for this asset yet.</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {entries.map((e) => (
              <li key={e.id} className="flex gap-3">
                <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm text-text-primary">
                    {ACTION_LABEL[e.action] ?? e.action}
                  </p>
                  <p className="text-xs text-text-muted">
                    {who(e.actor_id)} · {formatRelative(e.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  )
}
