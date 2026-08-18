import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, FileSpreadsheet, FileText, Download } from 'lucide-react'
import { PageHeader, Card, Button, Spinner, useToast, EmptyState } from '@/components/ui'
import { useFinancialYears } from '@/api/hooks/financialYears'
import { useAssetCategories, useAssetLookups } from '@/api/hooks/assetMasters'
import { useAssetReportsList, useAssetReportPreview, useArchiveAssetReport } from '@/api/hooks/assetReports'
import { assetReportsApi } from '@/api/endpoints/assetReports'
import { ReportExportMenu } from '@/components/reports/ReportExportMenu'
import { saveBlob } from '@/lib/download'
import { cn } from '@/lib/cn'

const UNIT_OPTIONS = [
  { key: 'absolute', label: 'Absolute (₹)' },
  { key: 'thousands', label: "Thousands (₹ '000)" },
  { key: 'lakhs', label: 'Lakhs (₹ Lakhs)' },
  { key: 'crores', label: 'Crores (₹ Cr)' },
] as const

const STATUS_OPTIONS = [
  { key: '', label: 'Capitalized (default)' },
  { key: 'all', label: 'All Statuses' },
  { key: 'capitalized', label: 'Capitalized' },
  { key: 'draft', label: 'Draft' },
  { key: 'ready', label: 'Ready' },
  { key: 'disposed', label: 'Disposed' },
] as const

const OP_STATUS_OPTIONS = [
  { key: '', label: 'All Operations' },
  { key: 'in_use', label: 'In Use' },
  { key: 'in_storage', label: 'In Storage' },
  { key: 'under_maintenance', label: 'Under Maintenance' },
  { key: 'decommissioned', label: 'Decommissioned' },
  { key: 'idle', label: 'Idle' },
] as const

const CONDITION_OPTIONS = [
  { key: '', label: 'All Conditions' },
  { key: 'excellent', label: 'Excellent' },
  { key: 'good', label: 'Good' },
  { key: 'fair', label: 'Fair' },
  { key: 'poor', label: 'Poor' },
  { key: 'scrap', label: 'Scrap' },
] as const

