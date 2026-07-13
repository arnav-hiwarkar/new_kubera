import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useAuditorAuth } from '@/auth/auditor'
import { ApiError } from '@/api/http'
import { Button, Field, Input } from '@/components/ui'
import { AuthLayout } from '@/pages/company/CompanyLogin'

interface FormValues {
  email: string
  password: string
}

export function AuditorLogin() {
  const { signIn } = useAuditorAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>()

  const from = (location.state as { from?: string } | null)?.from ?? '/auditor/app'

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
    <AuthLayout accent="auditor" title="Auditor Sign In" subtitle="Access your assigned engagements">
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
        <Button type="submit" loading={isSubmitting} className="mt-2 w-full bg-auditor hover:bg-auditor-hover">
          Sign In
        </Button>
        <p className="text-center text-sm text-text-secondary">
          New auditor?{' '}
          <Link to="/auditor/register" className="text-auditor hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
