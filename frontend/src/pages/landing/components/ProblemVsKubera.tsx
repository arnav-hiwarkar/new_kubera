import { XCircle, CheckCircle2, ShieldAlert, Sparkles } from 'lucide-react'

export function ProblemVsKubera() {
  const problems = [
    {
      title: 'Scattered Documentation',
      desc: 'Records chased across HR, Finance, Secretarial, and the CEO office under audit or tax filing deadlines.',
    },
    {
      title: 'Fragile Institutional Memory',
      desc: 'Critical governance knowledge, filings, and contracts walk out the door when key employees resign.',
    },
    {
      title: 'Drifting Standards & Formats',
      desc: 'Spreadsheet models and statutory compliance formats drift inconsistently with every new hire.',
    },
    {
      title: 'Unready for Due Diligence',
      desc: 'No single, secure source of truth to govern entities with confidence during audits or acquisitions.',
    },
  ]

  const solutions = [
    {
      title: 'Access-Controlled Buckets',
      desc: 'Every statutory record stored in dedicated role-isolated buckets, retrievable in seconds.',
    },
    {
      title: 'Continuous Institutional Memory',
      desc: 'Governance structure and historical audit records that outlast any individual employee.',
    },
    {
      title: 'Standardised Dual Regimes',
      desc: 'Standardized workflows and statutory depreciation rules across all departments and group entities.',
    },
    {
      title: 'Audit-Ready On Demand',
      desc: 'Scoped auditor access, trial balance imports, query trails, and instant compliance verification.',
    },
  ]

  return (
    <section id="why-kubera" className="border-y border-slate-200/80 bg-slate-50/50 py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <div className="text-xs font-bold tracking-wider text-indigo-600 uppercase">
            Why Kubera
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Compliance shouldn’t live in someone’s inbox.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">
            For owners, CEOs, and CFOs, statutory documentation is scattered across departments and people — until an audit,
            a due-diligence request, or a resignation makes that fragility expensive.
          </p>
        </div>

        {/* Side-by-side contrast cards */}
        <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-2">
          {/* The Problem Today */}
          <div className="rounded-2xl border border-rose-200/70 bg-white p-6 shadow-xs sm:p-8">
            <div className="flex items-center gap-3 border-b border-rose-100 pb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-50 text-rose-600">
                <ShieldAlert className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">The Problem Today</h3>
                <p className="text-xs text-slate-500">Unstructured inboxes & operational risk</p>
              </div>
            </div>
            <ul className="mt-6 space-y-5">
              {problems.map((item, i) => (
                <li key={i} className="flex items-start gap-3">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
                  <div>
                    <strong className="text-xs font-semibold text-slate-800">{item.title}: </strong>
                    <span className="text-xs text-slate-600">{item.desc}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* With Kubera */}
          <div className="rounded-2xl border border-indigo-200/80 bg-white p-6 shadow-sm ring-1 ring-indigo-500/10 sm:p-8">
            <div className="flex items-center gap-3 border-b border-indigo-100 pb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">With Kubera</h3>
                <p className="text-xs text-indigo-600 font-medium">Governed compliance & continuous treasury</p>
              </div>
            </div>
            <ul className="mt-6 space-y-5">
              {solutions.map((item, i) => (
                <li key={i} className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
                  <div>
                    <strong className="text-xs font-semibold text-slate-900">{item.title}: </strong>
                    <span className="text-xs text-slate-600">{item.desc}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Pull Quote */}
        <div className="mt-12 rounded-2xl bg-slate-900 p-8 text-center text-white shadow-sm">
          <p className="text-base font-medium text-slate-200 sm:text-lg">
            “A practical compliance operating layer for SMEs that need real governance — without building complex internal systems.”
          </p>
          <div className="mt-3 text-xs tracking-wider text-indigo-300 font-semibold uppercase">
            Kubera Corporate Compliance · Built by ETHDC
          </div>
        </div>
      </div>
    </section>
  )
}
