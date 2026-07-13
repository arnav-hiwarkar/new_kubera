import { companyClient } from '@/api/clients/company'
import { auditorClient } from '@/api/clients/auditor'
import type {
  LoginRequest,
  TokenResponse,
  AuditorRegister,
  AuditorOut,
  CompanyUserOut,
} from '@/api/types'

/** Company identity auth. Login/refresh handled by the HttpClient adapter. */
export const companyAuth = {
  login: (body: LoginRequest) =>
    companyClient.post<TokenResponse>('/api/v1/auth/company/login', { body }),
  me: () => companyClient.get<CompanyUserOut>('/api/v1/auth/company/me'),
}

/** Auditor identity auth — includes open self-registration. */
export const auditorAuth = {
  register: (body: AuditorRegister) =>
    auditorClient.post<AuditorOut>('/api/v1/auth/auditor/register', { body }),
  login: (body: LoginRequest) =>
    auditorClient.post<TokenResponse>('/api/v1/auth/auditor/login', { body }),
  me: () => auditorClient.get<AuditorOut>('/api/v1/auth/auditor/me'),
}
