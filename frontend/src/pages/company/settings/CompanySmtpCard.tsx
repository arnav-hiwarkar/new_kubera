import { useEffect, useState } from 'react'
import { Mail, CheckCircle2, AlertCircle, RefreshCw, Server, Send } from 'lucide-react'
import { Button, Field, Input, Switch, useToast, Spinner, ConfirmDialog } from '@/components/ui'
import {
  useCompanySmtp,
  useUpdateCompanySmtp,
  useVerifyCompanySmtp,
  useResetCompanySmtp,
} from '@/api/hooks/companySmtp'

export function CompanySmtpCard({ canEdit }: { canEdit: boolean }) {
  const toast = useToast()
  const { data: smtpConfig, isLoading } = useCompanySmtp()
  const updateMutation = useUpdateCompanySmtp()
  const verifyMutation = useVerifyCompanySmtp()
  const resetMutation = useResetCompanySmtp()

  const [form, setForm] = useState({
    host: '',
    port: 587,
    user: '',
    password: '',
    from_email: '',
    from_name: '',
    use_tls: true,
    use_ssl: false,
  })
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const [verifyResult, setVerifyResult] = useState<{ success: boolean; message: string; latency_ms?: number } | null>(null)

  useEffect(() => {
    if (smtpConfig && smtpConfig.configured) {
      setForm({
        host: smtpConfig.host || '',
        port: smtpConfig.port || 587,
        user: smtpConfig.user || '',
        password: '',
        from_email: smtpConfig.from_email || '',
        from_name: smtpConfig.from_name || '',
        use_tls: smtpConfig.use_tls,
        use_ssl: smtpConfig.use_ssl,
      })
    }
  }, [smtpConfig])

  if (isLoading) {
    return (
      <div className="rounded-card border border-border bg-bg-surface p-6 flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  const isConfigured = Boolean(smtpConfig?.configured)

  async function handleTestConnection() {
    setVerifyResult(null)
    try {
      const payload = {
        host: form.host.trim() || undefined,
        port: Number(form.port) || undefined,
        user: form.user.trim() || undefined,
        password: form.password || undefined,
        from_email: form.from_email.trim() || undefined,
        from_name: form.from_name.trim() || undefined,
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
      }
      const res = await verifyMutation.mutateAsync(payload)
      setVerifyResult({
        success: true,
        message: `Connected successfully (${res.latency_ms.toFixed(1)}ms latency)`,
        latency_ms: res.latency_ms,
      })
      toast.success('SMTP connection verified successfully!')
    } catch (err: any) {
      const msg = err?.message || 'SMTP connection verification failed.'
      setVerifyResult({
        success: false,
        message: msg,
      })
      toast.error(msg)
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!canEdit) return

    if (!form.host.trim() || !form.user.trim() || !form.from_email.trim() || !form.from_name.trim()) {
      toast.error('Please fill in all required SMTP fields.')
      return
    }

    if (!isConfigured && !form.password) {
      toast.error('Password is required for new SMTP configuration.')
      return
    }

    try {
      await updateMutation.mutateAsync({
        host: form.host.trim(),
        port: Number(form.port) || 587,
        user: form.user.trim(),
        password: form.password || undefined,
        from_email: form.from_email.trim(),
        from_name: form.from_name.trim(),
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
        is_active: true,
      })
      toast.success('Custom SMTP settings saved!')
      setForm((prev) => ({ ...prev, password: '' }))
    } catch (err: any) {
      toast.error(err?.message || 'Failed to save SMTP settings.')
    }
  }

  async function handleReset() {
    try {
      await resetMutation.mutateAsync()
      setShowResetConfirm(false)
      setVerifyResult(null)
      setForm({
        host: '',
        port: 587,
        user: '',
        password: '',
        from_email: '',
        from_name: '',
        use_tls: true,
        use_ssl: false,
      })
      toast.success('Reset to system default email (kubera@ethdc.in).')
    } catch (err: any) {
      toast.error(err?.message || 'Failed to reset SMTP configuration.')
    }
  }

  return (
    <div className="rounded-card border border-border bg-bg-surface p-6 sm:p-8 flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Mail className="h-5 w-5 text-accent-primary" />
            <h2 className="text-lg font-semibold text-text-primary">Outbound Email & Custom SMTP</h2>
          </div>
          <p className="text-sm text-text-secondary mt-1">
            Configure your company's mail server for sending auditor invites and compliance notices.
          </p>
        </div>

        <div>
          {isConfigured ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Custom SMTP Active
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-500/10 text-slate-600 border border-slate-500/20">
              <Server className="h-3.5 w-3.5" />
              Using System Default (kubera@ethdc.in)
            </span>
          )}
        </div>
      </div>

      {verifyResult && (
        <div
          className={`p-4 rounded-lg text-sm flex items-start gap-3 border ${
            verifyResult.success
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700'
              : 'bg-rose-500/10 border-rose-500/20 text-rose-700'
          }`}
        >
          {verifyResult.success ? (
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0 text-rose-600" />
          )}
          <div>
            <p className="font-medium">{verifyResult.success ? 'Verification Passed' : 'Verification Failed'}</p>
            <p className="mt-0.5 text-xs opacity-90">{verifyResult.message}</p>
          </div>
        </div>
      )}

      <form onSubmit={handleSave} className="flex flex-col gap-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="sm:col-span-2">
            <Field label="SMTP Host *" hint="e.g. smtp.office365.com, smtp.gmail.com">
              <Input
                value={form.host}
                onChange={(e) => setForm((prev) => ({ ...prev, host: e.target.value }))}
                placeholder="smtp.yourcompany.com"
                disabled={!canEdit}
                required
              />
            </Field>
          </div>

          <div>
            <Field label="Port *" hint="Usually 587 (TLS) or 465 (SSL)">
              <Input
                type="number"
                value={form.port}
                onChange={(e) => setForm((prev) => ({ ...prev, port: parseInt(e.target.value) || 587 }))}
                disabled={!canEdit}
                required
              />
            </Field>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="SMTP Username / Login *" hint="Account username or full email">
            <Input
              value={form.user}
              onChange={(e) => setForm((prev) => ({ ...prev, user: e.target.value }))}
              placeholder="audit@yourcompany.com"
              disabled={!canEdit}
              required
            />
          </Field>

          <Field
            label="SMTP Password *"
            hint={smtpConfig?.has_password ? 'Leave blank to keep existing password' : 'Encrypted with AES-256-GCM at rest'}
          >
            <Input
              type="password"
              value={form.password}
              onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
              placeholder={smtpConfig?.has_password ? '••••••••' : 'Enter SMTP password'}
              disabled={!canEdit}
              required={!isConfigured}
            />
          </Field>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="From Email Address *" hint="Address shown in recipient inboxes">
            <Input
              type="email"
              value={form.from_email}
              onChange={(e) => setForm((prev) => ({ ...prev, from_email: e.target.value }))}
              placeholder="audit@yourcompany.com"
              disabled={!canEdit}
              required
            />
          </Field>

          <Field label="From Display Name *" hint="Display name (e.g. Acme Corp Compliance)">
            <Input
              value={form.from_name}
              onChange={(e) => setForm((prev) => ({ ...prev, from_name: e.target.value }))}
              placeholder="Acme Compliance Team"
              disabled={!canEdit}
              required
            />
          </Field>
        </div>

        <div className="flex flex-wrap gap-6 py-2 border-y border-border">
          <div className="flex items-center gap-3">
            <Switch
              id="smtp_use_tls"
              checked={form.use_tls}
              onChange={(checked) => setForm((prev) => ({ ...prev, use_tls: checked }))}
              disabled={!canEdit}
            />
            <label htmlFor="smtp_use_tls" className="text-sm font-medium text-text-primary cursor-pointer">
              Use STARTTLS (Recommended for port 587)
            </label>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              id="smtp_use_ssl"
              checked={form.use_ssl}
              onChange={(checked) => setForm((prev) => ({ ...prev, use_ssl: checked }))}
              disabled={!canEdit}
            />
            <label htmlFor="smtp_use_ssl" className="text-sm font-medium text-text-primary cursor-pointer">
              Use Direct SSL (Port 465)
            </label>
          </div>
        </div>

        {canEdit && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2">
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <Button
                type="button"
                variant="secondary"
                onClick={handleTestConnection}
                disabled={verifyMutation.isPending || (!form.host && !isConfigured)}
                className="w-full sm:w-auto"
              >
                {verifyMutation.isPending ? (
                  <>
                    <Spinner size="sm" className="mr-2" /> Testing Connection...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4 mr-2" /> Test Connection
                  </>
                )}
              </Button>

              {isConfigured && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setShowResetConfirm(true)}
                  disabled={resetMutation.isPending}
                  className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                >
                  <RefreshCw className="h-4 w-4 mr-1.5" /> Revert to Default Mail
                </Button>
              )}
            </div>

            <Button
              type="submit"
              variant="primary"
              disabled={updateMutation.isPending}
              className="w-full sm:w-auto"
            >
              {updateMutation.isPending ? 'Saving...' : 'Save SMTP Settings'}
            </Button>
          </div>
        )}
      </form>

      <ConfirmDialog
        open={showResetConfirm}
        title="Reset Outbound Email"
        description="Are you sure you want to delete your custom SMTP configuration? All future emails will be sent through the platform's default email (kubera@ethdc.in)."
        confirmLabel="Reset to Default"
        variant="destructive"
        onConfirm={handleReset}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  )
}
