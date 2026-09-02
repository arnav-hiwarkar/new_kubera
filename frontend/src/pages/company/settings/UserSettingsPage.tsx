import { useState, useMemo, useRef } from 'react'
import { Card, Button, Field, Input } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { useChangePassword, useUploadAvatar, useUserAvatar } from '@/api/hooks/users'
import { AvatarCropperModal } from '@/components/users/AvatarCropperModal'
import { passwordRules } from '@/utils/passwordValidation'
import {
  User,
  Shield,
  Key,
  Camera,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Eye,
  EyeOff,
  Clock,
  Briefcase,
  Mail,
} from 'lucide-react'

const SPECIAL_CHARS_REGEX = /[-!@#$%^&*(),.?":{}|<>_=+`~/\\[\];]/

export function UserSettingsPage() {
  const { profile } = useCompanyAuth()
  const { avatarUrl } = useUserAvatar(profile?.id, profile?.has_avatar)
  const changePasswordMutation = useChangePassword()
  const uploadAvatarMutation = useUploadAvatar()

  // File picker state
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedImageSrc, setSelectedImageSrc] = useState<string | null>(null)
  const [isCropperOpen, setIsCropperOpen] = useState(false)
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const [avatarSuccess, setAvatarSuccess] = useState<string | null>(null)

  // Password form state
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showOldPassword, setShowOldPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null)

  // 3-hour avatar cooldown check
  const avatarCooldown = useMemo(() => {
    if (!profile?.avatar_updated_at) return null
    const updated = new Date(profile.avatar_updated_at)
    const now = new Date()
    const diffMs = now.getTime() - updated.getTime()
    const cooldownMs = 3 * 60 * 60 * 1000
    if (diffMs < cooldownMs) {
      const remainingMinutes = Math.ceil((cooldownMs - diffMs) / (60 * 1000))
      const hours = Math.floor(remainingMinutes / 60)
      const minutes = remainingMinutes % 60
      return {
        active: true,
        remainingText: hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`,
        nextAllowed: new Date(updated.getTime() + cooldownMs).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
      }
    }
    return null
  }, [profile?.avatar_updated_at])

  // 30-day password cooldown check
  const passwordCooldown = useMemo(() => {
    if (!profile?.password_changed_at) return null
    const changed = new Date(profile.password_changed_at)
    const now = new Date()
    const diffMs = now.getTime() - changed.getTime()
    const cooldownMs = 30 * 24 * 60 * 60 * 1000
    if (diffMs < cooldownMs) {
      const remainingDays = Math.ceil((cooldownMs - diffMs) / (24 * 60 * 60 * 1000))
      return {
        active: true,
        remainingDays,
        lastChangedDate: changed.toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        }),
        nextAllowedDate: new Date(changed.getTime() + cooldownMs).toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        }),
      }
    }
    return null
  }, [profile?.password_changed_at])

  // Real-time password criteria
  const passwordCriteria = useMemo(() => {
    return {
      hasMinLength: newPassword.length >= passwordRules.minLength.value,
      hasMaxLength: newPassword.length <= passwordRules.maxLength.value,
      hasUppercase: /[A-Z]/.test(newPassword),
      hasLowercase: /[a-z]/.test(newPassword),
      hasNumber: /[0-9]/.test(newPassword),
      hasSpecial: SPECIAL_CHARS_REGEX.test(newPassword),
      isDifferentFromOld: oldPassword ? newPassword !== oldPassword : true,
      matchesConfirm: confirmPassword.length > 0 && newPassword === confirmPassword,
    }
  }, [newPassword, oldPassword, confirmPassword])

  const isPasswordValid =
    passwordCriteria.hasMinLength &&
    passwordCriteria.hasMaxLength &&
    passwordCriteria.hasUppercase &&
    passwordCriteria.hasLowercase &&
    passwordCriteria.hasNumber &&
    passwordCriteria.hasSpecial &&
    passwordCriteria.isDifferentFromOld &&
    passwordCriteria.matchesConfirm &&
    oldPassword.length > 0

  // File selection
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setAvatarError(null)
    setAvatarSuccess(null)
    const file = e.target.files?.[0]
    if (!file) return

    if (file.size > 1024 * 1024) {
      setAvatarError('File size exceeds 1 MB. Please choose a smaller image.')
      return
    }

    const acceptedTypes = ['image/jpeg', 'image/png', 'image/webp']
    if (!acceptedTypes.includes(file.type)) {
      setAvatarError('Unsupported image format. Please upload a JPG, PNG, or WEBP.')
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      setSelectedImageSrc(reader.result as string)
      setIsCropperOpen(true)
    }
    reader.readAsDataURL(file)

    // Reset input so re-selecting the same file triggers onChange
    e.target.value = ''
  }

  // Upload cropped avatar
  const handleCropComplete = async (blob: Blob) => {
    setAvatarError(null)
    setAvatarSuccess(null)
    try {
      await uploadAvatarMutation.mutateAsync(blob)
      setAvatarSuccess('Profile picture updated successfully!')
      setTimeout(() => setAvatarSuccess(null), 5000)
    } catch (err) {
      setAvatarError(err instanceof Error ? err.message : 'Failed to upload profile picture.')
    }
  }

  // Submit password change
  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isPasswordValid) return
    setPasswordError(null)
    setPasswordSuccess(null)

    try {
      await changePasswordMutation.mutateAsync({
        old_password: oldPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      })
      setPasswordSuccess('Your password has been changed successfully.')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setTimeout(() => setPasswordSuccess(null), 5000)
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Failed to change password.')
    }
  }

  const initials = (profile?.full_name || profile?.email || '?')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  const canChangePassword = profile?.can_change_password !== false

  return (
    <div className="mx-auto max-w-4xl space-y-8 pb-12">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-text-primary">User Settings</h1>
        <p className="text-sm text-text-secondary mt-1">
          Manage your personal profile, security credentials, and account details.
        </p>
      </div>

      {/* 1. Account Details Overview */}
      <Card className="p-6">
        <div className="flex items-center gap-3 border-b border-border pb-4 mb-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
            <User className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-text-primary">Account Details</h2>
            <p className="text-xs text-text-muted">Your identity and organizational role.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <span className="block text-xs font-medium text-text-muted mb-1">Full Name</span>
            <p className="text-sm font-semibold text-text-primary">{profile?.full_name || '—'}</p>
          </div>

          <div>
            <span className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1">
              <Mail className="h-3 w-3" /> Email Address
            </span>
            <p className="text-sm font-medium text-text-primary">{profile?.email || '—'}</p>
          </div>

          <div>
            <span className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1">
              <Shield className="h-3 w-3" /> Role & Privilege
            </span>
            <span className="inline-flex items-center rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-accent">
              {profile?.role || 'employee'}
            </span>
          </div>

          <div>
            <span className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1">
              <Briefcase className="h-3 w-3" /> Department & Designation
            </span>
            <p className="text-sm text-text-secondary">
              {profile?.designation || 'No designation'}
              {profile?.department && ` • ${profile.department}`}
            </p>
          </div>
        </div>
      </Card>

      {/* 2. Profile Picture */}
      <Card className="p-6">
        <div className="flex items-center justify-between border-b border-border pb-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
              <Camera className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">Profile Picture</h2>
              <p className="text-xs text-text-muted">
                Displayed in the top navigation bar and comments. Max 1 MB (JPG, PNG, WEBP).
              </p>
            </div>
          </div>
        </div>

        {avatarError && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-status-action/10 border border-status-action/20 p-3 text-sm text-status-action">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{avatarError}</span>
          </div>
        )}

        {avatarSuccess && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-status-good/10 border border-status-good/20 p-3 text-sm text-status-good">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{avatarSuccess}</span>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center gap-6">
          {/* Avatar display */}
          <div className="relative group">
            <div className="h-24 w-24 overflow-hidden rounded-full border-2 border-accent/40 bg-gradient-to-br from-accent to-accent-active shadow-md flex items-center justify-center text-white text-2xl font-bold">
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt={profile?.full_name || 'Avatar'}
                  className="h-full w-full object-cover"
                />
              ) : (
                <span>{initials}</span>
              )}
            </div>
          </div>

          <div className="flex flex-col items-center sm:items-start gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={handleFileSelect}
              className="hidden"
            />

            {avatarCooldown?.active ? (
              <div className="flex items-center gap-2 text-xs text-text-muted bg-bg-raised border border-border rounded-lg px-3 py-2">
                <Clock className="h-3.5 w-3.5 text-accent" />
                <span>
                  Photo changed recently. Next update allowed at{' '}
                  <strong className="text-text-primary">{avatarCooldown.nextAllowed}</strong> (in{' '}
                  {avatarCooldown.remainingText}).
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <Button
                  variant="primary"
                  onClick={() => fileInputRef.current?.click()}
                  loading={uploadAvatarMutation.isPending}
                >
                  <Camera className="h-4 w-4 mr-2" />
                  Upload New Photo
                </Button>
                <span className="text-xs text-text-muted">JPG, PNG, or WEBP (Max 1 MB)</span>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* 3. Password Management (Conditionally Rendered) */}
      {canChangePassword && (
        <Card className="p-6">
          <div className="flex items-center gap-3 border-b border-border pb-4 mb-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
              <Key className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">Change Password</h2>
              <p className="text-xs text-text-muted">
                Update your login credentials. Passwords must satisfy enterprise security complexity.
              </p>
            </div>
          </div>

          {passwordCooldown?.active && (
            <div className="mb-6 flex items-start gap-3 rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-sm text-amber-500">
              <Clock className="h-5 w-5 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-semibold">30-Day Cooldown Active</strong>
                <span>
                  You last changed your password on {passwordCooldown.lastChangedDate}. You can update
                  your password again on{' '}
                  <strong>{passwordCooldown.nextAllowedDate}</strong> (in {passwordCooldown.remainingDays}{' '}
                  days).
                </span>
              </div>
            </div>
          )}

          {passwordError && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-status-action/10 border border-status-action/20 p-3 text-sm text-status-action">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{passwordError}</span>
            </div>
          )}

          {passwordSuccess && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-status-good/10 border border-status-good/20 p-3 text-sm text-status-good">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{passwordSuccess}</span>
            </div>
          )}

          <form onSubmit={handlePasswordSubmit} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Old Password */}
              <Field label="Current Password" htmlFor="oldPassword" required>
                <div className="relative">
                  <Input
                    id="oldPassword"
                    type={showOldPassword ? 'text' : 'password'}
                    value={oldPassword}
                    onChange={(e) => setOldPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    disabled={!!passwordCooldown?.active || changePasswordMutation.isPending}
                  />
                  <button
                    type="button"
                    onClick={() => setShowOldPassword((s) => !s)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-1"
                  >
                    {showOldPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>

              {/* New Password */}
              <Field label="New Password" htmlFor="newPassword" required>
                <div className="relative">
                  <Input
                    id="newPassword"
                    type={showNewPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    disabled={!!passwordCooldown?.active || changePasswordMutation.isPending}
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword((s) => !s)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-1"
                  >
                    {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>

              {/* Confirm New Password */}
              <Field label="Confirm New Password" htmlFor="confirmPassword" required>
                <div className="relative">
                  <Input
                    id="confirmPassword"
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    disabled={!!passwordCooldown?.active || changePasswordMutation.isPending}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((s) => !s)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-1"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>
            </div>

            {/* Real-time Checklist */}
            <div className="rounded-lg border border-border bg-bg-raised/50 p-4 space-y-2">
              <span className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
                Password Requirements
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <div className="flex items-center gap-1.5">
                  {passwordCriteria.hasMinLength && passwordCriteria.hasMaxLength ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-good shrink-0" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-text-muted shrink-0" />
                  )}
                  <span className={passwordCriteria.hasMinLength && passwordCriteria.hasMaxLength ? 'text-status-good font-medium' : 'text-text-muted'}>
                    8 to 72 characters
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {passwordCriteria.hasUppercase ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-good shrink-0" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-text-muted shrink-0" />
                  )}
                  <span className={passwordCriteria.hasUppercase ? 'text-status-good font-medium' : 'text-text-muted'}>
                    1 uppercase letter (A-Z)
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {passwordCriteria.hasLowercase ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-good shrink-0" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-text-muted shrink-0" />
                  )}
                  <span className={passwordCriteria.hasLowercase ? 'text-status-good font-medium' : 'text-text-muted'}>
                    1 lowercase letter (a-z)
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {passwordCriteria.hasNumber ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-good shrink-0" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-text-muted shrink-0" />
                  )}
                  <span className={passwordCriteria.hasNumber ? 'text-status-good font-medium' : 'text-text-muted'}>
                    1 number (0-9)
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {passwordCriteria.hasSpecial ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-good shrink-0" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-text-muted shrink-0" />
                  )}
                  <span className={passwordCriteria.hasSpecial ? 'text-status-good font-medium' : 'text-text-muted'}>
                    1 special character (!@#$)
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {passwordCriteria.matchesConfirm ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-good shrink-0" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-text-muted shrink-0" />
                  )}
                  <span className={passwordCriteria.matchesConfirm ? 'text-status-good font-medium' : 'text-text-muted'}>
                    Passwords match
                  </span>
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                type="submit"
                variant="primary"
                loading={changePasswordMutation.isPending}
                disabled={!isPasswordValid || !!passwordCooldown?.active}
              >
                Update Password
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Avatar Cropper Modal */}
      <AvatarCropperModal
        isOpen={isCropperOpen}
        imageSrc={selectedImageSrc}
        onClose={() => {
          setIsCropperOpen(false)
          setSelectedImageSrc(null)
        }}
        onCropComplete={handleCropComplete}
      />
    </div>
  )
}
