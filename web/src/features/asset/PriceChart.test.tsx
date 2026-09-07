import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PriceChart } from './PriceChart'
import type { ChartResponse } from '../../api/types'

const chart: ChartResponse = {
  symbol: 'AAPL',
  period: '3mo',
  points: [
    { date: '2026-01-01', close: 180, volume: 1_000_000, rsi: null },
    { date: '2026-01-02', close: 185, volume: 1_200_000, rsi: 62.3 },
  ],
  change_pct: 2.5,
  high: 190,
  low: 178,
}

function renderChart(props: Partial<Parameters<typeof PriceChart>[0]> = {}) {
  const onRetry = vi.fn()
  const onPeriodChange = vi.fn()
  render(
    <PriceChart isLoading={false} isError={false} onRetry={onRetry} period="3mo" onPeriodChange={onPeriodChange} {...props} />,
  )
  return { onRetry, onPeriodChange }
}

describe('PriceChart', () => {
  it('shows an honest empty state when the backend has no chart data', async () => {
    renderChart({ chart: { ...chart, points: [] } })
    await waitFor(() => expect(screen.getByText('No chart data available')).toBeInTheDocument())
  })

  it('renders the real historical series, including the RSI indicator only when the backend actually computed it', async () => {
    renderChart({ chart })
    await waitFor(() => expect(screen.getByLabelText('AAPL closing price, 3mo')).toBeInTheDocument())
    expect(screen.getByLabelText('AAPL RSI, 3mo')).toBeInTheDocument()
  })

  it('omits the RSI section entirely when no point has one', async () => {
    renderChart({ chart: { ...chart, points: chart.points.map((p) => ({ ...p, rsi: null })) } })
    await waitFor(() => expect(screen.getByLabelText('AAPL closing price, 3mo')).toBeInTheDocument())
    expect(screen.queryByText('RSI')).not.toBeInTheDocument()
  })

  it('calls onPeriodChange when a different time range is selected', async () => {
    const user = userEvent.setup()
    const { onPeriodChange } = renderChart({ chart })
    await user.click(screen.getByRole('tab', { name: '1Y' }))
    expect(onPeriodChange).toHaveBeenCalledWith('1y')
  })

  it('shows a retryable error state on chart failure', () => {
    renderChart({ isError: true, errorMessage: 'network down' })
    expect(screen.getByText('network down')).toBeInTheDocument()
  })
})
