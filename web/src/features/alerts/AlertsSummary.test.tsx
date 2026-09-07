import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AlertsSummary } from './AlertsSummary'
import type { Alert } from '../../api/types'

function makeAlert(overrides: Partial<Alert>): Alert {
  return {
    id: 1,
    owner: 'user-1',
    watchlist_id: null,
    symbol: 'AAPL',
    portfolio_id: null,
    category: 'price',
    alert_type: 'price_above',
    parameters: { threshold: 200 },
    cooldown_minutes: 60,
    enabled: true,
    last_state: {},
    last_checked_at: null,
    last_triggered_at: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('AlertsSummary', () => {
  it('derives counts only from the real returned alerts, never a fabricated success rate', () => {
    const alerts = [
      makeAlert({ id: 1, enabled: true, last_triggered_at: '2026-01-01T00:00:00Z' }),
      makeAlert({ id: 2, enabled: true, last_triggered_at: null }),
      makeAlert({ id: 3, enabled: false, last_triggered_at: null }),
    ]
    render(<AlertsSummary alerts={alerts} />)
    expect(screen.getByText('Total alerts')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    expect(screen.queryByText(/success rate|accuracy|performance/i)).not.toBeInTheDocument()
  })
})
