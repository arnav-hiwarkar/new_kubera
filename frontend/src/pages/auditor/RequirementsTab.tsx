import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Plus, Upload } from 'lucide-react'
import { Button, ConfirmDialog, EmptyState, Spinner, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import {
  useAuditorCloseRequirement,
  useAuditorDeleteRequirement,
  useAuditorListRequirements,
  useAuditorReopenRequirement,
} from '@/api/hooks/auditorEngagements'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'
import type { RequirementRequestResponse } from '@/api/types'
import { saveBlob } from '@/lib/download'
import {
  RequirementsOverview,
} from '@/components/auditease/requirements/RequirementsOverview'
import {
  deriveDisplayState,
  type RequirementStatusFilter,
} from '@/components/auditease/requirements/progress'
import { RequirementCard } from '@/components/auditease/requirements/RequirementCard'
import { NewRequirementModal } from '@/components/auditease/requirements/NewRequirementModal'
import { BulkImportModal } from '@/components/auditease/requirements/BulkImportModal'

export function RequirementsTab({
  engagementId,
}: {
  engagementId: string
  canQuery?: boolean
}) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useAuditorListRequirements(engagementId)
  const closeReq = useAuditorCloseRequirement()
  const reopenReq = useAuditorReopenRequirement()
  const delReq = useAuditorDeleteRequirement()

  const [filter, setFilter] = useState<RequirementStatusFilter>('all')
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [editingReq, setEditingReq] = useState<RequirementRequestResponse | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<RequirementRequestResponse | null>(null)

  const filteredReqs = useMemo(() => {
    if (filter === 'all') return reqs
    if (filter === 'open') return reqs.filter((r) => r.status === 'open')
    if (filter === 'closed') return reqs.filter((r) => r.status === 'closed')
    if (filter === 'awaiting') return reqs.filter((r) => deriveDisplayState(r) === 'awaiting')
    if (filter === 'responded') return reqs.filter((r) => deriveDisplayState(r) === 'responded')
    return reqs
  }, [reqs, filter])

  const nextSeq = Math.max(0, ...reqs.map((r) => r.seq_number ?? 0)) + 1
  const nextReqId = `REQ-${String(nextSeq).padStart(3, '0')}`

  const handleDownload = async (docId: string, filename: string) => {
    try {
      const blob = await auditorEngagementsApi.downloadDocument(docId)
      saveBlob(blob, filename || 'document')
    } catch {
      toast.error('Failed to download document')
    }
  }

  const handleClose = async (reqId: string) => {
    try {
      await closeReq.mutateAsync({ engagementId, reqId })
      toast.success('Requirement closed')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not close requirement')
    }
  }

  const handleReopen = async (reqId: string) => {
    try {
      await reopenReq.mutateAsync({ engagementId, reqId })
      toast.success('Requirement reopened')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not reopen requirement')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  return (
    <div className="flex flex-col gap-6">
      {/* Overview & Filter Bar */}
      <RequirementsOverview
        items={reqs}
        activeFilter={filter}
        onSelectFilter={setFilter}
      />

      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <h3 className="text-lg font-medium text-text-primary">
          Audit Requirements
        </h3>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowImport(true)}>
            <Upload className="h-4 w-4" /> Bulk import
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" /> New requirement
          </Button>
        </div>
      </div>

      {/* Requirements List */}
      {reqs.length === 0 ? (
        <EmptyState
          title="No requirements requested"
          description="Request documents from the company or bulk import a requirement list."
        />
      ) : filteredReqs.length === 0 ? (
        <EmptyState
          title={`No ${filter} requirements`}
          description="Try selecting another filter from the overview above."
        />
      ) : (
        <div className="flex flex-col gap-3">
          <AnimatePresence initial={false}>
            {filteredReqs.map((req) => (
              <motion.div
                key={req.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <RequirementCard
                  req={req}
                  variant="auditor"
                  engagementId={engagementId}
                  onClose={handleClose}
                  onReopen={handleReopen}
                  onEdit={(r) => setEditingReq(r)}
                  onDelete={(r) => setDeleteTarget(r)}
                  onDownloadDoc={handleDownload}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Modals */}
      {showCreate && (
        <NewRequirementModal
          engagementId={engagementId}
          nextReqId={nextReqId}
          onClose={() => setShowCreate(false)}
        />
      )}

      {editingReq && (
        <NewRequirementModal
          engagementId={engagementId}
          initial={editingReq}
          onClose={() => setEditingReq(null)}
        />
      )}

      {showImport && (
        <BulkImportModal
          engagementId={engagementId}
          onClose={() => setShowImport(false)}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          open
          title={`Delete ${deleteTarget.requirement_id_str || 'requirement'}?`}
          message="Requirements without submissions can be deleted permanently."
          confirmLabel="Delete"
          destructive
          onConfirm={() => {
            delReq
              .mutateAsync({ engagementId, reqId: deleteTarget.id })
              .then(() => toast.success('Requirement deleted'))
              .catch((err) =>
                toast.error(err instanceof ApiError ? err.message : 'Error deleting')
              )
              .finally(() => setDeleteTarget(null))
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
