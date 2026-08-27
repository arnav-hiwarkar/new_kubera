import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { CheckCircle2, Loader2, ArrowRight, ShieldCheck } from 'lucide-react'

interface LeadModalProps {
  open: boolean
  onClose: () => void
  initialEmail?: string
}

export function LeadModal({ open, onClose, initialEmail = '' }: LeadModalProps) {
  const [email, setEmail] = useState(initialEmail)
  const [companyName, setCompanyName] = useState('')
  const [phone, setPhone] = useState('')
  const [entitiesCount, setEntitiesCount] = useState<number | ''>('')
  const [notes, setNotes] = useState('')
  const [honeypot, setHoneypot] = useState('')
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const res = await fetch('/api/v1/leads/interest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          company_name: companyName.trim() || undefined,
          phone: phone.trim() || undefined,
          entities_count: entitiesCount ? Number(entitiesCount) : undefined,
          notes: notes.trim() || undefined,
          website_url_hp: honeypot || undefined,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Unable to submit request. Please try again.')
      }

      setSubmitted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setSubmitted(false)
    setEmail('')
    setCompanyName('')
    setPhone('')
    setEntitiesCount('')
    setNotes('')
    setHoneypot('')
    setError(null)
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleReset}
      title={submitted ? 'Request Received' : 'Request Access & Demonstration'}
      size="md"
    >
      {submitted ? (
        <div className="py-6 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
            <CheckCircle2 className="h-8 w-8" />
          </div>
          <h3 className="text-lg font-semibold text-slate-900">Thank You for Your Interest</h3>
          <p className="mt-2 text-sm text-slate-600">
            Your inquiry has been received by the Kubera onboarding team. We will review your requirements
            and contact you at <strong className="text-slate-900">{email}</strong> to configure your demonstration.
          </p>
          <div className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="h-4 w-4 text-indigo-600" />
            <span>Encrypted statutory records & enterprise isolation</span>
          </div>
          <button
            type="button"
            onClick={handleReset}
            className="mt-6 inline-flex items-center justify-center rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Done
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <p className="text-xs text-slate-600">
            Get Kubera configured for your business entities. Provide your work email and our team will get in touch directly.
          </p>

          {/* Anti-bot honeypot field - hidden from humans */}
          <div className="hidden" aria-hidden="true">
            <input
              type="text"
              name="website_url_hp"
              value={honeypot}
              onChange={(e) => setHoneypot(e.target.value)}
              tabIndex={-1}
              autoComplete="off"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">
              Work Email <span className="text-rose-500">*</span>
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="cfo@yourcompany.com"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold text-slate-700">Company Name</label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Acme Technologies Pvt Ltd"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700">Phone Number</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98765 43210"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">
              Number of Companies / Entities
            </label>
            <select
              value={entitiesCount}
              onChange={(e) => setEntitiesCount(e.target.value ? Number(e.target.value) : '')}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
            >
              <option value="">Select entity count...</option>
              <option value="1">1 Company (Single SME)</option>
              <option value="2">Up to 2 Companies (Standard Plan)</option>
              <option value="4">Up to 4 Companies (Pro Plan)</option>
              <option value="5">5+ Companies (Enterprise Group)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">
              Specific Compliance Priorities / Notes
            </label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. AuditEase trial balance import, Fixed Asset Register depreciation, Secretarial..."
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
            />
          </div>

          {error && (
            <div className="rounded-md bg-rose-50 p-3 text-xs text-rose-700">
              {error}
            </div>
          )}

          <div className="pt-2">
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Submitting...</span>
                </>
              ) : (
                <>
                  <span>Request Access</span>
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}
