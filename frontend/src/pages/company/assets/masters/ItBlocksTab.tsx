import { Lock } from 'lucide-react'
import { DataTable, type Column } from '@/components/ui'
import { useItBlocks } from '@/api/hooks/assetMasters'
import { humanize } from '@/api/enums'
import type { ItAssetBlockResponse } from '@/api/types'

/**
 * Read-only. The Appendix I blocks and their rates are statutory, shipped as seeded
 * global rows, and not something a company should be quietly editing — an
 * unnoticed rate change would silently misstate the tax computation. A company that
 * genuinely needs an extra block can add one, which is a deliberate act.
 */
export function ItBlocksTab() {
  const { data: blocks = [], isLoading } = useItBlocks()

  const columns: Column<ItAssetBlockResponse>[] = [
    {
      key: 'code',
      header: 'Block',
      sortValue: (b) => b.code,
      cell: (b) => (
        <span className="inline-flex items-center gap-1.5 font-mono text-xs">
          {b.code}
          {b.company_id === null && (
            <Lock className="h-3 w-3 text-text-muted" aria-label="Statutory, read-only" />
          )}
        </span>
      ),
    },
    { key: 'name', header: 'Description', sortValue: (b) => b.name },
    {
      key: 'block_class',
      header: 'Class',
      sortValue: (b) => b.block_class,
      cell: (b) => humanize(b.block_class),
    },
    {
      key: 'dep_rate',
      header: 'Rate',
      align: 'right',
      sortValue: (b) => b.dep_rate,
      cell: (b) => `${b.dep_rate}%`,
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Income Tax Act Appendix I blocks. Tax depreciation is computed at block level,
        not per asset, so each asset points at the block it belongs to. These rates are
        statutory and ship with the product.
      </p>
      <DataTable
        columns={columns}
        data={blocks}
        rowKey={(b) => b.id}
        loading={isLoading}
        pageSize={20}
        searchAccessors={(b) => `${b.code} ${b.name}`}
        searchPlaceholder="Search blocks…"
        emptyTitle="No blocks"
      />
    </div>
  )
}
