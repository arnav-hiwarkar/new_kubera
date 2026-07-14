import { useMemo, useState } from 'react'
import { Archive, Upload } from 'lucide-react'
import {
  PageHeader,
  Button,
  Select,
  DataTable,
  StatusBadge,
  useToast,
  type Column,
} from '@/components/ui'
import { DOCUMENT_STATUS, humanize } from '@/api/enums'
import { ApiError } from '@/api/http'
import type { DocumentResponse } from '@/api/types'
import { formatDate } from '@/lib/format'
import { useBuckets, useDocuments, useDownloadDocument } from '@/api/hooks/docvault'
import { BucketRail, type BucketSelection } from './BucketRail'
import { UploadDocumentModal } from './UploadDocumentModal'
import { DocumentDrawer } from './DocumentDrawer'

const LIVE_STATUSES = DOCUMENT_STATUS.filter((s) => s !== 'archived')

export function DocVaultPage() {
  const toast = useToast()
  const { data: buckets = [] } = useBuckets()
  const { data: documents = [], isLoading } = useDocuments()
  const download = useDownloadDocument()

  const [bucketSel, setBucketSel] = useState<BucketSelection>('all')
  const [statusFilter, setStatusFilter] = useState('') // '' = active (non-archived)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const bucketName = (id: string | null) =>
    id ? (buckets.find((b) => b.id === id)?.name ?? '—') : 'Uncategorized'

  const filtered = useMemo(() => {
    return documents.filter((d) => {
      // Bucket
      if (bucketSel === 'uncategorized' && d.bucket_id) return false
      if (bucketSel !== 'all' && bucketSel !== 'uncategorized' && d.bucket_id !== bucketSel)
        return false
      // Status
      if (statusFilter === '') return d.status !== 'archived'
      return d.status === statusFilter
    })
  }, [documents, bucketSel, statusFilter])

  // Look up the selected doc from the full list so the drawer stays valid even
  // when the current filter would hide it (e.g. right after archiving).
  const selectedDoc = documents.find((d) => d.id === selectedId) ?? null

  const currentVersionNo = (d: DocumentResponse) =>
    d.versions.find((v) => v.id === d.current_version_id)?.version_number ??
    Math.max(0, ...d.versions.map((v) => v.version_number))

  const handleDownload = (d: DocumentResponse) => {
    const cur = d.versions.find((v) => v.id === d.current_version_id) ?? d.versions.at(-1)
    if (!cur) {
      toast.error('No file to download')
      return
    }
    download
      .mutateAsync({ id: d.id, versionId: cur.id, filename: cur.original_filename })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : 'Download failed'))
  }

  const columns: Column<DocumentResponse>[] = [
    {
      key: 'title',
      header: 'Title',
      sortValue: (d) => d.title.toLowerCase(),
      cell: (d) => (
        <div>
          <div className="font-medium text-text-primary">{d.title}</div>
          {d.tags.length > 0 && (
            <div className="mt-0.5 flex flex-wrap gap-1">
              {d.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-bg-raised px-1.5 py-0.5 text-xs text-text-muted"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      ),
    },
    { key: 'bucket', header: 'Bucket', cell: (d) => bucketName(d.bucket_id) },
    {
      key: 'status',
      header: 'Status',
      sortValue: (d) => d.status,
      cell: (d) => <StatusBadge status={d.status} />,
    },
    {
      key: 'version',
      header: 'Version',
      align: 'right',
      cell: (d) => <span className="font-mono text-text-secondary">v{currentVersionNo(d)}</span>,
    },
    {
      key: 'updated',
      header: 'Updated',
      sortValue: (d) => d.updated_at,
      cell: (d) => <span className="text-text-secondary">{formatDate(d.updated_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      cell: (d) => (
        <button
          onClick={(e) => {
            e.stopPropagation()
            handleDownload(d)
          }}
          className="text-accent hover:underline"
        >
          Download
        </button>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="DOCUMENTS"
        icon={<Archive />}
        title="DocVault"
        description="Encrypted company document library with buckets and version history"
        actions={
          <Button onClick={() => setUploadOpen(true)}>
            <Upload />
            Upload
          </Button>
        }
      />

      <div className="flex gap-4">
        <BucketRail
          buckets={buckets}
          documents={documents}
          selected={bucketSel}
          onSelect={setBucketSel}
        />

        <div className="min-w-0 flex-1">
          <DataTable
            columns={columns}
            data={filtered}
            rowKey={(d) => d.id}
            loading={isLoading}
            searchAccessors={(d) => `${d.title} ${d.tags.join(' ')} ${bucketName(d.bucket_id)}`}
            searchPlaceholder="Search documents…"
            onRowClick={(d) => setSelectedId(d.id)}
            emptyTitle="No documents"
            emptyDescription="Upload a document to get started."
            toolbar={
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-8 w-44"
              >
                <option value="">Active documents</option>
                {LIVE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {humanize(s)}
                  </option>
                ))}
                <option value="archived">Archived</option>
              </Select>
            }
          />
        </div>
      </div>

      <UploadDocumentModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        buckets={buckets}
        defaultBucketId={
          bucketSel !== 'all' && bucketSel !== 'uncategorized' ? bucketSel : undefined
        }
      />
      <DocumentDrawer
        document={selectedDoc}
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        buckets={buckets}
      />
    </div>
  )
}
