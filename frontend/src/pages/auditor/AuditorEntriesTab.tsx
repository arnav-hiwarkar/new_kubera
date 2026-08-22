import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus, Trash2, ScrollText, Search, X, ChevronDown, Check } from 'lucide-react'
import { Card, Button, Spinner, StatusBadge, EmptyState, useToast, Drawer, Field } from '@/components/ui'
import { useAuditorListEntries, useAuditorDeleteEntry, useAuditorCreateEntry, useAuditorTrialBalanceAccounts } from '@/api/hooks/auditorEngagements'
import type { TrialBalanceAccountResponse } from '@/api/types'
import { formatMoney } from '@/lib/format'

type EntryLineState = {
  ledger_id: string
  amount: number
}

type LedgerDisplayFormat = 'code' | 'name'

const LEDGER_DISPLAY_KEY = 'auditease:ledger-display-format'

function getInitialLedgerDisplayFormat(): LedgerDisplayFormat {
  try {
    const stored = localStorage.getItem(LEDGER_DISPLAY_KEY)
    if (stored === 'code' || stored === 'name') return stored
  } catch {
    /* ignore */
  }
  return 'name'
}

function ledgerLabel(acc: TrialBalanceAccountResponse, format: LedgerDisplayFormat): string {
  if (format === 'code' && acc.ledger_code) return acc.ledger_code
  return acc.ledger_name
}

