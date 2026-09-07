import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { ApiErrorBody, TokenPairResponse } from './types'

/**
 * Base URL resolution:
 * - Local dev: Vite's own dev-server proxy forwards /api -> the backend
 *   directly (see vite.config.ts) - no CORS involved at all in dev.
 * - Production build: same-origin /api, expected to be routed to the
 *   backend by the reverse proxy (nginx, SERVER STEP 5) once that route
 *   is added there. Never a hardcoded domain - this repo has no real
 *   production domain yet (see docs/deployment/https-reverse-proxy.md).
 */
const BASE_URL = '/api'

const ACCESS_TOKEN_KEY = 'optitrade.access_token'
const REFRESH_TOKEN_KEY = 'optitrade.refresh_token'

/**
 * Token storage. localStorage, not a cookie: the backend issues bearer
 * tokens (users/schemas.py's TokenPairResponse), not a session cookie -
 * there is no server-side cookie mechanism to use instead. Never log
 * these values (see AuthContext and every call site below).
 */
export const tokenStorage = {
  getAccessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  setTokens(tokens: Pick<TokenPairResponse, 'access_token' | 'refresh_token'>) {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
}

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 20_000,
})

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** Notified once a session is confirmed dead (refresh itself failed) so
 * AuthContext can redirect to /login - the client layer never touches
 * routing directly. */
type SessionExpiredListener = () => void
let onSessionExpired: SessionExpiredListener | null = null
export function setSessionExpiredHandler(listener: SessionExpiredListener | null) {
  onSessionExpired = listener
}

/**
 * Refresh tokens rotate and are single-use (users/authentication.py's
 * refresh() revokes the old session and issues a brand new pair) - if
 * two requests 401 at the same moment, only ONE refresh call may
 * actually fire, or the second would try to redeem an already-revoked
 * token and fail. Every 401 handler awaits this same in-flight promise
 * instead of starting its own.
 */
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStorage.getRefreshToken()
  if (!refreshToken) {
    throw new Error('no refresh token available')
  }
  const response = await axios.post<TokenPairResponse>(`${BASE_URL}/auth/refresh`, {
    refresh_token: refreshToken,
  })
  tokenStorage.setTokens(response.data)
  return response.data.access_token
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status

    // Never retry the refresh call itself - that 401 means the session
    // is genuinely dead, not "needs a refresh".
    const isRefreshCall = config?.url?.includes('/auth/refresh')

    if (status === 401 && config && !config._retried && !isRefreshCall) {
      config._retried = true
      try {
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null
        })
        const newAccessToken = await refreshPromise
        config.headers.Authorization = `Bearer ${newAccessToken}`
        return apiClient(config)
      } catch {
        tokenStorage.clear()
        onSessionExpired?.()
        return Promise.reject(error)
      }
    }

    if (status === 401 && isRefreshCall) {
      tokenStorage.clear()
      onSessionExpired?.()
    }

    return Promise.reject(error)
  },
)

/** Extracts a human-readable message from the backend's standard
 * HTTPException body ({"detail": "..."}) or FastAPI's validation-error
 * shape ({"detail": [{"msg": "..."}]}), for centralized error display. */
export function apiErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as ApiErrorBody | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
    if (error.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
    if (!error.response) return 'Could not reach the server. Check your connection.'
  }
  return fallback
}
