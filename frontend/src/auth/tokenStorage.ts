/**
 * Namespaced token storage. Each identity system gets its own key prefix, so a
 * company session and an auditor session cannot read or clobber each other's
 * tokens. This is the storage-layer half of the frontend identity separation.
 */
export interface StoredTokens {
  accessToken: string
  refreshToken: string
}

export type IdentityNamespace = 'company' | 'auditor'

export interface TokenStorage {
  readonly namespace: IdentityNamespace
  get(): StoredTokens | null
  set(tokens: StoredTokens): void
  clear(): void
}

export function createTokenStorage(namespace: IdentityNamespace): TokenStorage {
  const key = `kubera.${namespace}.tokens`
  return {
    namespace,
    get() {
      const raw = localStorage.getItem(key)
      if (!raw) return null
      try {
        const parsed = JSON.parse(raw) as StoredTokens
        if (parsed?.accessToken && parsed?.refreshToken) return parsed
        return null
      } catch {
        return null
      }
    },
    set(tokens) {
      localStorage.setItem(key, JSON.stringify(tokens))
    },
    clear() {
      localStorage.removeItem(key)
    },
  }
}

export const companyTokenStorage = createTokenStorage('company')
export const auditorTokenStorage = createTokenStorage('auditor')