function LedgerPicker({
  accounts,
  value,
  onChange,
  format,
}: {
  accounts: TrialBalanceAccountResponse[]
  value: string
  onChange: (ledgerId: string) => void
  format: LedgerDisplayFormat
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const selected = useMemo(() => accounts.find((a) => a.id === value) ?? null, [accounts, value])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return accounts
    return accounts.filter(
      (a) =>
        a.ledger_name.toLowerCase().includes(q) ||
        (a.ledger_code ?? '').toLowerCase().includes(q),
    )
  }, [accounts, query])

  useEffect(() => {
    setHighlighted(0)
  }, [query])

  useEffect(() => {
    if (!open) return
    const node = listRef.current?.children[highlighted] as HTMLElement | undefined
    node?.scrollIntoView({ block: 'nearest' })
  }, [highlighted, open])

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [open])

  const openPicker = () => {
    setOpen(true)
    setQuery('')
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const selectAccount = (acc: TrialBalanceAccountResponse) => {
    onChange(acc.id)
    setOpen(false)
    setQuery('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((h) => Math.min(h + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const acc = filtered[highlighted]
      if (acc) selectAccount(acc)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      setQuery('')
    }
  }

  if (open || !selected) {
    return (
      <div ref={containerRef} className="relative flex-1">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
          <input
            ref={inputRef}
            type="text"
            className="w-full rounded-md border border-border bg-bg-surface py-1 pl-7 pr-7 text-sm text-text-primary placeholder:text-text-muted focus:border-auditor focus:outline-none"
            placeholder={selected ? undefined : 'Search ledger by code or name...'}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setOpen(true)}
          />
          <button
            type="button"
            tabIndex={-1}
            onClick={() => {
              setOpen(false)
              setQuery('')
            }}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 text-text-muted hover:text-text-primary"
            aria-label="Close ledger search"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
        {open && (
          <ul
            ref={listRef}
            className="absolute z-30 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-border bg-bg-surface shadow-lg"
          >
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-sm text-text-muted italic">No ledgers match "{query}"</li>
            ) : (
              filtered.map((acc, i) => {
                const isSelected = acc.id === value
                return (
                  <li key={acc.id}>
                    <button
                      type="button"
                      onMouseEnter={() => setHighlighted(i)}
                      onClick={() => selectAccount(acc)}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm ${
                        i === highlighted ? 'bg-bg-raised' : ''
                      }`}
                    >
                      <span className="min-w-0 truncate text-text-primary">
                        {format === 'code' && acc.ledger_code ? (
                          <>
                            <span className="font-medium">{acc.ledger_code}</span>
                            <span className="ml-2 text-text-muted">{acc.ledger_name}</span>
                          </>
                        ) : (
                          <>
                            <span className="font-medium">{acc.ledger_name}</span>
                            {acc.ledger_code && <span className="ml-2 text-text-muted">{acc.ledger_code}</span>}
                          </>
                        )}
                      </span>
                      {isSelected && <Check className="h-3.5 w-3.5 shrink-0 text-auditor" />}
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-1 items-center gap-1 rounded-md border border-border bg-bg-surface px-2 py-1">
      <button
        type="button"
        onClick={openPicker}
        className="min-w-0 flex-1 truncate text-left text-sm text-text-primary hover:text-text-secondary"
        title={`${selected.ledger_code ? `${selected.ledger_code} — ` : ''}${selected.ledger_name} (click to change)`}
      >
        {ledgerLabel(selected, format)}
      </button>
      <button
        type="button"
        onClick={() => onChange('')}
        className="shrink-0 rounded p-0.5 text-text-muted hover:bg-bg-raised hover:text-status-action"
        aria-label="Clear selected ledger"
        title="Clear selection"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

function NewEntryDrawer({
  isOpen,
  onClose,
  engagementId,
}: {
  isOpen: boolean
  onClose: () => void
  engagementId: string
}) {
  const [code, setCode] = useState('')
  const [description, setDescription] = useState('')
  const [debitLines, setDebitLines] = useState<EntryLineState[]>([])
  const [creditLines, setCreditLines] = useState<EntryLineState[]>([])
  const [ledgerFormat, setLedgerFormat] = useState<LedgerDisplayFormat>(getInitialLedgerDisplayFormat)

  const { data: tbAccounts = [] } = useAuditorTrialBalanceAccounts(engagementId)
  const createEntry = useAuditorCreateEntry()
  const toast = useToast()

  const totalDebit = debitLines.reduce((acc, l) => acc + (l.amount || 0), 0)
  const totalCredit = creditLines.reduce((acc, l) => acc + (l.amount || 0), 0)

  const handleAddLine = (side: 'debit' | 'credit') => {
    if (side === 'debit') setDebitLines([...debitLines, { ledger_id: '', amount: 0 }])
    else setCreditLines([...creditLines, { ledger_id: '', amount: 0 }])
  }

  const handleRemoveLine = (side: 'debit' | 'credit', index: number) => {
    if (side === 'debit') setDebitLines(debitLines.filter((_, i) => i !== index))
    else setCreditLines(creditLines.filter((_, i) => i !== index))
  }

  const updateLine = (side: 'debit' | 'credit', index: number, field: keyof EntryLineState, val: string | number) => {
    const arr = side === 'debit' ? [...debitLines] : [...creditLines]
    arr[index] = { ...arr[index], [field]: val }
    if (side === 'debit') setDebitLines(arr)
    else setCreditLines(arr)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!description) return toast.error('Description is required')
    if (debitLines.length === 0 && creditLines.length === 0) return toast.error('Add at least one line')
    if (totalDebit !== totalCredit) return toast.error('Total Debits must equal Total Credits')

    const hasEmptyLedger = [...debitLines, ...creditLines].some((l) => !l.ledger_id)
    if (hasEmptyLedger) return toast.error('All lines must have a selected ledger')

    const hasZeroAmount = [...debitLines, ...creditLines].some((l) => l.amount <= 0)
    if (hasZeroAmount) return toast.error('Amounts must be greater than zero')

    try {
      const lines = [
        ...debitLines.map((l) => ({ ...l, side: 'debit' as const })),
        ...creditLines.map((l) => ({ ...l, side: 'credit' as const })),
      ]
      await createEntry.mutateAsync({
        engagementId,
        body: { code: code || null, description, lines },
      })
      toast.success('Adjusting entry proposed')
      setCode('')
      setDescription('')
      setDebitLines([])
      setCreditLines([])
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create entry')
    }
  }

  const handleSetLedgerFormat = (format: LedgerDisplayFormat) => {
    setLedgerFormat(format)
    try {
      localStorage.setItem(LEDGER_DISPLAY_KEY, format)
    } catch {
      /* ignore */
    }
  }

  const renderLine = (line: EntryLineState, index: number, side: 'debit' | 'credit') => (
    <div key={index} className="flex items-center gap-2 mb-2">
      <LedgerPicker
        accounts={tbAccounts}
        value={line.ledger_id}
        onChange={(ledgerId) => updateLine(side, index, 'ledger_id', ledgerId)}
        format={ledgerFormat}
      />
      <input
        type="number"
        min="0"
        step="0.01"
        className="w-32 rounded-md border border-border bg-bg-surface px-2 py-1 text-sm text-text-primary focus:border-auditor focus:outline-none"
        placeholder="Amount"
        value={line.amount || ''}
        onChange={(e) => updateLine(side, index, 'amount', parseFloat(e.target.value) || 0)}
        required
      />
      <button
        type="button"
        onClick={() => handleRemoveLine(side, index)}
        className="p-1 text-text-muted hover:text-status-action"
        aria-label="Remove line"
        title="Remove this line"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  )

  return (
    <Drawer open={isOpen} onClose={onClose} title="New Adjusting Entry">
      <form onSubmit={handleSubmit} className="flex h-full flex-col">
        <div className="flex-1 overflow-y-auto p-4">
          <Field label="Entry Code (Optional)">
            <input
              type="text"
              className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-auditor focus:outline-none"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="e.g. AJE-01"
            />
          </Field>
          <Field label="Description">
            <textarea
              className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-auditor focus:outline-none"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Reason for adjustment"
              rows={3}
              required
            />
          </Field>

          <div className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-text-muted">Show ledgers by</span>
              <div className="flex rounded-md border border-border p-0.5">
                {(['code', 'name'] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => handleSetLedgerFormat(f)}
                    className={`rounded px-2 py-0.5 text-xs capitalize transition-colors ${
                      ledgerFormat === f
                        ? 'bg-auditor-subtle text-auditor font-medium'
                        : 'text-text-muted hover:text-text-primary'
                    }`}
                  >
                    Ledger {f}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-semibold text-text-primary">Debit Lines</h4>
              <Button type="button" variant="secondary" size="sm" onClick={() => handleAddLine('debit')}>
                <Plus className="mr-1 h-3 w-3" /> Add Debit
              </Button>
            </div>
            {debitLines.map((l, i) => renderLine(l, i, 'debit'))}
            {debitLines.length === 0 && <p className="text-xs text-text-muted italic">No debit lines</p>}
            <div className="text-right text-sm mt-1 font-medium text-text-primary">
              Total Debit: {formatMoney(totalDebit)}
            </div>
          </div>

          <div className="mt-6">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-semibold text-text-primary">Credit Lines</h4>
              <Button type="button" variant="secondary" size="sm" onClick={() => handleAddLine('credit')}>
                <Plus className="mr-1 h-3 w-3" /> Add Credit
              </Button>
            </div>
            {creditLines.map((l, i) => renderLine(l, i, 'credit'))}
            {creditLines.length === 0 && <p className="text-xs text-text-muted italic">No credit lines</p>}
            <div className="text-right text-sm mt-1 font-medium text-text-primary">
              Total Credit: {formatMoney(totalCredit)}
            </div>
          </div>
        </div>

        <div className="border-t border-border p-4 bg-bg-raised flex justify-end gap-3">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={createEntry.isPending} disabled={totalDebit !== totalCredit || totalDebit === 0}>
            Submit Entry
          </Button>
        </div>
      </form>
    </Drawer>
  )
}

export function AuditorEntriesTab({ engagementId }: { engagementId: string }) {
  const { data: entries = [], isLoading } = useAuditorListEntries(engagementId)
  const deleteEntry = useAuditorDeleteEntry()
  const toast = useToast()
  const [drawerOpen, setDrawerOpen] = useState(false)

  const handleDelete = async (entryId: string) => {
    if (!confirm('Are you sure you want to delete this proposed entry?')) return
    try {
      await deleteEntry.mutateAsync(entryId)
      toast.success('Entry deleted')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete entry')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Adjusting Entries</h3>
          <p className="text-sm text-text-muted">Propose adjusting journal entries to the company.</p>
        </div>
        <Button onClick={() => setDrawerOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> New Entry
        </Button>
      </div>

      {isLoading ? (
        <Spinner className="mx-auto mt-8 h-6 w-6" />
      ) : entries.length === 0 ? (
        <EmptyState
          icon={<ScrollText />}
          title="No entries yet"
          description="You haven't proposed any adjusting entries for this engagement."
          action={<Button onClick={() => setDrawerOpen(true)}>Create First Entry</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {entries.map((entry) => {
            const totalDebit = entry.lines.filter((l) => l.side === 'debit').reduce((s, l) => s + l.amount, 0)
            const totalCredit = entry.lines.filter((l) => l.side === 'credit').reduce((s, l) => s + l.amount, 0)

            return (
              <Card key={entry.id} className="flex flex-col gap-4">
                <div className="flex items-start justify-between border-b border-border pb-3">
                  <div>
                    <h4 className="text-base font-semibold text-text-primary">
                      {entry.code ? `${entry.code} - ` : ''}{entry.description}
                    </h4>
                    <div className="mt-1 flex items-center gap-2">
                      <StatusBadge status={entry.status} />
                      <span className="text-xs text-text-muted">
                        Proposed on {new Date(entry.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  {entry.status === 'proposed' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-status-action hover:text-status-action"
                      onClick={() => handleDelete(entry.id)}
                      loading={deleteEntry.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-8">
                  <div>
                    <h5 className="mb-2 text-sm font-semibold text-text-secondary">Debits</h5>
                    <ul className="space-y-2">
                      {entry.lines
                        .filter((l) => l.side === 'debit')
                        .map((l) => (
                          <li key={l.id} className="flex justify-between text-sm">
                            <span className="text-text-primary">
                              {l.ledger_code ? `${l.ledger_code} — ${l.ledger_name}` : l.ledger_name}
                            </span>
                            <span className="font-mono text-text-secondary">{formatMoney(l.amount)}</span>
                          </li>
                        ))}
                    </ul>
                    <div className="mt-2 border-t border-border pt-1 flex justify-between text-sm font-medium">
                      <span>Total Debit</span>
                      <span className="font-mono">{formatMoney(totalDebit)}</span>
                    </div>
                  </div>
                  <div>
                    <h5 className="mb-2 text-sm font-semibold text-text-secondary">Credits</h5>
                    <ul className="space-y-2">
                      {entry.lines
                        .filter((l) => l.side === 'credit')
                        .map((l) => (
                          <li key={l.id} className="flex justify-between text-sm">
                            <span className="text-text-primary">
                              {l.ledger_code ? `${l.ledger_code} — ${l.ledger_name}` : l.ledger_name}
                            </span>
                            <span className="font-mono text-text-secondary">{formatMoney(l.amount)}</span>
                          </li>
                        ))}
                    </ul>
                    <div className="mt-2 border-t border-border pt-1 flex justify-between text-sm font-medium">
                      <span>Total Credit</span>
                      <span className="font-mono">{formatMoney(totalCredit)}</span>
                    </div>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <NewEntryDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        engagementId={engagementId}
      />
    </div>
  )
}
