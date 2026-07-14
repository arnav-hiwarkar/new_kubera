import { useState, useRef } from 'react'
import { Download, MessagesSquare } from 'lucide-react'
import { Button, Card, Input, StatusBadge, Spinner, useToast, EmptyState } from '@/components/ui'
import { ApiError } from '@/api/http'
import { cn } from '@/lib/cn'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'
import { saveBlob } from '@/lib/download'
import {
  useAuditorListQueries,
  useAuditorCreateQuery,
  useAuditorAddQueryMessage,
  useAuditorCloseQuery,
} from '@/api/hooks/auditorEngagements'

export function QueriesTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: queries = [], isLoading } = useAuditorListQueries(engagementId)
  const createQuery = useAuditorCreateQuery()
  const addMsg = useAuditorAddQueryMessage()
  const closeQuery = useAuditorCloseQuery()

  const [activeQueryId, setActiveQueryId] = useState<string | null>(null)
  
  // New query state
  const [newMsg, setNewMsg] = useState('')
  const [newFile, setNewFile] = useState<File | null>(null)
  const newFileInput = useRef<HTMLInputElement>(null)

  // Reply state
  const [replyMsg, setReplyMsg] = useState('')
  const [replyFile, setReplyFile] = useState<File | null>(null)
  const replyFileInput = useRef<HTMLInputElement>(null)

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  const activeQuery = queries.find((q) => q.id === activeQueryId)

  const handleCreateQuery = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMsg.trim()) return
    const formData = new FormData()
    formData.append('initial_message', newMsg.trim())
    if (newFile) formData.append('file', newFile)

    try {
      const res = await createQuery.mutateAsync({ engagementId, formData })
      setNewMsg('')
      setNewFile(null)
      if (newFileInput.current) newFileInput.current.value = ''
      setActiveQueryId(res.id)
      toast.success('Query opened')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error')
    }
  }

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeQuery || !replyMsg.trim()) return
    const formData = new FormData()
    formData.append('text', replyMsg.trim())
    if (replyFile) formData.append('file', replyFile)

    try {
      await addMsg.mutateAsync({ engagementId, queryId: activeQuery.id, formData })
      setReplyMsg('')
      setReplyFile(null)
      if (replyFileInput.current) replyFileInput.current.value = ''
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error')
    }
  }

  const handleClose = async () => {
    if (!activeQuery) return
    try {
      await closeQuery.mutateAsync({ engagementId, queryId: activeQuery.id })
      toast.success('Query closed')
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

  return (
    <div className="flex h-[600px] gap-6">
      {/* Sidebar: Query List */}
      <div className="flex w-1/3 flex-col gap-4 overflow-y-auto border-r border-border pr-4">
        <Card className="flex flex-col gap-3">
          <h3 className="text-sm font-medium text-text-primary">New Query</h3>
          <form onSubmit={handleCreateQuery} className="flex flex-col gap-2">
            <Input
              value={newMsg}
              onChange={(e) => setNewMsg(e.target.value)}
              placeholder="Ask a question..."
              disabled={createQuery.isPending}
            />
            <input
              type="file"
              className="text-xs"
              ref={newFileInput}
              onChange={(e) => setNewFile(e.target.files?.[0] || null)}
              disabled={createQuery.isPending}
            />
            <Button type="submit" disabled={!newMsg.trim() || createQuery.isPending} className="mt-1">
              {createQuery.isPending ? 'Opening...' : 'Open Query'}
            </Button>
          </form>
        </Card>

        <div className="flex flex-col gap-2">
          {queries.map((q) => {
            const firstMsg = q.messages[0]?.text || 'No messages'
            return (
              <button
                key={q.id}
                onClick={() => setActiveQueryId(q.id)}
                className={cn(
                  'flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors',
                  activeQueryId === q.id
                    ? 'border-accent bg-accent/5'
                    : 'border-border bg-bg-surface hover:bg-bg-raised'
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
          })}
        </div>
      </div>

      {/* Main Content: Thread */}
      <div className="flex flex-1 flex-col rounded-lg border border-border bg-bg-surface">
        {activeQuery ? (
          <>
            <div className="flex items-center justify-between border-b border-border p-4">
              <h3 className="font-medium text-text-primary">Query Thread</h3>
              {activeQuery.status === 'open' && (
                <Button variant="secondary" onClick={handleClose} disabled={closeQuery.isPending}>
                  Close Query
                </Button>
              )}
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {activeQuery.messages.map((msg) => {
                const isAuditor = msg.sender_type === 'auditor'
                return (
                  <div key={msg.id} className={cn("flex flex-col", isAuditor ? "items-end" : "items-start")}>
                    <div className="mb-1 text-xs text-text-muted">
                      {isAuditor ? 'You (Auditor)' : 'Company'} · {new Date(msg.created_at).toLocaleTimeString()}
                    </div>
                    <div
                      className={cn(
                        "rounded-2xl px-4 py-2 text-sm",
                        isAuditor
                          ? "bg-accent text-accent-contrast"
                          : "bg-bg-raised text-text-primary"
                      )}
                    >
                      {msg.text}
                    </div>
                    {msg.attached_document_id && (
                      <button
                        onClick={() => handleDownload(msg.attached_document_id!)}
                        className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                      >
                        <Download className="h-3.5 w-3.5" /> Download Attachment
                      </button>
                    )}
                  </div>
                )
              })}
            </div>

            {activeQuery.status === 'open' && (
              <form onSubmit={handleReply} className="border-t border-border p-4">
                <div className="flex gap-2">
                  <div className="flex-1 flex flex-col gap-2">
                    <Input
                      value={replyMsg}
                      onChange={(e) => setReplyMsg(e.target.value)}
                      placeholder="Type your reply..."
                      disabled={addMsg.isPending}
                    />
                    <input
                      type="file"
                      className="text-xs"
                      ref={replyFileInput}
                      onChange={(e) => setReplyFile(e.target.files?.[0] || null)}
                      disabled={addMsg.isPending}
                    />
                  </div>
                  <Button type="submit" disabled={!replyMsg.trim() || addMsg.isPending}>
                    Send
                  </Button>
                </div>
              </form>
            )}
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState icon={<MessagesSquare />} title="Select a query" description="Choose a query from the list to view the thread." />
          </div>
        )}
      </div>
    </div>
  )
}
