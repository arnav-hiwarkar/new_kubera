import { useState } from 'react'
import { Button, Card, StatusBadge, Spinner, useToast, EmptyState, Select } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useListRequirements, useFulfillRequirement } from '@/api/hooks/auditease'
import { useDocuments, useDownloadDocument } from '@/api/hooks/docvault'

export function RequirementsTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useListRequirements(engagementId)
  const { data: docs = [] } = useDocuments()
  const fulfillReq = useFulfillRequirement()
  const downloadDoc = useDownloadDocument()
  
  const [selectedDocs, setSelectedDocs] = useState<Record<string, string>>({})

  const handleFulfill = async (reqId: string) => {
    const docId = selectedDocs[reqId]
    if (!docId) return
    try {
      await fulfillReq.mutateAsync({ engagementId, reqId, body: { document_id: docId } })
      toast.success('Requirement fulfilled')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error fulfilling requirement')
    }
  }

  const handleDownload = async (docId: string) => {
    const doc = docs.find(d => d.id === docId)
    if (!doc || !doc.current_version_id) {
      toast.error('Document not found')
      return
    }
    const version = doc.versions.find(v => v.id === doc.current_version_id)
    if (!version) return
    try {
      await downloadDoc.mutateAsync({ id: doc.id, versionId: version.id, filename: version.original_filename })
    } catch (err) {
      toast.error('Failed to download document')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  return (
    <div className="flex flex-col gap-4">
      {reqs.length === 0 ? (
        <EmptyState title="No requirements" description="The auditor hasn't requested any documents yet." />
      ) : (
        reqs.map((req) => (
          <Card key={req.id} className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1">
              <p className="font-medium text-text-primary">{req.description}</p>
              <div className="mt-1 flex items-center gap-2">
                <StatusBadge status={req.status} />
                <span className="text-xs text-text-secondary">
                  {new Date(req.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            
            <div className="flex w-full flex-col items-end gap-2 sm:w-1/3">
              {req.status === 'open' ? (
                <div className="flex w-full items-end gap-2">
                  <div className="flex-1">
                    <Select
                      value={selectedDocs[req.id] || ''}
                      onChange={(e) => setSelectedDocs({ ...selectedDocs, [req.id]: e.target.value })}
                    >
                      <option value="">Select docVault document...</option>
                      {docs.map(d => (
                        <option key={d.id} value={d.id}>{d.title}</option>
                      ))}
                    </Select>
                  </div>
                  <Button
                    onClick={() => handleFulfill(req.id)}
                    disabled={!selectedDocs[req.id] || fulfillReq.isPending}
                  >
                    Fulfill
                  </Button>
                </div>
              ) : (
                req.fulfilled_document_id && (
                  <Button variant="secondary" onClick={() => handleDownload(req.fulfilled_document_id!)}>
                    Download Document
                  </Button>
                )
              )}
            </div>
          </Card>
        ))
      )}
    </div>
  )
}
