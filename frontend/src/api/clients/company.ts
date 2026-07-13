import { HttpClient } from '@/api/http'
import { companyTokenStorage } from '@/auth/tokenStorage'

/**
 * Company-identity HTTP client. Reads only the `company` token namespace and
 * refreshes only against the company refresh endpoint.
 */
let onAuthFailure: () => void = () => {}

export function setCompanyAuthFailureHandler(handler: () => void) {
  onAuthFailure = handler
}

export const companyClient = new HttpClient({
  storage: companyTokenStorage,
  refreshPath: '/api/v1/auth/company/refresh',
  onAuthFailure: () => onAuthFailure(),
})
