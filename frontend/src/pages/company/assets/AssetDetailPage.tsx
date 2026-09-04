import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  ClipboardList,
  FileText,
  IndianRupee,
  MapPin,
  Percent,
  Receipt,
  Tag,
} from 'lucide-react'
import {
  Button,
  Card,
  ConfirmDialog,
  FullPageSpinner,
  StatusBadge,
  Tabs,
  useToast,
  type TabItem,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { useCompanyAuth } from '@/auth/company'
import { useAsset, useAssetTransition, useDeleteAsset } from '@/api/hooks/assets'
import { useCategoryNames } from '@/api/hooks/assetMasters'
import { humanize } from '@/api/enums'
import type { ValidationIssueResponse } from '@/api/types'
import { dateOrDash, money } from './assetFormat'
import { SerialGrid } from './SerialGrid'
import { AssetDisposalModal } from './AssetDisposalModal'
import { AcquisitionTab } from './tabs/AcquisitionTab'
import { AssignmentTab } from './tabs/AssignmentTab'
import { DepreciationTab } from './tabs/DepreciationTab'
import { DocumentsTab } from './tabs/DocumentsTab'
import { HistoryTab } from './tabs/HistoryTab'
import { IdentityTab } from './tabs/IdentityTab'
import { TaxTab } from './tabs/TaxTab'

const TAB_META: { id: string; label: string; icon: JSX.Element }[] = [
  { id: 'identity', label: 'Identity', icon: <Tag /> },
  { id: 'acquisition', label: 'Acquisition & costs', icon: <Receipt /> },
  { id: 'tax', label: 'Tax & GST', icon: <Percent /> },
  { id: 'depreciation', label: 'Depreciation', icon: <IndianRupee /> },
  { id: 'assignment', label: 'Assignment', icon: <MapPin /> },
  { id: 'documents', label: 'Documents', icon: <FileText /> },
  { id: 'history', label: 'History', icon: <ClipboardList /> },
]

export function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const { profile } = useCompanyAuth()
  const { data: detail, isLoading, isError } = useAsset(assetId)
  const categoryNames = useCategoryNames()

  const [tab, setTab] = useState('identity')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [disposalOpen, setDisposalOpen] = useState(false)
  const [applyToBatch, setApplyToBatch] = useState(true)

  const submit = useAssetTransition('submit')
  const approve = useAssetTransition('approve')
  const reject = useAssetTransition('reject')
  const remove = useDeleteAsset()

  // Per-tab count of what is still blocking the next transition — this is the
  // progressive-disclosure signal: the user sees where the gaps are without every
  // field shouting at once.
  const issuesByTab = useMemo(() => {
    const m: Record<string, ValidationIssueResponse[]> = {}
    for (const issue of detail?.blocking_issues ?? []) {
      m[issue.tab] = [...(m[issue.tab] ?? []), issue]
    }
    return m
  }, [detail?.blocking_issues])

  if (isLoading) return <FullPageSpinner />
  if (isError || !detail) {
    return (
      <Card className="p-6">
        <p className="text-text-secondary">This asset could not be loaded.</p>
        <Link to="/app/assets" className="mt-2 inline-block text-accent hover:underline">
          Back to the register
        </Link>
      </Card>
    )
  }

  const asset = detail.asset
  const acq = detail.acquisition
  const isAdmin = profile?.role === 'admin'
  const canApprove = isAdmin
  const canDispose = isAdmin
  const isDraft = asset.lifecycle_status === 'draft'
  const isReady = asset.lifecycle_status === 'ready'
  const locked = asset.lifecycle_status === 'capitalized' || asset.lifecycle_status === 'disposed'
  const batchSize = detail.siblings.length

  // Cost is frozen as soon as ANY unit in the batch is on the books, not just this one.
  const costLocked = detail.siblings.some(
    (s) => s.lifecycle_status === 'capitalized' || s.lifecycle_status === 'disposed',
  )

  const tabs: TabItem[] = TAB_META.map((t) => ({
    id: t.id,
    label: t.label,
    icon: t.icon,
    count: issuesByTab[t.id]?.length,
  }))

  const runTransition = async (
    kind: 'submit' | 'approve' | 'reject',
    mutation: typeof submit,
    successMessage: string,
  ) => {
    try {
      const res = await mutation.mutateAsync({
        id: asset.id,
        body: { apply_to_siblings: batchSize > 1 && applyToBatch },
      })
      toast.success(
        res.updated.length > 1 ? `${successMessage} — ${res.updated.length} units` : successMessage,
      )
    } catch (e) {
      if (e instanceof ApiError) {
        const d = e.detail as
          | { message?: string; issues?: ValidationIssueResponse[]; asset_code?: string }
          | string
        if (typeof d === 'object' && d?.issues?.length) {
          // Jump to the tab that owns the first gap rather than making the user hunt.
          setTab(d.issues[0].tab)
          toast.error(
            `${d.message ?? 'Not ready'}: ${d.issues.length} item${d.issues.length === 1 ? '' : 's'} outstanding`,
          )
          return
        }
        toast.error(typeof d === 'string' ? d : e.message)
        return
      }
      toast.error(e instanceof Error ? e.message : `Could not ${kind} the asset`)
    }
  }

  const handleDelete = async () => {
    try {
      await remove.mutateAsync(asset.id)
      toast.success('Draft deleted')
      navigate('/app/assets')
    } catch (e) {
      toast.error(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : e instanceof Error
            ? e.message
            : 'Could not delete',
      )
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          to="/app/assets"
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          Register
        </Link>
      </div>

      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold text-text-primary">{asset.asset_name}</h1>
              <StatusBadge status={asset.lifecycle_status} />
              {asset.condition && <StatusBadge status={asset.condition} />}
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-text-muted">
              <span className="font-mono text-text-secondary">{asset.asset_code ?? 'Untagged'}</span>
              {asset.category_id && <span>{categoryNames[asset.category_id] ?? '—'}</span>}
              {batchSize > 1 && (
                <span className="inline-flex items-center gap-1">
                  <Boxes className="h-3.5 w-3.5" />
                  Unit {asset.unit_index} of {batchSize}
                </span>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {batchSize > 1 && (isDraft || isReady) && (
              <label className="flex items-center gap-1.5 text-sm text-text-secondary">
                <input
                  type="checkbox"
                  checked={applyToBatch}
                  onChange={(e) => setApplyToBatch(e.target.checked)}
                />
                Apply to all {batchSize}
              </label>
            )}
            {isDraft && (
              <>
                {isAdmin && (
                  <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
                    Delete
                  </Button>
                )}
                <Button
                  onClick={() => runTransition('submit', submit, 'Submitted for approval')}
                  loading={submit.isPending}
                  disabled={(detail.blocking_issues.length ?? 0) > 0}
                >
                  {detail.blocking_issues.length > 0
                    ? `${detail.blocking_issues.length} item${detail.blocking_issues.length === 1 ? '' : 's'} outstanding`
                    : 'Submit for approval'}
                </Button>
              </>
            )}
            {isReady && canApprove && (
              <>
                <Button
                  variant="secondary"
                  onClick={() => runTransition('reject', reject, 'Sent back to draft')}
                  loading={reject.isPending}
                >
                  Send back
                </Button>
                <Button
                  onClick={() => runTransition('approve', approve, 'Capitalized')}
                  loading={approve.isPending}
                >
                  Approve & capitalize
                </Button>
              </>
            )}
            {isReady && !canApprove && (
              <span className="text-sm text-text-muted">Awaiting approval</span>
            )}
            {asset.lifecycle_status === 'capitalized' && (
              <>
                <span className="inline-flex items-center gap-1.5 text-sm text-status-verified">
                  <CheckCircle2 className="h-4 w-4" />
                  On the books
                </span>
                {canDispose && (
                  <Button variant="secondary" size="sm" onClick={() => setDisposalOpen(true)}>
                    Dispose Asset
                  </Button>
                )}
              </>
            )}
            {asset.lifecycle_status === 'disposed' && (
              <span className="inline-flex items-center gap-1.5 text-sm text-status-rejected font-medium">
                Disposed ({asset.disposal_type || 'sale'})
              </span>
            )}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-border pt-4 sm:grid-cols-4">
          <Figure label="Capitalized value" value={money(asset.original_cost)} />
          <Figure label="Capitalization date" value={dateOrDash(asset.capitalization_date)} />
          <Figure
            label="Useful life"
            value={
              asset.useful_life_months
                ? `${asset.useful_life_months} mo · ${(asset.dep_method ?? '').toUpperCase()}`
                : '—'
            }
          />
          <Figure label="Supplier" value={acq?.supplier_name_snapshot ?? '—'} />
        </div>
      </Card>

      {/* The checklist is the whole progressive-disclosure contract: nothing blocks
          saving, but this says exactly what is still needed and where it lives. */}
      {detail.blocking_issues.length > 0 && (
        <Card className="border-status-pending/40 bg-status-pending/5 p-4">
          <h3 className="text-sm font-semibold text-text-primary">
            {isDraft ? 'Needed before this can be submitted' : 'Needed before this can be capitalized'}
          </h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {detail.blocking_issues.map((issue) => (
              <li key={issue.field}>
                <button
                  type="button"
                  onClick={() => setTab(issue.tab)}
                  className="rounded-pill border border-border-strong bg-bg-surface px-2.5 py-1 text-xs text-text-secondary transition-colors hover:border-accent hover:text-accent"
                  title={issue.message ?? `Go to ${humanize(issue.tab)}`}
                >
                  {issue.label}
                  {issue.kind === 'invalid' && ' ⚠'}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {batchSize > 1 && (
        <SerialGrid
          anchorAssetId={asset.id}
          siblings={detail.siblings}
          currentAssetId={asset.id}
        />
      )}

      <Tabs tabs={tabs} value={tab} onChange={setTab} layoutGroup="asset-detail" />

      <div className="pb-8">
        {tab === 'identity' && (
          <IdentityTab
            detail={detail}
            locked={locked}
            fieldGroups={detail.applicable_field_groups}
          />
        )}
        {tab === 'acquisition' && <AcquisitionTab detail={detail} costLocked={costLocked} />}
        {tab === 'tax' && <TaxTab detail={detail} costLocked={costLocked} />}
        {tab === 'depreciation' && <DepreciationTab detail={detail} locked={locked} />}
        {tab === 'assignment' && <AssignmentTab detail={detail} />}
        {tab === 'documents' && <DocumentsTab detail={detail} />}
        {tab === 'history' && <HistoryTab detail={detail} />}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
        loading={remove.isPending}
        title="Delete this draft?"
        message="Drafts can be deleted outright. Once an asset is capitalized it can only leave the register through a disposal."
        confirmLabel="Delete draft"
        destructive
      />

      <AssetDisposalModal
        open={disposalOpen}
        onClose={() => setDisposalOpen(false)}
        assetId={asset.id}
        assetName={asset.asset_name}
        capitalizationDate={asset.capitalization_date}
      />
    </div>
  )
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-text-primary">{value}</p>
    </div>
  )
}
