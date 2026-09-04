import { useQuery } from '@tanstack/react-query'
import { Card, Spinner } from '@/components/ui'
import { useActivityLog } from '@/api/hooks/activity'
import type { AssetDetail } from '@/api/hooks/assets'
import { usersApi } from '@/api/endpoints/users'
import { formatRelative } from '@/lib/format'
import { dateOrDash, money, num } from '../assetFormat'
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
  'asset.disposed': 'Disposed',
}

const DISPOSAL_TYPE_LABEL: Record<string, string> = {
  sale: 'Sale',
  scrap: 'Scrapped',
  write_off: 'Written off',
  loss_destruction: 'Loss / destruction',
  insurance_claim: 'Insurance claim',
}

export function HistoryTab({ detail }: { detail: AssetDetail }) {
  const asset = detail.asset
  const { data: entries = [], isLoading } = useActivityLog({ entity_id: asset.id })

  // Compare numerically, not as strings: both are serialised Decimals, so
  // "10000.0" and "10000.00" are the same figure and should not read as a
  // divergence between the book and tax consideration.
  const itProceeds = num(asset.disposal_it_proceeds)
  const itProceedsDiffer = itProceeds !== null && itProceeds !== num(asset.sale_proceeds)

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

      {asset.lifecycle_status === 'disposed' && (
        <Card className="p-4">
          <h4 className="mb-2 text-sm font-semibold text-text-primary">Disposal</h4>
          <p className="mb-3 text-xs text-text-muted">
            Disposing an asset is an accounting event with a profit-or-loss consequence and
            there is no reversal path, so only a company admin can record one. The gain or
            loss itself depends on depreciation charged up to the disposal date — see the
            Depreciation tab for the figure.
          </p>
          <DerivedRow label="Disposal date" value={dateOrDash(asset.disposal_date)} />
          <DerivedRow
            label="Disposal type"
            value={
              asset.disposal_type
                ? (DISPOSAL_TYPE_LABEL[asset.disposal_type] ?? asset.disposal_type)
                : '—'
            }
          />
          <DerivedRow label="Sale proceeds" value={money(asset.sale_proceeds)} emphasis />
          {itProceedsDiffer && (
              <DerivedRow
                label="Sale consideration for Income Tax"
                value={money(asset.disposal_it_proceeds)}
                hint="Differs from the book proceeds; this is the figure the IT block uses."
              />
            )}
          <DerivedRow label="Buyer" value={asset.buyer_name || '—'} />
          <DerivedRow label="Disposal invoice no." value={asset.disposal_invoice_no || '—'} />
          <DerivedRow label="Remarks" value={asset.disposal_remarks || '—'} />
          <DerivedRow label="Disposed by" value={who(asset.disposed_by)} />
        </Card>
      )}

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
