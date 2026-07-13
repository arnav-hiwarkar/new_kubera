import { useState, useRef } from 'react'
import { Button, Input, Select, StatusBadge, Spinner, useToast, EmptyState } from '@/components/ui'
import { ApiError } from '@/api/http'
import { cn } from '@/lib/cn'
import { useListQueries, useAddQueryMessage } from '@/api/hooks/auditease'
import { useDocuments, useDownloadDocument } from '@/api/hooks/docvault'

export function QueriesTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: queries = [], isLoading } = useListQueries(engagementId)
  const { data: docs = [] } = useDocuments()
  const addMsg = useAddQueryMessage()
  const downloadDoc = useDownloadDocument()

  const [activeQueryId, setActiveQueryId] = useState<string | null>(null)
  
  // Reply state
  const [replyMsg, setReplyMsg] = useState('')
  const [replyFile, setReplyFile] = useState<File | null>(null)
  const [replyDocId, setReplyDocId] = useState('')
  const replyFileInput = useRef<HTMLInputElement>(null)

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  const activeQuery = queries.find((q) => q.id === activeQueryId)

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeQuery || !replyMsg.trim()) return
    
    if (replyFile && replyDocId) {
      toast.error('Choose either a file upload OR a docVault document, not both')
      return
    }

    const formData = new FormData()
    formData.append('text', replyMsg.trim())
    if (replyFile) formData.append('file', replyFile)
    if (replyDocId) formData.append('attached_document_id', replyDocId)

    try {
      await addMsg.mutateAsync({ engagementId, queryId: activeQuery.id, formData })
      setReplyMsg('')
      setReplyFile(null)
      setReplyDocId('')
      if (replyFileInput.current) replyFileInput.current.value = ''
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error')
    }
  }

  const handleDownload = async (docId: string) => {
    const doc = docs.find(d => d.id === docId)
    if (!doc || !doc.current_version_id) {
      toast.error('Document not found in docVault')
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

  return (
    <div className="flex h-[600px] gap-6">
      {/* Sidebar: Query List */}
      <div className="flex w-1/3 flex-col gap-2 overflow-y-auto border-r border-border pr-4">
        {queries.length === 0 ? (
          <EmptyState title="No queries" description="The auditor hasn't opened any queries yet." />
        ) : (
          queries.map((q) => {
            const firstMsg = q.messages[0]?.text || 'No messages'
            return (
              <button
                key={q.id}
                onClick={() => setActiveQueryId(q.id)}
                className={cn(
                  'flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors',
                  activeQueryId === q.id
                    ? 'border-accent bg-accent/5'
                    : 'border-border bg-surface hover:bg-surface-hover'
                )}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="truncate text-sm font-medium text-text-primary">
                    {firstMsg}
                  </span>
                  <StatusBadge status={q.status} />
                </div>
                <span className="text-xs text-text-secondary">
                  {new Date(q.created_at).toLocaleDateString()}
                </span>
              </button>
            )
          })
        )}
      </div>

      {/* Main Content: Thread */}
      <div className="flex flex-1 flex-col rounded-lg border border-border bg-surface">
        {activeQuery ? (
          <>
            <div className="flex items-center justify-between border-b border-border p-4">
              <h3 className="font-medium text-text-primary">Query Thread</h3>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {activeQuery.messages.map((msg) => {
                const isCompany = msg.sender_type === 'company_user'
                return (
                  <div key={msg.id} className={cn("flex flex-col", isCompany ? "items-end" : "items-start")}>
                    <div className="mb-1 text-xs text-text-muted">
                      {isCompany ? 'You' : 'Auditor'} · {new Date(msg.created_at).toLocaleTimeString()}
                    </div>
                    <div
                      className={cn(
                        "rounded-2xl px-4 py-2 text-sm",
                        isCompany
                          ? "bg-accent text-white"
                          : "bg-surface-hover text-text-primary"
                      )}
                    >
                      {msg.text}
                    </div>
                    {msg.attached_document_id && (
                      <button
                        onClick={() => handleDownload(msg.attached_document_id!)}
                        className="mt-1 text-xs font-medium text-accent hover:underline"
                      >
                        ↓ Download Attachment
                      </button>
                    )}
                  </div>
                )
              })}
            </div>

            {activeQuery.status === 'open' && (
              <form onSubmit={handleReply} className="border-t border-border p-4">
                <div className="flex flex-col gap-3">
                  <div className="flex gap-2">
                    <Input
                      value={replyMsg}
                      onChange={(e) => setReplyMsg(e.target.value)}
                      placeholder="Type your reply..."
                      disabled={addMsg.isPending}
                      className="flex-1"
                    />
                    <Button type="submit" disabled={!replyMsg.trim() || addMsg.isPending}>
                      Send
                    </Button>
                  </div>
                  
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-text-secondary whitespace-nowrap">Attach:</span>
                    <input
                      type="file"
                      className="text-xs max-w-[200px]"
                      ref={replyFileInput}
                      onChange={(e) => setReplyFile(e.target.files?.[0] || null)}
                      disabled={addMsg.isPending || !!replyDocId}
                    />
                    <span className="text-text-muted text-xs">OR</span>
                    <Select
                      value={replyDocId}
                      onChange={(e) => setReplyDocId(e.target.value)}
                      disabled={addMsg.isPending || !!replyFile}
                    >
                      <option value="">Select docVault file...</option>
                      {docs.map((d) => (
                        <option key={d.id} value={d.id}>{d.title}</option>
                      ))}
                    </Select>
                  </div>
                </div>
              </form>
            )}
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState title="Select a query" description="Choose a query from the list to view the thread." />
          </div>
        )}
      </div>
    </div>
  )
}
