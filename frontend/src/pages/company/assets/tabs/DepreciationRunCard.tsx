import { useMemo, useState } from 'react'
import { Button, Card, Field, Modal, Spinner, Textarea, useToast } from '@/components/ui'
import {
  CalculationDrawer,
  ExplainLink,
  type CalcTrace,
  type TraceTab,
} from '@/components/calc'
import { ApiError } from '@/api/http'
import { useFinancialYears } from '@/api/hooks/financialYears'
import {
  useAssetDepreciationLines,
  useCreateDepreciationRun,
  useDepreciationRuns,
  useExplainDepreciation,
  useFinalizeDepreciationRun,
  useItBlockDepreciationLines,
  useReopenDepreciationRun,
} from '@/api/hooks/depreciation'
import { useCompanyAuth } from '@/auth/company'
import { CheckCircle, Play, RotateCcw } from 'lucide-react'
import { money } from '../assetFormat'

/** A run figure, with a deep link into the step that produced it. */
function RunTile({
  label,
  value,
  valueClass,
  onExplain,
}: {
  label: string
  value: string
  valueClass: string
  onExplain: () => void
}) {
  return (
    <button
      type="button"
      onClick={onExplain}
      aria-label={`How was ${label} calculated?`}
      className="rounded-md border border-border bg-bg-inset/50 p-2.5 text-left hover:border-border-strong focus:outline-none focus:ring-1 focus:ring-accent"
    >
      <span className="text-text-muted">{label}</span>
      <span className={`mt-0.5 block font-semibold tabular-nums ${valueClass}`}>{value}</span>
    </button>
  )
}

/**
 * The depreciation run surface for one asset: pick a financial year, compute, finalize,
 * reopen, and see the resulting line.
 *
 * Separate from DepreciationTab because it owns its own queries and mutations and none
 * of the tab's form state — the tab is inputs, this is results.
 */