export function AssetReportsPage() {
  const { data: fys = [], isLoading: fysLoading } = useFinancialYears()
  const { data: categories = [] } = useAssetCategories()
  const { data: locations = [] } = useAssetLookups('location')
  const { data: branches = [] } = useAssetLookups('branch')
  const { data: departments = [] } = useAssetLookups('department')
  const { data: reports = [] } = useAssetReportsList()
  const toast = useToast()

  const [selectedFyId, setSelectedFyId] = useState<string>('')
  const [selectedReportKey, setSelectedReportKey] = useState<string>('fixed_asset_register')
  const [unit, setUnit] = useState<'absolute' | 'thousands' | 'lakhs' | 'crores'>('absolute')
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>('')
  const [selectedStatus, setSelectedStatus] = useState<string>('')
  const [selectedOpStatus, setSelectedOpStatus] = useState<string>('')
  const [selectedCondition, setSelectedCondition] = useState<string>('')
  const [selectedLocationId, setSelectedLocationId] = useState<string>('')
  const [selectedBranchId, setSelectedBranchId] = useState<string>('')
  const [selectedDepartmentId, setSelectedDepartmentId] = useState<string>('')
  const [downloadingPack, setDownloadingPack] = useState(false)

  const activeFyId = selectedFyId || (fys.length > 0 ? fys[0].id : '')
  const activeFy = fys.find((f) => f.id === activeFyId)

  const activeFilters = {
    category_id: selectedCategoryId || undefined,
    lifecycle_status: selectedStatus || undefined,
    operational_status: selectedOpStatus || undefined,
    condition: selectedCondition || undefined,
    location_id: selectedLocationId || undefined,
    branch_id: selectedBranchId || undefined,
  }

  const {
    data: previewHtml,
    isLoading: previewLoading,
    error: previewError,
  } = useAssetReportPreview(selectedReportKey, activeFyId, unit, activeFilters)

  const archiveMutation = useArchiveAssetReport()

  const handleExport = async (format: 'xlsx' | 'pdf' | 'html') => {
    if (!activeFyId) return
    const url = assetReportsApi.exportUrl(selectedReportKey, activeFyId, format, unit, activeFilters)
    const token = localStorage.getItem('company_token') || ''
    try {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error('Export failed')
      const blob = await res.blob()
      const ext = format === 'xlsx' ? 'xlsx' : format === 'pdf' ? 'pdf' : 'html'
      const filename = `${selectedReportKey}_${activeFy?.label || 'report'}.${ext}`
      saveBlob(blob, filename)
      toast.success(`Exported ${filename}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed')
    }
  }

  const handleArchive = async () => {
    if (!activeFyId) return
    try {
      await archiveMutation.mutateAsync({
        reportKey: selectedReportKey,
        financialYearId: activeFyId,
        format: 'pdf',
        unit,
        filters: activeFilters,
      })
      toast.success('Report archived to docVault')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Archive failed')
    }
  }

  const handleDownloadPack = async (format: 'xlsx' | 'pdf') => {
    if (!activeFyId) return
    setDownloadingPack(true)
    const url = assetReportsApi.packUrl(activeFyId, format, unit, activeFilters)
    const token = localStorage.getItem('company_token') || ''
    try {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error('Pack generation failed')
      const blob = await res.blob()
      const filename = `Asset_Register_Pack_${activeFy?.label || 'FY'}.${format}`
      saveBlob(blob, filename)
      toast.success(`Downloaded ${filename}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Pack download failed')
    } finally {
      setDownloadingPack(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/app/assets"
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          Register
        </Link>
      </div>

      <PageHeader
        eyebrow="OPERATIONS"
        icon={<FileSpreadsheet />}
        title="Asset Register Reports"
        description="Statutory schedules, Companies Act & Income Tax depreciation books, additions, disposals, and physical verification sheets."
      />

      {fysLoading ? (
        <Spinner className="mx-auto my-12 h-6 w-6" />
      ) : fys.length === 0 ? (
        <EmptyState
          title="No financial years found"
          description="Please set up a financial year in Asset Masters before generating asset register reports."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {/* Controls Bar */}
          <Card className="flex flex-wrap items-center justify-between gap-4 p-4">
            <div className="flex flex-wrap items-center gap-3">
              {/* Financial Year Selector */}
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Financial Year
                </label>
                <select
                  value={activeFyId}
                  onChange={(e) => setSelectedFyId(e.target.value)}
                  className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {fys.map((fy) => (
                    <option key={fy.id} value={fy.id}>
                      {fy.label} ({fy.status === 'open' ? 'Open' : 'Closed'})
                    </option>
                  ))}
                </select>
              </div>

              {/* Units Scaling */}
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Units
                </label>
                <select
                  value={unit}
                  onChange={(e) => setUnit(e.target.value as typeof unit)}
                  className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {UNIT_OPTIONS.map((u) => (
                    <option key={u.key} value={u.key}>
                      {u.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Category Filter */}
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Category
                </label>
                <select
                  value={selectedCategoryId}
                  onChange={(e) => setSelectedCategoryId(e.target.value)}
                  className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value="">All Categories</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Status Filter */}
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Lifecycle Status
                </label>
                <select
                  value={selectedStatus}
                  onChange={(e) => setSelectedStatus(e.target.value)}
                  className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Operational Status */}
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Operation
                </label>
                <select
                  value={selectedOpStatus}
                  onChange={(e) => setSelectedOpStatus(e.target.value)}
                  className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {OP_STATUS_OPTIONS.map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Condition */}
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Condition
                </label>
                <select
                  value={selectedCondition}
                  onChange={(e) => setSelectedCondition(e.target.value)}
                  className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  {CONDITION_OPTIONS.map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Location */}
              {locations.length > 0 && (
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Location
                  </label>
                  <select
                    value={selectedLocationId}
                    onChange={(e) => setSelectedLocationId(e.target.value)}
                    className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="">All Locations</option>
                    {locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Branch */}
              {branches.length > 0 && (
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Branch
                  </label>
                  <select
                    value={selectedBranchId}
                    onChange={(e) => setSelectedBranchId(e.target.value)}
                    className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="">All Branches</option>
                    {branches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Department */}
              {departments.length > 0 && (
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Department
                  </label>
                  <select
                    value={selectedDepartmentId}
                    onChange={(e) => setSelectedDepartmentId(e.target.value)}
                    className="h-9 rounded-btn border border-border-strong bg-bg-surface px-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="">All Departments</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Actions & Export */}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleDownloadPack('xlsx')}
                loading={downloadingPack}
              >
                <Download className="mr-1.5 h-4 w-4" />
                Download Pack (XLSX)
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleDownloadPack('pdf')}
                loading={downloadingPack}
              >
                <FileText className="mr-1.5 h-4 w-4" />
                Download Pack (PDF)
              </Button>
              <ReportExportMenu
                onExportExcel={() => handleExport('xlsx')}
                onExportPdf={() => handleExport('pdf')}
                onArchiveDocVault={handleArchive}
              />
            </div>
          </Card>

          {/* Report Tabs / Pills */}
          <div className="flex flex-wrap gap-2">
            {reports.map((r) => (
              <button
                key={r.key}
                type="button"
                onClick={() => setSelectedReportKey(r.key)}
                className={cn(
                  'rounded-btn border px-3 py-1.5 text-xs font-medium transition-colors',
                  selectedReportKey === r.key
                    ? 'border-accent bg-accent/10 text-accent font-semibold'
                    : 'border-border bg-bg-surface text-text-secondary hover:border-border-strong hover:text-text-primary',
                )}
              >
                {r.title}
              </button>
            ))}
          </div>

          {/* Live Preview Pane */}
          <Card className="min-h-[500px] overflow-hidden p-0">
            {previewLoading ? (
              <div className="flex h-96 items-center justify-center">
                <Spinner className="h-8 w-8 text-accent" />
              </div>
            ) : previewError ? (
              <div className="flex h-96 flex-col items-center justify-center gap-2 p-6 text-center">
                <p className="text-sm font-semibold text-status-action">Failed to load preview</p>
                <p className="text-xs text-text-muted">
                  {previewError instanceof Error ? previewError.message : 'Please check your parameters'}
                </p>
              </div>
            ) : previewHtml ? (
              <iframe
                title="Asset Report Preview"
                srcDoc={previewHtml}
                className="h-[750px] w-full border-0 bg-white"
                sandbox="allow-same-origin allow-scripts"
              />
            ) : (
              <EmptyState title="Select a report to preview" />
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
