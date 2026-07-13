import { HttpClient } from '@/api/http'
import { auditorTokenStorage } from '@/auth/tokenStorage'

/**
 * Auditor-identity HTTP client. Reads only the `auditor` token namespace and
 * refreshes only against the auditor refresh endpoint.
 */
let onAuthFailure: () => void = () => {}

export function setAuditorAuthFailureHandler(handler: () => void) {
  onAuthFailure = handler
}

export const auditorClient = new HttpClient({
  storage: auditorTokenStorage,
  refreshPath: '/api/v1/auth/auditor/refresh',
  onAuthFailure: () => onAuthFailure(),
})
