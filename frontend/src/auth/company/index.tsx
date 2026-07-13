import { createIdentityAuth } from '@/auth/createIdentityAuth'
import { companyTokenStorage } from '@/auth/tokenStorage'
import { companyAuth } from '@/api/endpoints/auth'
import { setCompanyAuthFailureHandler } from '@/api/clients/company'
import type { CompanyUserOut } from '@/api/types'

const company = createIdentityAuth<CompanyUserOut>({
  name: 'Company',
  storage: companyTokenStorage,
  loadProfile: () => companyAuth.me(),
  login: (credentials) => companyAuth.login(credentials),
  loginPath: '/login',
  registerFailureHandler: setCompanyAuthFailureHandler,
})

export const CompanyAuthProvider = company.Provider
export const useCompanyAuth = company.useAuth
export const CompanyGuard = company.Guard
