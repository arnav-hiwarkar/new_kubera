import { useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, CheckCircle2, ShieldCheck, Database, Layers, FileCheck, Sparkles } from 'lucide-react'

interface LandingHeroProps {
  onDirectSubmit: (email: string) => void
}

export function LandingHero({ onDirectSubmit }: LandingHeroProps) {
  const [email, setEmail] = useState('')
  const [quickSubmitted, setQuickSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleHeroSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return

    setLoading(true)
    try {
      const res = await fetch('/api/v1/leads/interest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })
      if (res.ok) {
        setQuickSubmitted(true)
      } else {
        onDirectSubmit(email.trim())
      }
    } catch {
      onDirectSubmit(email.trim())
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="relative overflow-hidden pt-12 pb-20 sm:pt-16 sm:pb-28">
      {/* Subtle background radial glow */}
      <div
        className="pointer-events-none absolute top-0 left-1/2 -z-10 h-[500px] w-full max-w-7xl -translate-x-1/2 opacity-40 blur-3xl"
        style={{
          background: 'radial-gradient(ellipse 60% 50% at 50% 0%, rgba(99, 102, 241, 0.25), transparent)',
        }}
      />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          {/* Tagline Badge */}
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2 rounded-full border border-indigo-200/80 bg-indigo-50/70 px-3.5 py-1 text-xs font-semibold text-indigo-700 shadow-2xs"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
            <span>SaaS · Built for SMEs & Multi-Company Groups</span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mt-6 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-5xl sm:leading-[1.15]"
          >
            A secure treasury for the records that keep your company{' '}
            <span className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-slate-900 bg-clip-text text-transparent">
              compliant, audit-ready, and continuous.
            </span>
          </motion.h1>

          {/* Subheading */}
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="mt-6 text-base leading-relaxed text-slate-600 sm:text-lg"
          >
            Compliance shouldn’t live in someone’s inbox. Kubera turns scattered statutory documentation,
            fixed asset depreciation regimes, and auditor workflows into one access-controlled system of record.
          </motion.p>

          {/* Email Capture CTA */}
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="mt-8 flex justify-center"
          >
            {quickSubmitted ? (
              <div className="flex items-center gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm font-medium text-emerald-800 shadow-xs">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                <span>Thank you! We’ve received your inquiry and will reach out to configure your access.</span>
              </div>
            ) : (
              <form
                onSubmit={handleHeroSubmit}
                className="flex w-full max-w-md flex-col gap-2.5 sm:flex-row sm:items-center"
              >
                <div className="relative flex-1">
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter work email (e.g. cfo@company.com)"
                    className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm shadow-xs placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900/20 disabled:opacity-60"
                >
                  <span>Request Access</span>
                  <ArrowRight className="h-4 w-4 text-indigo-400" />
                </button>
              </form>
            )}
          </motion.div>

          {/* Security & Feature Badges */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            className="mt-12 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-xs font-medium text-slate-500"
          >
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-indigo-600" />
              <span>Role-Based Access Buckets</span>
            </div>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-indigo-600" />
              <span>Dual-Book Depreciation</span>
            </div>
            <div className="flex items-center gap-2">
              <FileCheck className="h-4 w-4 text-indigo-600" />
              <span>Tamper-Evident Logs</span>
            </div>
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-600" />
              <span>Multi-Entity Consolidation</span>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
