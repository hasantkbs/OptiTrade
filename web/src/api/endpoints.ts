import { apiClient } from './client'
import type {
  Alert,
  AlertDashboardView,
  EngineDashboardView,
  LearningDashboardView,
  LoginRequest,
  MarketDashboardView,
  OverviewMetrics,
  Portfolio,
  PortfolioDashboardExtended,
  RegisterRequest,
  TokenPairResponse,
  UserResponse,
  Watchlist,
  WatchlistDashboardView,
  WatchlistItem,
} from './types'

/**
 * One function per real backend endpoint - the only place a request
 * URL/method/shape is written. UI components and feature hooks never
 * call `apiClient` directly (see src/features/*), so a contract change
 * only ever needs updating here.
 */

// ── Auth ─────────────────────────────────────────────────────────────────

export const authApi = {
  register: (body: RegisterRequest) => apiClient.post<UserResponse>('/auth/register', body).then((r) => r.data),
  login: (body: LoginRequest) => apiClient.post<TokenPairResponse>('/auth/login', body).then((r) => r.data),
  logout: (refreshToken: string) =>
    apiClient.post<{ status: string }>('/auth/logout', { refresh_token: refreshToken }).then((r) => r.data),
  me: () => apiClient.get<UserResponse>('/users/me').then((r) => r.data),
}

// ── Dashboard ────────────────────────────────────────────────────────────

export const dashboardApi = {
  overview: () => apiClient.get<OverviewMetrics>('/dashboard/overview').then((r) => r.data),
  engines: () => apiClient.get<EngineDashboardView>('/dashboard/engines').then((r) => r.data),
  watchlists: () => apiClient.get<WatchlistDashboardView>('/dashboard/watchlists').then((r) => r.data),
  alerts: () => apiClient.get<AlertDashboardView>('/dashboard/alerts').then((r) => r.data),
  market: (market = 'US') =>
    apiClient.get<MarketDashboardView>('/dashboard/market', { params: { market } }).then((r) => r.data),
  learning: () => apiClient.get<LearningDashboardView>('/dashboard/learning').then((r) => r.data),
  portfolio: (portfolioId: number) =>
    apiClient.get<PortfolioDashboardExtended>(`/dashboard/portfolios/${portfolioId}`).then((r) => r.data),
}

// ── Portfolios ───────────────────────────────────────────────────────────

export const portfolioApi = {
  list: () => apiClient.get<Portfolio[]>('/portfolios').then((r) => r.data),
}

// ── Watchlists ───────────────────────────────────────────────────────────

export const watchlistApi = {
  list: () => apiClient.get<Watchlist[]>('/watchlists').then((r) => r.data),
  items: (watchlistId: number) =>
    apiClient.get<WatchlistItem[]>(`/watchlists/${watchlistId}/items`).then((r) => r.data),
}

// ── Alerts ───────────────────────────────────────────────────────────────

export const alertsApi = {
  list: () => apiClient.get<Alert[]>('/alerts').then((r) => r.data),
}
