import { Shield, ArrowUpRight, Lock } from 'lucide-react'

interface LandingFooterProps {
  onRequestAccess: () => void
}

export function LandingFooter({ onRequestAccess }: LandingFooterProps) {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-12">
          {/* Brand Info */}
          <div className="md:col-span-5">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white shadow-sm">
                <Shield className="h-4 w-4 text-indigo-400" />
              </div>
              <span className="text-base font-bold tracking-tight text-slate-900">KUBERA</span>
            </div>
            <p className="mt-3 max-w-sm text-xs leading-relaxed text-slate-600">
              A secure treasury for the records that keep your company compliant, audit-ready, and continuous.
            </p>
            <div className="mt-4 text-xs font-semibold text-slate-500">
              A PRODUCT BY <span className="text-slate-900">ETHDC</span>
            </div>
          </div>

          {/* Platform Links */}
          <div className="md:col-span-3">
            <div className="text-xs font-bold tracking-wider text-slate-900 uppercase">
              Platform Modules
            </div>
            <ul className="mt-3 space-y-2 text-xs text-slate-600">
              <li>docVault (Repository Management)</li>
              <li>Asset Life Cycle & Dual Depreciation</li>
              <li>AuditEase (Audit Management)</li>
              <li>PMO / CEO Office & KRAs</li>
              <li>Kubera.ai (Feb 2027)</li>
            </ul>
          </div>

          {/* Quick Access */}
          <div className="md:col-span-4">
            <div className="text-xs font-bold tracking-wider text-slate-900 uppercase">
              Get Started
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-600">
              Ready to secure your compliance treasury? Request a demonstration configured around your entities.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={onRequestAccess}
                className="inline-flex items-center justify-center rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-xs transition hover:bg-indigo-500"
              >
                Request Access
              </button>
              <a
                href="/login"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
              >
                <Lock className="h-3.5 w-3.5 text-slate-400" />
                <span>Go to App</span>
                <ArrowUpRight className="h-3 w-3 text-slate-400" />
              </a>
            </div>
          </div>
        </div>

        <div className="mt-12 border-t border-slate-100 pt-6 text-center text-xs text-slate-400">
          © {new Date().getFullYear()} Kubera Corporate Compliance. All rights reserved. Built for SMEs & multi-company groups.
        </div>
      </div>
    </footer>
  )
}
