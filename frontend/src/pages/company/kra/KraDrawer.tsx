import { useEffect, useState } from 'react'
import { Drawer, Button, Field, Input, Textarea, Select, StatusBadge, useToast } from '@/components/ui'
import { useCreateKra, useUpdateKra } from '@/api/hooks/kra'
import { humanize } from '@/api/enums'
import type { KRAResponse } from '@/api/types'

type Me = { id: string; role: string }

interface KraDrawerProps {
  open: boolean
  onClose: () => void
  /** null → create mode; otherwise view/act on an existing KRA. */
  kra: KRAResponse | null
  me: Me
  /** Distinct existing cycle labels, for the create combobox. */
  cycles: string[]
  /** Display name of the KRA owner (for the view header). */
  ownerName?: string
}

const NEW_CYCLE = '__new__'

/** 1–5 rating selector. Stored as a plain number on the backend. */
function RatingSelect({
  value,
  onChange,
  disabled,
}: {
  value: number | null
  onChange: (v: number | null) => void
  disabled?: boolean
}) {
  return (
    <Select
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">Not rated</option>
      {[1, 2, 3, 4, 5].map((n) => (
        <option key={n} value={n}>
          {n} / 5
        </option>
      ))}
    </Select>
  )
}

/** Read-only labelled value used across the view sections. */
function ReadRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
      <span className="text-sm text-text-primary">{children}</span>
    </div>
  )
}

