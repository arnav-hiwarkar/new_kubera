import { useState, useEffect } from 'react'
import { Shield, KeyRound, CheckCircle2, UserPlus, RefreshCw, Copy, Check, Search, Filter } from 'lucide-react'

interface Lead {
  id: string
  email: string
  company_name?: string | null
  phone?: string | null
  entities_count?: number | null
  notes?: string | null
  status: 'new' | 'contacted' | 'converted' | 'archived'
  created_at: string
}

interface ProvisionResult {
  lead_id: string
  company_id: string
  company_name: string
  admin_email: string
  activation_key: string
  activation_expires_at?: string
}

export function OwnerLeadsPage() {
  const [apiKey, setApiKey] = useState<string>(() => sessionStorage.getItem('kubera_owner_key') || '')
  const [inputKey, setInputKey] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)

  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(false)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [searchTerm, setSearchTerm] = useState('')

  // Provisioning modal state
  const [provisioningLead, setProvisioningLead] = useState<Lead | null>(null)
  const [provisionResult, setProvisionResult] = useState<ProvisionResult | null>(null)
  const [provisionLoading, setProvisionLoading] = useState(false)
  const [provisionError, setProvisionError] = useState<string | null>(null)
  const [copiedKey, setCopiedKey] = useState(false)

  const fetchLeads = async (key: string) => {
    setLoading(true)
    setAuthError(null)
    try {
      const res = await fetch('/api/v1/owner/leads', {
        headers: { 'X-Internal-API-Key': key },
      })
      if (res.status === 403 || res.status === 401) {
        throw new Error('Invalid internal API key')
      }
      if (!res.ok) {
        throw new Error('Failed to load leads')
      }
      const data = await res.json()
      setLeads(data)
      setAuthenticated(true)
      sessionStorage.setItem('kubera_owner_key', key)
    } catch (err: any) {
      setAuthError(err.message || 'Authentication failed')
      setAuthenticated(false)
      sessionStorage.removeItem('kubera_owner_key')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (apiKey) {
      fetchLeads(apiKey)
    }
  }, [apiKey])

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputKey.trim()) return
    setApiKey(inputKey.trim())
  }

  const handleLogout = () => {
    setApiKey('')
    setInputKey('')
    setAuthenticated(false)
    sessionStorage.removeItem('kubera_owner_key')
  }

  const handleStatusChange = async (leadId: string, newStatus: string) => {
    try {
      const res = await fetch(`/api/v1/owner/leads/${leadId}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Internal-API-Key': apiKey,
        },
        body: JSON.stringify({ status: newStatus }),
      })
      if (res.ok) {
        setLeads((prev) =>
          prev.map((l) => (l.id === leadId ? { ...l, status: newStatus as any } : l))
        )
      }
    } catch (err) {
      console.error('Failed to update lead status', err)
    }
  }

  const handleProvision = async () => {
    if (!provisioningLead) return
    setProvisionLoading(true)
    setProvisionError(null)

    try {
      const res = await fetch(`/api/v1/owner/leads/${provisioningLead.id}/provision`, {
        method: 'POST',
        headers: {
          'X-Internal-API-Key': apiKey,
        },
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Provisioning failed')
      }

      setProvisionResult(data)
      setLeads((prev) =>
        prev.map((l) => (l.id === provisioningLead.id ? { ...l, status: 'converted' } : l))
      )
    } catch (err: any) {
      setProvisionError(err.message || 'Error creating company')
    } finally {
      setProvisionLoading(false)
    }
  }

  const handleCopyKey = () => {
    if (provisionResult?.activation_key) {
      navigator.clipboard.writeText(provisionResult.activation_key)
      setCopiedKey(true)
      setTimeout(() => setCopiedKey(false), 2000)
    }
  }

  // Filtered list
  const filteredLeads = leads.filter((lead) => {
    const matchesStatus = filterStatus === 'all' || lead.status === filterStatus
    const term = searchTerm.toLowerCase()
    const matchesSearch =
      !term ||
      lead.email.toLowerCase().includes(term) ||
      (lead.company_name && lead.company_name.toLowerCase().includes(term))
    return matchesStatus && matchesSearch
  })

  // Locked Authentication Screen
  if (!authenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4 text-white">
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400">
            <Shield className="h-6 w-6" />
          </div>
          <h2 className="mt-4 text-xl font-bold tracking-tight text-white">Kubera Operator Vault</h2>
          <p className="mt-1 text-xs text-slate-400">
            Private management portal for company inquiries & manual provisioning.
          </p>

          <form onSubmit={handleLogin} className="mt-6 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300">
                Internal Operator API Key
              </label>
              <div className="relative mt-1">
                <input
                  type="password"
                  required
                  value={inputKey}
                  onChange={(e) => setInputKey(e.target.value)}
                  placeholder="Enter INTERNAL_API_KEY..."
                  className="block w-full rounded-lg border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <KeyRound className="pointer-events-none absolute top-3 right-3 h-4 w-4 text-slate-600" />
              </div>
            </div>

            {authError && (
              <div className="rounded-lg bg-rose-500/10 border border-rose-500/20 p-3 text-xs text-rose-400">
                {authError}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? 'Authenticating...' : 'Unlock Portal'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-950 px-4 py-3.5 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <Shield className="h-4 w-4" />
            </div>
            <div>
              <div className="text-sm font-bold text-white">Kubera Operator Vault</div>
              <div className="text-[10px] text-slate-400">Inbound Leads & Company Provisioning</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => fetchLeads(apiKey)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-slate-800"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <button
              onClick={handleLogout}
              className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              Lock
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Metric Cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-xs font-semibold text-slate-400">Total Leads</div>
            <div className="mt-2 text-2xl font-extrabold text-white">{leads.length}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-xs font-semibold text-indigo-400">New Inquiries</div>
            <div className="mt-2 text-2xl font-extrabold text-white">
              {leads.filter((l) => l.status === 'new').length}
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-xs font-semibold text-amber-400">Contacted</div>
            <div className="mt-2 text-2xl font-extrabold text-white">
              {leads.filter((l) => l.status === 'contacted').length}
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-xs font-semibold text-emerald-400">Converted Companies</div>
            <div className="mt-2 text-2xl font-extrabold text-white">
              {leads.filter((l) => l.status === 'converted').length}
            </div>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-slate-400" />
            <span className="text-xs font-semibold text-slate-400">Filter:</span>
            {['all', 'new', 'contacted', 'converted', 'archived'].map((st) => (
              <button
                key={st}
                onClick={() => setFilterStatus(st)}
                className={`rounded-lg px-3 py-1 text-xs font-semibold capitalize transition ${
                  filterStatus === st
                    ? 'bg-indigo-600 text-white'
                    : 'border border-slate-800 bg-slate-950 text-slate-400 hover:text-white'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute top-2.5 left-3 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search email or company..."
              className="w-full rounded-lg border border-slate-800 bg-slate-950 py-1.5 pr-3 pl-8 text-xs text-white placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Leads Table */}
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
          <table className="min-w-full divide-y divide-slate-800 text-left text-xs">
            <thead className="bg-slate-900/50 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Lead Contact</th>
                <th className="px-4 py-3 font-semibold">Company / Entities</th>
                <th className="px-4 py-3 font-semibold">Notes / Scope</th>
                <th className="px-4 py-3 font-semibold">Submitted</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredLeads.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                    No leads found matching current filter.
                  </td>
                </tr>
              ) : (
                filteredLeads.map((lead) => (
                  <tr key={lead.id} className="hover:bg-slate-900/40">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-white">{lead.email}</div>
                      {lead.phone && <div className="text-[11px] text-slate-400">{lead.phone}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-200">{lead.company_name || '—'}</div>
                      <div className="text-[11px] text-slate-400">
                        {lead.entities_count ? `${lead.entities_count} entities` : '1 entity'}
                      </div>
                    </td>
                    <td className="max-w-xs px-4 py-3 truncate text-[11px] text-slate-400" title={lead.notes || ''}>
                      {lead.notes || '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {new Date(lead.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={lead.status}
                        onChange={(e) => handleStatusChange(lead.id, e.target.value)}
                        className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                      >
                        <option value="new">New</option>
                        <option value="contacted">Contacted</option>
                        <option value="converted">Converted</option>
                        <option value="archived">Archived</option>
                      </select>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {lead.status !== 'converted' ? (
                        <button
                          onClick={() => {
                            setProvisioningLead(lead)
                            setProvisionResult(null)
                            setProvisionError(null)
                          }}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white shadow-xs transition hover:bg-indigo-500"
                        >
                          <UserPlus className="h-3 w-3" />
                          <span>Provision</span>
                        </button>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          <span>Onboarded</span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>

      {/* Provisioning Modal */}
      {provisioningLead && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-950 p-6 text-white shadow-2xl">
            {provisionResult ? (
              <div>
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <h3 className="mt-4 text-lg font-bold text-white">Company Successfully Initialized</h3>
                <p className="mt-1 text-xs text-slate-400">
                  A company shell and per-company KEK have been minted. Share the one-shot activation key with the admin.
                </p>

                <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
                  <div>
                    <div className="text-[11px] font-semibold text-slate-400">Company Name</div>
                    <div className="text-xs font-bold text-white">{provisionResult.company_name}</div>
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold text-slate-400">Admin Email</div>
                    <div className="text-xs font-bold text-white">{provisionResult.admin_email}</div>
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold text-slate-400">One-Shot Activation Key (Valid 48h)</div>
                    <div className="mt-1 flex items-center gap-2">
                      <code className="flex-1 rounded bg-slate-950 px-3 py-1.5 font-mono text-xs text-indigo-300 select-all">
                        {provisionResult.activation_key}
                      </code>
                      <button
                        onClick={handleCopyKey}
                        className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-500"
                      >
                        {copiedKey ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>{copiedKey ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                <div className="mt-6 flex justify-end">
                  <button
                    onClick={() => {
                      setProvisioningLead(null)
                      setProvisionResult(null)
                    }}
                    className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-700"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <h3 className="text-lg font-bold text-white">Provision Company Account</h3>
                <p className="mt-1 text-xs text-slate-400">
                  This will create the company record, assign an encrypted per-company KEK, and create a pending admin login.
                </p>

                <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2 text-xs">
                  <div>
                    <span className="text-slate-400">Company: </span>
                    <strong className="text-white">
                      {provisioningLead.company_name || `Company (${provisioningLead.email.split('@')[0]})`}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Admin Email: </span>
                    <strong className="text-white">{provisioningLead.email}</strong>
                  </div>
                </div>

                {provisionError && (
                  <div className="mt-4 rounded-lg bg-rose-500/10 border border-rose-500/20 p-3 text-xs text-rose-400">
                    {provisionError}
                  </div>
                )}

                <div className="mt-6 flex justify-end gap-2">
                  <button
                    onClick={() => setProvisioningLead(null)}
                    className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-300 transition hover:bg-slate-800"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleProvision}
                    disabled={provisionLoading}
                    className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                  >
                    {provisionLoading ? 'Creating Company...' : 'Confirm & Generate Key'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
