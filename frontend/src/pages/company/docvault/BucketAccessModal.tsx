import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Modal, Button, Switch, Spinner, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { usersApi } from '@/api/endpoints/users'
import { useUpdateBucketAccess } from '@/api/hooks/docvault'
import type { BucketResponse, BucketVisibility } from '@/api/types'

export interface BucketAccessModalProps {
  bucket: BucketResponse | null
  open: boolean
  onClose: () => void
}

export function BucketAccessModal({ bucket, open, onClose }: BucketAccessModalProps) {
  const toast = useToast()
  const updateAccess = useUpdateBucketAccess()

  const [visibility, setVisibility] = useState<BucketVisibility>('everyone')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  // Only need the user list when the picker is open and restricting.
  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
    enabled: open,
  })

  // Non-admins are the only ones who can be gated. Admins always have full
  // access, deleted users can't be granted anything, and users without DocVault
  // module access can't open DocVault at all — so granting them a bucket is moot.
  const selectableUsers = useMemo(
    () =>
      users.filter(
        (u) => u.role !== 'admin' && !u.deleted_at && u.accessible_modules?.includes('docvault'),
      ),
    [users],
  )

  useEffect(() => {
    if (bucket) {
      setVisibility(bucket.visibility)
      setSelected(new Set(bucket.access_user_ids))
    }
  }, [bucket, open])

  if (!bucket) return null

  const toggleUser = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const handleSave = async () => {
    try {
      await updateAccess.mutateAsync({
        id: bucket.id,
        body: {
          visibility,
          user_ids: visibility === 'restricted' ? Array.from(selected) : [],
        },
      })
      toast.success('Bucket access updated')
      onClose()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not update access')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Access · ${bucket.name}`}>
      <div className="space-y-5">
        <p className="text-sm text-text-secondary">
          Choose who can see this bucket and its documents. Company admins always have
          access.
        </p>

        <div className="flex flex-col gap-3">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="radio"
              name="visibility"
              className="mt-1 accent-accent"
              checked={visibility === 'everyone'}
              onChange={() => setVisibility('everyone')}
            />
            <span>
              <span className="block text-sm font-medium text-text-primary">
                Everyone with DocVault access
              </span>
              <span className="block text-xs text-text-muted">
                Any user who can open DocVault can see this bucket.
              </span>
            </span>
          </label>

          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="radio"
              name="visibility"
              className="mt-1 accent-accent"
              checked={visibility === 'restricted'}
              onChange={() => setVisibility('restricted')}
            />
            <span>
              <span className="block text-sm font-medium text-text-primary">
                Specific users
              </span>
              <span className="block text-xs text-text-muted">
                Only the users you pick below can see this bucket and its files.
              </span>
            </span>
          </label>
        </div>

        {visibility === 'restricted' && (
          <div className="rounded-card border border-border p-3">
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
              Users with access
            </h4>
            {usersLoading ? (
              <div className="flex justify-center py-4">
                <Spinner />
              </div>
            ) : selectableUsers.length === 0 ? (
              <p className="py-2 text-sm text-text-muted">
                No non-admin users to grant access to.
              </p>
            ) : (
              <div className="flex max-h-64 flex-col gap-3 overflow-y-auto">
                {selectableUsers.map((u) => (
                  <Switch
                    key={u.id}
                    checked={selected.has(u.id)}
                    onChange={() => toggleUser(u.id)}
                    label={`${u.full_name} · ${u.email}`}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-3 border-t border-border pt-4">
          <Button variant="ghost" type="button" onClick={onClose} disabled={updateAccess.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSave} loading={updateAccess.isPending}>
            Save access
          </Button>
        </div>
      </div>
    </Modal>
  )
}
