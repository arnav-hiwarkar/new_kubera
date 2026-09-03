import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { EmptyState, Spinner, useToast } from '@/components/ui'
import { useListRequirements } from '@/api/hooks/auditease'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { saveBlob } from '@/lib/download'
import {
  RequirementsOverview,
} from '@/components/auditease/requirements/RequirementsOverview'
import {
  deriveDisplayState,
  type RequirementStatusFilter,
} from '@/components/auditease/requirements/progress'
import { RequirementCard } from '@/components/auditease/requirements/RequirementCard'

export function RequirementsTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useListRequirements(engagementId)

  const [filter, setFilter] = useState<RequirementStatusFilter>('all')

  const filteredReqs = useMemo(() => {
    if (filter === 'all') return reqs
    if (filter === 'open') return reqs.filter((r) => r.status === 'open')
    if (filter === 'closed') return reqs.filter((r) => r.status === 'closed')
    if (filter === 'awaiting') return reqs.filter((r) => deriveDisplayState(r) === 'awaiting')
    if (filter === 'responded') return reqs.filter((r) => deriveDisplayState(r) === 'responded')
    return reqs
  }, [reqs, filter])

  const handleDownload = async (docId: string, filename: string) => {
    try {
      const blob = await auditeaseCompanyApi.downloadDocument(docId)
      saveBlob(blob, filename || 'document')
    } catch {
      toast.error('Failed to download document')
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

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-medium text-text-primary">
          Requested Documents & Answers
        </h3>
      </div>

      {/* Requirements List */}
      {reqs.length === 0 ? (
        <EmptyState
          title="No requirements requested"
          description="Your auditor has not requested any documents yet."
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
                  variant="company"
                  engagementId={engagementId}
                  onDownloadDoc={handleDownload}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
