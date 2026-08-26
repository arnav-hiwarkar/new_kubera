import { ShieldCheck, UserMinus, Zap, Lock, Sliders, TrendingUp } from 'lucide-react'

export function WhyItPaysOff() {
  const values = [
    {
      roman: 'I',
      icon: ShieldCheck,
      title: 'Always Audit-Ready',
      desc: 'Structured, retrievable statutory and compliance records the moment auditors or authorities ask for them.',
    },
    {
      roman: 'II',
      icon: UserMinus,
      title: 'Lower Key-Person Risk',
      desc: 'Governance knowledge and historical records live securely in the platform, not in individuals who may resign.',
    },
    {
      roman: 'III',
      icon: Zap,
      title: 'Faster Reviews',
      desc: 'Complete statutory audit, investor due-diligence, and executive management preparation in a fraction of the time.',
    },
    {
      roman: 'IV',
      icon: Lock,
      title: 'Confidential by Design',
      desc: 'Purpose-built access-controlled buckets protect sensitive board minutes, cap tables, and contracts.',
    },
    {
      roman: 'V',
      icon: Sliders,
      title: 'Standardised Formats',
      desc: 'Consistent statutory document standards and asset depreciation models across every department and entity.',
    },
    {
      roman: 'VI',
      icon: TrendingUp,
      title: 'Scales With You',
      desc: 'Seamlessly grows from a single operating SME to a multi-company conglomerate or holding group.',
    },
  ]

  return (
    <section id="why-it-pays-off" className="border-t border-slate-200/80 bg-slate-50/50 py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <div className="text-xs font-bold tracking-wider text-indigo-600 uppercase">
            Why It Pays Off
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            The value, in plain terms.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">
            Tangible operational governance and risk reduction for company leadership.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {values.map((v, i) => {
            const Icon = v.icon
            return (
              <div
                key={i}
                className="group relative rounded-2xl border border-slate-200 bg-white p-6 shadow-xs transition hover:border-indigo-300 hover:shadow-md"
              >
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 transition group-hover:bg-indigo-600 group-hover:text-white">
                    <Icon className="h-5 w-5" />
                  </div>
                  <span className="font-mono text-xs font-bold text-slate-400">
                    {v.roman}
                  </span>
                </div>
                <h3 className="mt-5 text-sm font-bold text-slate-900">{v.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-600">{v.desc}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