export function KraDrawer({ open, onClose, kra, me, cycles, ownerName }: KraDrawerProps) {
  const toast = useToast()
  const createKra = useCreateKra()
  const updateKra = useUpdateKra()

  // Plan fields (create + draft edit)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [weightage, setWeightage] = useState('0')
  const [targetMetric, setTargetMetric] = useState('')
  const [cycle, setCycle] = useState('')
  const [cycleMode, setCycleMode] = useState<'existing' | 'new'>('existing')
  // Progress / appraisal fields
  const [selfRating, setSelfRating] = useState<number | null>(null)
  const [selfComment, setSelfComment] = useState('')
  const [managerRating, setManagerRating] = useState<number | null>(null)
  const [managerComment, setManagerComment] = useState('')
  const [rejectionReason, setRejectionReason] = useState('')

  // Sync local state whenever the target KRA (or create mode) changes.
  useEffect(() => {
    if (!open) return
    setTitle(kra?.title ?? '')
    setDescription(kra?.description ?? '')
    setWeightage(kra ? String(kra.weightage) : '0')
    setTargetMetric(kra?.target_metric ?? '')
    setCycle(kra?.cycle ?? '')
    setCycleMode(kra ? 'existing' : cycles.length ? 'existing' : 'new')
    setSelfRating(kra?.employee_self_rating ?? null)
    setSelfComment(kra?.employee_comment ?? '')
    setManagerRating(kra?.manager_rating ?? null)
    setManagerComment(kra?.manager_comment ?? '')
    setRejectionReason('')
  }, [open, kra, cycles.length])

  const isCreate = !kra
  const isOwner = !!kra && kra.user_id === me.id
  const canManage = !!kra && (kra.manager_id === me.id || me.role === 'admin')
  const status = kra?.status
  // We collapse "approved" into the same tracking phase as "in_progress" (the
  // manager's approval moves the plan straight into progress).
  const inProgress = status === 'approved' || status === 'in_progress'

  const busy = createKra.isPending || updateKra.isPending

  const planBody = () => ({
    title: title.trim(),
    description: description.trim(),
    weightage: Number(weightage) || 0,
    target_metric: targetMetric.trim() || null,
    cycle: cycle.trim(),
  })

  const handleCreate = async () => {
    if (!title.trim() || !description.trim() || !cycle.trim()) {
      return toast.error('Title, description and cycle are required')
    }
    try {
      await createKra.mutateAsync(planBody())
      toast.success('KRA created as draft')
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to create KRA')
    }
  }

  const patch = async (body: Parameters<typeof updateKra.mutateAsync>[0]['body'], msg: string) => {
    if (!kra) return
    try {
      await updateKra.mutateAsync({ id: kra.id, body })
      toast.success(msg)
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Action failed')
    }
  }

  const submitForApproval = () => {
    if (!title.trim() || !description.trim() || !cycle.trim()) {
      return toast.error('Title, description and cycle are required')
    }
    return patch({ ...planBody(), status: 'pending_approval' }, 'Submitted for approval')
  }
  const saveDraft = () => patch(planBody(), 'Draft saved')
  const approve = () => patch({ status: 'in_progress' }, 'Plan approved')
  const rejectPlan = () => {
    if (!rejectionReason.trim()) return toast.error('A rejection reason is required')
    return patch({ status: 'rejected', rejection_reason: rejectionReason.trim() }, 'KRA rejected')
  }
  const submitReview = () => {
    if (selfRating == null) return toast.error('Provide your self-rating before submitting')
    return patch(
      { status: 'review_submitted', employee_self_rating: selfRating, employee_comment: selfComment.trim() || null },
      'Submitted for review',
    )
  }
  const complete = () => {
    if (managerRating == null) return toast.error('Provide a manager rating before completing')
    return patch(
      { status: 'completed', manager_rating: managerRating, manager_comment: managerComment.trim() || null },
      'KRA completed',
    )
  }
  const rejectReview = () => {
    if (!rejectionReason.trim()) return toast.error('A rejection reason is required')
    return patch({ status: 'rejected', rejection_reason: rejectionReason.trim() }, 'KRA rejected')
  }

  // --- Footer actions per stage/role ---
  const footer = (() => {
    if (isCreate) {
      return (
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCreate} loading={busy}>Create draft</Button>
        </>
      )
    }
    if (status === 'draft' && (isOwner || me.role === 'admin')) {
      return (
        <>
          <Button variant="secondary" onClick={saveDraft} loading={busy}>Save draft</Button>
          <Button onClick={submitForApproval} loading={busy}>Submit for approval</Button>
        </>
      )
    }
    if (status === 'pending_approval' && canManage) {
      return (
        <>
          <Button variant="secondary" onClick={rejectPlan} loading={busy}>Reject</Button>
          <Button onClick={approve} loading={busy}>Approve</Button>
        </>
      )
    }
    if (inProgress && (isOwner || me.role === 'admin')) {
      return (
        <>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button onClick={submitReview} loading={busy}>Submit for review</Button>
        </>
      )
    }
    if (status === 'review_submitted' && canManage) {
      return (
        <>
          <Button variant="secondary" onClick={rejectReview} loading={busy}>Reject</Button>
          <Button onClick={complete} loading={busy}>Complete</Button>
        </>
      )
    }
    return <Button variant="ghost" onClick={onClose}>Close</Button>
  })()

  // --- Editable regions ---
  const editingPlan = isCreate || (status === 'draft' && (isOwner || me.role === 'admin'))
  const editingSelf = inProgress && (isOwner || me.role === 'admin')
  const editingManager = status === 'review_submitted' && canManage
  const collectingRejection =
    (status === 'pending_approval' || status === 'review_submitted') && canManage

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={isCreate ? 'New KRA' : kra?.title}
      subtitle={
        isCreate ? (
          'Define a key result area for a review cycle'
        ) : (
          <span className="flex items-center gap-2">
            <StatusBadge status={kra!.status} />
            <span>{kra!.cycle}</span>
            {ownerName && <span className="text-text-muted">· {ownerName}</span>}
          </span>
        )
      }
      footer={footer}
    >
      <div className="flex flex-col gap-4">
        {editingPlan ? (
          <>
            <Field label="Title" required>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Grow regional revenue" />
            </Field>
            <Field label="Description" required>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What does success look like?"
                rows={3}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Weightage" hint="Relative importance">
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={weightage}
                  onChange={(e) => setWeightage(e.target.value)}
                />
              </Field>
              <Field label="Target metric" hint="Optional">
                <Input
                  value={targetMetric}
                  onChange={(e) => setTargetMetric(e.target.value)}
                  placeholder="e.g. ₹2 Cr"
                />
              </Field>
            </div>
            <Field label="Cycle" required hint="e.g. FY25-Q1">
              {cycleMode === 'existing' && cycles.length > 0 ? (
                <Select
                  value={cycles.includes(cycle) ? cycle : ''}
                  onChange={(e) => {
                    if (e.target.value === NEW_CYCLE) {
                      setCycle('')
                      setCycleMode('new')
                    } else {
                      setCycle(e.target.value)
                    }
                  }}
                >
                  <option value="" disabled>
                    Select a cycle…
                  </option>
                  {cycles.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                  <option value={NEW_CYCLE}>+ New cycle…</option>
                </Select>
              ) : (
                <Input
                  value={cycle}
                  onChange={(e) => setCycle(e.target.value)}
                  placeholder="FY25-Q1"
                  autoFocus={cycleMode === 'new'}
                />
              )}
            </Field>
          </>
        ) : (
          <>
            <ReadRow label="Description">{kra!.description}</ReadRow>
            <div className="grid grid-cols-2 gap-3">
              <ReadRow label="Weightage">{kra!.weightage}</ReadRow>
              <ReadRow label="Target metric">{kra!.target_metric || '—'}</ReadRow>
            </div>
          </>
        )}

        {/* Employee self-assessment */}
        {(editingSelf || (kra && (kra.employee_self_rating != null || kra.employee_comment))) && (
          <div className="rounded-card border border-border p-3">
            <h4 className="mb-2 text-sm font-semibold text-text-primary">Self-assessment</h4>
            {editingSelf ? (
              <div className="flex flex-col gap-3">
                <Field label="Your rating" required>
                  <RatingSelect value={selfRating} onChange={setSelfRating} />
                </Field>
                <Field label="Your comment">
                  <Textarea value={selfComment} onChange={(e) => setSelfComment(e.target.value)} rows={2} />
                </Field>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <ReadRow label="Rating">
                  {kra!.employee_self_rating != null ? `${kra!.employee_self_rating} / 5` : '—'}
                </ReadRow>
                {kra!.employee_comment && <ReadRow label="Comment">{kra!.employee_comment}</ReadRow>}
              </div>
            )}
          </div>
        )}

        {/* Manager appraisal */}
        {(editingManager || (kra && (kra.manager_rating != null || kra.manager_comment))) && (
          <div className="rounded-card border border-border p-3">
            <h4 className="mb-2 text-sm font-semibold text-text-primary">Manager appraisal</h4>
            {editingManager ? (
              <div className="flex flex-col gap-3">
                <Field label="Manager rating" required>
                  <RatingSelect value={managerRating} onChange={setManagerRating} />
                </Field>
                <Field label="Manager comment">
                  <Textarea value={managerComment} onChange={(e) => setManagerComment(e.target.value)} rows={2} />
                </Field>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <ReadRow label="Rating">
                  {kra!.manager_rating != null ? `${kra!.manager_rating} / 5` : '—'}
                </ReadRow>
                {kra!.manager_comment && <ReadRow label="Comment">{kra!.manager_comment}</ReadRow>}
              </div>
            )}
          </div>
        )}

        {/* Rejection reason: collected on reject, or shown once rejected */}
        {collectingRejection && (
          <Field label="Rejection reason" hint="Required only if you reject">
            <Textarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              rows={2}
              placeholder="Explain what needs to change"
            />
          </Field>
        )}
        {status === 'rejected' && kra!.rejection_reason && (
          <div className="rounded-card border border-status-action/40 bg-status-action-bg/40 p-3">
            <h4 className="mb-1 text-sm font-semibold text-status-action">
              {humanize('rejected')}
            </h4>
            <p className="text-sm text-text-primary">{kra!.rejection_reason}</p>
          </div>
        )}
      </div>
    </Drawer>
  )
}
