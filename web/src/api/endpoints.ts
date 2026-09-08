import { apiClient } from './client'
import type {
  Alert,
  AlertDashboardView,
  AddWatchlistItemRequest,
  ChartPeriod,
  ChartResponse,
  CreateAlertRequest,
  CreatePortfolioRequest,
  CreateWatchlistRequest,
  DepositRequest,
  EngineDashboardView,
  LearningDashboardView,
  LoginRequest,
  MarketDashboardView,
  OverviewMetrics,
  PipelineResponse,
  Portfolio,
  PortfolioDashboardExtended,
  PriceQuote,
  RegisterRequest,
  ScanReport,
  TokenPairResponse,
  TradeRequest,
  Transaction,
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
  create: (body: CreatePortfolioRequest) => apiClient.post<Portfolio>('/portfolios', body).then((r) => r.data),
  /**
   * The real ledger of deposits/withdrawals/buys/sells/dividends/fees
   * (portfolio/models.py::Transaction) - despite the URL, this is
   * distinct from portfolio *snapshot* history (equity curve over
   * time), which has no read endpoint at all (see PortfolioPage's
   * PerformanceHistory/DrawdownAnalysis unavailable states).
   */
  transactions: (portfolioId: number, symbol?: string) =>
    apiClient
      .get<Transaction[]>(`/portfolios/${portfolioId}/history`, { params: symbol ? { symbol } : undefined })
      .then((r) => r.data),
  /**
   * Records a real BUY/SELL transaction (portfolio/service.py's
   * PortfolioService.buy/sell) - positions, average cost, and realized/
   * unrealized P&L are never computed here; they're always replayed by
   * the backend from the transaction ledger this appends to (GET
   * /dashboard/portfolios/{id}, already wired in PortfolioPage).
   */
  buy: (portfolioId: number, body: TradeRequest) =>
    apiClient.post<Transaction>(`/portfolios/${portfolioId}/buy`, body).then((r) => r.data),
  sell: (portfolioId: number, body: TradeRequest) =>
    apiClient.post<Transaction>(`/portfolios/${portfolioId}/sell`, body).then((r) => r.data),
  /**
   * Records a real cash DEPOSIT (portfolio/service.py's
   * PortfolioService.deposit) - cash_balance is never set here; it's
   * always replayed by the backend from the transaction ledger this
   * appends to (GET /dashboard/portfolios/{id}).
   */
  deposit: (portfolioId: number, body: DepositRequest) =>
    apiClient.post<Transaction>(`/portfolios/${portfolioId}/deposit`, body).then((r) => r.data),
}

// ── Watchlists ───────────────────────────────────────────────────────────

export const watchlistApi = {
  list: () => apiClient.get<Watchlist[]>('/watchlists').then((r) => r.data),
  create: (body: CreateWatchlistRequest) => apiClient.post<Watchlist>('/watchlists', body).then((r) => r.data),
  items: (watchlistId: number) =>
    apiClient.get<WatchlistItem[]>(`/watchlists/${watchlistId}/items`).then((r) => r.data),
  addItem: (watchlistId: number, body: AddWatchlistItemRequest) =>
    apiClient.post<WatchlistItem>(`/watchlists/${watchlistId}/items`, body).then((r) => r.data),
  removeItem: (watchlistId: number, symbol: string) =>
    apiClient.delete<{ status: string }>(`/watchlists/${watchlistId}/items/${encodeURIComponent(symbol)}`).then((r) => r.data),
}

// ── Alerts ───────────────────────────────────────────────────────────────

export const alertsApi = {
  list: () => apiClient.get<Alert[]>('/alerts').then((r) => r.data),
  create: (body: CreateAlertRequest) => apiClient.post<Alert>('/alerts', body).then((r) => r.data),
  setEnabled: (alertId: number, enabled: boolean) =>
    apiClient.patch<Alert>(`/alerts/${alertId}/enabled`, { enabled }).then((r) => r.data),
  remove: (alertId: number) => apiClient.delete<{ status: string }>(`/alerts/${alertId}`).then((r) => r.data),
  /**
   * On-demand scan of the caller's own alerts only
   * (main.py::scan_my_alerts -> AlertScheduler.run_scan) - no body, no
   * polling; strictly a user-triggered action (rate-limited 5/minute).
   */
  scan: () => apiClient.post<ScanReport>('/alerts/scan').then((r) => r.data),
}

// ── Asset Explorer: price / chart / quant analysis ──────────────────────
// GET /price and GET /chart require no auth on the backend, but the
// request interceptor attaches a bearer token whenever one exists
// anyway (harmless - same as every other call here).

export const priceApi = {
  get: (symbol: string) => apiClient.get<PriceQuote>(`/price/${encodeURIComponent(symbol)}`).then((r) => r.data),
}

export const chartApi = {
  get: (symbol: string, period: ChartPeriod) =>
    apiClient.get<ChartResponse>(`/chart/${encodeURIComponent(symbol)}`, { params: { period } }).then((r) => r.data),
}

export const quantApi = {
  /**
   * The sole canonical decision path (pipeline.service.PipelineService,
   * behind /quant/analyze) - the legacy /analyze endpoint is a pinned,
   * separate scoring system this app deliberately does not surface (see
   * that endpoint's own backend docstring).
   */
  analyze: (symbol: string, assetType = 'stock') =>
    apiClient.post<PipelineResponse>('/quant/analyze', { symbol, asset_type: assetType }).then((r) => r.data),
}
