import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useLocation, Link } from 'react-router-dom'
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
    <AuthLayout accent="company" title="Company Sign In" subtitle="Access your compliance workspace">
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {formError && (
          <div className="rounded-btn border border-status-action/40 badge-bg-action px-3 py-2 text-sm text-status-action">
            {formError}
          </div>
        )}
        <Field label="Email" htmlFor="email" required error={errors.email?.message}>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            error={!!errors.email}
            {...register('email', { required: 'Email is required' })}
          />
        </Field>
        <Field label="Password" htmlFor="password" required error={errors.password?.message}>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            error={!!errors.password}
            {...register('password', { required: 'Password is required' })}
          />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
          Sign In
        </Button>
        <p className="text-center text-sm text-text-secondary">
          Are you an auditor?{' '}
          <Link to="/auditor/login" className="text-accent hover:underline">
            Auditor portal
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}

/** Shared centered auth-page frame used by both identities' login/register. */
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
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <span
            className={`flex h-8 w-8 items-center justify-center rounded text-sm font-bold text-white ${
              accent === 'auditor' ? 'bg-auditor' : 'bg-accent'
            }`}
          >
            K
          </span>
          <span className="text-lg font-semibold text-text-primary">
            {accent === 'auditor' ? 'Kubera Audit' : 'Kubera'}
          </span>
        </div>
        <div className="rounded-card border border-border bg-bg-surface p-6 shadow-card">
          <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
          {subtitle && <p className="mb-5 mt-1 text-sm text-text-secondary">{subtitle}</p>}
          {children}
        </div>
      </div>
    </div>
  )
}
