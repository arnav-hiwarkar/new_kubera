import { useState } from 'react'
import { Button, DataTable, useToast, type Column } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useDocumentTypes, useDeleteDocumentType, type Domain } from '@/api/hooks/compliance'
import type { DocumentTypeResponse } from '@/api/types'
import { DocumentTypeModal } from './DocumentTypeModal'
import { readFields } from './schema'

export function DocumentTypesTab({ domain }: { domain: Domain }) {
  const toast = useToast()
  const { data: types = [], isLoading } = useDocumentTypes(domain)
  const del = useDeleteDocumentType(domain)

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<DocumentTypeResponse | null>(null)

  const openCreate = () => {
    setEditing(null)
    setModalOpen(true)
  }
  const openEdit = (t: DocumentTypeResponse) => {
    setEditing(t)
    setModalOpen(true)
  }

  const handleDelete = async (t: DocumentTypeResponse) => {
    if (!window.confirm(`Delete "${t.name}"?`)) return
    try {
      await del.mutateAsync(t.id)
      toast.success('Document type deleted')
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast.error('This type has records — remove them first.')
      } else {
        toast.error(e instanceof Error ? e.message : 'Failed to delete type')
      }
    }
  }

  const columns: Column<DocumentTypeResponse>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (t) => t.name.toLowerCase(),
      cell: (t) => <span className="font-medium text-text-primary">{t.name}</span>,
    },
    {
      key: 'template',
      header: 'Template',
      align: 'center',
      cell: (t) => (t.template_file_id ? '✓' : '—'),
    },
    {
      key: 'fields',
      header: 'Fields',
      align: 'right',
      sortValue: (t) => readFields(t.metadata_schema).length,
      cell: (t) => readFields(t.metadata_schema).length,
    },
    {
      key: 'due_date_rule',
      header: 'Due rule',
      cell: (t) => t.due_date_rule || '—',
    },
    {
      key: 'source',
      header: 'Source',
      cell: (t) =>
        t.company_id === null ? (
          <span className="text-text-muted">System</span>
        ) : (
          <span className="text-text-primary">Company</span>
        ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      cell: (t) =>
        t.company_id !== null ? (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => openEdit(t)}>
              Edit
            </Button>
            <Button variant="danger" onClick={() => handleDelete(t)}>
              Delete
            </Button>
          </div>
        ) : (
          <span className="text-text-muted">—</span>
        ),
    },
  ]

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button onClick={openCreate}>New type</Button>
      </div>

      <DataTable
        columns={columns}
        data={types}
        rowKey={(t) => t.id}
        loading={isLoading}
        searchAccessors={(t) => `${t.name} ${t.due_date_rule ?? ''}`}
        searchPlaceholder="Search document types…"
        emptyTitle="No document types"
        emptyDescription="Create a company document type to start capturing records."
      />

      <DocumentTypeModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        domain={domain}
        docType={editing}
      />
    </div>
  )
}
