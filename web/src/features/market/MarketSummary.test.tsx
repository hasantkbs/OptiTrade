import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MarketSummary } from './MarketSummary'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { market: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MarketSummary />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const marketView = {
  regime_distribution: { bull: 5 },
  volatility_map: { AAPL: 0.2 },
  sector_heatmap: [
    { sector: 'Technology', opportunity_score: 8.2, avg_change_pct: 1.4, trend: 'up' },
    { sector: 'Energy', opportunity_score: 3.1, avg_change_pct: -0.5, trend: 'down' },
  ],
  news_impact_summary: [{ symbol: 'AAPL', sentiment_score: 0.6, sentiment_label: 'Positive', headline_count: 12 }],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MarketSummary', () => {
  it('shows an honest empty state when no sector data is available', async () => {
    mockedDashboardApi.market.mockResolvedValueOnce({ ...marketView, sector_heatmap: [], news_impact_summary: [] })
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No sector data yet')).toBeInTheDocument())
  })

  it('renders real sector opportunity and news sentiment data, never a fabricated market status', async () => {
    mockedDashboardApi.market.mockResolvedValueOnce(marketView)
    renderWithClient()
    await waitFor(() => expect(screen.getByLabelText('Top sectors by opportunity score')).toBeInTheDocument())
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('12 headlines')).toBeInTheDocument()
    expect(screen.getByText('Positive')).toBeInTheDocument()
  })
})