export function DepreciationRunCard({
  assetId,
  itBlockId,
}: {
  assetId: string
  itBlockId?: string | null
}) {
  const toast = useToast()
  const { profile } = useCompanyAuth()
  const isAdmin = profile?.role === 'admin'

  const { data: fys = [] } = useFinancialYears()
  const { data: runs = [] } = useDepreciationRuns()
  const createRun = useCreateDepreciationRun()
  const finalizeRun = useFinalizeDepreciationRun()
  const reopenRunMutation = useReopenDepreciationRun()

  const [reopenOpen, setReopenOpen] = useState(false)
  const [reopenReason, setReopenReason] = useState('')
  const [selectedFyId, setSelectedFyId] = useState<string>(fys[0]?.id || '')

  const activeFyId = selectedFyId || fys[0]?.id || ''
  const latestRunForFy = runs.find((r) => r.financial_year_id === activeFyId)
  const { data: runLines = [], isLoading: linesLoading } = useAssetDepreciationLines(
    latestRunForFy?.id || '',
  )
  const assetLine = runLines.find((l) => l.asset_id === assetId)

  const { data: itLines = [] } = useItBlockDepreciationLines(latestRunForFy?.id || '')

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [focusStep, setFocusStep] = useState<string | undefined>(undefined)
  const [forceProjection, setForceProjection] = useState(false)

  // Read through a local shape rather than the generated response type: `calc_trace`
  // only appears in `schema.d.ts` once `npm run gen:api` has been run against a
  // backend carrying Task 6, and this must compile before then.
  type WithTrace = { calc_trace?: CalcTrace | null }
  const recordedCa = (assetLine as WithTrace | undefined)?.calc_trace ?? null
  const recordedIt = itBlockId
    ? ((itLines.find((l) => l.it_block_id === itBlockId) as WithTrace | undefined)
        ?.calc_trace ?? null)
    : null

  // Nothing recorded for this year at all: project straight away, since there is no
  // recorded figure a projection could be confused with.
  const noLineYet = !assetLine
  // A line that predates traces is a different case, and says so rather than being
  // quietly replaced by today's inputs.
  const linePredatesTraces = !!assetLine && !recordedCa

  const wantProjection = drawerOpen && (forceProjection || noLineYet)
  const projection = useExplainDepreciation(assetId, activeFyId, wantProjection)

  const tabs: TraceTab[] = useMemo(() => {
    if (wantProjection) {
      const data = projection.data
      if (!data) return []
      return [
        { id: 'ca', label: 'Companies Act', trace: data.companies_act },
        ...(data.income_tax
          ? [{ id: 'it', label: 'Income Tax', trace: data.income_tax }]
          : []),
      ]
    }
    return [
      ...(recordedCa ? [{ id: 'ca', label: 'Companies Act', trace: recordedCa }] : []),
      ...(recordedIt ? [{ id: 'it', label: 'Income Tax', trace: recordedIt }] : []),
    ]
  }, [wantProjection, projection.data, recordedCa, recordedIt])

  const projectionError =
    projection.error instanceof ApiError && typeof projection.error.detail === 'string'
      ? projection.error.detail
      : projection.error instanceof Error
        ? projection.error.message
        : null

  const openDrawer = (step?: string) => {
    setFocusStep(step)
    setForceProjection(false)
    setDrawerOpen(true)
  }

  const activeFy = fys.find((f) => f.id === activeFyId)
  const isFyClosed = activeFy?.status === 'closed'

  const handleRunDepreciation = async () => {
    if (!activeFyId) {
      toast.error('Please create or select a financial year first')
      return
    }
    if (isFyClosed) {
      toast.error('This financial year is closed. Reopen it first.')
      return
    }
    try {
      await createRun.mutateAsync({ financialYearId: activeFyId })
      toast.success('Depreciation run computed successfully')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to run depreciation')
    }
  }

  const handleFinalize = async () => {
    if (!isAdmin) {
      toast.error('Only administrators can finalize depreciation runs')
      return
    }
    if (isFyClosed) {
      toast.error('This financial year is closed. Reopen it first.')
      return
    }
    if (!latestRunForFy) return
    try {
      await finalizeRun.mutateAsync(latestRunForFy.id)
      toast.success('Depreciation run finalized')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to finalize run')
    }
  }

  const handleReopen = async () => {
    if (!isAdmin) {
      toast.error('Only administrators can reopen depreciation runs')
      return
    }
    if (isFyClosed) {
      toast.error('This financial year is closed. Reopen it first.')
      return
    }
    const trimmed = reopenReason.trim()
    if (!latestRunForFy || trimmed.length < 3) return
    try {
      await reopenRunMutation.mutateAsync({ runId: latestRunForFy.id, reason: trimmed })
      toast.success('Run reopened to draft')
      setReopenOpen(false)
      setReopenReason('')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reopen run')
    }
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <h4 className="text-sm font-semibold text-text-primary">
            Depreciation Calculation &amp; Schedule
          </h4>
          <p className="text-xs text-text-muted">Schedule II computation for the financial year</p>
        </div>
        <div className="flex items-center gap-2">
          <ExplainLink onClick={() => openDrawer()} />
          <select
            aria-label="Select Financial Year"
            value={activeFyId}
            onChange={(e) => setSelectedFyId(e.target.value)}
            className="h-8 rounded-btn border border-border-strong bg-bg-surface px-2.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
          >
            {fys.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label} ({f.status})
              </option>
            ))}
          </select>
          {isFyClosed && (
            <span className="rounded bg-status-rejected/10 px-2 py-0.5 text-xs font-semibold text-status-rejected">
              Closed (Read-only)
            </span>
          )}
          <Button
            size="sm"
            onClick={handleRunDepreciation}
            loading={createRun.isPending}
            disabled={!activeFyId || isFyClosed}
            title={isFyClosed ? 'Financial year is closed' : undefined}
          >
            <Play className="mr-1 h-3.5 w-3.5" />
            Compute
          </Button>
          {isAdmin && latestRunForFy && latestRunForFy.status === 'draft' && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleFinalize}
              loading={finalizeRun.isPending}
              disabled={isFyClosed}
              title={isFyClosed ? 'Financial year is closed' : undefined}
            >
              <CheckCircle className="mr-1 h-3.5 w-3.5" />
              Finalize
            </Button>
          )}
          {isAdmin && latestRunForFy && latestRunForFy.status === 'finalized' && (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setReopenOpen(true)}
                disabled={isFyClosed}
                title={isFyClosed ? 'Financial year is closed. Reopen the financial year first.' : undefined}
              >
                <RotateCcw className="mr-1 h-3.5 w-3.5" />
                Reopen
              </Button>
              {/* ConfirmDialog renders a static message only, so the reason
                  field needs its own Modal-based dialog. */}
              <Modal
                open={reopenOpen}
                onClose={() => setReopenOpen(false)}
                title="Reopen finalized depreciation?"
                size="sm"
                footer={
                  <>
                    <Button
                      variant="secondary"
                      onClick={() => setReopenOpen(false)}
                      disabled={reopenRunMutation.isPending}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleReopen}
                      loading={reopenRunMutation.isPending}
                      disabled={reopenReason.trim().length < 3}
                    >
                      Confirm reopen
                    </Button>
                  </>
                }
              >
                <p className="text-sm text-text-secondary">
                  {latestRunForFy.financial_year_label ?? 'This year'} will flip back to draft so
                  you can correct inputs and regenerate. Redo years oldest-first.
                </p>
                <Field
                  className="mt-3"
                  label="Reason (recorded in the audit log)"
                  required
                  hint="At least 3 characters"
                >
                  <Textarea
                    aria-label="Reason"
                    value={reopenReason}
                    onChange={(e) => setReopenReason(e.target.value)}
                  />
                </Field>
              </Modal>
            </>
          )}
        </div>
      </div>

      {linesLoading ? (
        <Spinner className="mx-auto my-6 h-5 w-5" />
      ) : assetLine ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
          <RunTile
            label="Opening Gross Block"
            value={money(String(assetLine.opening_gross_block))}
            valueClass="text-text-primary"
            onExplain={() => openDrawer('opening_gross_block')}
          />
          <RunTile
            label="Additions / Disposals"
            value={`+${money(String(assetLine.additions))} / -${money(String(assetLine.disposals))}`}
            valueClass="text-text-primary"
            onExplain={() => openDrawer('additions')}
          />
          <RunTile
            label="Depreciation (FY)"
            value={money(String(assetLine.depreciation_for_year))}
            valueClass="text-status-action"
            onExplain={() => openDrawer('depreciation_for_year')}
          />
          <RunTile
            label="Closing Carrying Amount (NBV)"
            value={money(String(assetLine.closing_carrying_amount))}
            valueClass="text-status-verified"
            onExplain={() => openDrawer('closing_carrying_amount')}
          />
        </div>
      ) : (
        <p className="mt-3 text-xs text-text-muted">
          No calculation run recorded yet for this financial year. Click "Compute" above to execute
          the depreciation engine.
        </p>
      )}

      <CalculationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        tabs={tabs}
        focusStep={focusStep}
        loading={wantProjection && projection.isLoading}
        error={wantProjection ? projectionError : null}
        emptyNote={
          linePredatesTraces && !forceProjection
            ? 'This run was recorded before calculation traces were kept.'
            : undefined
        }
        onShowProjection={
          linePredatesTraces && !forceProjection ? () => setForceProjection(true) : undefined
        }
        contextNote={
          [
            latestRunForFy
              ? latestRunForFy.status === 'finalized'
                ? 'Finalized run'
                : 'Draft run'
              : undefined,
            !itBlockId ? 'Asset is not in an income-tax block yet' : undefined,
          ]
            .filter(Boolean)
            .join(' · ') || undefined
        }
      />
    </Card>
  )
}
