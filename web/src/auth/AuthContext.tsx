import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authApi } from '../api/endpoints'
import { apiErrorMessage, setSessionExpiredHandler, tokenStorage } from '../api/client'
import type { UserResponse } from '../api/types'

type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  status: AuthStatus
  user: UserResponse | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Set once, on a failed login attempt, and cleared on the next attempt - the
   * login screen owns displaying it. */
  loginError: string | null
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  const [user, setUser] = useState<UserResponse | null>(null)
  const [loginError, setLoginError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // The single choke point for logout, a failed session restoration,
  // AND a failed token refresh (see setSessionExpiredHandler below) -
  // clearing the TanStack Query cache here, not just the tokens, is
  // what guarantees a previous account's cached portfolio/alerts/
  // dashboard data can never flash on screen for whoever uses this
  // browser next (WEB STEP 8 Phase 2: "protected data is not displayed
  // after logout").
  const clearSession = useCallback(() => {
    tokenStorage.clear()
    setUser(null)
    setStatus('unauthenticated')
    queryClient.clear()
  }, [queryClient])

  // Login is removed from the UI (web simplification): every visitor
  // is silently authenticated as one shared guest account, via a
  // dedicated unauthenticated endpoint (POST /auth/guest) that needs
  // no credential from the frontend at all - see api/endpoints.ts and
  // main.py::auth_guest. The /login screen is NOT deleted - it stays
  // as an automatic fallback only, reachable if guest auto-login
  // itself fails (e.g. a backend outage), never part of the normal path.
  const guestLogin = useCallback(async () => {
    try {
      const tokens = await authApi.guest()
      tokenStorage.setTokens(tokens)
      const me = await authApi.me()
      setUser(me)
      setStatus('authenticated')
    } catch {
      setStatus('unauthenticated')
    }
  }, [])

  // Session persistence: on load, if a token pair already exists (a
  // previous browser session), verify it against the backend rather
  // than trusting it blindly - an invalid/revoked token falls through
  // to a fresh guest auto-login rather than a broken authenticated shell.
  useEffect(() => {
    let cancelled = false
    async function restoreSession() {
      if (!tokenStorage.getAccessToken()) {
        await guestLogin()
        return
      }
      try {
        const me = await authApi.me()
        if (!cancelled) {
          setUser(me)
          setStatus('authenticated')
        }
      } catch {
        if (!cancelled) await guestLogin()
      }
    }
    void restoreSession()
    return () => {
      cancelled = true
    }
  }, [guestLogin])

  // Safety net: any later transition to 'unauthenticated' (a failed
  // token refresh, an explicit logout) silently re-authenticates as
  // the guest account rather than stranding the visitor on /login.
  useEffect(() => {
    if (status === 'unauthenticated') {
      void guestLogin()
    }
  }, [status, guestLogin])

  // The API client layer (src/api/client.ts) has no knowledge of
  // routing/state - it just calls this when a refresh attempt itself
  // fails, meaning the session is genuinely over.
  useEffect(() => {
    setSessionExpiredHandler(clearSession)
    return () => setSessionExpiredHandler(null)
  }, [clearSession])

  const login = useCallback(async (email: string, password: string) => {
    setLoginError(null)
    try {
      const tokens = await authApi.login({ email, password })
      tokenStorage.setTokens(tokens)
      const me = await authApi.me()
      setUser(me)
      setStatus('authenticated')
    } catch (error) {
      setLoginError(apiErrorMessage(error, 'Could not sign in. Please try again.'))
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    const refreshToken = tokenStorage.getRefreshToken()
    try {
      if (refreshToken) await authApi.logout(refreshToken)
    } catch {
      // Logging out locally must succeed even if the network call
      // fails (offline, already-expired token) - never trap the user
      // in an authenticated shell they explicitly asked to leave.
    } finally {
      clearSession()
    }
  }, [clearSession])

  const value = useMemo(
    () => ({ status, user, login, logout, loginError }),
    [status, user, login, logout, loginError],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
