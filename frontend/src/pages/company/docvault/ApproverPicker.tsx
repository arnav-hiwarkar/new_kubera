import { useState, useMemo, useRef, useEffect } from 'react'
import { Search, UserCheck, Check, ChevronDown, X } from 'lucide-react'
import { useUsers } from '@/api/hooks/users'
import { Spinner } from '@/components/ui'
import { cn } from '@/lib/cn'
import type { BucketResponse } from '@/api/types'

export interface ApproverPickerProps {
  value?: string | null
  onChange: (userId: string | null) => void
  bucketId?: string | null
  buckets?: BucketResponse[]
  disabled?: boolean
  className?: string
}

export function ApproverPicker({
  value,
  onChange,
  bucketId,
  buckets = [],
  disabled = false,
  className,
}: ApproverPickerProps) {
  const { data: users = [], isLoading } = useUsers()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  // Focus input when opened
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus()
    }
  }, [open])

  // Target bucket (if any)
  const targetBucket = useMemo(
    () => (bucketId ? buckets.find((b) => b.id === bucketId) : null),
    [bucketId, buckets],
  )

  // Eligible approvers
  const eligibleUsers = useMemo(() => {
    return users.filter((u) => {
      if (u.deleted_at) return false
      // Must have docvault access
      const hasVaultAccess = u.role === 'admin' || u.accessible_modules?.includes('docvault')
      if (!hasVaultAccess) return false

      // If bucket is restricted, must have access to that bucket
      if (targetBucket && targetBucket.visibility === 'restricted') {
        if (u.role !== 'admin' && !targetBucket.access_user_ids?.includes(u.id)) {
          return false
        }
      }
      return true
    })
  }, [users, targetBucket])

  // Filtered by search query
  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return eligibleUsers
    return eligibleUsers.filter(
      (u) =>
        u.full_name?.toLowerCase().includes(q) ||
        u.email?.toLowerCase().includes(q) ||
        u.designation?.toLowerCase().includes(q) ||
        u.department?.toLowerCase().includes(q),
    )
  }, [eligibleUsers, search])

  const selectedUser = useMemo(
    () => users.find((u) => u.id === value) ?? null,
    [users, value],
  )

  const getInitials = (name?: string, email?: string) => {
    const src = name || email || '?'
    return src
      .split(' ')
      .map((n) => n[0])
      .slice(0, 2)
      .join('')
      .toUpperCase()
  }

  return (
    <div ref={dropdownRef} className={cn('relative w-full', className)}>
      {selectedUser ? (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-bg-surface p-2.5 transition-colors hover:border-accent/40">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-subtle font-medium text-xs text-accent">
              {getInitials(selectedUser.full_name, selectedUser.email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-sm font-medium text-text-primary">
                  {selectedUser.full_name || selectedUser.email}
                </span>
                {selectedUser.role === 'admin' && (
                  <span className="rounded bg-accent/10 px-1 py-0.2 text-[10px] font-semibold uppercase text-accent">
                    Admin
                  </span>
                )}
              </div>
              <p className="truncate text-xs text-text-muted">{selectedUser.email}</p>
            </div>
          </div>
          {!disabled && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setOpen(true)}
                className="rounded px-2 py-1 text-xs font-medium text-text-secondary hover:bg-bg-raised hover:text-text-primary"
              >
                Change
              </button>
              <button
                type="button"
                onClick={() => onChange(null)}
                aria-label="Remove approver"
                className="rounded p-1 text-text-muted hover:bg-bg-raised hover:text-danger"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => !disabled && setOpen(!open)}
          disabled={disabled}
          className={cn(
            'flex h-10 w-full items-center justify-between rounded-lg border border-border bg-bg-surface px-3 text-left text-sm transition-colors',
            'hover:border-accent/40 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        >
          <span className="flex items-center gap-2 text-text-muted">
            <UserCheck className="h-4 w-4 text-text-muted" />
            <span>Select an approver from your company…</span>
          </span>
          <ChevronDown className="h-4 w-4 text-text-muted" />
        </button>
      )}

      {open && (
        <div className="absolute z-50 mt-1 max-h-72 w-full overflow-hidden rounded-card border border-border bg-bg-surface shadow-popover animate-fade-in-up">
          {/* Search bar */}
          <div className="flex items-center border-b border-border px-3 py-2">
            <Search className="mr-2 h-4 w-4 shrink-0 text-text-muted" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, email, or department…"
              className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="rounded p-0.5 text-text-muted hover:text-text-primary"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* User list */}
          <div className="max-h-56 overflow-y-auto p-1">
            {isLoading ? (
              <div className="flex justify-center py-6">
                <Spinner />
              </div>
            ) : filteredUsers.length === 0 ? (
              <div className="p-4 text-center text-sm text-text-muted">
                {search ? 'No matching team members with DocVault access found.' : 'No eligible approvers found.'}
              </div>
            ) : (
              filteredUsers.map((user) => {
                const isSelected = user.id === value
                return (
                  <button
                    key={user.id}
                    type="button"
                    onClick={() => {
                      onChange(user.id)
                      setOpen(false)
                      setSearch('')
                    }}
                    className={cn(
                      'flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm transition-colors',
                      isSelected ? 'bg-accent-subtle/60 text-accent font-medium' : 'hover:bg-bg-raised text-text-primary',
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-subtle font-medium text-xs text-accent">
                        {getInitials(user.full_name, user.email)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate font-medium">{user.full_name || user.email}</span>
                          {user.role === 'admin' && (
                            <span className="rounded bg-accent/10 px-1 py-0.2 text-[9px] font-semibold uppercase text-accent">
                              Admin
                            </span>
                          )}
                          {user.department && (
                            <span className="rounded bg-bg-raised px-1 py-0.2 text-[10px] text-text-muted">
                              {user.department}
                            </span>
                          )}
                        </div>
                        <p className="truncate text-xs text-text-muted">{user.email}</p>
                      </div>
                    </div>
                    {isSelected && <Check className="h-4 w-4 shrink-0 text-accent" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
