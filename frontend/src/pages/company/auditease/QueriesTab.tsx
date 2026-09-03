import { useState, useRef } from 'react'
import { Download, MessagesSquare, FolderPlus, X, FileText } from 'lucide-react'
import { Button, Input, StatusBadge, Spinner, useToast, EmptyState } from '@/components/ui'
import { ApiError } from '@/api/http'
import { cn } from '@/lib/cn'
import { useListQueries, useAddQueryMessage } from '@/api/hooks/auditease'
import { useDocuments } from '@/api/hooks/docvault'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { saveBlob } from '@/lib/download'
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess } from '@/auth/company/modules'

export function QueriesTab({ engagementId }: { engagementId: string }) {
  const { profile } = useCompanyAuth()
  const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
  const toast = useToast()
  const { data: queries = [], isLoading } = useListQueries(engagementId)
  const { data: docs = [] } = useDocuments()
  const addMsg = useAddQueryMessage()

  const [activeQueryId, setActiveQueryId] = useState<string | null>(null)
  
  // Reply state
  const [replyMsg, setReplyMsg] = useState('')
  const [replyFile, setReplyFile] = useState<File | null>(null)
  const [replyDocId, setReplyDocId] = useState('')
  const [showPickerModal, setShowPickerModal] = useState(false)
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
    try {
      const doc = await auditeaseCompanyApi.getDocument(docId)
      const blob = await auditeaseCompanyApi.downloadDocument(docId)
      const version = doc.versions?.find((v) => v.id === doc.current_version_id)
      saveBlob(blob, version?.original_filename || 'document')
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
                    : 'border-border bg-bg-surface hover:bg-bg-raised'
                )}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="truncate text-sm font-medium text-text-primary">
                    {firstMsg}
                  </span>
                  <StatusBadge status={q.status} />
                </div>
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  <span>{new Date(q.created_at).toLocaleDateString()}</span>
                  {q.requirement_id && (
                    <span className="px-1.5 py-0.2 rounded text-[10px] bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 font-medium">
                      Requirement Query
                    </span>
                  )}
                </div>
              </button>
            )
          })
        )}
      </div>

      {/* Main Content: Thread */}
      <div className="flex flex-1 flex-col rounded-lg border border-border bg-bg-surface">
        {activeQuery ? (
          <>
            <div className="flex items-center justify-between border-b border-border p-4">
              <div className="flex items-center gap-2">
                <h3 className="font-medium text-text-primary">Query Thread</h3>
                {activeQuery.requirement_id && (
                  <span className="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 font-medium">
                    Linked to Requirement
                  </span>
                )}
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {activeQuery.messages.map((msg) => {
                const isCompany = msg.sender_type === 'company_user'
                return (
                  <div key={msg.id} className={cn("flex flex-col", isCompany ? "items-end" : "items-start")}>
                    <div className="mb-1 text-xs text-text-muted">
                      {msg.sender_name ?? (isCompany ? 'You' : 'Auditor')} · {new Date(msg.created_at).toLocaleTimeString()}
                    </div>
                    <div
                      className={cn(
                        "rounded-2xl px-4 py-2 text-sm",
                        isCompany
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
                  
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <span className="text-text-secondary whitespace-nowrap">Attach:</span>
                    <input
                      type="file"
                      className="text-xs max-w-[200px]"
                      ref={replyFileInput}
                      onChange={(e) => {
                        setReplyFile(e.target.files?.[0] || null)
                        if (e.target.files?.[0]) setReplyDocId('')
                      }}
                      disabled={addMsg.isPending}
                    />
                    <span className="text-text-muted text-xs">OR</span>
                    {canBrowseDocVault && (
                      <button
                        type="button"
                        onClick={() => setShowPickerModal(true)}
                        disabled={addMsg.isPending}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-border bg-bg-surface hover:bg-bg-raised text-xs text-text-primary transition-colors"
                      >
                        <FolderPlus className="w-3.5 h-3.5 text-zinc-500" />
                        <span>{replyDocId ? 'Change DocVault Document' : 'Select from DocVault'}</span>
                      </button>
                    )}
                    {replyDocId && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800">
                        <FileText className="w-3 h-3 text-blue-500 shrink-0" />
                        <span className="truncate max-w-[150px]">{docs.find((d) => d.id === replyDocId)?.title || 'Selected Doc'}</span>
                        <button
                          type="button"
                          onClick={() => setReplyDocId('')}
                          className="p-0.5 text-blue-400 hover:text-blue-600 rounded"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    )}
                  </div>
                </div>
              </form>
            )}

            {showPickerModal && (
              <DocVaultPickerModal
                open={showPickerModal}
                multiple={false}
                selectedDocIds={replyDocId ? [replyDocId] : []}
                onClose={() => setShowPickerModal(false)}
                onConfirm={(ids) => {
                  setReplyDocId(ids[0] || '')
                  if (ids.length > 0) {
                    setReplyFile(null)
                    if (replyFileInput.current) replyFileInput.current.value = ''
                  }
                }}
              />
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
