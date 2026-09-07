import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RiskAnalytics } from './RiskAnalytics'
import type { Recommendation, RiskAnalytics as RiskAnalyticsData } from '../../api/types'

const risk: RiskAnalyticsData = {
  volatility_pct: 12.4,
  beta: 1.15,
  correlation_matrix: { AAPL: { AAPL: 1, MSFT: 0.62 }, MSFT: { AAPL: 0.62, MSFT: 1 } },
  diversification_score: 0.6,
  var_95_pct: -3.2,
  cvar_95_pct: -4.8,
  max_drawdown_pct: -8.5,
  expected_drawdown_pct: -5.1,
  downside_risk_pct: 6.3,
  concentration_risk: 0.42,
}

const recommendations: Recommendation[] = [
  { recommendation_type: 'concentration', severity: 'warning', symbol: 'AAPL', message: 'AAPL is over 40% of the portfolio.', evidence: [] },
]

describe('RiskAnalytics', () => {
  it('shows an honest message when risk has not been computed', () => {
    render(<RiskAnalytics risk={null} recommendations={[]} />)
    expect(screen.getByText('Risk analytics have not been computed for this portfolio yet.')).toBeInTheDocument()
  })

  it('renders real risk metrics, the bounded concentration meter, and the correlation matrix', () => {
    render(<RiskAnalytics risk={risk} recommendations={[]} />)
    expect(screen.getByText('12.4%')).toBeInTheDocument()
    expect(screen.getByText('1.15')).toBeInTheDocument()
    expect(screen.getByText('0.42')).toBeInTheDocument()
    expect(screen.getAllByText('0.62').length).toBeGreaterThan(0)
    expect(screen.getByText('No recommendations right now.')).toBeInTheDocument()
  })

  it('renders real recommendations without inventing a severity scheme', () => {
    render(<RiskAnalytics risk={risk} recommendations={recommendations} />)
    expect(screen.getByText('AAPL is over 40% of the portfolio.')).toBeInTheDocument()
    expect(screen.getByText('concentration')).toBeInTheDocument()
  })
})
