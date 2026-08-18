import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Boxes, IndianRupee, Landmark, Laptop, Settings2 } from 'lucide-react'
import {
  Button,
  DataTable,
  PageHeader,
  Select,
  StatCard,
  StatusBadge,
  Tabs,
  useToast,
  type Column,
  type TabItem,
} from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { useAssets } from '@/api/hooks/assets'
import { useCategoryNames, useLookupNames } from '@/api/hooks/assetMasters'
import { assetsApi } from '@/api/endpoints/assets'
import { ASSET_CONDITION, ASSET_OPERATIONAL_STATUS, humanize } from '@/api/enums'
import { formatMoney } from '@/lib/format'
import { saveBlob } from '@/lib/download'
import type { AssetResponse } from '@/api/types'
import { dateOrDash, num } from './assetFormat'
import { QuickAddAssetModal } from './QuickAddAssetModal'
import { AssetColumnPicker } from './AssetColumnPicker'
import { useColumnPreference } from './useColumnPreference'

/** Preset views. Drafts and pending work are the daily job; capitalized is the
 *  statutory register. One undifferentiated list serves neither well. */
const VIEWS: { id: string; label: string; lifecycle?: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'draft', label: 'Drafts', lifecycle: 'draft' },
  { id: 'ready', label: 'Awaiting approval', lifecycle: 'ready' },
  { id: 'capitalized', label: 'Capitalized', lifecycle: 'capitalized' },
  { id: 'disposed', label: 'Disposed', lifecycle: 'disposed' },
]

