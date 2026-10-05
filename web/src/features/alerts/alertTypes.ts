import type { AlertCategory, AlertType } from '../../api/types'

export interface AlertParameterField {
  /** The exact key the backend reads via `alert.parameters.get(key, ...)`
   * (watchlist/price_alerts.py, technical_alerts.py, alert_engine.py,
   * news_alerts.py, portfolio_alerts.py) - never invented. */
  key: string
  label: string
  required?: boolean
  /** The backend's own configured default (watchlist/config.py) when
   * the field is left blank - env-overridable, so phrased as "backend
   * default" rather than a guaranteed production value. */
  hint?: string
}

export interface AlertTypeConfig {
  type: AlertType
  category: AlertCategory
  label: string
  symbol: 'required' | 'optional' | 'none'
  parameters: AlertParameterField[]
}

/**
 * One entry per value of the backend's actual `AlertType` enum
 * (watchlist/models.py), verified against each category's evaluator
 * module for exactly which fields are required vs. optional-with-a-
 * default (WEB STEP 6 audit). This is the single source of truth the
 * create-alert form renders from - never a hardcoded/guessed subset.
 *
 * News alerts: `Alert`'s own docstring claims a news alert "may... be
 * sector-wide (neither symbol nor portfolio set)", but
 * `NewsAlertEvaluator.evaluate()` actually raises `InvalidAlertError`
 * for all three news types when `symbol` is missing - the code, not
 * the docstring, is what runs, so `symbol` is modeled as required here.
 */
export const ALERT_TYPE_CONFIG: AlertTypeConfig[] = [
  {
    type: 'price_above',
    category: 'price',
    label: 'Price Above',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Threshold price', required: true }],
  },
  {
    type: 'price_below',
    category: 'price',
    label: 'Price Below',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Threshold price', required: true }],
  },
  {
    type: 'price_percent_move',
    category: 'price',
    label: 'Price % Move',
    symbol: 'required',
    parameters: [{ key: 'threshold_pct', label: 'Move threshold (%)', hint: 'Backend default: 5%' }],
  },
  {
    type: 'price_gap',
    category: 'price',
    label: 'Price Gap',
    symbol: 'required',
    parameters: [{ key: 'threshold_pct', label: 'Gap threshold (%)', hint: 'Backend default: 3%' }],
  },
  {
    type: 'rsi_threshold',
    category: 'technical',
    label: 'RSI Threshold',
    symbol: 'required',
    parameters: [
      { key: 'overbought', label: 'Overbought level', hint: 'Backend default: 70' },
      { key: 'oversold', label: 'Oversold level', hint: 'Backend default: 30' },
    ],
  },
  { type: 'macd_crossover', category: 'technical', label: 'MACD Crossover', symbol: 'required', parameters: [] },
  { type: 'ema_crossover', category: 'technical', label: 'EMA Crossover', symbol: 'required', parameters: [] },
  {
    type: 'bollinger_breakout',
    category: 'technical',
    label: 'Bollinger Breakout',
    symbol: 'required',
    parameters: [
      { key: 'upper_percent_b', label: 'Upper %B', hint: 'Backend default: 1.0' },
      { key: 'lower_percent_b', label: 'Lower %B', hint: 'Backend default: 0.0' },
    ],
  },
  {
    type: 'volume_spike',
    category: 'technical',
    label: 'Volume Spike',
    symbol: 'required',
    parameters: [{ key: 'spike_ratio', label: 'Spike ratio', hint: 'Backend default: 2.0x' }],
  },
  {
    type: 'atr_expansion',
    category: 'technical',
    label: 'ATR Expansion',
    symbol: 'required',
    parameters: [{ key: 'expansion_ratio', label: 'Expansion ratio', hint: 'Backend default: 1.5x' }],
  },
  { type: 'decision_buy', category: 'decision', label: 'Decision: BUY appears', symbol: 'required', parameters: [] },
  { type: 'decision_sell', category: 'decision', label: 'Decision: SELL appears', symbol: 'required', parameters: [] },
  {
    type: 'confidence_change',
    category: 'decision',
    label: 'Confidence Change',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Change threshold', hint: 'Backend default: 0.15' }],
  },
  {
    type: 'expected_return_change',
    category: 'decision',
    label: 'Expected Return Change',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Change threshold (%)', hint: 'Backend default: 3%' }],
  },
  {
    type: 'risk_change',
    category: 'decision',
    label: 'Risk Change',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Change threshold (%)', hint: 'Backend default: 5%' }],
  },
  {
    type: 'news_high_impact',
    category: 'news',
    label: 'News: High Impact',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Impact threshold', hint: 'Backend default: 0.6' }],
  },
  {
    type: 'news_sector',
    category: 'news',
    label: 'News: Sector Impact',
    symbol: 'required',
    parameters: [{ key: 'threshold', label: 'Impact threshold', hint: 'Backend default: 0.5' }],
  },
  {
    type: 'news_breaking',
    category: 'news',
    label: 'News: Breaking',
    symbol: 'required',
    parameters: [{ key: 'max_age_minutes', label: 'Max age (minutes)', hint: 'Backend default: 120' }],
  },
]

export const ALERT_CATEGORY_LABEL: Record<AlertCategory, string> = {
  price: 'Price',
  technical: 'Technical',
  decision: 'Decision Engine',
  news: 'News',
  portfolio: 'Portfolio',
}

const TYPE_CONFIG_BY_TYPE: Partial<Record<AlertType, AlertTypeConfig>> = Object.fromEntries(
  ALERT_TYPE_CONFIG.map((config) => [config.type, config]),
)

export function alertTypeConfig(type: AlertType): AlertTypeConfig | undefined {
  return TYPE_CONFIG_BY_TYPE[type]
}

/** Presentation only - never changes the value sent to/received from the backend. */
export function formatAlertType(type: AlertType): string {
  return alertTypeConfig(type)?.label ?? type.replace(/_/g, ' ')
}

export function alertTypesForCategory(category: AlertCategory): AlertTypeConfig[] {
  return ALERT_TYPE_CONFIG.filter((config) => config.category === category)
}
