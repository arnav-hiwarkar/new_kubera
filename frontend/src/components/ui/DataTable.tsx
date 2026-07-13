import { useMemo, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Spinner } from './Spinner'
import { Input } from './Field'
import { EmptyState } from './EmptyState'

export interface Column<T> {
  key: string
  header: string
  /** Cell renderer. Defaults to String(row[key]). */
  cell?: (row: T) => ReactNode
  /** Value used for sorting; enables the sort control when provided. */
  sortValue?: (row: T) => string | number
  align?: 'left' | 'right' | 'center'
  className?: string
}

export interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  rowKey: (row: T) => string
  loading?: boolean
  /** Client-side free-text filter over these accessors. */
  searchAccessors?: (row: T) => string
  searchPlaceholder?: string
  pageSize?: number
  onRowClick?: (row: T) => void
  emptyTitle?: string
  emptyDescription?: string
  toolbar?: ReactNode
}

type SortState = { key: string; dir: 'asc' | 'desc' } | null

export function DataTable<T>({
  columns,
  data,
  rowKey,
  loading,
  searchAccessors,
  searchPlaceholder = 'Search…',
  pageSize = 10,
  onRowClick,
  emptyTitle = 'No records',
  emptyDescription,
  toolbar,
}: DataTableProps<T>) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(0)

  const filtered = useMemo(() => {
    if (!query || !searchAccessors) return data
    const q = query.toLowerCase()
    return data.filter((row) => searchAccessors(row).toLowerCase().includes(q))
  }, [data, query, searchAccessors])

  const sorted = useMemo(() => {
    if (!sort) return filtered
    const col = columns.find((c) => c.key === sort.key)
    if (!col?.sortValue) return filtered
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      const av = col.sortValue!(a)
      const bv = col.sortValue!(b)
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })
  }, [filtered, sort, columns])

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const pageRows = sorted.slice(safePage * pageSize, safePage * pageSize + pageSize)

  const toggleSort = (col: Column<T>) => {
    if (!col.sortValue) return
    setPage(0)
    setSort((prev) =>
      prev?.key === col.key
        ? { key: col.key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key: col.key, dir: 'asc' },
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {(searchAccessors || toolbar) && (
        <div className="flex items-center justify-between gap-2">
          {searchAccessors ? (
            <Input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setPage(0)
              }}
              placeholder={searchPlaceholder}
              className="h-8 max-w-xs"
            />
          ) : (
            <div />
          )}
          {toolbar}
        </div>
      )}

      <div className="overflow-x-auto rounded-card border border-border bg-bg-surface">
        <table className="w-full border-collapse text-base">
          <thead>
            <tr className="border-b border-border bg-bg-raised/50">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => toggleSort(col)}
                  className={cn(
                    'px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-text-secondary',
                    col.align === 'right' && 'text-right',
                    col.align === 'center' && 'text-center',
                    col.sortValue && 'cursor-pointer select-none hover:text-text-primary',
                    col.className,
                  )}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {sort?.key === col.key && (
                      <span aria-hidden>{sort.dir === 'asc' ? '▲' : '▼'}</span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center">
                  <Spinner className="mx-auto h-6 w-6" />
                </td>
              </tr>
            ) : pageRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState
                    title={emptyTitle}
                    description={emptyDescription}
                    className="border-0"
                  />
                </td>
              </tr>
            ) : (
              pageRows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    'border-b border-border last:border-0',
                    onRowClick && 'cursor-pointer hover:bg-bg-raised/60',
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'px-3 py-2 text-text-primary',
                        col.align === 'right' && 'text-right',
                        col.align === 'center' && 'text-center',
                        col.className,
                      )}
                    >
                      {col.cell ? col.cell(row) : String((row as Record<string, unknown>)[col.key] ?? '')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {sorted.length > pageSize && (
        <div className="flex items-center justify-between text-sm text-text-secondary">
          <span>
            {safePage * pageSize + 1}–{Math.min((safePage + 1) * pageSize, sorted.length)} of{' '}
            {sorted.length}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="rounded-btn border border-border px-2 py-1 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              className="rounded-btn border border-border px-2 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
