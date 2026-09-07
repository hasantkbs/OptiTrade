import { describe, expect, it } from 'vitest'
import { ALERT_TYPE_CONFIG, alertTypeConfig, alertTypesForCategory, formatAlertType } from './alertTypes'
import type { AlertCategory } from '../../api/types'

describe('alertTypes', () => {
  it('covers every category the backend defines', () => {
    const categories = new Set(ALERT_TYPE_CONFIG.map((c) => c.category))
    const expected: AlertCategory[] = ['price', 'technical', 'decision', 'news', 'portfolio']
    for (const category of expected) {
      expect(categories.has(category)).toBe(true)
      expect(alertTypesForCategory(category).length).toBeGreaterThan(0)
    }
  })

  it('formats a raw backend alert_type into a friendly label without changing the underlying value', () => {
    expect(formatAlertType('price_above')).toBe('Price Above')
    expect(alertTypeConfig('price_above')?.type).toBe('price_above')
  })

  it('marks portfolio alert types as requiring a portfolio and never a plain symbol select for VaR/drawdown/concentration', () => {
    const varConfig = alertTypeConfig('portfolio_var_exceeded')
    expect(varConfig?.requiresPortfolio).toBe(true)
    expect(varConfig?.symbol).toBe('none')
  })

  it('marks price_above/price_below thresholds as required, matching the backend raising an error without one', () => {
    expect(alertTypeConfig('price_above')?.parameters.find((p) => p.key === 'threshold')?.required).toBe(true)
    expect(alertTypeConfig('price_below')?.parameters.find((p) => p.key === 'threshold')?.required).toBe(true)
  })

  it('requires a symbol for news alerts, matching the evaluator code rather than the Alert model docstring', () => {
    expect(alertTypeConfig('news_high_impact')?.symbol).toBe('required')
    expect(alertTypeConfig('news_breaking')?.symbol).toBe('required')
    expect(alertTypeConfig('news_sector')?.symbol).toBe('required')
  })
})
