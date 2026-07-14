import { useMemo, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Spinner } from './Spinner'
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
            <div className="relative max-w-xs flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setPage(0)
                }}
                placeholder={searchPlaceholder}
                className="h-9 w-full rounded-input border border-border-strong bg-bg-surface pl-9 pr-3 text-base text-text-primary placeholder:text-text-muted transition-shadow focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/15"
              />
            </div>
          ) : (
            <div />
          )}
          {toolbar}
        </div>
      )}

      <div className="overflow-x-auto rounded-card border border-border bg-bg-surface shadow-card">
        <table className="w-full border-collapse text-base">
          <thead>
            <tr className="border-b border-border bg-bg-inset">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => toggleSort(col)}
                  className={cn(
                    'px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.04em] text-text-secondary',
                    col.align === 'right' && 'text-right',
                    col.align === 'center' && 'text-center',
                    col.sortValue && 'cursor-pointer select-none transition-colors hover:text-text-primary',
                    col.className,
                  )}
                >
                  <span
                    className={cn(
                      'inline-flex items-center gap-1',
                      col.align === 'right' && 'flex-row-reverse',
                    )}
                  >
                    {col.header}
                    {col.sortValue &&
                      (sort?.key === col.key ? (
                        sort.dir === 'asc' ? (
                          <ChevronUp className="h-3.5 w-3.5 text-accent" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-accent" />
                        )
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 opacity-25" />
                      ))}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="py-14 text-center">
                  <Spinner className="mx-auto h-6 w-6" />
                </td>
              </tr>
            ) : pageRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState
                    title={emptyTitle}
                    description={emptyDescription}
                    className="border-0 shadow-none"
                  />
                </td>
              </tr>
            ) : (
              pageRows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    'border-b border-border transition-colors last:border-0',
                    onRowClick && 'cursor-pointer hover:bg-accent-subtle/40',
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'px-4 py-3 text-text-primary',
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
            Showing <span className="font-medium text-text-primary">{safePage * pageSize + 1}–{Math.min((safePage + 1) * pageSize, sorted.length)}</span> of{' '}
            <span className="font-medium text-text-primary">{sorted.length}</span>
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="flex h-8 items-center gap-1 rounded-btn border border-border-strong px-2.5 transition-colors hover:bg-bg-raised disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <ChevronLeft className="h-4 w-4" /> Prev
            </button>
            <span className="px-2 font-mono text-xs text-text-muted">
              {safePage + 1} / {pageCount}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              className="flex h-8 items-center gap-1 rounded-btn border border-border-strong px-2.5 transition-colors hover:bg-bg-raised disabled:opacity-40 disabled:hover:bg-transparent"
            >
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
