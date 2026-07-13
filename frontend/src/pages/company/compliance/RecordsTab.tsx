import { useMemo, useState } from 'react'
import { Button, Input, Select, Spinner, EmptyState } from '@/components/ui'
import { docvaultApi } from '@/api/endpoints/docvault'
import { saveBlob } from '@/lib/download'
import { formatDate } from '@/lib/format'
import { useMeetingRecords, useDocumentTypes, type Domain } from '@/api/hooks/compliance'
import type { DocumentTypeResponse, MeetingRecordResponse } from '@/api/types'
import { readFields, type FieldDef } from './schema'
import { RecordModal } from './RecordModal'

type View = 'type' | 'month'

interface TypeInfo {
  name: string
  fields: FieldDef[]
}

/** Read structured_metadata as a string map (values were stored as strings). */
function readValues(metadata: unknown): Record<string, string> {
  const raw = metadata as Record<string, unknown> | null
  if (!raw || typeof raw !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v != null) out[k] = String(v)
  }
  return out
}

function monthKey(date: string | null | undefined): string {
  if (!date) return 'Undated'
  const d = new Date(date)
  if (Number.isNaN(d.getTime())) return 'Undated'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'long' })
}

export function RecordsTab({ domain }: { domain: Domain }) {
  const { data: recordsData, isLoading } = useMeetingRecords(domain)
  const { data: typesData } = useDocumentTypes(domain)

  const records = useMemo(() => recordsData ?? [], [recordsData])
  const types = useMemo(() => typesData ?? [], [typesData])

  const typeById = useMemo(() => {
    const map: Record<string, TypeInfo> = {}
    for (const t of types) map[t.id] = { name: t.name, fields: readFields(t.metadata_schema) }
    return map
  }, [types])

  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [thisMonth, setThisMonth] = useState(false)
  const [view, setView] = useState<View>('type')
  const [modalOpen, setModalOpen] = useState(false)

  const now = new Date()
  const curYear = now.getFullYear()
  const curMonth = now.getMonth()

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return records.filter((r) => {
      if (typeFilter && r.doc_type_id !== typeFilter) return false
      if (thisMonth) {
        if (!r.record_date) return false
        const d = new Date(r.record_date)
        if (d.getFullYear() !== curYear || d.getMonth() !== curMonth) return false
      }
      if (q) {
        const name = typeById[r.doc_type_id]?.name ?? ''
        const hay = `${name} ${JSON.stringify(r.structured_metadata ?? {})}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [records, typeFilter, thisMonth, search, typeById, curYear, curMonth])

  const groups = useMemo(() => {
    const map = new Map<string, MeetingRecordResponse[]>()
    if (view === 'type') {
      for (const r of filtered) {
        const label = typeById[r.doc_type_id]?.name ?? 'Unknown type'
        const list = map.get(label) ?? []
        list.push(r)
        map.set(label, list)
      }
      return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
    }
    // By month, newest first (Undated last).
    for (const r of filtered) {
      const label = monthKey(r.record_date)
      const list = map.get(label) ?? []
      list.push(r)
      map.set(label, list)
    }
    return [...map.entries()].sort((a, b) => {
      if (a[0] === 'Undated') return 1
      if (b[0] === 'Undated') return -1
      return new Date(b[1][0].record_date ?? 0).getTime() - new Date(a[1][0].record_date ?? 0).getTime()
    })
  }, [filtered, view, typeById])

  const handleDownload = async (r: MeetingRecordResponse, typeName: string) => {
    if (!r.document_id) return
    const blob = await docvaultApi.downloadDocument(r.document_id)
    saveBlob(blob, `${typeName}-${r.record_date ?? 'doc'}`)
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search records…"
          className="h-8 max-w-[220px]"
        />
        <Select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="h-8 max-w-[200px]"
        >
          <option value="">All types</option>
          {types.map((t: DocumentTypeResponse) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
        <Button
          variant={thisMonth ? 'primary' : 'secondary'}
          onClick={() => setThisMonth((v) => !v)}
        >
          This month
        </Button>
        <div className="ml-auto flex gap-1">
          <Button variant={view === 'type' ? 'primary' : 'ghost'} onClick={() => setView('type')}>
            By type
          </Button>
          <Button variant={view === 'month' ? 'primary' : 'ghost'} onClick={() => setView('month')}>
            By month
          </Button>
          <Button onClick={() => setModalOpen(true)}>New record</Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No records"
          description="Create a record to capture a completed compliance document."
        />
      ) : (
        <div className="flex flex-col gap-6">
          {groups.map(([label, rows]) => (
            <div key={label}>
              <h3 className="mb-2 text-sm font-semibold text-text-primary">
                {label} <span className="text-text-muted">({rows.length})</span>
              </h3>
              <div className="rounded-card border border-border divide-y divide-border">
                {rows.map((r) => {
                  const info = typeById[r.doc_type_id]
                  const typeName = info?.name ?? 'Unknown type'
                  const values = readValues(r.structured_metadata)
                  const preview = (info?.fields ?? [])
                    .filter((f) => values[f.key])
                    .slice(0, 2)
                    .map((f) => `${f.label}: ${values[f.key]}`)
                  return (
                    <div key={r.id} className="flex items-center gap-4 px-4 py-3">
                      <div className="w-28 shrink-0 text-sm text-text-secondary">
                        {r.record_date ? formatDate(r.record_date) : '—'}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-text-primary">{typeName}</div>
                        {preview.length > 0 && (
                          <div className="truncate text-xs text-text-muted">{preview.join(' · ')}</div>
                        )}
                      </div>
                      {r.document_id && (
                        <Button variant="ghost" onClick={() => void handleDownload(r, typeName)}>
                          Download
                        </Button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      <RecordModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        domain={domain}
        types={types}
      />
    </div>
  )
}
