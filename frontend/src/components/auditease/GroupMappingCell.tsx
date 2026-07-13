import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, Modal, Field, Input } from '@/components/ui'
import {
  useLedgerGroups,
  useMapLedger,
  useCreateLedgerGroup,
} from '@/api/hooks/auditease'

export function GroupMappingCell({
  accountId,
  currentGroupId,
}: {
  accountId: string
  currentGroupId: string | null
}) {
  const { engagementId = '' } = useParams()
  const { data: groups = [] } = useLedgerGroups()
  const mapLedger = useMapLedger()

  const [isCreating, setIsCreating] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const [parentGroupId, setParentGroupId] = useState('')

  const createGroup = useCreateLedgerGroup()

  // Flatten and format groups for the dropdown
  // We want to show the full path for each group that doesn't have children.
  // Wait, the hook returns LedgerGroupResponse: { id, parent_id, name, level, has_children }
  
  // Helper to build full path string for a group
  const getPath = (groupId: string): string => {
    const g = groups.find((x) => x.id === groupId)
    if (!g) return ''
    if (g.parent_id) {
      return `${getPath(g.parent_id)} › ${g.name}`
    }
    return g.name
  }

  const mappableGroups = groups
    .map((g) => ({
      id: g.id,
      path: getPath(g.id),
    }))
    .sort((a, b) => a.path.localeCompare(b.path))

  const parentOptions = groups
    .filter((g) => g.level < 2) // can only create children under level 0 or level 1
    .map((g) => ({
      id: g.id,
      path: getPath(g.id),
    }))
    .sort((a, b) => a.path.localeCompare(b.path))

  const handleSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    if (val === '__CREATE__') {
      setIsCreating(true)
      return
    }
    if (val && val !== currentGroupId) {
      mapLedger.mutate({ engagementId, ledgerId: accountId, groupId: val })
    }
  }

  const handleCreate = async () => {
    if (!newGroupName.trim() || !parentGroupId) return
    const res = await createGroup.mutateAsync({ name: newGroupName.trim(), parent_id: parentGroupId })
    mapLedger.mutate({ engagementId, ledgerId: accountId, groupId: res.id })
    setIsCreating(false)
    setNewGroupName('')
    setParentGroupId('')
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={currentGroupId || ''}
        onChange={handleSelect}
        className="w-full max-w-[250px] truncate rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none"
      >
        <option value="" disabled>
          -- Select Group --
        </option>
        {mappableGroups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.path}
          </option>
        ))}
        <option value="__CREATE__" className="font-semibold text-accent">
          + Create New Subgroup...
        </option>
      </select>

      <Modal
        open={isCreating}
        onClose={() => setIsCreating(false)}
        title="Create Subgroup"
        description="Add a custom subgroup for mapping ledgers."
      >
        <div className="flex flex-col gap-4">
          <Field label="Parent Group" required>
            <select
              value={parentGroupId}
              onChange={(e) => setParentGroupId(e.target.value)}
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none"
            >
              <option value="" disabled>
                -- Select Parent --
              </option>
              {parentOptions.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.path}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Subgroup Name" required>
            <Input
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              placeholder="e.g. Miscellaneous"
              autoFocus
            />
          </Field>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => setIsCreating(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              loading={createGroup.isPending || mapLedger.isPending}
              disabled={!newGroupName.trim() || !parentGroupId}
            >
              Create & Map
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
