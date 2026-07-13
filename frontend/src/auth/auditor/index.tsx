import { createIdentityAuth } from '@/auth/createIdentityAuth'
import { auditorTokenStorage } from '@/auth/tokenStorage'
import { auditorAuth } from '@/api/endpoints/auth'
import { setAuditorAuthFailureHandler } from '@/api/clients/auditor'
import type { AuditorOut } from '@/api/types'

const auditor = createIdentityAuth<AuditorOut>({
  name: 'Auditor',
  storage: auditorTokenStorage,
  loadProfile: () => auditorAuth.me(),
  login: (credentials) => auditorAuth.login(credentials),
  loginPath: '/auditor/login',
  registerFailureHandler: setAuditorAuthFailureHandler,
})

export const AuditorAuthProvider = auditor.Provider
export const useAuditorAuth = auditor.useAuth
export const AuditorGuard = auditor.Guard
