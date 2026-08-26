import { Shield, ArrowUpRight, Lock } from 'lucide-react'
import { getAppUrl } from '@/lib/domain'

interface LandingHeaderProps {
  onRequestAccess: () => void
}

export function LandingHeader({ onRequestAccess }: LandingHeaderProps) {
  return (
    <header className="sticky top-0 z-30 w-full border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3.5 sm:px-6 lg:px-8">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white shadow-sm ring-1 ring-slate-900/10">
            <Shield className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-base font-bold tracking-tight text-slate-900">KUBERA</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                CORPORATE
              </span>
            </div>
            <div className="text-[10px] font-medium tracking-wider text-slate-400 uppercase">
              A Product by ETHDC
            </div>
          </div>
        </div>

        {/* Desktop Nav */}
        <nav className="hidden items-center gap-7 md:flex">
          <a
            href="#why-kubera"
            className="text-xs font-semibold text-slate-600 transition hover:text-indigo-600"
          >
            Why Kubera
          </a>
          <a
            href="#modules"
            className="text-xs font-semibold text-slate-600 transition hover:text-indigo-600"
          >
            Platform Modules
          </a>
          <a
            href="#why-it-pays-off"
            className="text-xs font-semibold text-slate-600 transition hover:text-indigo-600"
          >
            Why It Pays Off
          </a>
          <a
            href="#pricing"
            className="text-xs font-semibold text-slate-600 transition hover:text-indigo-600"
          >
            Membership & Pricing
          </a>
        </nav>

        {/* CTA Buttons */}
        <div className="flex items-center gap-3">
          <a
            href={getAppUrl('/login')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-xs transition hover:border-slate-300 hover:bg-slate-50"
          >
            <Lock className="h-3.5 w-3.5 text-slate-400" />
            <span>Go to App</span>
            <ArrowUpRight className="h-3 w-3 text-slate-400" />
          </a>
          <button
            type="button"
            onClick={onRequestAccess}
            className="inline-flex items-center justify-center rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-indigo-500"
          >
            Request Access
          </button>
        </div>
      </div>
    </header>
  )
}
