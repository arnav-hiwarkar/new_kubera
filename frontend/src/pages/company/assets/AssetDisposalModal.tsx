import { useState } from 'react'
import { Modal, Button, Field, Input, Select, useToast } from '@/components/ui'
import { assetsApi } from '@/api/endpoints/assets'
import { ApiError } from '@/api/http'
import { useQueryClient } from '@tanstack/react-query'

interface AssetDisposalModalProps {
  open: boolean
  onClose: () => void
  assetId: string
  assetName: string
  capitalizationDate?: string | null
}

const DISPOSAL_TYPES = [
  { value: 'sale', label: 'Sale' },
  { value: 'scrap', label: 'Scrapped' },
  { value: 'write_off', label: 'Written Off' },
  { value: 'loss_destruction', label: 'Loss / Destruction' },
  { value: 'insurance_claim', label: 'Insurance Claim' },
]

export function AssetDisposalModal({
  open,
  onClose,
  assetId,
  assetName,
  capitalizationDate,
}: AssetDisposalModalProps) {
  const [disposalDate, setDisposalDate] = useState(
    new Date().toISOString().split('T')[0],
  )
  const [disposalType, setDisposalType] = useState('sale')
  const [saleProceeds, setSaleProceeds] = useState('0')
  const [buyerName, setBuyerName] = useState('')
  const [invoiceNo, setInvoiceNo] = useState('')
  const [remarks, setRemarks] = useState('')
  const [loading, setLoading] = useState(false)

  const qc = useQueryClient()
  const toast = useToast()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await assetsApi.dispose(assetId, {
        disposal_date: disposalDate,
        disposal_type: disposalType,
        sale_proceeds: Number(saleProceeds) || 0,
        buyer_name: buyerName.trim() || undefined,
        disposal_invoice_no: invoiceNo.trim() || undefined,
        disposal_remarks: remarks.trim() || undefined,
      })
      toast.success(`Asset "${assetName}" marked as disposed`)
      qc.invalidateQueries({ queryKey: ['assets'] })
      qc.invalidateQueries({ queryKey: ['asset', assetId] })
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        toast.error(err.message || 'You do not have permission to dispose of assets.')
        onClose()
      } else {
        toast.error(err instanceof Error ? err.message : 'Failed to dispose asset')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Dispose Asset: ${assetName}`}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-sm text-text-secondary">
          Disposing of an asset removes it from active gross block and computes the gain or loss on disposal during the financial year depreciation run.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Disposal Date" required>
            <Input
              type="date"
              min={capitalizationDate || undefined}
              value={disposalDate}
              onChange={(e) => setDisposalDate(e.target.value)}
              required
            />
          </Field>
          <Field label="Disposal Type" required>
            <Select
              value={disposalType}
              onChange={(e) => setDisposalType(e.target.value)}
            >
              {DISPOSAL_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Sale Proceeds (₹)" required>
          <Input
            type="number"
            step="0.01"
            min="0"
            value={saleProceeds}
            onChange={(e) => setSaleProceeds(e.target.value)}
            required
          />
        </Field>

        {disposalType === 'sale' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Buyer Name">
              <Input
                placeholder="e.g. Acme Scrap Co"
                value={buyerName}
                onChange={(e) => setBuyerName(e.target.value)}
              />
            </Field>
            <Field label="Disposal Invoice / Bill No.">
              <Input
                placeholder="e.g. INV-DISP-001"
                value={invoiceNo}
                onChange={(e) => setInvoiceNo(e.target.value)}
              />
            </Field>
          </div>
        )}

        <Field label="Remarks">
          <Input
            placeholder="Reason for disposal, condition, etc."
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
          />
        </Field>

        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" loading={loading}>
            Confirm Disposal
          </Button>
        </div>
      </form>
    </Modal>
  )
}
