import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import type { TokenStorage } from '@/auth/tokenStorage'
import type { TokenResponse, LoginRequest } from '@/api/types'
import { FullPageSpinner } from '@/components/ui/Spinner'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface IdentityAuth<Profile> {
  status: AuthStatus
  profile: Profile | null
  signIn: (credentials: LoginRequest) => Promise<void>
  signOut: () => void
}

interface IdentityAuthConfig<Profile> {
  /** Human name of the identity, used in error messages/devtools. */
  name: string
  storage: TokenStorage
  /** Fetch the current profile using the stored access token. */
  loadProfile: () => Promise<Profile>
  /** Perform the login request and return the token pair. */
  login: (credentials: LoginRequest) => Promise<TokenResponse>
  /** Where the guard redirects an unauthenticated visitor. */
  loginPath: string
  /** Registers the client's 401/refresh-failure handler (forces sign-out). */
  registerFailureHandler: (handler: () => void) => void
}

/**
 * Builds a self-contained auth context + guard for a single identity system.
 * Each instance reads ONLY its own token storage, so two identities built with
 * this factory cannot see or authenticate against each other's sessions.
 */
export function createIdentityAuth<Profile>(config: IdentityAuthConfig<Profile>) {
  const Context = createContext<IdentityAuth<Profile> | null>(null)
  Context.displayName = `${config.name}AuthContext`

  function Provider({ children }: { children: ReactNode }) {
    const [profile, setProfile] = useState<Profile | null>(null)
    const [status, setStatus] = useState<AuthStatus>('loading')
    // Guard against setting state after unmount during async hydration.
    const mounted = useRef(true)

    const signOut = useCallback(() => {
      config.storage.clear()
      if (mounted.current) {
        setProfile(null)
        setStatus('unauthenticated')
      }
    }, [])

    const hydrate = useCallback(async () => {
      if (!config.storage.get()) {
        setStatus('unauthenticated')
        return
      }
      try {
        const p = await config.loadProfile()
        if (!mounted.current) return
        setProfile(p)
        setStatus('authenticated')
      } catch {
        // Token invalid/expired and refresh failed — treat as signed out.
        signOut()
      }
    }, [signOut])

    const signIn = useCallback(
      async (credentials: LoginRequest) => {
        const tokens = await config.login(credentials)
        config.storage.set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
        })
        const p = await config.loadProfile()
        if (!mounted.current) return
        setProfile(p)
        setStatus('authenticated')
      },
      [],
    )

    useEffect(() => {
      mounted.current = true
      config.registerFailureHandler(signOut)
      void hydrate()
      return () => {
        mounted.current = false
      }
    }, [hydrate, signOut])

    const value = useMemo<IdentityAuth<Profile>>(
      () => ({ status, profile, signIn, signOut }),
      [status, profile, signIn, signOut],
    )

    return <Context.Provider value={value}>{children}</Context.Provider>
  }

  function useAuth(): IdentityAuth<Profile> {
    const ctx = useContext(Context)
    if (!ctx) {
      throw new Error(`use${config.name}Auth must be used within the ${config.name} AuthProvider`)
    }
    return ctx
  }

  /**
   * Route guard. Renders child routes only when THIS identity is authenticated.
   * A session belonging to any other identity is invisible here — the guard only
   * ever consults its own auth context (and thus its own token namespace).
   */
  function Guard() {
    const { status } = useAuth()
    const location = useLocation()
    if (status === 'loading') return <FullPageSpinner />
    if (status === 'unauthenticated') {
      return <Navigate to={config.loginPath} replace state={{ from: location.pathname }} />
    }
    return <Outlet />
  }

  return { Provider, useAuth, Guard }
}
