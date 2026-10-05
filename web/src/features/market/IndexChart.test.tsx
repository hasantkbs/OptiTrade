import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { IndexChart } from './IndexChart'
import type { ChartResponse } from '../../api/types'

const chart: ChartResponse = {
  symbol: 'BTC-USD', period: '3mo', change_pct: 5.2, high: 70000, low: 60000,
  points: [
    { date: '2026-01-01', close: 65000, volume: 1000, rsi: null },
    { date: '2026-01-02', close: 66000, volume: 1100, rsi: null },
  ],
}

describe('IndexChart', () => {
  it('shows a loading state', () => {
    render(<IndexChart title="Bitcoin" chart={null} isLoading isError={false} />)
    expect(screen.getByText('Bitcoin')).toBeInTheDocument()
  })

  it('shows an error state with the given message', () => {
    render(<IndexChart title="Bitcoin" chart={null} isLoading={false} isError errorMessage="network error" />)
    expect(screen.getByText('network error')).toBeInTheDocument()
  })

  it('renders the real chart data, including the change percentage', () => {
    render(<IndexChart title="Bitcoin" chart={chart} isLoading={false} isError={false} />)
    expect(screen.getByText('Bitcoin')).toBeInTheDocument()
    expect(screen.getByText('+5.20%')).toBeInTheDocument()
  })

  it('shows an unavailable state when chart is null and not loading/error', () => {
    render(<IndexChart title="Bitcoin" chart={null} isLoading={false} isError={false} />)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
  })
})
