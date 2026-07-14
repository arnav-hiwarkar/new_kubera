import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ShieldCheck, Layers, LineChart, AlertCircle } from 'lucide-react'
import { useCompanyAuth } from '@/auth/company'
import { ApiError } from '@/api/http'
import { Button, Field, Input } from '@/components/ui'

interface FormValues {
  email: string
  password: string
}

export function CompanyLogin() {
  const { signIn } = useCompanyAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>()

  const from = (location.state as { from?: string } | null)?.from ?? '/app'

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await signIn(values)
      navigate(from, { replace: true })
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Login failed. Please try again.')
    }
  })

  return (
    <AuthLayout accent="company" title="Welcome back" subtitle="Sign in to your compliance workspace">
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {formError && (
          <div className="flex items-center gap-2 rounded-btn border border-status-action/40 badge-bg-action px-3 py-2 text-sm text-status-action">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {formError}
          </div>
        )}
        <Field label="Email" htmlFor="email" required error={errors.email?.message}>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            placeholder="you@company.com"
            error={!!errors.email}
            {...register('email', { required: 'Email is required' })}
          />
        </Field>
        <Field label="Password" htmlFor="password" required error={errors.password?.message}>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            error={!!errors.password}
            {...register('password', { required: 'Password is required' })}
          />
        </Field>
        <Button type="submit" size="lg" loading={isSubmitting} className="mt-2 w-full">
          Sign In
        </Button>
        <p className="text-center text-sm text-text-secondary">
          Are you an auditor?{' '}
          <Link to="/auditor/login" className="font-medium text-accent hover:underline">
            Auditor portal
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}

/* ── Brand panel content per identity ───────────────────────────────────── */
const identity = {
  company: {
    wordmark: 'Kubera',
    tagline: 'The operating system for corporate compliance.',
    grad: 'from-accent to-accent-active',
    points: [
      { icon: Layers, text: 'Every module — DocVault, ROC, KRA, Assets & more — in one workspace.' },
      { icon: ShieldCheck, text: 'Bank-grade access control and a complete, tamper-evident audit trail.' },
      { icon: LineChart, text: 'Real-time visibility across your entire finance and compliance stack.' },
    ],
  },
  auditor: {
    wordmark: 'Kubera Audit',
    tagline: 'Run every engagement from a single, secure workspace.',
    grad: 'from-auditor to-auditor-hover',
    points: [
      { icon: Layers, text: 'Trial balances, mappings, requirements and queries — all in one place.' },
      { icon: ShieldCheck, text: 'Scoped, read-safe access to exactly the engagements you’re invited to.' },
      { icon: LineChart, text: 'Track balance checks and open items in real time as you work.' },
    ],
  },
}

/** Shared split-screen auth frame used by both identities' login/register. */
export function AuthLayout({
  accent,
  title,
  subtitle,
  children,
}: {
  accent: 'company' | 'auditor'
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  const id = identity[accent]
  const logoGrad = id.grad

  return (
    <div className="flex min-h-screen bg-bg-primary">
      {/* Brand panel */}
      <div className={`relative hidden w-1/2 overflow-hidden bg-gradient-to-br ${id.grad} lg:flex`}>
        {/* Aurora mesh */}
        <div className="pointer-events-none absolute inset-0 opacity-70">
          <div className="absolute -left-24 -top-24 h-96 w-96 rounded-full bg-white/20 blur-3xl" style={{ animation: 'aurora 18s ease-in-out infinite' }} />
          <div className="absolute bottom-0 right-0 h-[28rem] w-[28rem] rounded-full bg-black/20 blur-3xl" style={{ animation: 'aurora 22s ease-in-out infinite reverse' }} />
        </div>
        {/* Subtle grid */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              'linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)',
            backgroundSize: '44px 44px',
          }}
        />
        <div className="relative z-10 flex flex-col justify-between p-12 text-white">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/15 text-lg font-bold backdrop-blur-sm">
              K
            </span>
            <span className="text-lg font-bold tracking-display">{id.wordmark}</span>
          </div>

          <div className="max-w-md">
            <motion.h1
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className="text-3xl font-bold leading-tight tracking-display"
            >
              {id.tagline}
            </motion.h1>
            <ul className="mt-8 flex flex-col gap-4">
              {id.points.map((p, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: 0.15 + i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                  className="flex items-start gap-3 text-white/90"
                >
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/15 backdrop-blur-sm">
                    <p.icon className="h-4 w-4" />
                  </span>
                  <span className="text-base leading-relaxed">{p.text}</span>
                </motion.li>
              ))}
            </ul>
          </div>

          <p className="text-sm text-white/60">© {new Date().getFullYear()} Kubera. All rights reserved.</p>
        </div>
      </div>

      {/* Form panel */}
      <div className="flex w-full items-center justify-center px-6 py-12 lg:w-1/2">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-sm"
        >
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br ${logoGrad} text-md font-bold text-white`}>
              K
            </span>
            <span className="text-lg font-bold tracking-display text-text-primary">{id.wordmark}</span>
          </div>
          <h2 className="text-2xl font-bold tracking-display text-text-primary">{title}</h2>
          {subtitle && <p className="mb-7 mt-1.5 text-base text-text-secondary">{subtitle}</p>}
          {children}
        </motion.div>
      </div>
    </div>
  )
}
