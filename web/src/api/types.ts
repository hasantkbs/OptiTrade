/**
 * Types mirroring backend/users/schemas.py and backend/dashboard/models.py
 * exactly (field names, optionality, shapes) - never invented. Where the
 * backend hasn't shipped an endpoint yet (decisions feed, AI analyst,
 * research), no type exists here either; the corresponding page renders
 * an explicit "not available" state instead of a fabricated shape.
 */

// ── Auth (users/schemas.py) ─────────────────────────────────────────────

export interface RegisterRequest {
  email: string
  password: string
  display_name: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenPairResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface UserResponse {
  id: number
  email: string
  display_name: string
  is_email_verified: boolean
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

// ── Dashboard (dashboard/models.py) ─────────────────────────────────────

export interface TimeSeriesPoint {
  timestamp: string
  value: number
}

export interface LearningStatus {
  engines_tracked: number
  total_samples: number
  pending_samples: number
  last_evaluated_at: string | null
}

export interface OverviewMetrics {
  total_users: number
  active_users: number
  total_portfolios: number
  total_watchlists: number
  total_alerts: number
  total_paper_accounts: number
  total_models: number
  active_engines: number
  learning_status: LearningStatus
  generated_at: string
}

export type RollingWindow = '7d' | '30d' | '90d' | 'lifetime'
export type DriftType = 'degrading' | 'improving' | 'unstable' | 'stable'

export interface AccuracyMetrics {
  engine_name: string
  engine_version: string
  window: RollingWindow
  sample_count: number
  accuracy: number
  precision: number
  recall: number
  calibration_error: number
  confidence_reliability: number
  expected_return_error: number
  volatility_error: number
  computed_at: string
}

export interface DriftSignal {
  engine_name: string
  engine_version: string
  drift_type: DriftType
  magnitude: number
  recent_window: RollingWindow
  baseline_window: RollingWindow
  evidence: string
  detected_at: string
}

export interface EngineAccuracySnapshot {
  engine_name: string
  engine_version: string
  accuracy_by_window: Partial<Record<RollingWindow, AccuracyMetrics>>
  current_weight: number | null
  latest_drift: DriftSignal | null
}

export interface CalibrationSnapshot {
  model_id: string
  method: string
  calibration_error_before: number
  calibration_error_after: number
  computed_at: string
}

export interface EngineDashboardView {
  engines: EngineAccuracySnapshot[]
  calibration: CalibrationSnapshot[]
  drift_signals: DriftSignal[]
  confidence_history: TimeSeriesPoint[]
  regime_distribution: Record<string, number>
  expected_return_history: TimeSeriesPoint[]
  generated_at: string
}

export interface WatchlistDashboardView {
  total_watchlists: number
  total_items: number
  total_favorites: number
  most_tracked_symbols: string[]
  items_by_folder: Record<string, number>
  generated_at: string
}

export interface TriggerEventSnapshot {
  alert_id: number
  symbol: string | null
  message: string
  triggered_at: string
}

export interface AlertDashboardView {
  active_alerts: number
  fired_last_24h: number
  recently_fired: TriggerEventSnapshot[]
  trigger_frequency_by_type: Record<string, number>
  generated_at: string
}

export interface SectorSnapshot {
  sector: string
  opportunity_score: number
  avg_change_pct: number
  trend: string
}

export interface NewsImpactSnapshot {
  symbol: string
  sentiment_score: number
  sentiment_label: string
  headline_count: number
}

export interface MarketDashboardView {
  regime_distribution: Record<string, number>
  volatility_map: Record<string, number>
  sector_heatmap: SectorSnapshot[]
  news_impact_summary: NewsImpactSnapshot[]
  generated_at: string
}

export interface EngineRanking {
  engine_name: string
  engine_version: string
  accuracy: number
  current_weight: number | null
  rank: number
}

export interface LearningDashboardView {
  engine_rankings: EngineRanking[]
  recent_samples: unknown[]
  promotion_candidates: unknown[]
  drift_alerts: DriftSignal[]
  calibration_history: unknown[]
  generated_at: string
}

// ── Portfolio (portfolio/models.py) ─────────────────────────────────────

export interface Portfolio {
  id: number | null
  owner: string
  name: string
  base_currency: string
  created_at: string
}

export type TransactionType = 'deposit' | 'withdrawal' | 'buy' | 'sell' | 'dividend' | 'fee' | 'tax'

export interface Transaction {
  id: number | null
  portfolio_id: number
  transaction_type: TransactionType
  symbol: string | null
  quantity: number | null
  price: number | null
  amount: number
  fee: number
  tax: number
  currency: string
  executed_at: string
  notes: string
  created_at: string
}

export interface AllocationBreakdown {
  by_symbol_pct: Record<string, number>
  by_sector_pct: Record<string, number>
  by_country_pct: Record<string, number>
  by_currency_pct: Record<string, number>
  cash_weight_pct: number
}

export interface RiskAnalytics {
  volatility_pct: number
  beta: number | null
  correlation_matrix: Record<string, Record<string, number>>
  diversification_score: number
  var_95_pct: number
  cvar_95_pct: number
  max_drawdown_pct: number
  expected_drawdown_pct: number
  downside_risk_pct: number
  concentration_risk: number
}

export interface PositionAnalytics {
  symbol: string
  quantity: number
  average_cost: number
  current_price: number
  cost_basis: number
  current_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  realized_pnl: number
  weight_pct: number
  sector: string
  country: string
  currency: string
}

export type RecommendationType = 'rebalance' | 'overweight' | 'diversification' | 'concentration' | 'decision_signal'
export type RecommendationSeverity = 'info' | 'warning' | 'critical'

export interface Recommendation {
  recommendation_type: RecommendationType
  severity: RecommendationSeverity
  symbol: string | null
  message: string
  evidence: string[]
}

export interface PortfolioDashboard {
  portfolio_id: number
  as_of: string
  cash_balance: number
  total_value: number
  realized_pnl: number
  unrealized_pnl: number
  positions: PositionAnalytics[]
  allocation: AllocationBreakdown
  risk: RiskAnalytics | null
  recommendations: Recommendation[]
}

export interface PortfolioDashboardExtended {
  dashboard: PortfolioDashboard
  sharpe_ratio: number | null
  generated_at: string
}

// ── Watchlist (watchlist/models.py) ─────────────────────────────────────

export interface Watchlist {
  id: number | null
  owner: string
  name: string
  created_at: string
}

export interface WatchlistItem {
  id: number | null
  watchlist_id: number
  symbol: string
  is_favorite: boolean
  folder: string | null
  tags: string[]
  notes: string
  added_at: string
}

// ── Alerts (watchlist/models.py) ────────────────────────────────────────

export type AlertCategory = 'price' | 'technical' | 'decision' | 'news' | 'portfolio'

export interface Alert {
  id: number | null
  owner: string
  watchlist_id: number | null
  symbol: string | null
  portfolio_id: number | null
  category: AlertCategory
  alert_type: string
  parameters: Record<string, number>
  cooldown_minutes: number
  enabled: boolean
  last_state: string | null
  last_checked_at: string | null
  last_triggered_at: string | null
  created_at: string
}

// ── Generic API error shape (FastAPI's default HTTPException body) ─────

export interface ApiErrorBody {
  detail: string | { msg: string; [key: string]: unknown }[]
}
