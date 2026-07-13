import { useState } from 'react'
import { Button, Card, Field, Input, StatusBadge, Spinner, useToast, EmptyState } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAuditorListRequirements, useAuditorCreateRequirement } from '@/api/hooks/auditorEngagements'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'
import { saveBlob } from '@/lib/download'

export function RequirementsTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useAuditorListRequirements(engagementId)
  const createReq = useAuditorCreateRequirement()
  
  const [description, setDescription] = useState('')

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!description.trim()) return
    try {
      await createReq.mutateAsync({ engagementId, body: { description: description.trim() } })
      setDescription('')
      toast.success('Requirement requested')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error')
    }
  }

  const handleDownload = async (docId: string) => {
    try {
      const doc = await auditorEngagementsApi.getDocument(docId)
      const blob = await auditorEngagementsApi.downloadDocument(docId)
      const version = doc.versions.find((v) => v.id === doc.current_version_id)
      const filename = version?.original_filename || 'document'
      saveBlob(blob, filename)
    } catch (err) {
      toast.error('Failed to download document')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h2 className="mb-4 text-lg font-medium text-text-primary">Request a Document</h2>
        <form onSubmit={handleCreate} className="flex items-end gap-4">
          <div className="flex-1">
            <Field label="Description">
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. FY24 Bank Statements"
                disabled={createReq.isPending}
              />
            </Field>
          </div>
          <Button type="submit" disabled={!description.trim() || createReq.isPending}>
            {createReq.isPending ? 'Requesting...' : 'Request'}
          </Button>
        </form>
      </Card>

      <div className="flex flex-col gap-4">
        <h3 className="text-lg font-medium text-text-primary">Requested Documents</h3>
        {reqs.length === 0 ? (
          <EmptyState title="No requirements" description="You haven't requested any documents yet." />
        ) : (
          reqs.map((req) => (
            <Card key={req.id} className="flex items-center justify-between">
              <div>
                <p className="font-medium text-text-primary">{req.description}</p>
                <div className="mt-1 flex items-center gap-2">
                  <StatusBadge status={req.status} />
                  <span className="text-xs text-text-secondary">
                    {new Date(req.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
              {req.status === 'fulfilled' && req.fulfilled_document_id && (
                <Button variant="secondary" onClick={() => handleDownload(req.fulfilled_document_id!)}>
                  Download
                </Button>
              )}
            </Card>
          ))
        )}
      </div>
    </div>
  )
}
