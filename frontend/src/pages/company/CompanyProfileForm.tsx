import { useEffect, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { Button, Field, Input, useToast } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import type { CompanyProfile, CompanyProfileUpdate } from '@/api/endpoints/companyProfile'
import { companyProfileApi } from '@/api/endpoints/companyProfile'
import { useUpdateCompanyProfile, useUploadLogo } from '@/api/hooks/companyProfile'

// Client-side mirrors of the backend format validators.
const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/
const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$/
const CIN_RE = /^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$/
const PINCODE_RE = /^[0-9]{6}$/

type FieldKey = keyof CompanyProfileUpdate

const TEXT_FIELDS: FieldKey[] = [
  'legal_name', 'cin', 'pan', 'gstin', 'tan',
  'address_line1', 'address_line2', 'city', 'state', 'pincode',
  'contact_email', 'contact_phone', 'date_of_incorporation', 'website', 'industry',
]

function emptyToNull(v: string): string | null {
  const t = v.trim()
  return t === '' ? null : t
}

export function CompanyProfileForm({
  profile,
  mode,
  onSaved,
}: {
  profile: CompanyProfile
  mode: 'onboarding' | 'settings'
  onSaved?: (updated: CompanyProfile) => void
}) {
  const toast = useToast()
  const { profile: user } = useCompanyAuth()
  const canEdit = user?.role === 'admin'

  const update = useUpdateCompanyProfile()
  const uploadLogo = useUploadLogo()

  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(TEXT_FIELDS.map((k) => [k, (profile[k as keyof CompanyProfile] as string) ?? ''])),
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  // Load the current logo (authenticated fetch -> object URL).
  useEffect(() => {
    let revoked: string | null = null
    if (profile.has_logo) {
      companyProfileApi
        .getLogoBlob()
        .then((blob) => {
          const url = URL.createObjectURL(blob)
          revoked = url
          setLogoUrl(url)
        })
        .catch(() => setLogoUrl(null))
    }
    return () => {
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [profile.has_logo])

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  // Everything is optional. We only sanity-check the format of values the
  // admin actually typed; empty fields are always allowed.
  function validate(): boolean {
    const e: Record<string, string> = {}
    if (form.pan?.trim() && !PAN_RE.test(form.pan.trim().toUpperCase()))
      e.pan = 'Invalid PAN (AAAAA9999A)'
    if (form.cin?.trim() && !CIN_RE.test(form.cin.trim().toUpperCase()))
      e.cin = 'Invalid CIN (21 characters)'
    if (form.gstin?.trim() && !GSTIN_RE.test(form.gstin.trim().toUpperCase()))
      e.gstin = 'Invalid GSTIN (15 characters)'
    if (form.pincode?.trim() && !PINCODE_RE.test(form.pincode.trim()))
      e.pincode = 'Invalid pincode (6 digits)'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault()
    if (!canEdit) return
    if (!validate()) {
      toast.error('Please fix the highlighted fields')
      return
    }
    const body: CompanyProfileUpdate = {}
    for (const k of TEXT_FIELDS) {
      ;(body as Record<string, string | null>)[k] = emptyToNull(form[k] ?? '')
    }
    // Finishing onboarding marks the profile complete even if fields were left
    // blank, so the admin isn't bounced back to this page.
    if (mode === 'onboarding') body.mark_completed = true
    try {
      const updated = await update.mutateAsync(body)
      toast.success('Company profile saved')
      onSaved?.(updated)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save profile')
    }
  }

  async function onLogoChange(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0]
    ev.target.value = '' // allow re-selecting the same file
    if (!file) return
    if (!['image/png', 'image/jpeg', 'image/svg+xml'].includes(file.type)) {
      toast.error('Logo must be PNG, JPG, or SVG')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Logo must be 2 MB or smaller')
      return
    }
    try {
      await uploadLogo.mutateAsync(file)
      setLogoUrl(URL.createObjectURL(file))
      toast.success('Logo updated')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to upload logo')
    }
  }

  const fieldProps = (k: string) => ({
    value: form[k] ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value),
    disabled: !canEdit,
    error: !!errors[k],
  })

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-8">
      {/* Logo */}
      <section className="flex items-center gap-5">
        <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl border border-border bg-bg-surface">
          {logoUrl ? (
            <img src={logoUrl} alt="Company logo" className="h-full w-full object-contain" />
          ) : (
            <span className="text-xs text-text-muted">No logo</span>
          )}
        </div>
        {canEdit && (
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-btn border border-border-strong bg-bg-surface px-3 py-2 text-sm font-medium text-text-secondary hover:border-accent">
            <UploadCloud className="h-4 w-4" />
            {uploadLogo.isPending ? 'Uploading…' : 'Upload logo'}
            <input type="file" accept="image/png,image/jpeg,image/svg+xml" className="hidden" onChange={onLogoChange} />
          </label>
        )}
      </section>

      {/* Basic */}
      <section className="flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-text-primary">Company details</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Legal name" htmlFor="legal_name" error={errors.legal_name}>
            <Input id="legal_name" placeholder="Acme Pvt Ltd" {...fieldProps('legal_name')} />
          </Field>
          <Field label="Industry" htmlFor="industry" error={errors.industry}>
            <Input id="industry" placeholder="e.g. Software" {...fieldProps('industry')} />
          </Field>
          <Field label="Website" htmlFor="website" error={errors.website}>
            <Input id="website" placeholder="https://…" {...fieldProps('website')} />
          </Field>
          <Field label="Date of incorporation" htmlFor="date_of_incorporation" error={errors.date_of_incorporation}>
            <Input id="date_of_incorporation" type="date" {...fieldProps('date_of_incorporation')} />
          </Field>
        </div>
      </section>

      {/* Statutory */}
      <section className="flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-text-primary">Statutory identifiers</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="CIN" htmlFor="cin" error={errors.cin} hint="21-character Corporate Identity Number">
            <Input id="cin" placeholder="U12345MH2020PTC123456" {...fieldProps('cin')} />
          </Field>
          <Field label="PAN" htmlFor="pan" error={errors.pan}>
            <Input id="pan" placeholder="AAAAA9999A" {...fieldProps('pan')} />
          </Field>
          <Field label="GSTIN" htmlFor="gstin" error={errors.gstin} hint="Optional — only if GST-registered">
            <Input id="gstin" placeholder="27ABCDE1234F1Z5" {...fieldProps('gstin')} />
          </Field>
          <Field label="TAN" htmlFor="tan" error={errors.tan}>
            <Input id="tan" placeholder="Optional" {...fieldProps('tan')} />
          </Field>
        </div>
      </section>

      {/* Address */}
      <section className="flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-text-primary">Registered office</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Address line 1" htmlFor="address_line1" error={errors.address_line1} className="sm:col-span-2">
            <Input id="address_line1" {...fieldProps('address_line1')} />
          </Field>
          <Field label="Address line 2" htmlFor="address_line2" error={errors.address_line2} className="sm:col-span-2">
            <Input id="address_line2" {...fieldProps('address_line2')} />
          </Field>
          <Field label="City" htmlFor="city" error={errors.city}>
            <Input id="city" {...fieldProps('city')} />
          </Field>
          <Field label="State" htmlFor="state" error={errors.state}>
            <Input id="state" {...fieldProps('state')} />
          </Field>
          <Field label="Pincode" htmlFor="pincode" error={errors.pincode}>
            <Input id="pincode" placeholder="400001" {...fieldProps('pincode')} />
          </Field>
        </div>
      </section>

      {/* Contact */}
      <section className="flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-text-primary">Contact</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Contact email" htmlFor="contact_email" error={errors.contact_email}>
            <Input id="contact_email" type="email" {...fieldProps('contact_email')} />
          </Field>
          <Field label="Contact phone" htmlFor="contact_phone" error={errors.contact_phone}>
            <Input id="contact_phone" {...fieldProps('contact_phone')} />
          </Field>
        </div>
      </section>

      {canEdit ? (
        <div className="flex items-center justify-end gap-3">
          {mode === 'onboarding' && (
            <span className="text-sm text-text-muted">All fields are optional — you can fill these in later.</span>
          )}
          <Button type="submit" size="lg" loading={update.isPending}>
            {mode === 'onboarding' ? 'Complete setup' : 'Save changes'}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-text-muted">Only an admin can edit these details.</p>
      )}
    </form>
  )
}
