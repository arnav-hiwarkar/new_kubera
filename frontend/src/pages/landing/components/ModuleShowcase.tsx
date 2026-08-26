import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FolderLock, Calculator, FileSpreadsheet, Briefcase, Sparkles, Check, ArrowRight } from 'lucide-react'

interface ModuleShowcaseProps {
  onRequestAccess: () => void
}

export function ModuleShowcase({ onRequestAccess }: ModuleShowcaseProps) {
  const [activeTab, setActiveTab] = useState(0)

  const modules = [
    {
      id: 'docvault',
      title: 'Module 01: Repository Management',
      shortTitle: 'docVault (Repository)',
      icon: FolderLock,
      tagline: 'Purpose-built document buckets with role-based access.',
      desc: 'Ensure the right people see the right records — and nothing else. Strict company-isolated encryption keeps board resolutions, filings, and financial contracts secure.',
      pillars: [
        'SECRETARIAL & BOARD MINUTES',
        'ROC FILINGS & FORMS',
        'GST & TAXATION ARCHIVES',
        'HR & PAYROLL GOVERNANCE',
        'LEGAL & MATERIAL CONTRACTS',
        'BANKING & FINANCE AGREEMENTS',
      ],
      badge: 'Multi-Tenant Encrypted',
    },
    {
      id: 'assets',
      title: 'Module 02: Asset Life Cycle',
      shortTitle: 'Fixed Asset Register',
      icon: Calculator,
      tagline: 'Dual-regime statutory depreciation from capitalisation to disposal.',
      desc: 'Eliminate spreadsheet drift. Automated dual-book depreciation under the Companies Act 2013 and Income Tax Act 1961 with transparent calculation traces.',
      pillars: [
        'COMPANIES ACT (USEFUL LIFE / SLM & WDV)',
        'INCOME TAX ACT (BLOCK OF ASSETS)',
        'AUTOMATED CALCULATION TRACES',
        'CAPITALISATION & ADDITIONS AUDIT',
        'DISPOSAL & SCRAP LOGGING',
        'STATUTORY AUDIT-READY SCHEDULES',
      ],
      badge: 'Dual Statutory Books',
    },
    {
      id: 'auditease',
      title: 'Module 03: Audit Management',
      shortTitle: 'AuditEase',
      icon: FileSpreadsheet,
      tagline: 'From trial balance import to final certified reports.',
      desc: 'Grant scoped access to external statutory auditors. Map trial balances, track PBC document requests, resolve audit queries, and review tamper-evident logs.',
      pillars: [
        'MULTI-CYCLE TRIAL BALANCE IMPORT',
        'LEDGER & SCHEDULE MAPPING',
        'SCOPED AUDITOR PORTAL ACCESS',
        'REAL-TIME PBC QUERY TRACKING',
        'TAMPER-EVIDENT ACTIVITY LOGS',
        'FINAL REPORT COMPILATION & EXPORT',
      ],
      badge: 'Auditor Workflow',
    },
    {
      id: 'pmo',
      title: 'Module 04: PMO / CEO Office',
      shortTitle: 'PMO & Governance',
      icon: Briefcase,
      tagline: 'A leadership command centre for commercial and statutory health.',
      desc: 'Keep leadership and the board informed with master registries, client and partner directories, KRA tracking, and rolling cash collection projections.',
      pillars: [
        'MARKET SEGMENTS & CLIENT REGISTRIES',
        'PARTNER PROGRAM MANAGEMENT',
        'KRA & EXECUTIVE OBJECTIVE TRACKING',
        'ROLLING COLLECTION FORECASTS',
        'MULTI-ENTITY CONSOLIDATED VIEW',
        'EXECUTIVE MEETING RECORDS',
      ],
      badge: 'Leadership Command',
    },
  ]

  const activeModule = modules[activeTab]

  return (
    <section id="modules" className="py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <div className="text-xs font-bold tracking-wider text-indigo-600 uppercase">
            The Platform
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Four modules, one vault.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">
            Every module connects to your central encrypted treasury, standardizing operations across every department and entity.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-2">
          {modules.map((m, idx) => {
            const Icon = m.icon
            const isSelected = activeTab === idx
            return (
              <button
                key={m.id}
                onClick={() => setActiveTab(idx)}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition sm:text-sm ${
                  isSelected
                    ? 'bg-slate-900 text-white shadow-sm'
                    : 'border border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <Icon className={`h-4 w-4 ${isSelected ? 'text-indigo-400' : 'text-slate-400'}`} />
                <span>{m.shortTitle}</span>
              </button>
            )
          })}
        </div>

        {/* Active Module Card */}
        <div className="mt-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeModule.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="rounded-3xl border border-slate-200 bg-white p-8 shadow-xs sm:p-10"
            >
              <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-center">
                <div className="lg:col-span-7">
                  <div className="inline-flex items-center gap-2 rounded-md bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700">
                    <span>{activeModule.badge}</span>
                  </div>
                  <h3 className="mt-4 text-xl font-bold text-slate-900 sm:text-2xl">
                    {activeModule.title}
                  </h3>
                  <p className="mt-2 text-sm font-medium text-indigo-600">
                    {activeModule.tagline}
                  </p>
                  <p className="mt-4 text-sm leading-relaxed text-slate-600">
                    {activeModule.desc}
                  </p>

                  <div className="mt-8 flex items-center gap-4">
                    <button
                      type="button"
                      onClick={onRequestAccess}
                      className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs transition hover:bg-indigo-500"
                    >
                      <span>Explore this module</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-100 bg-slate-50/70 p-6 lg:col-span-5">
                  <div className="text-xs font-bold tracking-wider text-slate-500 uppercase">
                    Core Capabilities
                  </div>
                  <ul className="mt-4 space-y-3">
                    {activeModule.pillars.map((pillar, i) => (
                      <li key={i} className="flex items-center gap-2.5 text-xs font-medium text-slate-800">
                        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
                          <Check className="h-3 w-3" />
                        </div>
                        <span>{pillar}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Kubera.ai Roadmap Teaser */}
        <div className="mt-8 rounded-2xl border border-indigo-200/80 bg-gradient-to-r from-indigo-900 via-slate-900 to-indigo-950 p-6 text-white sm:p-8">
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/20 px-3 py-0.5 text-xs font-semibold text-indigo-300">
                <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                <span>Launching February 2027</span>
              </div>
              <h4 className="mt-2 text-lg font-bold text-white">Kubera.ai — Intelligence & Document Analysis Layer</h4>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-300">
                An AI intelligence extension for your existing license: automated audit assistance, document compliance verification,
                and collection forecasting with rolling projections.
              </p>
            </div>
            <span className="shrink-0 rounded-lg border border-indigo-400/30 bg-white/10 px-3 py-1.5 text-xs font-medium text-indigo-200">
              Future Roadmap
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
