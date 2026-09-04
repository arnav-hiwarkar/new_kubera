import { useState } from 'react'
import { Modal, Button, Field, Input, Select, useToast } from '@/components/ui'
import { assetsApi } from '@/api/endpoints/assets'
import type { AssetDisposalRequest } from '@/api/types'
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
  const [disposalType, setDisposalType] = useState<AssetDisposalRequest['disposal_type']>('sale')
  const [saleProceeds, setSaleProceeds] = useState('0')
  // Sale consideration for Income Tax. Left blank the server defaults it to the
  // book proceeds, which is right whenever the two agree — but when they differ
  // this is the only way to record the figure the IT block computation needs.
  const [itProceeds, setItProceeds] = useState('')
  const [buyerName, setBuyerName] = useState('')
  const [invoiceNo, setInvoiceNo] = useState('')
  const [remarks, setRemarks] = useState('')
  const [loading, setLoading] = useState(false)

  const qc = useQueryClient()
  const toast = useToast()

  // The two types `validate_disposal` requires proceeds for are the two where a
  // separate tax consideration is meaningful.
  const proceedsRelevant = disposalType === 'sale' || disposalType === 'insurance_claim'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await assetsApi.dispose(assetId, {
        disposal_date: disposalDate,
        disposal_type: disposalType,
        sale_proceeds: Number(saleProceeds) || 0,
        disposal_it_proceeds: itProceeds.trim() === '' ? undefined : Number(itProceeds),
        buyer_name: buyerName.trim() || undefined,
        disposal_invoice_no: invoiceNo.trim() || undefined,
        disposal_remarks: remarks.trim() || undefined,
      })
      toast.success(`Asset "${assetName}" marked as disposed`)
      qc.invalidateQueries({ queryKey: ['assets'] })
      qc.invalidateQueries({ queryKey: ['asset', assetId] })
      onClose()
    } catch (err) {
      // The server is the authority on who may dispose (KUB-020): only an admin.
      // Reaching a 403 here means the button was rendered from a stale profile —
      // a role changed mid-session, or a hand-crafted request. A 409 means the
      // asset is no longer capitalized, usually because someone else disposed
      // of it first. Neither can be fixed by resubmitting this form, so close it
      // and refresh instead of leaving a dead-end dialog open.
      if (err instanceof ApiError && (err.status === 403 || err.status === 409)) {
        toast.error(
          err.status === 403
            ? 'You do not have permission to dispose of assets. Ask a company admin.'
            : err.message || 'This asset is no longer on the books.',
        )
        qc.invalidateQueries({ queryKey: ['assets'] })
        qc.invalidateQueries({ queryKey: ['asset', assetId] })
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
          <Field label="Disposal Date" htmlFor="disposal-date" required>
            <Input
              id="disposal-date"
              type="date"
              min={capitalizationDate || undefined}
              value={disposalDate}
              onChange={(e) => setDisposalDate(e.target.value)}
              required
            />
          </Field>
          <Field label="Disposal Type" htmlFor="disposal-type" required>
            <Select
              id="disposal-type"
              value={disposalType}
              onChange={(e) =>
                setDisposalType(e.target.value as AssetDisposalRequest['disposal_type'])
              }
            >
              {DISPOSAL_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Sale Proceeds (₹)" htmlFor="sale-proceeds" required>
            <Input
              id="sale-proceeds"
              type="number"
              step="0.01"
              min="0"
              value={saleProceeds}
              onChange={(e) => setSaleProceeds(e.target.value)}
              required
            />
          </Field>
          {proceedsRelevant && (
            <Field
              label="Sale consideration for Income Tax (₹)"
              htmlFor="disposal-it-proceeds"
              hint="Only if it differs from the book proceeds. Blank uses the figure above."
            >
              <Input
                id="disposal-it-proceeds"
                type="number"
                step="0.01"
                min="0"
                placeholder="Same as book proceeds"
                value={itProceeds}
                onChange={(e) => setItProceeds(e.target.value)}
              />
            </Field>
          )}
        </div>

        {disposalType === 'sale' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Buyer Name" htmlFor="buyer-name">
              <Input
                id="buyer-name"
                placeholder="e.g. Acme Scrap Co"
                value={buyerName}
                onChange={(e) => setBuyerName(e.target.value)}
              />
            </Field>
            <Field label="Disposal Invoice / Bill No." htmlFor="disposal-invoice-no">
              <Input
                id="disposal-invoice-no"
                placeholder="e.g. INV-DISP-001"
                value={invoiceNo}
                onChange={(e) => setInvoiceNo(e.target.value)}
              />
            </Field>
          </div>
        )}

        <Field label="Remarks" htmlFor="disposal-remarks">
          <Input
            id="disposal-remarks"
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
