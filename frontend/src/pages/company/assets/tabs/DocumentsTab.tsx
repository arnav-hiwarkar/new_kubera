import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import {
  Button,
  Card,
  EmptyState,
  Field,
  FileUploadDropzone,
  Select,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { ACQUISITION_DOC_ROLES, PHOTO_DOC_ROLES } from '@/api/endpoints/assets'
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess } from '@/auth/company/modules'
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
import {
  useAttachAssetDocument,
  useDetachAssetDocument,
  useUploadAssetDocument,
  type AssetDetail,
} from '@/api/hooks/assets'
import { ASSET_DOC_ROLE } from '@/api/enums'
import type { AssetDocRole } from '@/api/types'
import { formatBytes } from '@/lib/format'
import { AssetPhoto } from '../AssetPhoto'
import { DOC_ROLE_LABEL } from '../assetFormat'
import { SectionShell } from './SectionShell'

export function DocumentsTab({ detail }: { detail: AssetDetail }) {
  const asset = detail.asset
  const toast = useToast()
  const upload = useUploadAssetDocument()
  const detach = useDetachAssetDocument()
  const attach = useAttachAssetDocument()
  const { profile } = useCompanyAuth()
  const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
  const [showPicker, setShowPicker] = useState(false)

  const [role, setRole] = useState<AssetDocRole>('asset_photo')
  const [pending, setPending] = useState<File | null>(null)

  const isAcquisitionRole = ACQUISITION_DOC_ROLES.includes(role)

  const handleAttachExisting = async (documentIds: string[]) => {
    const documentId = documentIds[0]
    if (!documentId) return
    if (isAcquisitionRole && !asset.acquisition_id) {
      toast.error('This asset has no acquisition batch to attach shared paperwork to')
      return
    }
    try {
      await attach.mutateAsync({
        assetId: asset.id,
        body: { document_id: documentId, doc_role: role },
      })
      toast.success(`${DOC_ROLE_LABEL[role]} attached`)
    } catch (e) {
      toast.error(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : e instanceof Error
            ? e.message
            : 'Attach failed',
      )
    }
  }

  const handleUpload = async () => {
    if (!pending) return
    if (isAcquisitionRole && !asset.acquisition_id) {
      toast.error('This asset has no acquisition batch to attach shared paperwork to')
      return
    }
    const fd = new FormData()
    fd.append('file', pending)
    fd.append('doc_role', role)
    try {
      await upload.mutateAsync({
        assetId: isAcquisitionRole ? undefined : asset.id,
        acquisitionId: isAcquisitionRole ? (asset.acquisition_id ?? undefined) : undefined,
        formData: fd,
      })
      toast.success(`${DOC_ROLE_LABEL[role]} attached`)
      setPending(null)
    } catch (e) {
      toast.error(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : e instanceof Error
            ? e.message
            : 'Upload failed',
      )
    }
  }

  const handleDetach = async (linkId: string) => {
    try {
      await detach.mutateAsync(linkId)
      toast.success('Removed')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not remove the attachment')
    }
  }

  const photos = detail.documents.filter((d) => PHOTO_DOC_ROLES.includes(d.doc_role))
  const papers = detail.documents.filter((d) => !PHOTO_DOC_ROLES.includes(d.doc_role))

  return (
    <SectionShell dirty={false} saving={false} onSave={() => {}} onReset={() => {}}>
      <div>
        <h3 className="text-md font-semibold text-text-primary">Documents & photographs</h3>
        <p className="mt-0.5 text-sm text-text-muted">
          Invoice, purchase order, GRN, e-way bill and approvals belong to the whole
          batch and are shared by every unit. Photographs and certificates are per unit.
        </p>
      </div>

      <Card className="p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[220px_1fr]">
          <Field
            label="Attach as"
            hint={isAcquisitionRole ? 'Shared with all units in the batch' : 'This unit only'}
          >
            <Select
              value={role}
              aria-label="Attach as"
              onChange={(e) => setRole(e.target.value as AssetDocRole)}
            >
              {ASSET_DOC_ROLE.map((r) => (
                <option key={r} value={r}>
                  {DOC_ROLE_LABEL[r]}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex flex-col gap-2">
            <FileUploadDropzone
              onFilesSelected={(files) => setPending(files[0] ?? null)}
              hint={pending ? pending.name : 'PDF, image or document. Stored encrypted in DocVault.'}
            />
            {pending && (
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setPending(null)}>
                  Cancel
                </Button>
                <Button onClick={handleUpload} loading={upload.isPending}>
                  Upload
                </Button>
              </div>
            )}
            {canBrowseDocVault && (
              <div className="flex justify-end">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={isAcquisitionRole}
                  onClick={() => setShowPicker(true)}
                >
                  Attach from DocVault
                </Button>
              </div>
            )}
          </div>
        </div>
      </Card>

      <div>
        <h4 className="mb-2 text-sm font-semibold text-text-primary">
          Photographs {photos.length > 0 && <span className="text-text-muted">({photos.length})</span>}
        </h4>
        {photos.length === 0 ? (
          <p className="text-sm text-text-muted">
            No photographs yet. One asset photograph is required before the asset can be
            submitted for approval.
          </p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {photos.map((d) => (
              <div key={d.id} className="flex flex-col items-center gap-1">
                <AssetPhoto
                  linkId={d.id}
                  alt={d.original_filename ?? DOC_ROLE_LABEL[d.doc_role]}
                  mimeType={d.mime_type}
                />
                <span className="max-w-[96px] truncate text-xs text-text-muted">
                  {DOC_ROLE_LABEL[d.doc_role]}
                </span>
                <button
                  type="button"
                  className="text-xs text-status-action hover:underline"
                  onClick={() => handleDetach(d.id)}
                  aria-label={`Remove ${d.original_filename ?? 'photograph'}`}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h4 className="mb-2 text-sm font-semibold text-text-primary">Documents</h4>
        {papers.length === 0 ? (
          <EmptyState title="No documents" description="Attach the supplier invoice to get started." />
        ) : (
          <ul className="divide-y divide-border rounded-card border border-border">
            {papers.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text-primary">
                    {d.original_filename ?? d.title ?? 'Document'}
                  </p>
                  <p className="text-xs text-text-muted">
                    {DOC_ROLE_LABEL[d.doc_role]}
                    {d.acquisition_id ? ' · shared with the batch' : ''}
                    {d.size_bytes ? ` · ${formatBytes(d.size_bytes)}` : ''}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${d.original_filename ?? 'document'}`}
                  onClick={() => handleDetach(d.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showPicker && (
        <DocVaultPickerModal
          open={showPicker}
          multiple={false}
          selectedDocIds={[]}
          title="Select a document from DocVault"
          confirmLabel="Attach"
          onClose={() => setShowPicker(false)}
          onConfirm={(ids) => {
            setShowPicker(false)
            handleAttachExisting(ids)
          }}
        />
      )}
    </SectionShell>
  )
}
