import { useQuery } from '@tanstack/react-query'
import { Field, Input, Select, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useUpdateAsset, type AssetDetail } from '@/api/hooks/assets'
import { usersApi } from '@/api/endpoints/users'
import { ASSET_CONDITION, ASSET_OPERATIONAL_STATUS, humanize } from '@/api/enums'
import type { AssetUpdate } from '@/api/types'
import { LookupSelect } from '../LookupSelect'
import { useSectionForm } from '../useSectionForm'
import { SectionShell } from './SectionShell'

export function AssignmentTab({ detail }: { detail: AssetDetail }) {
  const asset = detail.asset
  const toast = useToast()
  const update = useUpdateAsset()

  // Listing users is admin-only; a non-admin simply gets the free-text custodian
  // path instead of a dropdown, which is also the path used for staff with no login.
  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
  const users = usersQuery.data ?? []

  const form = useSectionForm(
    {
      branch_id: asset.branch_id,
      cost_centre_id: asset.cost_centre_id,
      department_id: asset.department_id,
      location_id: asset.location_id,
      custodian_id: asset.custodian_id,
      custodian_name: asset.custodian_name ?? '',
      custodian_employee_code: asset.custodian_employee_code ?? '',
      operational_status: asset.operational_status,
      condition: asset.condition,
    },
    async (patch) => {
      try {
        await update.mutateAsync({ id: asset.id, body: patch as AssetUpdate })
        toast.success('Saved')
      } catch (e) {
        toast.error(
          e instanceof ApiError && typeof e.detail === 'string'
            ? e.detail
            : e instanceof Error
              ? e.message
              : 'Save failed',
        )
      }
    },
  )
  const { values, set } = form

  return (
    <SectionShell
      title="Assignment & location"
      description="Where the asset sits and who is responsible for it. These stay editable after capitalization — a transfer is not a cost change."
      dirty={form.dirty}
      saving={form.saving}
      onSave={form.save}
      onReset={form.reset}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <LookupSelect kind="branch" label="Branch" value={values.branch_id} onChange={(v) => set('branch_id', v)} required />
        <LookupSelect
          kind="cost_centre"
          label="Cost centre"
          value={values.cost_centre_id}
          onChange={(v) => set('cost_centre_id', v)}
          required
        />
        <LookupSelect
          kind="department"
          label="Department"
          value={values.department_id}
          onChange={(v) => set('department_id', v)}
          required
        />
        <LookupSelect
          kind="location"
          label="Location"
          value={values.location_id}
          onChange={(v) => set('location_id', v)}
          required
        />
      </div>

      <fieldset className="rounded-card border border-border p-4">
        <legend className="px-1 text-sm font-medium text-text-secondary">Custodian</legend>
        <p className="mb-3 text-xs text-text-muted">
          Pick a user, or type a name for someone without a login (drivers, operators,
          security staff). One of the two is required.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="User">
            <Select
              value={values.custodian_id ?? ''}
              disabled={usersQuery.isError}
              aria-label="Custodian user"
              onChange={(e) => set('custodian_id', e.target.value || null)}
            >
              <option value="">Not a system user</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Custodian name">
            <Input
              value={values.custodian_name}
              aria-label="Custodian name"
              onChange={(e) => set('custodian_name', e.target.value)}
            />
          </Field>
          <Field label="Employee code">
            <Input
              value={values.custodian_employee_code}
              aria-label="Employee code"
              onChange={(e) => set('custodian_employee_code', e.target.value)}
            />
          </Field>
        </div>
      </fieldset>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Asset status" required hint="How the asset is being used right now">
          <Select
            value={values.operational_status ?? ''}
            aria-label="Asset status"
            onChange={(e) =>
              set('operational_status', (e.target.value || null) as typeof values.operational_status)
            }
          >
            <option value="">Not set</option>
            {ASSET_OPERATIONAL_STATUS.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Condition" required>
          <Select
            value={values.condition ?? ''}
            aria-label="Condition"
            onChange={(e) => set('condition', (e.target.value || null) as typeof values.condition)}
          >
            <option value="">Not set</option>
            {ASSET_CONDITION.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </Select>
        </Field>
      </div>
    </SectionShell>
  )
}
