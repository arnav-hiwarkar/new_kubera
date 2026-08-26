import { Check, Shield, ArrowRight, Sparkles } from 'lucide-react'

interface PricingSectionProps {
  onRequestAccess: () => void
}

export function PricingSection({ onRequestAccess }: PricingSectionProps) {
  const tiers = [
    {
      name: 'STANDARD',
      price: '₹60,000',
      period: 'per year',
      scope: 'Up to 2 companies',
      desc: 'Core compliance repository and statutory features for a focused operating SME.',
      features: [
        'docVault Encrypted Repository (2 entities)',
        'Fixed Asset Register & Depreciation',
        'AuditEase Scoped Auditor Workflows',
        'Standard Role-Based Access Control',
        'Standard Support & Migration Assistance',
      ],
      popular: false,
      buttonText: 'Select Standard',
    },
    {
      name: 'PRO',
      price: '₹100,000',
      period: 'per year',
      scope: 'Up to 4 companies',
      desc: 'Multi-company configuration and extended modules for growing business groups.',
      features: [
        'Everything in Standard, up to 4 entities',
        'Dual-Book Companies Act & IT Act Depreciation',
        'AuditEase Multi-Cycle & PBC Management',
        'PMO / CEO Office & KRA Tracking',
        'Rolling Collections & Executive Cash Forecasts',
        'Priority Technical & Onboarding Support',
      ],
      popular: true,
      buttonText: 'Select Pro',
    },
    {
      name: 'ENTERPRISE',
      price: 'Custom',
      period: 'tailored on request',
      scope: 'Above 5 companies',
      desc: 'Tailored compliance architecture, custom master data, and white-labelled options.',
      features: [
        'Unlimited or 5+ Group Entities',
        'Dedicated Master Data & Statutory Setup',
        'Custom Roles, Domains & White-Labelling',
        'Dedicated Onboarding Account Manager',
        'Tailored SLA & Direct Operator Assistance',
      ],
      popular: false,
      buttonText: 'Request Enterprise',
    },
  ]

  return (
    <section id="pricing" className="py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <div className="text-xs font-bold tracking-wider text-indigo-600 uppercase">
            Membership
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Introductory pricing, sized to your business.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">
            Predictable SaaS subscriptions without internal systems to build or maintain.
          </p>
        </div>

        {/* Pricing Cards */}
        <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-3">
          {tiers.map((tier, i) => (
            <div
              key={i}
              className={`relative flex flex-col justify-between rounded-3xl p-8 shadow-xs ${
                tier.popular
                  ? 'border-2 border-indigo-600 bg-white ring-4 ring-indigo-500/10 shadow-lg'
                  : 'border border-slate-200 bg-white'
              }`}
            >
              {tier.popular && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-3 py-1 text-[11px] font-bold tracking-wider text-white uppercase shadow-sm">
                    <Sparkles className="h-3 w-3" /> Most Popular
                  </span>
                </div>
              )}

              <div>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold tracking-wider text-slate-900 uppercase">
                    {tier.name}
                  </h3>
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                    {tier.scope}
                  </span>
                </div>

                <div className="mt-6 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
                    {tier.price}
                  </span>
                  <span className="text-xs font-semibold text-slate-500">{tier.period}</span>
                </div>

                <p className="mt-3 text-xs leading-relaxed text-slate-600">{tier.desc}</p>

                <div className="mt-6 border-t border-slate-100 pt-6">
                  <div className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
                    What’s Included
                  </div>
                  <ul className="mt-4 space-y-3">
                    {tier.features.map((feat, fidx) => (
                      <li key={fidx} className="flex items-start gap-2.5 text-xs font-medium text-slate-700">
                        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-600" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-8">
                <button
                  type="button"
                  onClick={onRequestAccess}
                  className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-semibold shadow-xs transition ${
                    tier.popular
                      ? 'bg-indigo-600 text-white hover:bg-indigo-500'
                      : 'bg-slate-900 text-white hover:bg-slate-800'
                  }`}
                >
                  <span>{tier.buttonText}</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Payment & Terms Details */}
        <div className="mt-12 grid grid-cols-1 gap-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-6 sm:grid-cols-3 sm:p-8">
          <div>
            <div className="text-xs font-bold text-slate-900 uppercase">Payment Model</div>
            <p className="mt-1 text-xs text-slate-600">
              50% advance on signing, balance 50% within three months of onboarding.
            </p>
          </div>
          <div>
            <div className="text-xs font-bold text-slate-900 uppercase">Applicable Taxes</div>
            <p className="mt-1 text-xs text-slate-600">
              GST and statutory taxes charged extra, as applicable.
            </p>
          </div>
          <div>
            <div className="text-xs font-bold text-slate-900 uppercase">Deployment</div>
            <p className="mt-1 text-xs text-slate-600">
              SaaS subscription with managed encryption keys and zero infrastructure maintenance.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
