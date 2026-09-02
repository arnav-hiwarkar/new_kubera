import { useState } from 'react'
import { Plus, Calendar, Lock, Unlock } from 'lucide-react'
import { Button, Field, Input, Modal, Spinner, useToast, EmptyState } from '@/components/ui'
import {
  useFinancialYears,
  useCreateFinancialYear,
  useCloseFinancialYear,
  useReopenFinancialYear,
} from '@/api/hooks/financialYears'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/cn'
import { useCompanyAuth } from '@/auth/company'

export function FinancialYearsTab() {
  const { profile } = useCompanyAuth()
  const isAdmin = profile?.role === 'admin'

  const { data: fys, isLoading } = useFinancialYears()
  const createFY = useCreateFinancialYear()
  const closeFY = useCloseFinancialYear()
  const reopenFY = useReopenFinancialYear()
  const toast = useToast()

  const [modalOpen, setModalOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [startDate, setStartDate] = useState('2024-04-01')
  const [endDate, setEndDate] = useState('2025-03-31')

  const [reopenModalOpen, setReopenModalOpen] = useState(false)
  const [selectedFyForReopen, setSelectedFyForReopen] = useState<{ id: string; label: string } | null>(null)
  const [reopenReason, setReopenReason] = useState('')

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!label.trim()) return
    try {
      await createFY.mutateAsync({
        label: label.trim(),
        start_date: startDate,
        end_date: endDate,
      })
      toast.success(`Created financial year ${label}`)
      setModalOpen(false)
      setLabel('')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create financial year')
    }
  }

  const handleToggleStatus = async (fy: { id: string; label: string; status: 'open' | 'closed' }) => {
    if (!isAdmin) {
      toast.error('Only administrators can close or reopen financial years')
      return
    }
    if (fy.status === 'open') {
      try {
        await closeFY.mutateAsync(fy.id)
        toast.success(`Closed financial year ${fy.label}`)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to close financial year')
      }
    } else {
      setSelectedFyForReopen(fy)
      setReopenReason('')
      setReopenModalOpen(true)
    }
  }

  const handleReopenSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isAdmin) {
      toast.error('Only administrators can close or reopen financial years')
      return
    }
    if (!selectedFyForReopen) return
    const trimmed = reopenReason.trim()
    if (trimmed.length < 10) {
      toast.error('Reason must be at least 10 characters long')
      return
    }
    try {
      await reopenFY.mutateAsync({ id: selectedFyForReopen.id, reason: trimmed })
      toast.success(`Reopened financial year ${selectedFyForReopen.label}`)
      setReopenModalOpen(false)
      setSelectedFyForReopen(null)
      setReopenReason('')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to reopen financial year')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-text-primary">Financial Years</h3>
          <p className="text-sm text-text-muted">
            Manage accounting periods for Companies Act and Income Tax depreciation schedules.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => setModalOpen(true)} size="sm">
            <Plus className="mr-1.5 h-4 w-4" />
            Add Financial Year
          </Button>
        )}
      </div>

      {isLoading ? (
        <Spinner className="mx-auto mt-8 h-6 w-6" />
      ) : !fys || fys.length === 0 ? (
        <EmptyState
          title="No financial years created"
          description="Add your first financial year (e.g. 2024-25 from 01/04/2024 to 31/03/2025)."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-bg-surface shadow-xs">
          <table className="w-full text-left text-sm text-text-secondary">
            <thead className="bg-bg-inset text-xs font-medium uppercase tracking-wider text-text-muted">
              <tr>
                <th className="px-4 py-3">Financial Year</th>
                <th className="px-4 py-3">Period</th>
                <th className="px-4 py-3">Status</th>
                {isAdmin && <th className="px-4 py-3 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {fys.map((fy) => (
                <tr key={fy.id} className="hover:bg-bg-inset/30">
                  <td className="px-4 py-3 font-medium text-text-primary">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4 text-accent" />
                      <span>{fy.label}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {formatDate(fy.start_date)} &mdash; {formatDate(fy.end_date)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold',
                        fy.status === 'open'
                          ? 'bg-status-verified/10 text-status-verified'
                          : 'bg-status-rejected/10 text-status-rejected',
                      )}
                    >
                      {fy.status === 'open' ? 'Open' : 'Closed'}
                    </span>
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleStatus(fy)}
                        loading={closeFY.isPending || reopenFY.isPending}
                      >
                        {fy.status === 'open' ? (
                          <>
                            <Lock className="mr-1 h-3.5 w-3.5" />
                            Close
                          </>
                        ) : (
                          <>
                            <Unlock className="mr-1 h-3.5 w-3.5" />
                            Reopen
                          </>
                        )}
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add FY Modal */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Add Financial Year">
        <form onSubmit={handleCreate} className="flex flex-col gap-4">
          <Field label="Label" required>
            <Input
              placeholder="e.g. 2024-25 or FY 2024-25"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              required
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Start Date" required>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
            </Field>
            <Field label="End Date" required>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                required
              />
            </Field>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={createFY.isPending}>
              Create
            </Button>
          </div>
        </form>
      </Modal>

      {/* Reopen FY Modal */}
      <Modal
        open={reopenModalOpen}
        onClose={() => {
          setReopenModalOpen(false)
          setSelectedFyForReopen(null)
          setReopenReason('')
        }}
        title={`Reopen Financial Year ${selectedFyForReopen?.label || ''}`}
      >
        <form onSubmit={handleReopenSubmit} className="flex flex-col gap-4">
          <p className="text-xs text-text-muted">
            Reopening a closed statutory period is a privileged operation. Please provide an audit justification (minimum 10 characters).
          </p>
          <Field label="Audit Reason" required>
            <Input
              placeholder="e.g. Correcting depreciation schedule per auditor request"
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              required
            />
          </Field>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setReopenModalOpen(false)
                setSelectedFyForReopen(null)
                setReopenReason('')
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={reopenFY.isPending}
              disabled={reopenReason.trim().length < 10}
            >
              Confirm Reopen
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