export function AssetsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { profile } = useCompanyAuth()
  const isAdmin = profile?.role === 'admin'

  const [view, setView] = useState('all')
  const [operational, setOperational] = useState('')
  const [condition, setCondition] = useState('')
  const [quickAddOpen, setQuickAddOpen] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const { visible, setVisible } = useColumnPreference()

  const lifecycle = VIEWS.find((v) => v.id === view)?.lifecycle
  const filters = {
    ...(lifecycle ? { lifecycle_status: lifecycle } : {}),
    ...(operational ? { operational_status: operational } : {}),
    ...(condition ? { condition } : {}),
  }
  const { data: assets = [], isLoading } = useAssets(filters)
  // Unfiltered copy, so the stat cards and the view counts describe the whole
  // register rather than whatever is currently filtered on screen.
  const { data: allAssets = [] } = useAssets()

  const categoryNames = useCategoryNames()
  const lookupNames = useLookupNames()

  // Gross block is what makes this a register rather than a list, so it counts
  // capitalized assets only — a draft is not on the books and including it would
  // overstate the balance sheet.
  const stats = useMemo(() => {
    const capitalized = allAssets.filter((a) => a.lifecycle_status === 'capitalized')
    return {
      total: allAssets.length,
      capitalized: capitalized.length,
      grossBlock: capitalized.reduce((sum, a) => sum + (num(a.original_cost) ?? 0), 0),
      pending: allAssets.filter((a) => a.lifecycle_status === 'ready').length,
      drafts: allAssets.filter((a) => a.lifecycle_status === 'draft').length,
      disposed: allAssets.filter((a) => a.lifecycle_status === 'disposed').length,
    }
  }, [allAssets])

  const counts: Record<string, number> = {
    all: stats.total,
    draft: stats.drafts,
    ready: stats.pending,
    capitalized: stats.capitalized,
    disposed: stats.disposed,
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      saveBlob(await assetsApi.exportExcel(), 'fixed_assets.xlsx')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const allColumns: Record<string, Column<AssetResponse>> = {
    asset_code: {
      key: 'asset_code',
      header: 'Tag',
      sortValue: (a) => a.asset_code ?? '',
      cell: (a) => <span className="font-mono text-xs">{a.asset_code ?? '—'}</span>,
    },
    asset_name: {
      key: 'asset_name',
      header: 'Asset',
      sortValue: (a) => a.asset_name.toLowerCase(),
      cell: (a) => (
        <div>
          <div className="font-medium text-text-primary">{a.asset_name}</div>
          {a.manufacturer_serial_number && (
            <div className="text-xs text-text-muted">{a.manufacturer_serial_number}</div>
          )}
        </div>
      ),
    },
    category: {
      key: 'category',
      header: 'Category',
      sortValue: (a) => categoryNames[a.category_id ?? ''] ?? '',
      cell: (a) => categoryNames[a.category_id ?? ''] ?? '—',
    },
    lifecycle_status: {
      key: 'lifecycle_status',
      header: 'Stage',
      sortValue: (a) => a.lifecycle_status,
      cell: (a) => <StatusBadge status={a.lifecycle_status} />,
    },
    operational_status: {
      key: 'operational_status',
      header: 'Status',
      sortValue: (a) => a.operational_status ?? '',
      cell: (a) => (a.operational_status ? <StatusBadge status={a.operational_status} /> : '—'),
    },
    condition: {
      key: 'condition',
      header: 'Condition',
      sortValue: (a) => a.condition ?? '',
      cell: (a) => (a.condition ? <StatusBadge status={a.condition} /> : '—'),
    },
    original_cost: {
      key: 'original_cost',
      header: 'Cost',
      align: 'right',
      sortValue: (a) => num(a.original_cost) ?? 0,
      cell: (a) => {
        const n = num(a.original_cost)
        return n === null ? '—' : formatMoney(n)
      },
    },
    location: {
      key: 'location',
      header: 'Location',
      sortValue: (a) => lookupNames[a.location_id ?? ''] ?? '',
      cell: (a) => lookupNames[a.location_id ?? ''] ?? '—',
    },
    branch: {
      key: 'branch',
      header: 'Branch',
      sortValue: (a) => lookupNames[a.branch_id ?? ''] ?? '',
      cell: (a) => lookupNames[a.branch_id ?? ''] ?? '—',
    },
    department: {
      key: 'department',
      header: 'Department',
      sortValue: (a) => lookupNames[a.department_id ?? ''] ?? '',
      cell: (a) => lookupNames[a.department_id ?? ''] ?? '—',
    },
    cost_centre: {
      key: 'cost_centre',
      header: 'Cost centre',
      sortValue: (a) => lookupNames[a.cost_centre_id ?? ''] ?? '',
      cell: (a) => lookupNames[a.cost_centre_id ?? ''] ?? '—',
    },
    custodian: {
      key: 'custodian',
      header: 'Custodian',
      cell: (a) => a.custodian_name || (a.custodian_id ? 'Assigned user' : 'Unassigned'),
    },
    capitalization_date: {
      key: 'capitalization_date',
      header: 'Capitalized',
      sortValue: (a) => a.capitalization_date ?? '',
      cell: (a) => dateOrDash(a.capitalization_date),
    },
    useful_life_months: {
      key: 'useful_life_months',
      header: 'Life',
      align: 'right',
      sortValue: (a) => a.useful_life_months ?? 0,
      cell: (a) => (a.useful_life_months ? `${a.useful_life_months} mo` : '—'),
    },
    dep_method: {
      key: 'dep_method',
      header: 'Method',
      sortValue: (a) => a.dep_method ?? '',
      cell: (a) => (a.dep_method ? a.dep_method.toUpperCase() : '—'),
    },
    warranty_expiry_date: {
      key: 'warranty_expiry_date',
      header: 'Warranty ends',
      sortValue: (a) => a.warranty_expiry_date ?? '',
      cell: (a) => dateOrDash(a.warranty_expiry_date),
    },
  }

  const columns = visible.map((key) => allColumns[key]).filter(Boolean)
  const tabs: TabItem[] = VIEWS.map((v) => ({ id: v.id, label: v.label, count: counts[v.id] }))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="OPERATIONS"
        icon={<Laptop />}
        title="Fixed assets"
        description="Statutory fixed asset register — Companies Act and Income Tax"
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => navigate('/app/assets/reports')}>
              Reports
            </Button>
            {isAdmin && (
              <Button variant="secondary" onClick={() => navigate('/app/assets/masters')}>
                Masters
              </Button>
            )}
            <Button variant="secondary" onClick={handleExport} loading={exporting}>
              Export
            </Button>
            <Button onClick={() => setQuickAddOpen(true)}>New asset</Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Assets in register"
          value={stats.total}
          icon={<Boxes />}
          tone="accent"
          loading={isLoading}
        />
        <StatCard
          label="Gross block"
          value={stats.grossBlock}
          prefix="₹"
          decimals={2}
          icon={<IndianRupee />}
          tone="gold"
          loading={isLoading}
          sub="Capitalized assets only"
        />
        <StatCard
          label="Capitalized"
          value={stats.capitalized}
          icon={<Landmark />}
          tone="info"
          loading={isLoading}
          sub={`${stats.drafts} draft${stats.drafts === 1 ? '' : 's'} not yet on the books`}
        />
        <StatCard
          label="Awaiting approval"
          value={stats.pending}
          icon={<Settings2 />}
          tone={stats.pending > 0 ? 'warning' : 'neutral'}
          loading={isLoading}
        />
      </div>

      <Tabs tabs={tabs} value={view} onChange={setView} layoutGroup="asset-views" />

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={operational}
          onChange={(e) => setOperational(e.target.value)}
          className="h-8 max-w-[180px]"
          aria-label="Filter by asset status"
        >
          <option value="">All statuses</option>
          {ASSET_OPERATIONAL_STATUS.map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </Select>
        <Select
          value={condition}
          onChange={(e) => setCondition(e.target.value)}
          className="h-8 max-w-[180px]"
          aria-label="Filter by condition"
        >
          <option value="">All conditions</option>
          {ASSET_CONDITION.map((c) => (
            <option key={c} value={c}>
              {humanize(c)}
            </option>
          ))}
        </Select>
      </div>

      <DataTable
        columns={columns}
        data={assets}
        rowKey={(a) => a.id}
        loading={isLoading}
        pageSize={25}
        onRowClick={(a) => navigate(`/app/assets/${a.id}`)}
        searchAccessors={(a) =>
          `${a.asset_name} ${a.asset_code ?? ''} ${a.manufacturer_serial_number ?? ''} ${a.manufacturer ?? ''}`
        }
        searchPlaceholder="Search by name, tag or serial…"
        emptyTitle="No assets"
        emptyDescription="Create an asset to start building the register."
        toolbar={
          <Button variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>
            Columns
          </Button>
        }
      />

      <QuickAddAssetModal open={quickAddOpen} onClose={() => setQuickAddOpen(false)} />
      <AssetColumnPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        options={Object.entries(allColumns).map(([key, col]) => ({ key, label: col.header }))}
        visible={visible}
        onChange={setVisible}
      />
    </div>
  )
}
