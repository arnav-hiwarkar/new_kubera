import { useEffect, useState } from 'react'
import { ApiError } from '@/api/http'
import { useImportMappings, useMappingSources } from '@/api/hooks/auditease'
import type { MappingImportResult } from '@/api/types'
import {
  Button,
  Field,
  Modal,
  Select,
  Spinner,
  StatusBadge,
  Switch,
  useToast,
} from '@/components/ui'

export function ImportMappingModal({
  open,
  onClose,
  engagementId,
  mappedTargetCount,
}: {
  open: boolean
  onClose: () => void
  engagementId: string
  mappedTargetCount: number
}) {
  const toast = useToast()
  const { data: sources = [], isLoading } = useMappingSources(engagementId, open)
  const importMappings = useImportMappings()
  const [sourceId, setSourceId] = useState('')
  const [preserveExisting, setPreserveExisting] = useState(false)
  const [result, setResult] = useState<MappingImportResult | null>(null)

  useEffect(() => {
    if (open && !sourceId && sources.length > 0) {
      setSourceId(sources[0].engagement_id)
    }
  }, [open, sourceId, sources])

  const close = () => {
    setSourceId('')
    setPreserveExisting(false)
    setResult(null)
    importMappings.reset()
    onClose()
  }

  const runImport = async () => {
    if (!sourceId) return
    try {
      const response = await importMappings.mutateAsync({
        engagementId,
        body: {
          source_engagement_id: sourceId,
          overwrite_existing: !preserveExisting,
        },
      })
      setResult(response)
      toast.success(
        `Assigned ${response.assigned_count} of ${response.source_mapped_count} source mappings`,
      )
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : 'Could not import mappings')
    }
  }

  if (result) {
    return (
      <Modal
        open={open}
        onClose={close}
        title="Mapping import complete"
        footer={<Button onClick={close}>Done</Button>}
      >
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <ResultCount label="Assigned" value={result.assigned_count} tone="text-status-verified" />
          <ResultCount label="Updated" value={result.updated_count} tone="text-status-verified" />
          <ResultCount label="Already correct" value={result.already_correct_count} />
          <ResultCount label="Existing preserved" value={result.preserved_existing_count} />
          <ResultCount label="Unused source" value={result.unused_source_count} />
          <ResultCount label="Unresolved" value={result.unresolved_count} tone="text-status-pending" />
        </div>
        {result.issues.length > 0 && (
          <div className="mt-5">
            <p className="mb-2 text-sm font-medium text-text-secondary">
              Ledgers requiring attention
            </p>
            <div className="max-h-64 overflow-auto rounded-card border border-border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-bg-raised text-text-secondary">
                  <tr>
                    <th className="px-3 py-2 text-left">Ledger</th>
                    <th className="px-3 py-2 text-left">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.issues.map((issue) => (
                    <tr key={issue.target_ledger_id} className="border-t border-border">
                      <td className="px-3 py-2">
                        <div className="font-medium text-text-primary">{issue.ledger_name}</div>
                        {issue.ledger_code && (
                          <div className="text-xs text-text-muted">{issue.ledger_code}</div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-text-secondary">
                        {issueReason(issue.reason)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Modal>
    )
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Import mapping"
      footer={
        <>
          <Button variant="secondary" onClick={close}>Cancel</Button>
          <Button
            onClick={runImport}
            loading={importMappings.isPending}
            disabled={!sourceId || isLoading}
          >
            Import mapping
          </Button>
        </>
      }
    >
      {isLoading ? (
        <Spinner className="mx-auto my-8 h-6 w-6" />
      ) : sources.length === 0 ? (
        <div className="rounded-card border border-border bg-bg-raised/40 p-5 text-center">
          <p className="text-sm font-medium text-text-primary">No mapping source available</p>
          <p className="mt-1 text-sm text-text-muted">
            Map at least one ledger in another engagement, then return here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <Field
            label="Source engagement"
            hint="Only engagements with at least one mapped ledger are shown."
          >
            <Select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
              {sources.map((source) => (
                <option key={source.engagement_id} value={source.engagement_id}>
                  {source.period_label} — {source.mapped_ledger_count} of {source.total_ledger_count} mapped
                </option>
              ))}
            </Select>
          </Field>

          {sourceId && (
            <div className="flex items-center gap-2 text-sm text-text-muted">
              <span>Source status:</span>
              <StatusBadge status={sources.find((source) => source.engagement_id === sourceId)?.status ?? 'draft'} />
            </div>
          )}

          <div className="rounded-card border border-border p-3">
            <Switch
              checked={preserveExisting}
              onChange={setPreserveExisting}
              label="Preserve existing mappings"
              disabled={mappedTargetCount === 0}
            />
            <p className="mt-1 pl-14 text-xs text-text-muted">
              {mappedTargetCount === 0
                ? 'There are no existing target mappings to preserve.'
                : `Off by default. The source will replace matching mappings among ${mappedTargetCount} currently mapped target ledger${mappedTargetCount === 1 ? '' : 's'}.`}
            </p>
          </div>
        </div>
      )}
    </Modal>
  )
}

function issueReason(reason: string) {
  switch (reason) {
    case 'source_exhausted':
      return 'All matching source ledgers were already assigned'
    case 'identity_disagreement':
      return 'Ledger code and name do not identify the same source ledger'
    case 'ambiguous_source_mapping':
      return 'Identical source ledgers map to different groups'
    default:
      return 'No matching source ledger'
  }
}

function ResultCount({
  label,
  value,
  tone = 'text-text-primary',
}: {
  label: string
  value: number
  tone?: string
}) {
  return (
    <div className="rounded-card border border-border bg-bg-raised/40 p-3">
      <div className={`text-xl font-semibold ${tone}`}>{value}</div>
      <div className="text-xs text-text-muted">{label}</div>
    </div>
  )
}
