import { describe, it, expect, vi } from 'vitest'
import { render, act, waitFor } from '@testing-library/react'
import { createIdentityAuth, type IdentityAuth } from './createIdentityAuth'
import type { TokenStorage, StoredTokens } from '@/auth/tokenStorage'

function makeStorage(): TokenStorage {
  let tokens: StoredTokens | null = null
  return {
    namespace: 'company',
    get: () => tokens,
    set: (t) => { tokens = t },
    clear: () => { tokens = null },
  }
}

function setup(clearCache: () => void) {
  const storage = makeStorage()
  const login = vi.fn().mockResolvedValue({
    access_token: 'a', refresh_token: 'r', role: 'admin', full_name: 'X',
  })
  const loadProfile = vi.fn().mockResolvedValue({ id: '1', role: 'admin' })

  const auth = createIdentityAuth<{ id: string; role: string }>({
    name: 'Test',
    storage,
    loadProfile,
    login,
    loginPath: '/login',
    registerFailureHandler: vi.fn(),
    clearCache,
  })

  let ctx: IdentityAuth<{ id: string; role: string }> | null = null
  function Capture() {
    ctx = auth.useAuth()
    return null
  }
  render(
    <auth.Provider>
      <Capture />
    </auth.Provider>,
  )
  return { getCtx: () => ctx! }
}

describe('createIdentityAuth cache reset', () => {
  it('clears the cache on sign-in and again on sign-out', async () => {
    const clearCache = vi.fn()
    const { getCtx } = setup(clearCache)

    // Fresh mount with no stored token: hydrate resolves to unauthenticated and
    // must NOT clear the cache.
    await waitFor(() => expect(getCtx().status).toBe('unauthenticated'))
    expect(clearCache).not.toHaveBeenCalled()

    // Sign-in clears once (drops any previous tenant's cache).
    await act(async () => {
      await getCtx().signIn({ email: 'e@x.com', password: 'pw' })
    })
    expect(clearCache).toHaveBeenCalledTimes(1)
    expect(getCtx().status).toBe('authenticated')

    // Sign-out clears again.
    act(() => getCtx().signOut())
    expect(clearCache).toHaveBeenCalledTimes(2)
    expect(getCtx().status).toBe('unauthenticated')
  })
})
