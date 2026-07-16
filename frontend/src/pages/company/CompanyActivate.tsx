import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { companyAuth } from '@/api/endpoints/auth'
import { ApiError } from '@/api/http'
import { Button, Field, Input } from '@/components/ui'
import { AuthLayout } from '@/pages/company/CompanyLogin'

interface FormValues {
  email: string
  activation_key: string
  full_name: string
  password: string
  confirmPassword: string
}

export function CompanyActivate() {
  const navigate = useNavigate()
  const [formError, setFormError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>()

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await companyAuth.activate({
        email: values.email,
        activation_key: values.activation_key.trim(),
        password: values.password,
        full_name: values.full_name,
      })
      setDone(true)
      // Give the user a moment to read the success note, then send to login.
      setTimeout(() => navigate('/login', { replace: true }), 1800)
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : 'Activation failed. Please try again.',
      )
    }
  })

  if (done) {
    return (
      <AuthLayout accent="company" title="Account activated" subtitle="Redirecting you to sign in…">
        <div className="flex items-center gap-2 rounded-btn border border-status-verified/40 bg-status-verified/10 px-3 py-2 text-sm text-status-verified">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          Your password is set. You can now sign in with your email and password.
        </div>
        <Link to="/login" className="mt-4 block text-center text-sm font-medium text-accent hover:underline">
          Go to sign in
        </Link>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      accent="company"
      title="Activate your account"
      subtitle="Enter the product key we sent you, then choose a password"
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {formError && (
          <div className="flex items-center gap-2 rounded-btn border border-status-action/40 badge-bg-action px-3 py-2 text-sm text-status-action">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {formError}
          </div>
        )}
        <Field label="Registered email" htmlFor="email" required error={errors.email?.message}>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            placeholder="you@company.com"
            error={!!errors.email}
            {...register('email', { required: 'Email is required' })}
          />
        </Field>
        <Field label="Product key" htmlFor="activation_key" required error={errors.activation_key?.message}>
          <Input
            id="activation_key"
            type="text"
            placeholder="Paste the key we gave you"
            error={!!errors.activation_key}
            {...register('activation_key', { required: 'Product key is required' })}
          />
        </Field>
        <Field label="Your name" htmlFor="full_name" required error={errors.full_name?.message}>
          <Input
            id="full_name"
            type="text"
            autoComplete="name"
            placeholder="Full name"
            error={!!errors.full_name}
            {...register('full_name', { required: 'Name is required' })}
          />
        </Field>
        <Field label="Password" htmlFor="password" required error={errors.password?.message}>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            placeholder="At least 8 characters"
            error={!!errors.password}
            {...register('password', {
              required: 'Password is required',
              minLength: { value: 8, message: 'Password must be at least 8 characters' },
            })}
          />
        </Field>
        <Field label="Confirm password" htmlFor="confirmPassword" required error={errors.confirmPassword?.message}>
          <Input
            id="confirmPassword"
            type="password"
            autoComplete="new-password"
            placeholder="Re-enter your password"
            error={!!errors.confirmPassword}
            {...register('confirmPassword', {
              required: 'Please confirm your password',
              validate: (v) => v === watch('password') || 'Passwords do not match',
            })}
          />
        </Field>
        <Button type="submit" size="lg" loading={isSubmitting} className="mt-2 w-full">
          Activate & set password
        </Button>
        <p className="text-center text-sm text-text-secondary">
          Already activated?{' '}
          <Link to="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
