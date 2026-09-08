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

export interface CreatePortfolioRequest {
  name: string
  /** Optional - portfolio/models.py::CreatePortfolioRequest defaults this
   * server-side (Portfolio.base_currency = "USD") when omitted. The
   * request schema also has a deprecated `owner` field the backend
   * always ignores (owner is the authenticated caller) - never sent. */
  base_currency?: string
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

/** dashboard/models.py::LearningSampleSnapshot - `source` is the real
 * live/shadow distinction (learning/models.py::SampleSource); a shadow
 * sample is collected by invoking an engine's vote() outside any live
 * decision and never influences one (WEB STEP 7 audit). */
export type SampleSource = 'live' | 'shadow'

export interface LearningSampleSnapshot {
  symbol: string
  source: SampleSource
  decision: Prediction
  confidence: number
  decided_at: string
  evaluated: boolean
  correct: boolean | null
}

/**
 * learning/models.py::PromotionCandidate - "a recommendation for a
 * human (or a future automated step) to review, never an automatic
 * promotion" (the backend model's own docstring). Never used here to
 * drive an action - read-only display only (WEB STEP 7).
 */
export interface PromotionCandidate {
  engine_name: string
  candidate_version: string
  live_version: string
  window: RollingWindow
  candidate_accuracy: number
  live_accuracy: number
  candidate_sample_count: number
}

export interface CalibrationHistoryPoint {
  engine_name: string
  engine_version: string
  window: RollingWindow
  calibration_error: number
  confidence_reliability: number
  computed_at: string
}

export interface LearningDashboardView {
  engine_rankings: EngineRanking[]
  recent_samples: LearningSampleSnapshot[]
  promotion_candidates: PromotionCandidate[]
  drift_alerts: DriftSignal[]
  calibration_history: CalibrationHistoryPoint[]
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

/** portfolio/models.py::TradeRequest - body for both POST
 * /portfolios/{id}/buy and .../sell. The backend uppercases `symbol`
 * itself (PortfolioService.buy/sell) and always resolves the *current*
 * market price separately, only for valuation - `price` here is the
 * trade's own historical entry/exit price and must come from the user,
 * never be auto-filled from a live quote. */
export interface TradeRequest {
  symbol: string
  quantity: number
  price: number
  fee?: number
  tax?: number
  notes?: string
}

/** portfolio/models.py::DepositRequest - body for POST
 * /portfolios/{id}/deposit. Cash is never a stored field on `Portfolio`
 * itself - the backend replays it from the transaction ledger, so a
 * deposit is just another `Transaction` this appends to. */
export interface DepositRequest {
  amount: number
  currency?: string
  notes?: string
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

/** watchlist/models.py::AlertType - every value the backend's own enum
 * defines, verified against the current repository (WEB STEP 6 audit).
 * Not the "priceAbove/decisionBuy" camelCase list from earlier
 * assumptions - the real backend uses these exact snake_case values. */
export type AlertType =
  | 'price_above'
  | 'price_below'
  | 'price_percent_move'
  | 'price_gap'
  | 'rsi_threshold'
  | 'macd_crossover'
  | 'ema_crossover'
  | 'bollinger_breakout'
  | 'volume_spike'
  | 'atr_expansion'
  | 'decision_buy'
  | 'decision_sell'
  | 'confidence_change'
  | 'expected_return_change'
  | 'risk_change'
  | 'news_high_impact'
  | 'news_sector'
  | 'news_breaking'
  | 'portfolio_allocation_exceeded'
  | 'portfolio_var_exceeded'
  | 'portfolio_drawdown_exceeded'
  | 'portfolio_concentration'

export type AlertSeverity = 'info' | 'warning' | 'critical'

export interface Alert {
  id: number | null
  owner: string
  watchlist_id: number | null
  symbol: string | null
  portfolio_id: number | null
  category: AlertCategory
  alert_type: AlertType
  parameters: Record<string, number>
  cooldown_minutes: number
  enabled: boolean
  last_state: Record<string, number>
  last_checked_at: string | null
  last_triggered_at: string | null
  created_at: string
}

export interface CreateAlertRequest {
  category: AlertCategory
  alert_type: AlertType
  parameters?: Record<string, number>
  watchlist_id?: number | null
  symbol?: string | null
  portfolio_id?: number | null
  cooldown_minutes?: number
}

/** watchlist/models.py::AlertTriggerEvent - only ever seen inside a
 * ScanReport outcome; never a standalone field on `Alert` itself. */
export interface AlertTriggerEvent {
  alert_id: number
  owner: string
  symbol: string | null
  portfolio_id: number | null
  category: AlertCategory
  alert_type: AlertType
  severity: AlertSeverity
  message: string
  evidence: Record<string, number>
  related_decision: Prediction | null
  triggered_at: string
}

export type AlertCheckStatus =
  | 'triggered'
  | 'not_triggered'
  | 'skipped_cooldown'
  | 'skipped_dedup'
  | 'skipped_not_due'
  | 'timeout'
  | 'failed'

export interface AlertCheckOutcome {
  alert_id: number
  status: AlertCheckStatus
  duration_ms: number
  attempts: number
  error_type: string | null
  trigger_event: AlertTriggerEvent | null
}

export interface ScanReport {
  started_at: string
  total_alerts: number
  checked_count: number
  triggered_count: number
  outcomes: AlertCheckOutcome[]
}

export interface CreateWatchlistRequest {
  name: string
}

export interface AddWatchlistItemRequest {
  symbol: string
  is_favorite?: boolean
  folder?: string | null
  tags?: string[]
  notes?: string
}

// ── Price / Chart (main.py's raw dict response + models/schemas.py) ────

/** GET /price/{symbol} returns a plain dict, not a named Pydantic model -
 * this mirrors its exact keys. No currency/exchange/previous-close field
 * exists on it - only `price` and the already-computed `change_pct`. */
export interface PriceQuote {
  symbol: string
  price: number
  change_pct: number
  timestamp: string
}

export type ChartPeriod = '1mo' | '3mo' | '6mo' | '1y'

export interface ChartPoint {
  date: string
  close: number
  volume: number
  rsi: number | null
}

export interface ChartResponse {
  symbol: string
  period: string
  points: ChartPoint[]
  change_pct: number
  high: number
  low: number
}

// ── Quant Research Platform (pipeline/models.py + decision_engine/models.py) ─

export type Prediction = 'BUY' | 'HOLD' | 'SELL'
export type EngineExecutionStatus = 'success' | 'timeout' | 'failed' | 'invalid'

export interface EngineBreakdownItem {
  engine_name: string
  engine_version: string
  status: EngineExecutionStatus
  prediction: Prediction | null
  confidence: number | null
  expected_return: number | null
  volatility: number | null
  evidence: string[]
}

export interface QuantRiskAssessment {
  risk_level: string
  expected_volatility: number
  data_sufficiency: number
}

export interface PipelineMetadata {
  pipeline_version: string
  total_duration_ms: number
  stage_durations_ms: Record<string, number>
  engines_available: number
  engines_succeeded: number
  degraded: boolean
  timestamp: string
}

export interface PipelineResponse {
  symbol: string
  decision: Prediction
  confidence: number
  expected_return: number
  expected_volatility: number
  engine_breakdown: EngineBreakdownItem[]
  evidence: string[]
  risk: QuantRiskAssessment
  explanation: string
  metadata: PipelineMetadata
}

// ── Generic API error shape (FastAPI's default HTTPException body) ─────

export interface ApiErrorBody {
  detail: string | { msg: string; [key: string]: unknown }[]
}
