import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Download, Upload } from 'lucide-react'
import { Button, Card, Field, Input, PageHeader, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { assetsApi } from '@/api/endpoints/assets'
import { saveBlob } from '@/lib/download'
import { useCreateExistingAsset, useImportAssets } from '@/api/hooks/assets'
import { useCategoryTree } from '@/api/hooks/assetMasters'
import { CategoryPicker } from './CategoryPicker'
import { LookupSelect } from './LookupSelect'

type Errors = Record<string, string>

/** Shape of one entry in the 422 detail array the import endpoint returns. */
interface ImportRowError {
  row: number | string
  message: string
}

const OPENING_FIELDS = ['opening_accumulated_depreciation', 'opening_wdv', 'opening_it_wdv'] as const

/** Opening entry: one asset the company owned before this register (or before
 *  the current year). Mirrors the backend's pre-FY validation so mistakes die
 *  here, not in a depreciation run months later. The server re-checks exactly;
 *  the April-1 heuristic here is only first-line UX. */
export function ExistingAssetPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const create = useCreateExistingAsset()
  const importAssets = useImportAssets()
  const { tree } = useCategoryTree()

  // Bulk entry: download the template, fill it, import it. A rejected file
  // reports its failing rows inline because the whole file is atomic.
  const importInputRef = useRef<HTMLInputElement>(null)
  const [importErrors, setImportErrors] = useState<ImportRowError[]>([])

  const downloadTemplate = async () => {
    try {
      saveBlob(await assetsApi.downloadImportTemplate(), 'asset_import_template.xlsx')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not download the template')
    }
  }

  const doImport = async (file: File) => {
    setImportErrors([])
    try {
      const res = await importAssets.mutateAsync(file)
      toast.success(`Imported ${res.created_count} assets`)
      if (res.first_asset_id) navigate(`/app/assets/${res.first_asset_id}`)
    } catch (e) {
      if (e instanceof ApiError && Array.isArray(e.detail)) {
        const rows = e.detail as ImportRowError[]
        setImportErrors(rows.slice(0, 20))
        toast.error(`${rows.length} rows failed — nothing was imported`)
      } else {
        toast.error(e instanceof Error ? e.message : 'Import failed')
      }
    }
  }

  const [values, setValues] = useState({
    asset_name: '', categoryId: '', original_cost: '', purchase_date: '',
    put_to_use_date: '', capitalization_date: '',
    opening_accumulated_depreciation: '', opening_wdv: '', opening_it_wdv: '',
    useful_life_months: '', useful_life_override_reason: '', residual_pct: '',
    custodian_name: '', serial_number: '', remarks: '', branch_id: '' as string | null,
  })
  const [errors, setErrors] = useState<Errors>({})
  const set = (k: keyof typeof values, v: string) => setValues((s) => ({ ...s, [k]: v }))

  const applyDefaultsAndPick = (categoryId: string) => {
    set('categoryId', categoryId)
    for (const g of tree) {
      const leaf =
        g.children.find((c) => c.id === categoryId) ??
        (g.parent.id === categoryId ? g.children[0] : undefined)
      if (leaf) {
        setValues((s) => ({
          ...s, categoryId,
          useful_life_months:
            s.useful_life_months || (leaf.default_useful_life_months ? String(leaf.default_useful_life_months) : ''),
          residual_pct:
            s.residual_pct || (leaf.default_residual_pct != null ? String(leaf.default_residual_pct) : ''),
        }))
        return
      }
    }
  }

  const picked = (() => {
    for (const g of tree) {
      if (g.parent.id === values.categoryId) return { path: [g.parent.name], leafName: g.parent.name }
      const c = g.children.find((x) => x.id === values.categoryId)
      if (c) return { path: [g.parent.name, c.name], leafName: c.name }
    }
    return null
  })()

  const isProbablyPreFY = (dateStr: string) => {
    const d = new Date(dateStr)
    if (Number.isNaN(d.getTime())) return false
    const now = new Date()
    const fyStartYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
    return d < new Date(fyStartYear, 3, 1) // India FY starts April 1
  }

  const validate = (): boolean => {
    const e: Errors = {}
    if (!values.asset_name.trim()) e.asset_name = 'Required'
    if (!values.categoryId) e.category_id = 'Required'
    const cost = Number(values.original_cost)
    if (!values.original_cost.trim() || Number.isNaN(cost) || cost <= 0) e.original_cost = 'Required, greater than 0'
    for (const k of OPENING_FIELDS) {
      const v = values[k].trim() === '' ? null : Number(values[k])
      if (v !== null && Number.isNaN(v)) e[k] = 'Must be a number'
      else if (v !== null && v < 0) e[k] = 'Cannot be negative'
      else if (v !== null && v > cost) e[k] = 'Cannot exceed original cost'
    }
    const effective = values.put_to_use_date || values.capitalization_date
    if (effective && isProbablyPreFY(effective)) {
      const missing = OPENING_FIELDS.filter((k) => values[k].trim() === '')
      if (missing.length) {
        e.opening =
          'Opening WDV (tax), WDV (books) and accumulated depreciation are all required for assets predating this financial year'
      }
    }
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const submit = async () => {
    if (!validate()) return
    try {
      const created = await create.mutateAsync({
        asset_name: values.asset_name.trim(),
        category_path: picked?.path ?? [],
        original_cost: values.original_cost,
        purchase_date: values.purchase_date || null,
        put_to_use_date: values.put_to_use_date || null,
        capitalization_date: values.capitalization_date || null,
        opening_accumulated_depreciation: values.opening_accumulated_depreciation || null,
        opening_wdv: values.opening_wdv || null,
        opening_it_wdv: values.opening_it_wdv || null,
        useful_life_months: values.useful_life_months ? Number(values.useful_life_months) : null,
        useful_life_override_reason: values.useful_life_override_reason || null,
        residual_pct: values.residual_pct || null,
        custodian_name: values.custodian_name || null,
        serial_number: values.serial_number || null,
        remarks: values.remarks || null,
        branch_id: values.branch_id || null,
      })
      toast.success('Draft asset created')
      navigate(`/app/assets/${created.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError && typeof err.detail === 'string' ? err.detail
        : err instanceof Error ? err.message : 'Could not create the asset')
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        eyebrow="OPERATIONS"
        title="Add existing asset"
        description="Record an asset the company already owned — with its opening book and tax values."
        actions={
          <>
            <Button variant="secondary" onClick={downloadTemplate}>
              <Download className="mr-1.5 h-4 w-4" />Download template
            </Button>
            <Button
              variant="secondary"
              onClick={() => importInputRef.current?.click()}
              loading={importAssets.isPending}
            >
              <Upload className="mr-1.5 h-4 w-4" />Import
            </Button>
            <input
              ref={importInputRef}
              type="file"
              accept=".xlsx,.csv"
              className="hidden"
              aria-label="Import file"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) doImport(file)
                e.target.value = ''
              }}
      />

      {importErrors.length > 0 && (
        <div className="rounded-card border border-status-action/40 bg-status-action/5 p-3">
          <p className="text-sm font-medium text-status-action">Nothing was imported</p>
          <ul className="mt-2 space-y-1 text-xs text-text-primary">
            {importErrors.map((e, i) => (
              <li key={i}>
                Row {e.row} — {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}
            <Button variant="ghost" onClick={() => navigate('/app/assets')}>
              <ArrowLeft className="mr-1.5 h-4 w-4" />Back</Button>
          </>
        }
      />

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
        <Field label="Asset name" required error={errors.asset_name}>
          <Input aria-label="Asset name" value={values.asset_name}
                 onChange={(e) => set('asset_name', e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <CategoryPicker value={values.categoryId} onChange={applyDefaultsAndPick}
                          error={errors.category_id} required />
        </div>
        <Field label="Serial number">
          <Input aria-label="Serial number" value={values.serial_number}
                 onChange={(e) => set('serial_number', e.target.value)} />
        </Field>
        <Field label="Custodian">
          <Input aria-label="Custodian" value={values.custodian_name}
                 onChange={(e) => set('custodian_name', e.target.value)} />
        </Field>
      </Card>

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
        <Field label="Original cost" required error={errors.original_cost}>
          <Input aria-label="Original cost" type="number" min={0} step="0.01"
                 value={values.original_cost}
                 onChange={(e) => set('original_cost', e.target.value)} />
        </Field>
        <Field label="Purchase date">
          <Input aria-label="Purchase date" type="date" value={values.purchase_date}
                 onChange={(e) => set('purchase_date', e.target.value)} />
        </Field>
        <Field label="Put-to-use date">
          <Input aria-label="Put-to-use date" type="date" value={values.put_to_use_date}
                 onChange={(e) => set('put_to_use_date', e.target.value)} />
        </Field>
        <Field label="Capitalization date">
          <Input aria-label="Capitalization date" type="date" value={values.capitalization_date}
                 onChange={(e) => set('capitalization_date', e.target.value)} />
        </Field>
      </Card>

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
        <Field label="Useful life (months)" hint="Pre-filled from the category default">
          <Input aria-label="Useful life (months)" type="number" min={1}
                 value={values.useful_life_months}
                 onChange={(e) => set('useful_life_months', e.target.value)} />
        </Field>
        <Field label="Residual %">
          <Input aria-label="Residual %" type="number" min={0} max={100} step="0.01"
                 value={values.residual_pct}
                 onChange={(e) => set('residual_pct', e.target.value)} />
        </Field>
        <Field label="Life override reason" className="sm:col-span-3"
               hint="Required when the life differs from Schedule II defaults">
          <Input aria-label="Life override reason" value={values.useful_life_override_reason}
                 onChange={(e) => set('useful_life_override_reason', e.target.value)} />
        </Field>
      </Card>

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
        <p className="text-xs text-text-muted sm:col-span-3">
          Opening balances as on the register cutover. All three are required when
          the asset predates the current financial year.
        </p>
        <Field label="Opening accumulated depreciation" error={errors.opening_accumulated_depreciation}>
          <Input aria-label="Opening accumulated depreciation" type="number" min={0} step="0.01"
                 value={values.opening_accumulated_depreciation}
                 onChange={(e) => set('opening_accumulated_depreciation', e.target.value)} />
        </Field>
        <Field label="Opening WDV (books)" error={errors.opening_wdv}>
          <Input aria-label="Opening WDV (books)" type="number" min={0} step="0.01"
                 value={values.opening_wdv}
                 onChange={(e) => set('opening_wdv', e.target.value)} />
        </Field>
        <Field label="Opening WDV (tax)" error={errors.opening_it_wdv}>
          <Input aria-label="Opening WDV (tax)" type="number" min={0} step="0.01"
                 value={values.opening_it_wdv}
                 onChange={(e) => set('opening_it_wdv', e.target.value)} />
        </Field>
        {errors.opening && (
          <p className="text-xs font-medium text-status-action sm:col-span-3">{errors.opening}</p>
        )}
      </Card>

      <Card className="p-4">
        <LookupSelect kind="branch" label="Branch" value={values.branch_id ?? ''}
                      onChange={(v) => set('branch_id', v || '')} />
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => navigate('/app/assets')}>Cancel</Button>
        <Button onClick={submit} loading={create.isPending}>Save draft</Button>
      </div>
    </div>
  )
}
