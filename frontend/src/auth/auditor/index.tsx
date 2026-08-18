import { createIdentityAuth } from '@/auth/createIdentityAuth'
import { auditorTokenStorage } from '@/auth/tokenStorage'
import { auditorAuth } from '@/api/endpoints/auth'
import { setAuditorAuthFailureHandler } from '@/api/clients/auditor'
import { queryClient } from '@/lib/queryClient'
import type { AuditorOut } from '@/api/types'

const auditor = createIdentityAuth<AuditorOut>({
  name: 'Auditor',
  storage: auditorTokenStorage,
  loadProfile: () => auditorAuth.me(),
  login: (credentials) => auditorAuth.login(credentials),
  loginPath: '/auditor/login',
  registerFailureHandler: setAuditorAuthFailureHandler,
  // Drop cached data on sign-in/out so a new session never sees stale data.
  clearCache: () => queryClient.clear(),
})

export const AuditorAuthProvider = auditor.Provider
export const useAuditorAuth = auditor.useAuth
export const AuditorGuard = auditor.Guard
