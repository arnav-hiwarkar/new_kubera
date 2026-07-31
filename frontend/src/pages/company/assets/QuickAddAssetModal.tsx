import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Field, Input, Modal, Select, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useQuickAddAsset } from '@/api/hooks/assets'
import { useSuppliers } from '@/api/hooks/assetMasters'
import { CategoryPicker } from './CategoryPicker'
import { LookupSelect } from './LookupSelect'
import { formatMoney } from '@/lib/format'

type FieldErrors = Record<string, string>

export interface QuickAddAssetModalProps {
  open: boolean
  onClose: () => void
}

/**
 * The whole create form: six fields.
 *
 * Everything else on the ~85-field register is enrichment and happens on the detail
 * page, because a user recording a delivery usually does not yet have the invoice,
 * the capitalization date or the photographs. Saving produces a DRAFT, which the
 * backend validates only for name + category, so nothing here can block on data
 * that does not exist yet.
 *
 * Quantity > 1 explodes into that many individually tagged assets sharing one
 * acquisition — which is what makes per-unit location and partial disposal possible.
 */
export function QuickAddAssetModal({ open, onClose }: QuickAddAssetModalProps) {
  const navigate = useNavigate()
  const toast = useToast()
  const quickAdd = useQuickAddAsset()
  const { data: suppliers = [] } = useSuppliers()

  const [assetName, setAssetName] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [unitPrice, setUnitPrice] = useState('')
  const [supplierId, setSupplierId] = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [branchId, setBranchId] = useState<string | null>(null)
  const [errors, setErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (!open) return
    setAssetName('')
    setCategoryId('')
    setQuantity('1')
    setUnitPrice('')
    setSupplierId('')
    setPurchaseDate('')
    setBranchId(null)
    setErrors({})
  }, [open])

  const qty = Number(quantity) || 0
  const price = Number(unitPrice) || 0
  const lineTotal = qty * price

  const validate = (): boolean => {
    const errs: FieldErrors = {}
    if (!assetName.trim()) errs.asset_name = 'Required'
    if (!categoryId) errs.category_id = 'Pick a category and subcategory'
    if (!Number.isInteger(qty) || qty < 1) errs.quantity = 'Must be a whole number, at least 1'
    if (qty > 2000) errs.quantity = 'Create at most 2000 units at a time'
    if (unitPrice.trim() !== '' && price < 0) errs.unit_basic_price = 'Cannot be negative'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    try {
      const created = await quickAdd.mutateAsync({
        asset_name: assetName.trim(),
        category_id: categoryId,
        quantity: qty,
        unit_basic_price: unitPrice.trim() === '' ? null : String(price),
        supplier_id: supplierId || null,
        purchase_date: purchaseDate || null,
        branch_id: branchId,
      })
      toast.success(
        created.quantity > 1
          ? `Created ${created.quantity} draft assets`
          : 'Draft asset created',
      )
      onClose()
      // Land on the detail page so enrichment is the obvious next step.
      navigate(`/app/assets/${created.first_asset_id}`)
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === 'string') {
        toast.error(e.detail)
        return
      }
      toast.error(e instanceof Error ? e.message : 'Could not create the asset')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New asset"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={quickAdd.isPending}>
            Create draft
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-muted">
          Just the essentials — you can add invoice, tax, depreciation and photographs
          afterwards. Nothing is posted to the books until the asset is approved.
        </p>

        <Field label="Asset name" required error={errors.asset_name}>
          <Input
            value={assetName}
            error={!!errors.asset_name}
            placeholder="e.g. Dell Latitude 5450"
            aria-label="Asset name"
            onChange={(e) => setAssetName(e.target.value)}
          />
        </Field>

        <CategoryPicker
          value={categoryId}
          onChange={setCategoryId}
          error={errors.category_id}
          required
        />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="Quantity"
            required
            error={errors.quantity}
            hint={qty > 1 ? `Creates ${qty} separately tagged assets` : 'One asset'}
          >
            <Input
              type="number"
              min={1}
              step={1}
              value={quantity}
              error={!!errors.quantity}
              aria-label="Quantity"
              onChange={(e) => setQuantity(e.target.value)}
            />
          </Field>

          <Field
            label="Basic price (per unit)"
            error={errors.unit_basic_price}
            hint={qty > 1 && price > 0 ? `Line total ₹${formatMoney(lineTotal)}` : 'Excluding GST'}
          >
            <Input
              type="number"
              min={0}
              step="0.01"
              value={unitPrice}
              error={!!errors.unit_basic_price}
              aria-label="Basic price (per unit)"
              onChange={(e) => setUnitPrice(e.target.value)}
            />
          </Field>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="Supplier"
            hint={suppliers.length === 0 ? 'No suppliers yet — add them under Asset masters.' : undefined}
          >
            <Select
              value={supplierId}
              aria-label="Supplier"
              onChange={(e) => setSupplierId(e.target.value)}
            >
              <option value="">Not set</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code} — {s.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Purchase / receipt date">
            <Input
              type="date"
              value={purchaseDate}
              aria-label="Purchase / receipt date"
              onChange={(e) => setPurchaseDate(e.target.value)}
            />
          </Field>
        </div>

        <LookupSelect
          kind="branch"
          label="Branch"
          value={branchId}
          onChange={setBranchId}
          hint="Decides the place of supply, so it sets CGST+SGST vs IGST."
        />
      </div>
    </Modal>
  )
}
