import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DrawdownAnalysis } from './DrawdownAnalysis'
import type { RiskAnalytics } from '../../api/types'

const risk: RiskAnalytics = {
  volatility_pct: 12,
  beta: 1.1,
  correlation_matrix: {},
  diversification_score: 0.6,
  var_95_pct: -3,
  cvar_95_pct: -4,
  max_drawdown_pct: -8.5,
  expected_drawdown_pct: -5.1,
  downside_risk_pct: 6,
  concentration_risk: 0.2,
}

describe('DrawdownAnalysis', () => {
  it('shows an honest message when risk has not been computed', () => {
    render(<DrawdownAnalysis risk={null} />)
    expect(screen.getByText('Not yet computed for this portfolio.')).toBeInTheDocument()
  })

  it('shows the real scalar drawdown figures and an honest unavailable state for history, never a chart', () => {
    render(<DrawdownAnalysis risk={risk} />)
    expect(screen.getByText('-8.5%')).toBeInTheDocument()
    expect(screen.getByText('-5.1%')).toBeInTheDocument()
    expect(screen.getByText('Historical drawdown not available')).toBeInTheDocument()
  })
})
