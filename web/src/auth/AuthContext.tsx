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

  // Session persistence: on load, if a token pair already exists (a
  // previous browser session), verify it against the backend rather
  // than trusting it blindly - an expired/revoked token surfaces as a
  // clean redirect to /login instead of a broken authenticated shell.
  useEffect(() => {
    let cancelled = false
    async function restoreSession() {
      if (!tokenStorage.getAccessToken()) {
        setStatus('unauthenticated')
        return
      }
      try {
        const me = await authApi.me()
        if (!cancelled) {
          setUser(me)
          setStatus('authenticated')
        }
      } catch {
        if (!cancelled) clearSession()
      }
    }
    void restoreSession()
    return () => {
      cancelled = true
    }
  }, [clearSession])

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
