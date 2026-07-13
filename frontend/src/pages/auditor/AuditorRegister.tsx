import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, Link } from 'react-router-dom'
import { auditorAuth } from '@/api/endpoints/auth'
import { useAuditorAuth } from '@/auth/auditor'
import { ApiError } from '@/api/http'
import { Button, Field, Input, useToast } from '@/components/ui'
import { AuthLayout } from '@/pages/company/CompanyLogin'

interface FormValues {
  name: string
  email: string
  password: string
}

export function AuditorRegister() {
  const { signIn } = useAuditorAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>()

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await auditorAuth.register(values)
      // Backend registration doesn't return tokens, so log in immediately after.
      await signIn({ email: values.email, password: values.password })
      toast.success('Account created')
      navigate('/auditor/app', { replace: true })
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Registration failed.')
    }
  })

  return (
    <AuthLayout accent="auditor" title="Auditor Registration" subtitle="Self-service auditor sign up">
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {formError && (
          <div className="rounded-btn border border-status-action/40 badge-bg-action px-3 py-2 text-sm text-status-action">
            {formError}
          </div>
        )}
        <Field label="Full name" htmlFor="name" required error={errors.name?.message}>
          <Input id="name" error={!!errors.name} {...register('name', { required: 'Name is required' })} />
        </Field>
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
            autoComplete="new-password"
            error={!!errors.password}
            {...register('password', { required: 'Password is required', minLength: { value: 8, message: 'Min 8 characters' } })}
          />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-2 w-full bg-auditor hover:bg-auditor-hover">
          Create account
        </Button>
        <p className="text-center text-sm text-text-secondary">
          Already registered?{' '}
          <Link to="/auditor/login" className="text-auditor hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
