import { companyClient } from '@/api/clients/company'

export interface CompanySmtpConfig {
  configured: boolean
  host: string | null
  port: number
  user: string | null
  from_email: string | null
  from_name: string | null
  use_tls: boolean
  use_ssl: boolean
  is_active: boolean
  has_password: boolean
  last_tested_at: string | null
}

export interface CompanySmtpUpdate {
  host: string
  port: number
  user: string
  password?: string
  from_email: string
  from_name: string
  use_tls: boolean
  use_ssl: boolean
  is_active: boolean
}

export interface CompanySmtpVerifyPayload {
  host?: string
  port?: number
  user?: string
  password?: string
  from_email?: string
  from_name?: string
  use_tls?: boolean
  use_ssl?: boolean
}

export interface CompanySmtpVerifyResponse {
  success: boolean
  host: string
  port: number
  user: string
  latency_ms: number
  message: string
}

export const companySmtpApi = {
  get: () => companyClient.get<CompanySmtpConfig>('/api/v1/company/smtp'),
  update: (body: CompanySmtpUpdate) =>
    companyClient.put<CompanySmtpConfig>('/api/v1/company/smtp', { body }),
  verify: (body: CompanySmtpVerifyPayload) =>
    companyClient.post<CompanySmtpVerifyResponse>('/api/v1/company/smtp/verify', { body }),
  reset: () => companyClient.delete<CompanySmtpConfig>('/api/v1/company/smtp'),
}
